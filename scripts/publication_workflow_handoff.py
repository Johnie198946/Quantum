#!/usr/bin/env python3
"""Materialize and acknowledge the fixed ai-toolkit Workflow handoff.

This client creates content inputs only. It never generates images, prepares,
reviews, stages, releases, or publishes an edition.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
from typing import Any
from zoneinfo import ZoneInfo

try:
    from scripts import publication_editorial_remote as editorial
    from scripts import publication_release_remote as transport
except ImportError:
    import publication_editorial_remote as editorial
    import publication_release_remote as transport

from backend.services.publication_workflow_handoff import (
    PublicationHandoffError,
    canonical_json,
    validate_ai_toolkit_artifact,
)

ENVELOPE_FIELDS = {
    "version",
    "schedule_id",
    "workflow_id",
    "execution_id",
    "plan_id",
    "plan_hash",
    "activation_revision",
    "primary_agent_id",
    "artifact_id",
    "artifact_sha256",
    "scheduled_for",
}
SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
STATE_FILE = "workflow-handoff-state.json"
DB_FILE = ".publication-workflow-consumptions.sqlite3"
LEDGER_DDL = """CREATE TABLE publication_workflow_consumptions (
execution_id TEXT NOT NULL,
schedule_id TEXT NOT NULL,
artifact_id TEXT PRIMARY KEY,
artifact_sha256 TEXT NOT NULL,
envelope_sha256 TEXT NOT NULL,
output_directory TEXT NOT NULL UNIQUE,
status TEXT NOT NULL CHECK(status IN ('materializing','waiting_assets','revision_requested','acknowledged')),
attempt_id TEXT,
updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)"""


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _validate_export(value: Any, expected_schedule_id: str) -> tuple[dict[str, Any], bytes, bytes]:
    if not isinstance(value, dict) or set(value) != {"envelope", "envelope_sha256", "artifact_b64"}:
        raise PublicationHandoffError("invalid workflow handoff export")
    envelope = value["envelope"]
    if (
        not isinstance(envelope, dict)
        or set(envelope) != ENVELOPE_FIELDS
        or envelope.get("version") != "publication-workflow-handoff-v1"
        or any(
            not isinstance(envelope.get(field), str)
            or SAFE_COMPONENT.fullmatch(envelope[field]) is None
            for field in ("schedule_id", "workflow_id", "execution_id", "plan_id", "artifact_id")
        )
        or not isinstance(envelope.get("artifact_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", envelope["artifact_sha256"]) is None
        or not isinstance(envelope.get("plan_hash"), str)
        or re.fullmatch(r"[0-9a-f]{64}", envelope["plan_hash"]) is None
        or type(envelope.get("activation_revision")) is not int
        or envelope["activation_revision"] < 1
        or not isinstance(envelope.get("primary_agent_id"), str)
        or SAFE_COMPONENT.fullmatch(envelope["primary_agent_id"]) is None
        or (envelope.get("scheduled_for") is not None and not isinstance(envelope["scheduled_for"], str))
    ):
        raise PublicationHandoffError("invalid workflow handoff envelope")
    if not expected_schedule_id or envelope["schedule_id"] != expected_schedule_id:
        raise PublicationHandoffError("workflow handoff schedule does not match the pinned local schedule")
    envelope_raw = canonical_json(envelope)
    if _digest(envelope_raw) != value["envelope_sha256"]:
        raise PublicationHandoffError("workflow handoff envelope hash mismatch")
    try:
        artifact_raw = base64.b64decode(value["artifact_b64"], validate=True)
    except (TypeError, ValueError) as exc:
        raise PublicationHandoffError("workflow artifact encoding is invalid") from exc
    if _digest(artifact_raw) != envelope["artifact_sha256"]:
        raise PublicationHandoffError("workflow artifact hash mismatch")
    validate_ai_toolkit_artifact(artifact_raw)
    return envelope, envelope_raw, artifact_raw


def _connect_ledger(root: Path) -> sqlite3.Connection:
    db = sqlite3.connect(root / DB_FILE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute(LEDGER_DDL.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1))
    schema = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='publication_workflow_consumptions'"
    ).fetchone()[0]
    if "artifact_id TEXT PRIMARY KEY" not in schema or "revision_requested" not in schema:
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("ALTER TABLE publication_workflow_consumptions RENAME TO publication_workflow_consumptions_v1")
            db.execute(LEDGER_DDL)
            db.execute(
                """INSERT INTO publication_workflow_consumptions
                (execution_id,schedule_id,artifact_id,artifact_sha256,envelope_sha256,
                 output_directory,status,attempt_id,updated_at)
                SELECT execution_id,schedule_id,artifact_id,artifact_sha256,envelope_sha256,
                 output_directory,status,attempt_id,updated_at
                FROM publication_workflow_consumptions_v1"""
            )
            db.execute("DROP TABLE publication_workflow_consumptions_v1")
            db.commit()
        except Exception:
            db.rollback()
            raise
    return db


def _write(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _expected_state(envelope: dict[str, Any], envelope_raw: bytes, artifact_raw: bytes) -> dict[str, Any]:
    try:
        scheduled = datetime.fromisoformat(envelope["scheduled_for"])
        if scheduled.tzinfo is None:
            raise ValueError
        issue_date = scheduled.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    except (TypeError, ValueError) as exc:
        raise PublicationHandoffError("workflow handoff scheduled_for is invalid") from exc
    return {
        "version": "publication-workflow-consumption-v1",
        "status": "waiting_assets",
        "execution_id": envelope["execution_id"],
        "schedule_id": envelope["schedule_id"],
        "series_id": "ai-toolkit",
        "issue_date": issue_date,
        "artifact_id": envelope["artifact_id"],
        "plan_hash": envelope["plan_hash"],
        "activation_revision": envelope["activation_revision"],
        "primary_agent_id": envelope["primary_agent_id"],
        "artifact_sha256": _digest(artifact_raw),
        "envelope_sha256": _digest(envelope_raw),
        "next_action": "generate the five real publication images, then run existing build_initial/start and prepare",
    }


def _verify_existing_output(
    target: Path,
    envelope: dict[str, Any],
    envelope_raw: bytes,
    artifact_raw: bytes,
) -> None:
    if target.is_symlink() or not target.is_dir():
        raise PublicationHandoffError("handoff output path conflicts")
    content = validate_ai_toolkit_artifact(artifact_raw)
    source_entries = []
    execution_entries = []
    expected = {
        "workflow-envelope.json": envelope_raw,
        "workflow-artifact.json": artifact_raw,
        "body.md": content["body"].encode("utf-8"),
        STATE_FILE: canonical_json(_expected_state(envelope, envelope_raw, artifact_raw)),
    }
    for group, destination, prefix in (
        (content["source_documents"], source_entries, "source"),
        (content["execution_documents"], execution_entries, "execution"),
    ):
        for index, document in enumerate(group, 1):
            name = f"inputs/{prefix}-{index:02d}.txt"
            expected[name] = document["content"].encode("utf-8")
            destination.append({"kind": document["kind"], "path": name})
    source_entries.extend(
        [
            {"kind": "workflow_handoff_envelope", "path": "workflow-envelope.json"},
            {"kind": "workflow_artifact", "path": "workflow-artifact.json"},
        ]
    )
    expected["content-submission.json"] = canonical_json(
        {
            "title": content["title"],
            "summary": content["summary"],
            "editorial_brief": content["editorial_brief"],
            "learning_objectives": content["learning_objectives"],
            "source_files": source_entries,
            "execution_files": execution_entries,
        }
    )
    for name, raw in expected.items():
        path = target / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != raw:
            raise PublicationHandoffError("existing handoff output conflicts")


def materialize_export(
    value: Any,
    output_root: Path,
    *,
    expected_schedule_id: str,
    _fail_after_rename: bool = False,
) -> dict[str, Any]:
    """Atomically consume one export and stop in waiting_assets."""
    if value == {"status": "waiting_workflow", "available": False}:
        return value
    envelope, envelope_raw, artifact_raw = _validate_export(value, expected_schedule_id)
    content = validate_ai_toolkit_artifact(artifact_raw)
    root = Path(output_root).expanduser().absolute()
    if root.is_symlink():
        raise PublicationHandoffError("output root must not be a symlink")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not root.is_dir():
        raise PublicationHandoffError("output root must be a directory")
    directory_name = f"ai-toolkit-{envelope['artifact_id']}"
    if SAFE_COMPONENT.fullmatch(directory_name) is None:
        raise PublicationHandoffError("derived output directory is invalid")
    target = root / directory_name
    artifact_hash = _digest(artifact_raw)
    envelope_hash = _digest(envelope_raw)

    with _connect_ledger(root) as ledger:
        ledger.execute("BEGIN IMMEDIATE")
        row = ledger.execute(
            "SELECT * FROM publication_workflow_consumptions WHERE artifact_id=?",
            (envelope["artifact_id"],),
        ).fetchone()
        binding = (
            envelope["schedule_id"],
            envelope["artifact_id"],
            artifact_hash,
            envelope_hash,
            directory_name,
        )
        if row is not None and tuple(row[key] for key in (
            "schedule_id", "artifact_id", "artifact_sha256", "envelope_sha256", "output_directory"
        )) != binding:
            raise PublicationHandoffError("workflow consumption binding conflicts")
        if row is None:
            ledger.execute(
                """INSERT INTO publication_workflow_consumptions
                (execution_id,schedule_id,artifact_id,artifact_sha256,envelope_sha256,output_directory,status)
                VALUES (?,?,?,?,?,?, 'materializing')""",
                (envelope["execution_id"], *binding),
            )
        ledger.commit()

    if target.exists():
        _verify_existing_output(target, envelope, envelope_raw, artifact_raw)
    else:
        temporary = Path(tempfile.mkdtemp(prefix=f".{directory_name}-{artifact_hash[:12]}-", dir=root))
        try:
            _write(temporary / "body.md", content["body"].encode("utf-8"))
            source_entries = []
            execution_entries = []
            inputs = temporary / "inputs"
            inputs.mkdir(mode=0o700)
            for group, destination, prefix in (
                (content["source_documents"], source_entries, "source"),
                (content["execution_documents"], execution_entries, "execution"),
            ):
                for index, document in enumerate(group, 1):
                    name = f"inputs/{prefix}-{index:02d}.txt"
                    _write(temporary / name, document["content"].encode("utf-8"))
                    destination.append({"kind": document["kind"], "path": name})
            _write(temporary / "workflow-envelope.json", envelope_raw)
            _write(temporary / "workflow-artifact.json", artifact_raw)
            source_entries.extend(
                [
                    {"kind": "workflow_handoff_envelope", "path": "workflow-envelope.json"},
                    {"kind": "workflow_artifact", "path": "workflow-artifact.json"},
                ]
            )
            submission = {
                "title": content["title"],
                "summary": content["summary"],
                "editorial_brief": content["editorial_brief"],
                "learning_objectives": content["learning_objectives"],
                "source_files": source_entries,
                "execution_files": execution_entries,
            }
            _write(temporary / "content-submission.json", canonical_json(submission))
            _write(
                temporary / STATE_FILE,
                canonical_json(_expected_state(envelope, envelope_raw, artifact_raw)),
            )
            os.replace(temporary, target)
            directory_fd = os.open(root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    if _fail_after_rename:
        raise RuntimeError("synthetic crash after atomic rename")
    with _connect_ledger(root) as ledger:
        ledger.execute("BEGIN IMMEDIATE")
        ledger.execute(
            """UPDATE publication_workflow_consumptions
            SET status='waiting_assets',updated_at=CURRENT_TIMESTAMP WHERE artifact_id=?""",
            (envelope["artifact_id"],),
        )
        ledger.commit()
    return {
        "status": "waiting_assets",
        "output_directory": str(target),
        "execution_id": envelope["execution_id"],
        "artifact_sha256": artifact_hash,
        "envelope_sha256": envelope_hash,
    }


def acknowledge_manifest(manifest_path: Path, remote: editorial.Remote) -> dict[str, Any]:
    manifest_path, manifest = editorial.load_manifest(manifest_path)
    if len(manifest["items"]) != 1 or manifest["items"][0]["status"] != "staged":
        raise PublicationHandoffError("acknowledgement requires one staged manifest item")
    item = manifest["items"][0]
    base = manifest_path.parent
    state_path = editorial.local_path(base, STATE_FILE)
    state = json.loads(editorial.read(state_path))
    if not isinstance(state, dict) or state.get("status") not in {"waiting_assets", "acknowledged"}:
        raise PublicationHandoffError("workflow handoff state is invalid")
    bundle_path = editorial.local_path(base, item["bundle_file"])
    json.loads(editorial.read(bundle_path))
    contract = item.get("quality_contract")
    if not isinstance(contract, dict) or not isinstance(contract.get("attempt_id"), str):
        raise PublicationHandoffError("publication attempt is unavailable")
    source_hashes = {
        (entry["kind"], entry["sha256"])
        for entry in item["source_files"]
        if isinstance(entry, dict)
    }
    required = {
        ("workflow_artifact", state.get("artifact_sha256")),
        ("workflow_handoff_envelope", state.get("envelope_sha256")),
    }
    if not required <= source_hashes:
        raise PublicationHandoffError("prepared manifest does not bind workflow handoff files")
    batch = item.get("batch")
    if not isinstance(batch, str):
        raise PublicationHandoffError("prepared manifest batch is unavailable")
    uploaded = remote.upload(batch, editorial.read(bundle_path), ".json")
    result = remote.operator(
        "acknowledge-workflow-handoff",
        "--bundle",
        uploaded,
        "--execution-id",
        state["execution_id"],
        "--artifact-id",
        state["artifact_id"],
        "--artifact-sha256",
        state["artifact_sha256"],
        "--envelope-sha256",
        state["envelope_sha256"],
        "--attempt-id",
        contract["attempt_id"],
    )
    if result.get("status") != "completed" or result.get("attempt_id") != contract["attempt_id"]:
        raise PublicationHandoffError("workflow acknowledgement readback mismatch")
    updated = {**state, "status": "acknowledged", "attempt_id": contract["attempt_id"]}
    editorial.save(state_path, updated)
    root = base.parent
    ledger_path = root / DB_FILE
    if ledger_path.exists():
        with _connect_ledger(root) as ledger:
            ledger.execute("BEGIN IMMEDIATE")
            cursor = ledger.execute(
                """UPDATE publication_workflow_consumptions
                SET status='acknowledged',attempt_id=?,updated_at=CURRENT_TIMESTAMP
                WHERE artifact_id=? AND artifact_sha256=? AND envelope_sha256=?""",
                (contract["attempt_id"], state["artifact_id"], state["artifact_sha256"], state["envelope_sha256"]),
            )
            if cursor.rowcount != 1:
                raise PublicationHandoffError("workflow consumption ledger acknowledgement mismatch")
            ledger.commit()
    return result


def request_revision_manifest(manifest_path: Path, remote: editorial.Remote) -> dict[str, Any]:
    """Relay one exact rejected local handoff to the fixed server operator."""
    manifest_path, manifest = editorial.load_manifest(manifest_path)
    if len(manifest["items"]) != 1 or manifest["items"][0]["status"] != "rejected":
        raise PublicationHandoffError("revision requires one rejected manifest item")
    item = manifest["items"][0]
    base = manifest_path.parent
    state_path = editorial.local_path(base, STATE_FILE)
    state = json.loads(editorial.read(state_path))
    schedule_id = os.environ.get("PUBLICATION_AI_TOOLKIT_SCHEDULE_ID", "")
    if (
        not isinstance(state, dict)
        or state.get("status") not in {"waiting_assets", "revision_requested"}
        or state.get("series_id") != "ai-toolkit"
        or state.get("schedule_id") != schedule_id
        or not isinstance(state.get("issue_date"), str)
    ):
        raise PublicationHandoffError("workflow handoff state or pinned schedule is invalid")
    envelope_path = editorial.local_path(base, "workflow-envelope.json")
    envelope_raw = editorial.read(envelope_path)
    envelope = json.loads(envelope_raw)
    artifact_raw = editorial.read(editorial.local_path(base, "workflow-artifact.json"))
    validated, _, _ = _validate_export({
        "envelope": envelope,
        "envelope_sha256": state.get("envelope_sha256"),
        "artifact_b64": base64.b64encode(artifact_raw).decode("ascii"),
    }, schedule_id)
    if (
        validated.get("artifact_id") != state.get("artifact_id")
        or _digest(envelope_raw) != state.get("envelope_sha256")
        or any(state.get(field) != validated.get(field) for field in (
            "plan_hash", "activation_revision", "primary_agent_id",
        ))
    ):
        raise PublicationHandoffError("local revision envelope binding mismatch")
    contract = item.get("quality_contract")
    if not isinstance(contract, dict) or not isinstance(contract.get("attempt_id"), str):
        raise PublicationHandoffError("rejected publication attempt is unavailable")
    bundle_path = editorial.local_path(base, item["bundle_file"])
    review_path = editorial.local_path(base, item["review_file"])
    bundle_remote = remote.upload(item["batch"], editorial.read(bundle_path), ".json")
    review_remote = remote.upload(item["batch"], editorial.read(review_path), ".json")
    result = remote.operator(
        "request-workflow-revision",
        "--envelope", remote.upload(item["batch"], envelope_raw, ".json"),
        "--envelope-sha256", state["envelope_sha256"],
        "--bundle", bundle_remote,
        "--review-file", review_remote,
        "--attempt-id", contract["attempt_id"],
    )
    if result.get("status") != "queued" or result.get("artifact_id") != state["artifact_id"]:
        raise PublicationHandoffError("workflow revision readback mismatch")
    updated = {**state, "status": "revision_requested", "attempt_id": contract["attempt_id"]}
    editorial.save(state_path, updated)
    root = base.parent
    with _connect_ledger(root) as ledger:
        ledger.execute("BEGIN IMMEDIATE")
        cursor = ledger.execute(
            """UPDATE publication_workflow_consumptions
            SET status='revision_requested',attempt_id=?,updated_at=CURRENT_TIMESTAMP
            WHERE artifact_id=? AND envelope_sha256=?""",
            (contract["attempt_id"], state["artifact_id"], state["envelope_sha256"]),
        )
        if cursor.rowcount != 1:
            raise PublicationHandoffError("workflow consumption ledger revision mismatch")
        ledger.commit()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-file")
    parser.add_argument("--known-hosts-file")
    commands = parser.add_subparsers(dest="action", required=True)
    fetch = commands.add_parser("fetch")
    fetch.add_argument("--output-root", required=True, type=Path)
    acknowledge = commands.add_parser("acknowledge")
    acknowledge.add_argument("--manifest", required=True, type=Path)
    revision = commands.add_parser("request-revision")
    revision.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        identity, known_hosts = transport._trust(args)
        remote = editorial.Remote(identity, known_hosts)
        if args.action == "fetch":
            schedule_id = os.environ.get("PUBLICATION_AI_TOOLKIT_SCHEDULE_ID", "")
            result = materialize_export(
                remote.operator("export-workflow-handoff"), args.output_root,
                expected_schedule_id=schedule_id,
            )
        elif args.action == "acknowledge":
            result = acknowledge_manifest(args.manifest, remote)
        else:
            result = request_revision_manifest(args.manifest, remote)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"publication workflow handoff failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
