from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid

import pytest

from backend.api.tenant import current_tenant
from backend.db import SessionLocal
from backend.models.workflow import (
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowPlanVersion,
)
from backend.services.capability_catalog import (
    describe_capability,
    invoke_capability,
    search_capabilities,
)
from backend.services.workflow_artifacts import run_root, store_artifact


async def _artifact(
    tmp_path, monkeypatch, content: bytes, extension: str = "json", *,
    clarification_session_id: str | None = "generated",
):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    suffix = uuid.uuid4().hex[:16]
    workflow = WorkflowDefinition(
        id=f"wf_{suffix}", tenant_key="tenant-a", created_by="user-a",
        title="Structured", description="consume structured artifact",
        clarification_session_id=(
            f"wfs_{suffix}" if clarification_session_id == "generated"
            else clarification_session_id
        ),
    )
    plan = WorkflowPlanVersion(
        id=f"wfp_{suffix}", workflow_id=workflow.id, version=1,
        dsl={}, goal="consume", deliverable="json",
    )
    execution = WorkflowExecution(
        id=f"wfr_{suffix}", workflow_id=workflow.id, plan_id=plan.id,
        tenant_key="tenant-a", idempotency_key=f"run-{suffix}",
    )
    async with SessionLocal() as db:
        db.add(workflow)
        await db.flush()
        db.add(plan)
        await db.flush()
        db.add(execution)
        await db.flush()
        artifact = store_artifact(
            execution, node_run_id=None, kind="evidence", title="private artifact",
            content=content, extension=extension,
        )
        db.add(artifact)
        await db.commit()
    return execution, artifact


async def _invoke(execution, artifact, *, payload=None, key="request-structured", **changes):
    data = {
        "execution_id": execution.id,
        "artifact_id": artifact.id,
        "expected_content_hash": artifact.content_hash,
        **changes,
    }
    payload = payload or {"tenant_key": "tenant-a", "user_id": "user-a"}
    token = current_tenant.set(str(payload["tenant_key"]))
    try:
        return await invoke_capability(
            "artifact.consume_structured", data, payload=payload,
            idempotency_key=key,
        )
    finally:
        current_tenant.reset(token)


@pytest.mark.asyncio
async def test_structured_consumption_search_describe_invoke_and_receipt_replay(
    tmp_path, monkeypatch
):
    body = {"name": "private-value", "count": 3}
    execution, artifact = await _artifact(
        tmp_path, monkeypatch, json.dumps(body).encode()
    )
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "count": {"type": "integer", "minimum": 0},
        },
        "required": ["name", "count"],
        "additionalProperties": False,
    }

    assert search_capabilities("consume structured artifact")[0]["id"] == (
        "artifact.consume_structured"
    )
    described = describe_capability("artifact.consume_structured")
    assert described and described["implementation_status"] == "implemented"
    first = await _invoke(execution, artifact, expected_schema=schema)
    replay = await _invoke(execution, artifact, expected_schema=schema)

    assert first == replay
    assert first["status"] == "completed"
    assert first["events"] == [{
        "type": "artifact.consumed", "version": 1,
        "payload": first["events"][0]["payload"],
    }]
    result = first["events"][0]["payload"]
    assert result["structured_payload"] == body
    receipt = result["receipt"]
    assert first["receipt"]["invocation_id"].startswith("qcp-")
    assert first["receipt"]["capability_version"] == "1.0.0"
    assert first["receipt"]["status"] == "completed"
    assert first["receipt"]["event_type"] == "artifact.consumed"
    assert "receipt_id" not in first["receipt"]
    assert receipt["tenant_key"] == "tenant-a"
    assert receipt["user_id"] == "user-a"
    assert receipt["execution_id"] == execution.id
    assert receipt["artifact_id"] == artifact.id
    assert receipt["artifact_content_hash"] == artifact.content_hash
    assert receipt["capability_id"] == "artifact.consume_structured"
    assert receipt["capability_version"] == "1.0.0"
    assert receipt["schema_version"] == "json-schema-draft-2020-12-restricted"
    assert receipt["status"] == "completed"
    assert receipt["result_digest"] == hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert "private-value" not in json.dumps(receipt)
    persisted = list((run_root(execution) / "consumptions").glob("*.json"))
    assert len(persisted) == 1
    assert json.loads(persisted[0].read_text()) == receipt


@pytest.mark.asyncio
async def test_structured_consumption_enforces_owner_hash_schema_format_and_size(
    tmp_path, monkeypatch
):
    execution, artifact = await _artifact(tmp_path, monkeypatch, b'{"value":"ok"}')
    wrong_tenant = await _invoke(
        execution, artifact, payload={"tenant_key": "tenant-b", "user_id": "user-a"}
    )
    wrong_user = await _invoke(
        execution, artifact, payload={"tenant_key": "tenant-a", "user_id": "user-b"}
    )
    mismatch = await _invoke(
        execution, artifact, expected_content_hash="0" * 64, key="request-hash-mismatch"
    )
    schema_mismatch = await _invoke(
        execution,
        artifact,
        key="request-schema-mismatch",
        expected_schema={
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )
    unsafe_schema = await _invoke(
        execution,
        artifact,
        key="request-schema-unsafe",
        expected_schema={"type": "string", "pattern": ".*"},
    )
    _, binary = await _artifact(tmp_path, monkeypatch, b"PK\x03\x04", "bin")
    unsupported = await _invoke(execution=_, artifact=binary, key="request-binary")
    oversized_execution, oversized = await _artifact(
        tmp_path, monkeypatch, b'"' + b"x" * (1024 * 1024) + b'"'
    )
    too_large = await _invoke(
        oversized_execution, oversized, key="request-oversized"
    )

    assert wrong_tenant["error"]["code"] == "domain_rejected"
    assert wrong_user["error"]["code"] == "domain_rejected"
    assert mismatch["error"]["code"] == "artifact_hash_mismatch"
    assert schema_mismatch["error"]["code"] == "contract_invalid"
    assert unsafe_schema["error"]["code"] == "contract_invalid"
    assert unsupported["error"]["code"] == "unsupported_artifact_format"
    assert too_large["error"]["code"] == "artifact_too_large"


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [b'{"value":1e400}', b'{"value":NaN}', b'{"value":Infinity}', b'{"value":-Infinity}'])
async def test_structured_consumption_rejects_every_non_finite_number(
    tmp_path, monkeypatch, raw
):
    execution, artifact = await _artifact(tmp_path, monkeypatch, raw)

    result = await _invoke(execution, artifact, key="request-non-finite-" + hashlib.sha256(raw).hexdigest()[:8])

    assert result["status"] == "failed"
    assert result["error"]["code"] == "artifact_parse_failed"
    assert not list((run_root(execution) / "consumptions").glob("*.json"))


@pytest.mark.asyncio
async def test_null_clarification_session_still_requires_workflow_creator(
    tmp_path, monkeypatch
):
    execution, artifact = await _artifact(
        tmp_path, monkeypatch, b'{"value":"private"}',
        clarification_session_id=None,
    )

    denied = await _invoke(
        execution, artifact,
        payload={"tenant_key": "tenant-a", "user_id": "user-b"},
    )

    assert denied["error"]["code"] == "execution_not_found"


@pytest.mark.asyncio
async def test_structured_consumption_conflict_corruption_missing_and_concurrency(
    tmp_path, monkeypatch
):
    execution, artifact = await _artifact(tmp_path, monkeypatch, b'{"value":"ok"}')
    schema = {
        "type": "object", "properties": {"value": {"type": "string"}},
        "required": ["value"], "additionalProperties": False,
    }
    first = await _invoke(execution, artifact, key="request-drift", expected_schema=schema)
    conflict = await _invoke(
        execution,
        artifact,
        key="request-drift",
        expected_schema={
            **schema,
            "properties": {
                **schema["properties"], "optional": {"type": "boolean"},
            },
        },
    )
    hash_conflict = await _invoke(
        execution, artifact, key="request-drift", expected_content_hash="0" * 64,
    )
    assert first["status"] == "completed"
    assert conflict["error"]["code"] == "idempotency_conflict"
    assert hash_conflict["error"]["code"] == "idempotency_conflict"

    concurrent = await asyncio.gather(*(
        _invoke(execution, artifact, key="request-concurrent", expected_schema=schema)
        for _index in range(8)
    ))
    assert {item["events"][0]["payload"]["receipt"]["receipt_id"] for item in concurrent} == {
        concurrent[0]["events"][0]["payload"]["receipt"]["receipt_id"]
    }

    await _invoke(execution, artifact, key="request-corrupt", expected_schema=schema)
    directory = run_root(execution) / "consumptions"
    corrupt_hash = hashlib.sha256(
        f"artifact.consume_structured:{hashlib.sha256(b'request-corrupt').hexdigest()}".encode()
    ).hexdigest()
    corrupt_path = directory / f"{corrupt_hash}.json"
    corrupt_path.write_text("{broken", encoding="utf-8")
    corrupt = await _invoke(
        execution, artifact, key="request-corrupt", expected_schema=schema
    )
    assert corrupt["error"]["code"] == "consumption_receipt_invalid"

    prior_missing = await _invoke(
        execution, artifact, key="request-missing", expected_schema=schema
    )
    missing_hash = hashlib.sha256(
        f"artifact.consume_structured:{hashlib.sha256(b'request-missing').hexdigest()}".encode()
    ).hexdigest()
    (directory / f"{missing_hash}.json").unlink()
    recovered = await _invoke(
        execution, artifact, key="request-missing", expected_schema=schema
    )
    assert recovered["status"] == "completed"
    assert recovered["events"][0]["payload"]["structured_payload"] == {"value": "ok"}
    assert recovered["events"][0]["payload"]["receipt"]["receipt_id"] == (
        prior_missing["events"][0]["payload"]["receipt"]["receipt_id"]
    )

    crash_key = "request-lock-only"
    crash_hash = hashlib.sha256(
        f"artifact.consume_structured:{hashlib.sha256(crash_key.encode()).hexdigest()}".encode()
    ).hexdigest()
    (directory / f"{crash_hash}.lock").touch(mode=0o600)
    crash_recovered = await _invoke(
        execution, artifact, key=crash_key, expected_schema=schema
    )
    assert crash_recovered["status"] == "completed"


@pytest.mark.asyncio
async def test_structured_consumption_rejects_symlinked_artifact(tmp_path, monkeypatch):
    execution, artifact = await _artifact(tmp_path, monkeypatch, b'{"value":"ok"}')
    path = run_root(execution) / artifact.relative_path
    target = path.with_name("real.json")
    path.rename(target)
    path.symlink_to(target.name)

    denied = await _invoke(execution, artifact, key="request-symlink")

    assert denied["error"]["code"] == "artifact_file_unavailable"
    path.unlink()
    path.mkdir()
    non_regular = await _invoke(execution, artifact, key="request-directory")
    assert non_regular["error"]["code"] == "artifact_file_unavailable"


@pytest.mark.asyncio
async def test_structured_consumption_rejects_hardlinks_and_unsafe_receipt_store(
    tmp_path, monkeypatch
):
    execution, artifact = await _artifact(tmp_path, monkeypatch, b'{"value":"ok"}')
    artifact_path = run_root(execution) / artifact.relative_path
    os.link(artifact_path, artifact_path.with_name("artifact-hardlink.json"))
    denied = await _invoke(execution, artifact, key="request-artifact-hardlink")
    assert denied["error"]["code"] == "artifact_file_unavailable"

    artifact_path.with_name("artifact-hardlink.json").unlink()
    completed = await _invoke(execution, artifact, key="request-receipt-link")
    directory = run_root(execution) / "consumptions"
    receipt = next(
        path for path in directory.glob("*.json")
        if json.loads(path.read_text())["receipt_id"]
        == completed["events"][0]["payload"]["receipt"]["receipt_id"]
    )
    outside = tmp_path / "outside-receipt.json"
    receipt.rename(outside)
    receipt.symlink_to(outside)
    replay = await _invoke(execution, artifact, key="request-receipt-link")
    assert replay["error"]["code"] == "consumption_receipt_invalid"

    hardlink_result = await _invoke(
        execution, artifact, key="request-receipt-hardlink"
    )
    hardlink_receipt = next(
        path for path in directory.glob("*.json")
        if not path.is_symlink()
        and json.loads(path.read_text())["receipt_id"]
        == hardlink_result["events"][0]["payload"]["receipt"]["receipt_id"]
    )
    os.link(hardlink_receipt, tmp_path / "receipt-hardlink.json")
    hardlink_replay = await _invoke(
        execution, artifact, key="request-receipt-hardlink"
    )
    assert hardlink_replay["error"]["code"] == "consumption_receipt_invalid"


@pytest.mark.asyncio
async def test_structured_consumption_rejects_symlinked_receipt_directory(
    tmp_path, monkeypatch
):
    execution, artifact = await _artifact(tmp_path, monkeypatch, b'{"value":"ok"}')
    directory = run_root(execution) / "consumptions"
    outside = tmp_path / "outside-consumptions"
    outside.mkdir()
    directory.symlink_to(outside, target_is_directory=True)

    denied = await _invoke(execution, artifact, key="request-store-symlink")

    assert denied["error"]["code"] == "consumption_store_invalid"


def test_fd_read_is_bound_to_opened_inode_during_path_replacement(tmp_path, monkeypatch):
    from backend.services import artifact_consumption as consumption

    original = tmp_path / "artifact.json"
    moved = tmp_path / "opened.json"
    outside = tmp_path / "outside.json"
    original.write_bytes(b'{"value":"original"}')
    outside.write_bytes(b'{"value":"substitute"}')
    directory_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    real_fstat = os.fstat
    replaced = False

    def replace_after_open(file_fd):
        nonlocal replaced
        if not replaced:
            replaced = True
            original.rename(moved)
            original.symlink_to(outside)
        return real_fstat(file_fd)

    monkeypatch.setattr(consumption.os, "fstat", replace_after_open)
    try:
        assert consumption._read_regular_at(
            directory_fd, "artifact.json", 1024
        ) == b'{"value":"original"}'
    finally:
        os.close(directory_fd)
