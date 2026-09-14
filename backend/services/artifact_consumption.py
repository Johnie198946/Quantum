"""Tenant-owned, hash-bound structured workflow artifact consumption."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.workflow import (
    WorkflowArtifact,
    WorkflowDefinition,
    WorkflowExecution,
)
from backend.services.capability_catalog import CapabilityContractError, validate_instance
from backend.services.workflow_artifacts import run_root, vault_root


CAPABILITY_ID = "artifact.consume_structured"
CAPABILITY_VERSION = "1.0.0"
SCHEMA_VERSION = "json-schema-draft-2020-12-restricted"
# Hermes caps ordinary tool-bearing input at 12k characters; a 1 MiB tool result
# would dominate its model/event context. 128 KiB bounds that amplification.
MAX_STRUCTURED_BYTES = 128 * 1024
MAX_SCHEMA_BYTES = 16 * 1024
MAX_RECEIPT_BYTES = 32 * 1024
_SCHEMA_KEYS = {
    "type", "properties", "required", "additionalProperties", "items", "enum",
    "minLength", "maxLength", "minimum", "maximum",
}
_SCHEMA_TYPES = {"object", "array", "string", "integer", "boolean"}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _reject(code: str, message: str) -> None:
    raise HTTPException(status_code=409, detail={"code": code, "message": message})


def _validate_schema(schema: dict[str, Any], *, depth: int = 0) -> None:
    if depth > 16 or len(_canonical(schema)) > MAX_SCHEMA_BYTES:
        raise CapabilityContractError("expected_schema exceeds limits")
    unknown = set(schema) - _SCHEMA_KEYS
    if unknown or schema.get("type") not in _SCHEMA_TYPES:
        raise CapabilityContractError("expected_schema uses unsupported keywords or type")
    schema_type = schema["type"]
    if "enum" in schema and (
        not isinstance(schema["enum"], list)
        or not schema["enum"]
        or len(schema["enum"]) > 100
    ):
        raise CapabilityContractError("expected_schema enum is invalid")
    for bound in ("minLength", "maxLength", "minimum", "maximum"):
        if bound in schema and (
            not isinstance(schema[bound], int) or isinstance(schema[bound], bool)
        ):
            raise CapabilityContractError("expected_schema bounds are invalid")
    if schema_type == "object":
        properties = schema.get("properties")
        required = schema.get("required", [])
        if (
            not isinstance(properties, dict)
            or schema.get("additionalProperties") is not False
            or not isinstance(required, list)
            or any(not isinstance(item, str) for item in required)
            or not set(required).issubset(properties)
        ):
            raise CapabilityContractError(
                "object expected_schema requires properties, required and additionalProperties=false"
            )
        for name, child in properties.items():
            if not isinstance(name, str) or not name or len(name) > 200 or not isinstance(child, dict):
                raise CapabilityContractError("expected_schema properties are invalid")
            _validate_schema(child, depth=depth + 1)
    elif schema_type == "array":
        if not isinstance(schema.get("items"), dict):
            raise CapabilityContractError("array expected_schema requires items")
        _validate_schema(schema["items"], depth=depth + 1)
    elif "properties" in schema or "required" in schema or "items" in schema:
        raise CapabilityContractError("expected_schema keywords do not match type")
    if schema_type != "string" and ({"minLength", "maxLength"} & set(schema)):
        raise CapabilityContractError("expected_schema string bounds do not match type")
    if schema_type != "integer" and ({"minimum", "maximum"} & set(schema)):
        raise CapabilityContractError("expected_schema numeric bounds do not match type")


def _validate_payload_shape(value: Any, *, depth: int = 0, budget: list[int] | None = None) -> None:
    budget = budget or [10_000]
    budget[0] -= 1
    if depth > 32 or budget[0] < 0:
        raise CapabilityContractError("structured artifact exceeds nesting limits")
    if isinstance(value, float) and not math.isfinite(value):
        _reject("artifact_parse_failed", "Artifact contains a non-finite number")
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for item in value:
            _validate_payload_shape(item, depth=depth + 1, budget=budget)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _validate_payload_shape(item, depth=depth + 1, budget=budget)
        return
    raise CapabilityContractError("structured artifact contains unsupported JSON values")


_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)


def _open_run_root(execution: Any) -> tuple[int, Path]:
    """Open every run-root component without following attacker-controlled links."""
    root = run_root(execution)
    base = vault_root()
    try:
        parts = root.relative_to(base).parts
        current_fd = os.open(base, _DIRECTORY_FLAGS)
        for part in parts:
            next_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd, root
    except (OSError, ValueError):
        try:
            os.close(current_fd)
        except (NameError, OSError):
            pass
        raise HTTPException(status_code=404, detail={"code": "artifact_file_unavailable"})


def _open_private_directory(parent_fd: int, name: str) -> int:
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    try:
        directory_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        metadata = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise OSError("unsafe consumption directory")
        return directory_fd
    except OSError:
        try:
            os.close(directory_fd)
        except (NameError, OSError):
            pass
        _reject("consumption_store_invalid", "Consumption store is invalid")


def _read_regular_at(directory_fd: int, name: str, maximum: int) -> bytes | None:
    try:
        file_fd = os.open(name, _READ_FLAGS, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    try:
        metadata = os.fstat(file_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
        ):
            raise OSError("unsafe file")
        if metadata.st_size > maximum:
            raise OverflowError("file exceeds limit")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(file_fd, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > maximum:
            raise OverflowError("file exceeds limit")
        return content
    finally:
        os.close(file_fd)


def _read_artifact(root_fd: int, relative: Path, expected_hash: str) -> bytes:
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise HTTPException(status_code=404, detail={"code": "artifact_file_unavailable"})
    directory_fd = os.dup(root_fd)
    try:
        for part in relative.parts[:-1]:
            next_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        raw = _read_regular_at(directory_fd, relative.parts[-1], MAX_STRUCTURED_BYTES)
    except OverflowError:
        _reject("artifact_too_large", "Structured artifact exceeds size limit")
    except OSError:
        raise HTTPException(status_code=404, detail={"code": "artifact_file_unavailable"})
    finally:
        os.close(directory_fd)
    if raw is None:
        raise HTTPException(status_code=404, detail={"code": "artifact_file_unavailable"})
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        _reject("artifact_hash_mismatch", "Artifact content hash verification failed")
    return raw


def _atomic_write(directory_fd: int, name: str, content: bytes) -> None:
    temporary = f".{name}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    file_fd = -1
    try:
        file_fd = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise OSError("unsafe temporary receipt")
        view = memoryview(content)
        while view:
            written = os.write(file_fd, view)
            view = view[written:]
        os.fsync(file_fd)
        os.close(file_fd)
        file_fd = -1
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _read_receipt(directory_fd: int, name: str) -> dict[str, Any] | None:
    try:
        raw = _read_regular_at(directory_fd, name, MAX_RECEIPT_BYTES)
        if raw is None:
            return None
        value = json.loads(raw.decode("utf-8"))
    except (OSError, OverflowError, UnicodeDecodeError, json.JSONDecodeError):
        _reject("consumption_receipt_invalid", "Consumption receipt is invalid")
    if not isinstance(value, dict):
        _reject("consumption_receipt_invalid", "Consumption receipt is invalid")
    return value


def _verified_receipt(
    receipt: dict[str, Any], *, expected: dict[str, Any], receipt_id: str
) -> dict[str, Any]:
    fixed = {
        "receipt_id", "tenant_key", "user_id", "execution_id", "artifact_id",
        "artifact_content_hash", "schema_digest", "schema_version", "capability_id",
        "capability_version", "idempotency_key_hash", "payload_digest", "consumed_at",
        "result_digest", "status",
    }
    if set(receipt) != fixed or any(receipt.get(key) != value for key, value in expected.items()):
        _reject("consumption_receipt_invalid", "Consumption receipt binding failed")
    if receipt.get("receipt_id") != receipt_id or receipt.get("status") != "completed":
        _reject("consumption_receipt_invalid", "Consumption receipt binding failed")
    try:
        datetime.fromisoformat(str(receipt["consumed_at"]).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        _reject("consumption_receipt_invalid", "Consumption receipt timestamp is invalid")
    return receipt


async def consume_structured_artifact(
    data: dict[str, Any], payload: dict[str, Any], idempotency_key: str
) -> dict[str, Any]:
    """Authorize, CAS-read, parse, validate and receipt one JSON artifact."""
    tenant_key = str(payload.get("tenant_key") or "")
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    async with SessionLocal() as db:
        execution = (
            await db.execute(
                select(WorkflowExecution).where(
                    WorkflowExecution.id == data["execution_id"],
                    WorkflowExecution.tenant_key == tenant_key,
                )
            )
        ).scalar_one_or_none()
        workflow = (
            await db.execute(
                select(WorkflowDefinition).where(
                    WorkflowDefinition.id == execution.workflow_id,
                    WorkflowDefinition.tenant_key == tenant_key,
                )
            )
        ).scalar_one_or_none() if execution is not None else None
        if execution is None or workflow is None or (
            workflow.clarification_session_id and workflow.created_by != user_id
        ):
            raise HTTPException(status_code=404, detail="工作流执行不存在")
        if not user_id or workflow.created_by != user_id:
            raise HTTPException(status_code=404, detail={"code": "execution_not_found"})
        artifact = (
            await db.execute(
                select(WorkflowArtifact).where(
                    WorkflowArtifact.id == data["artifact_id"],
                    WorkflowArtifact.execution_id == execution.id,
                )
            )
        ).scalar_one_or_none()
        if artifact is None:
            raise HTTPException(status_code=404, detail={"code": "artifact_not_found"})

    expected_hash = data["expected_content_hash"]
    tenant_key = str(payload.get("tenant_key") or "")
    key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
    request = {
        "execution_id": execution.id,
        "artifact_id": artifact.id,
        "expected_content_hash": expected_hash,
        "expected_schema": data.get("expected_schema"),
    }
    payload_digest = _digest(request)
    identity = hashlib.sha256(f"{CAPABILITY_ID}:{key_hash}".encode()).hexdigest()
    relative = Path(artifact.relative_path)
    if relative.suffix.lower() != ".json":
        _reject("unsupported_artifact_format", "Only JSON workflow artifacts are supported")
    schema = data.get("expected_schema")
    if schema is not None:
        _validate_schema(schema)
    schema_digest = _digest(schema or {})
    receipt_id = "acr_" + hashlib.sha256(
        f"{tenant_key}:{user_id}:{CAPABILITY_ID}:{key_hash}:{payload_digest}".encode()
    ).hexdigest()[:40]
    root_fd, _ = _open_run_root(execution)
    try:
        directory_fd = _open_private_directory(root_fd, "consumptions")
    except Exception:
        os.close(root_fd)
        raise
    receipt_name = f"{identity}.json"
    lock_name = f"{identity}.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    lock_fd = -1
    try:
        lock_fd = os.open(lock_name, flags, 0o600, dir_fd=directory_fd)
        lock_metadata = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(lock_metadata.st_mode)
            or lock_metadata.st_nlink != 1
            or lock_metadata.st_uid != os.getuid()
            or stat.S_IMODE(lock_metadata.st_mode) & 0o077
        ):
            raise OSError("unsafe consumption lock")
    except OSError:
        if lock_fd >= 0:
            os.close(lock_fd)
        os.close(directory_fd)
        os.close(root_fd)
        _reject("consumption_store_invalid", "Consumption lock is invalid")
    try:
        with os.fdopen(lock_fd, "a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            prior = _read_receipt(directory_fd, receipt_name)
            if prior is not None and prior.get("payload_digest") != payload_digest:
                _reject("idempotency_conflict", "Idempotency key payload conflict")
            if artifact.content_hash != expected_hash:
                _reject(
                    "artifact_hash_mismatch",
                    "Artifact metadata hash does not match expectation",
                )

            raw = _read_artifact(root_fd, relative, expected_hash)
            try:
                structured = json.loads(
                    raw.decode("utf-8"),
                    parse_constant=lambda value: (_ for _ in ()).throw(
                        ValueError(f"invalid JSON constant: {value}")
                    ),
                )
            except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError):
                _reject("artifact_parse_failed", "Artifact is not valid UTF-8 JSON")
            _validate_payload_shape(structured)
            if schema is not None:
                validate_instance(structured, schema, "artifact")
            expected_receipt = {
                "tenant_key": tenant_key,
                "user_id": user_id,
                "execution_id": execution.id,
                "artifact_id": artifact.id,
                "artifact_content_hash": expected_hash,
                "schema_digest": schema_digest,
                "schema_version": SCHEMA_VERSION,
                "capability_id": CAPABILITY_ID,
                "capability_version": CAPABILITY_VERSION,
                "idempotency_key_hash": key_hash,
                "payload_digest": payload_digest,
                "result_digest": _digest(structured),
            }
            if prior is not None:
                receipt = _verified_receipt(
                    prior, expected=expected_receipt, receipt_id=receipt_id
                )
                return {"structured_payload": structured, "receipt": receipt}
            receipt = {
                "receipt_id": receipt_id,
                **expected_receipt,
                "consumed_at": datetime.now(timezone.utc).isoformat(),
                "status": "completed",
            }
            try:
                _atomic_write(directory_fd, receipt_name, _canonical(receipt))
            except OSError:
                _reject("consumption_store_invalid", "Consumption receipt write failed")
            persisted = _read_receipt(directory_fd, receipt_name)
            if persisted != receipt:
                _reject("consumption_receipt_invalid", "Consumption receipt verification failed")
            return {
                "structured_payload": structured,
                "receipt": _verified_receipt(
                    persisted, expected=expected_receipt, receipt_id=receipt_id
                ),
            }
    finally:
        os.close(directory_fd)
        os.close(root_fd)
