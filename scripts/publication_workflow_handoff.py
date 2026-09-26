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
    configured_handoff_schedule,
    publication_occurrence,
    publication_system_fields,
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


def _validate_export(value: Any, expected_schedule_id: str, expected_series_id: str | None = None, expected_issue_key: str | None = None) -> tuple[dict[str, Any], bytes, bytes]:
    if not isinstance(value, dict) or set(value) != {"envelope", "envelope_sha256", "artifact_b64"}:
        raise PublicationHandoffError("invalid workflow handoff export")
    envelope = value["envelope"]
    if (
        not isinstance(envelope, dict)
        or set(envelope) != (ENVELOPE_FIELDS | ({"series_id", "issue_date", "issue_key", "issue_slot", "release_at", "writer_session"} if envelope.get("version") == "publication-workflow-handoff-v2" else set()))
        or envelope.get("version") not in {"publication-workflow-handoff-v1", "publication-workflow-handoff-v2"}
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
    if expected_series_id is not None and (
        envelope.get("version") != "publication-workflow-handoff-v2"
        or envelope.get("series_id") != expected_series_id
        or configured_handoff_schedule(expected_series_id) != expected_schedule_id
    ):
        raise PublicationHandoffError("workflow handoff series binding mismatch")
    if envelope.get("version") == "publication-workflow-handoff-v2":
        series_id = envelope.get("series_id")
        if configured_handoff_schedule(series_id) != expected_schedule_id:
            raise PublicationHandoffError("workflow handoff configured schedule mismatch")
        try:
            occurrence = publication_occurrence(series_id, datetime.fromisoformat(envelope["scheduled_for"]))
        except (TypeError, ValueError, KeyError) as exc:
            raise PublicationHandoffError("workflow publication occurrence is invalid") from exc
        if any(envelope.get(key) != value for key, value in occurrence.items()):
            raise PublicationHandoffError("workflow handoff occurrence binding mismatch")
        if not isinstance(envelope.get("writer_session"), str) or not envelope["writer_session"]:
            raise PublicationHandoffError("workflow author session is missing")
    if expected_issue_key is not None and envelope.get("issue_key") != expected_issue_key:
        raise PublicationHandoffError("workflow handoff issue binding mismatch")
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
        "series_id": envelope.get("series_id", "ai-toolkit"),
        **({key: envelope[key] for key in ("issue_key", "issue_slot", "release_at", "writer_session")}
           if envelope.get("version") == "publication-workflow-handoff-v2" else {}),
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
    system_fields = publication_system_fields(content, envelope.get("series_id", "ai-toolkit"))
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
            "editorial_brief": system_fields["editorial_brief"],
            "learning_objectives": system_fields["learning_objectives"],
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
    expected_series_id: str | None = None,
    expected_issue_key: str | None = None,
    _fail_after_rename: bool = False,
) -> dict[str, Any]:
    """Atomically consume one export and stop in waiting_assets."""
    if value == {"status": "waiting_workflow", "available": False} or (
        isinstance(value, dict) and value.get("status") == "preflight_revision_requested"
        and value.get("available") is False
    ):
        return value
    envelope, envelope_raw, artifact_raw = _validate_export(value, expected_schedule_id, expected_series_id, expected_issue_key)
    content = validate_ai_toolkit_artifact(artifact_raw)
    system_fields = publication_system_fields(content, envelope.get("series_id", "ai-toolkit"))
    root = Path(output_root).expanduser().absolute()
    if root.is_symlink():
        raise PublicationHandoffError("output root must not be a symlink")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not root.is_dir():
        raise PublicationHandoffError("output root must be a directory")
    directory_name = f"{envelope.get('series_id', 'ai-toolkit')}-{envelope['artifact_id']}"
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
                "editorial_brief": system_fields["editorial_brief"],
                "learning_objectives": system_fields["learning_objectives"],
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
        *(("--series-id", state["series_id"]) if "writer_session" in state else ()),
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
    schedule_id = configured_handoff_schedule(state.get("series_id", "ai-toolkit"))
    if (
        not isinstance(state, dict)
        or state.get("status") not in {"waiting_assets", "revision_requested"}
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
        *(("--series-id", state["series_id"]) if "writer_session" in state else ()),
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



def native_output_root() -> Path:
    return Path.home() / ".hermes/outputs/quantumn-editorial-v2"


def _native_artifact_path(value: str) -> Path:
    root = native_output_root().absolute()
    candidate = Path(value).expanduser().absolute()
    if not candidate.resolve().is_relative_to(root.resolve()) or candidate.resolve() == root.resolve():
        raise PublicationHandoffError("native content artifact must be inside publication output root")
    if any(part.is_symlink() for part in (candidate, *candidate.parents)) or not candidate.is_file():
        raise PublicationHandoffError("native content artifact path is unsafe")
    return candidate



def author_input(job_id: str, profile: str, remote, *, now: datetime | None = None) -> str:
    """Assign one current-day occurrence from configured jobs and server truth."""
    from backend.services.knowledge_publication_store import SERIES, publication_slot
    if profile not in {"default", "story"}:
        raise PublicationHandoffError("unsupported native author profile")
    configured = {key for key, value in SERIES.items() if value.get("enabled", True)
                  and value.get("author_job_id") == job_id and value.get("author_profile", "default") == profile}
    if not configured:
        raise PublicationHandoffError("native author job is not configured for this profile")
    current = (now or datetime.now(ZoneInfo("Asia/Shanghai"))).astimezone(ZoneInfo("Asia/Shanghai"))
    day = current.date().isoformat()
    status = remote.operator("status")
    expected = status.get("expected_issues")
    if not isinstance(expected, list) or not isinstance(status.get("items"), list):
        raise PublicationHandoffError("server publication occurrence status is unavailable")
    occupied = {(row.get("series_id"), row.get("issue_key", row.get("issue_date")))
                for row in status["items"] if row.get("state") in {"published", "scheduled", "staged"}}
    for path in editorial.manifests(native_output_root()) if native_output_root().exists() else []:
        try:
            _, manifest = editorial.load_manifest(path)
            for item in manifest["items"]:
                if item["status"] in {"prepared", "await_review", "staged"}:
                    bundle = json.loads(editorial.read(editorial.local_path(path.parent, item["bundle_file"])))
                    slot = publication_slot(bundle["series_id"], bundle["issue_date"], bundle.get("issue_slot"))
                    occupied.add((bundle["series_id"], slot["issue_key"]))
        except (ValueError, KeyError, OSError):
            continue
    for state_path in [*native_output_root().glob("*/native-content-state.json"), *native_output_root().glob("*/workflow-handoff-state.json")]:
        state = json.loads(editorial.read(state_path))
        if state.get("status") != "waiting_assets":
            continue
        manifest_path = state_path.parent / "draft-manifest.json"
        if manifest_path.exists():
            _, manifest = editorial.load_manifest(manifest_path)
            if any(item["status"] == "rejected" for item in manifest["items"]):
                continue
        if state.get("series_id") not in configured:
            continue
        if state_path.name == "native-content-state.json":
            found = native_content_binding(state["series_id"], state["issue_key"], writer_session=state.get("writer_session"))
            if (found is None or editorial.read(editorial.local_path(state_path.parent, "native-author.json")) != canonical_json(found[0])
                    or editorial.read(editorial.local_path(state_path.parent, "native-content.json")) != found[1]
                    or editorial.read(editorial.local_path(state_path.parent, "body.md")) != found[2]["body"].encode("utf-8")):
                raise PublicationHandoffError("pending native author content binding is invalid")
        else:
            envelope_raw = editorial.read(editorial.local_path(state_path.parent, "workflow-envelope.json"))
            artifact_raw = editorial.read(editorial.local_path(state_path.parent, "workflow-artifact.json"))
            envelope = json.loads(envelope_raw)
            _validate_export({"envelope": envelope, "envelope_sha256": state["envelope_sha256"], "artifact_b64": base64.b64encode(artifact_raw).decode("ascii")}, configured_handoff_schedule(state["series_id"]))
            _verify_existing_output(state_path.parent, envelope, envelope_raw, artifact_raw)
        occupied.add((state.get("series_id"), state.get("issue_key", state.get("issue_date"))))
    candidates = []
    for row in expected:
        if row.get("series_id") not in configured or row.get("issue_date") != day:
            continue
        occurrence = publication_slot(row["series_id"], day, row.get("issue_slot"))
        if any(row.get(key) != value for key, value in occurrence.items()):
            raise PublicationHandoffError("server occurrence conflicts with configured release slots")
        if (row["series_id"], row["issue_key"]) not in occupied:
            candidates.append({"series_id": row["series_id"], "issue_date": day,
                               **occurrence, "author_job_id": job_id})
    if not candidates:
        return "NO_NEW_DRAFT"
    request = sorted(candidates, key=lambda value: (value["release_at"], value["series_id"]))[0]
    return "PUBLICATION_CONTENT_REQUEST\n" + canonical_json(request).decode("utf-8") + "\nEND_PUBLICATION_CONTENT_REQUEST"


def assets_input() -> str:
    """Select one immutable, unprepared content handoff; never ask the asset model to scan."""
    root = native_output_root()
    if not root.exists():
        return "NO_NEW_DRAFT"
    states = sorted([*root.glob("*/native-content-state.json"), *root.glob("*/workflow-handoff-state.json")])
    for state_path in states:
        base = state_path.parent
        if base.is_symlink() or not base.resolve().is_relative_to(root.resolve()):
            raise PublicationHandoffError("asset handoff directory is unsafe")
        state = json.loads(editorial.read(state_path))
        if state.get("status") != "waiting_assets":
            continue
        manifest_path = base / "draft-manifest.json"
        if manifest_path.exists():
            _, manifest = editorial.load_manifest(manifest_path)
            if manifest["items"]:
                continue
        if state_path.name == "native-content-state.json":
            result = fetch_native(state["series_id"], state["issue_key"], root)
            if result.get("status") != "waiting_assets" or result.get("output_directory") != str(base):
                continue
        else:
            envelope_raw = editorial.read(editorial.local_path(base, "workflow-envelope.json"))
            artifact_raw = editorial.read(editorial.local_path(base, "workflow-artifact.json"))
            envelope = json.loads(envelope_raw)
            _validate_export({"envelope": envelope, "envelope_sha256": state["envelope_sha256"],
                              "artifact_b64": base64.b64encode(artifact_raw).decode("ascii")},
                             configured_handoff_schedule(state["series_id"]))
            _verify_existing_output(base, envelope, envelope_raw, artifact_raw)
        request = {"output_directory": str(base), "series_id": state["series_id"],
                   "issue_date": state["issue_date"], "issue_slot": state.get("issue_slot", "12:00"),
                   "artifact_sha256": state["artifact_sha256"]}
        return canonical_json({"publication_asset_request": request}).decode("utf-8")
    return "NO_NEW_DRAFT"


def native_content_binding(series_id: str, issue_key: str, *, writer_session: str | None = None):
    """Read the configured native author's terminal result; never trust author identity fields."""
    from backend.services.knowledge_publication_store import SERIES, publication_slot
    config = SERIES.get(series_id)
    if not config or not config.get("enabled", True):
        raise PublicationHandoffError("native publication series is unknown or disabled")
    profile, job_id = config.get("author_profile", "default"), config.get("author_job_id")
    if profile not in {"default", "story"} or not isinstance(job_id, str) or not SAFE_COMPONENT.fullmatch(job_id):
        raise PublicationHandoffError("native author profile or job binding is unavailable")
    day, separator, slot = issue_key.partition("T")
    occurrence = publication_slot(series_id, day, slot if separator else "12:00")
    if occurrence["issue_key"] != issue_key:
        raise PublicationHandoffError("native issue key is not canonical")
    home = Path.home() / ".hermes"
    db_path = home / "state.db" if profile == "default" else home / "profiles" / profile / "state.db"
    if not db_path.is_file() or any(part.is_symlink() for part in (db_path, *db_path.parents)):
        return None
    with sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        sessions = db.execute("SELECT * FROM sessions WHERE profile_name=? AND user_id IS NULL AND source='cron' AND ended_at IS NOT NULL AND end_reason='cron_complete' ORDER BY ended_at DESC", (profile,)).fetchall()
        for session in sessions:
            sid = session["id"]
            if not session["ended_at"]:
                continue
            if not sid.startswith(f"cron_{job_id}_") or (writer_session and f"hermes:{sid}" != writer_session):
                continue
            final = db.execute("SELECT * FROM messages WHERE session_id=? AND active=1 AND compacted=0 ORDER BY id DESC LIMIT 1", (sid,)).fetchone()
            if final is None or final["role"] != "assistant" or final["finish_reason"] != "stop" or final["tool_calls"]:
                continue
            try:
                value = json.loads(final["content"] or "")
            except (ValueError, TypeError):
                continue
            if not isinstance(value, dict) or set(value) != {"publication_content_result"}:
                continue
            result = value["publication_content_result"]
            if not isinstance(result, dict) or set(result) != {"series_id", "issue_date", "issue_slot", "artifact_file"}:
                continue
            if (result["series_id"], result["issue_date"], result["issue_slot"]) != (series_id, day, occurrence["issue_slot"]):
                continue
            if not isinstance(result["artifact_file"], str):
                raise PublicationHandoffError("native artifact file is invalid")
            first = db.execute("SELECT content FROM messages WHERE session_id=? AND role='user' AND active=1 AND compacted=0 ORDER BY id LIMIT 1", (sid,)).fetchone()
            if first is None:
                raise PublicationHandoffError("native content has no system occurrence request")
            from backend.services.publication_review_provenance import _request
            try:
                request = _request((first["content"] or "").replace("PUBLICATION_CONTENT_REQUEST", "PUBLICATION_REVIEW_REQUEST"))
            except (ValueError, TypeError) as exc:
                raise PublicationHandoffError("native content occurrence request is invalid") from exc
            expected_request = {"series_id": series_id, "issue_date": day, **occurrence, "author_job_id": job_id}
            if request != expected_request:
                raise PublicationHandoffError("native content result does not match system occurrence request")
            source = _native_artifact_path(result["artifact_file"])
            raw = editorial.read(source)
            content = validate_ai_toolkit_artifact(raw)
            binding = {"version": "publication-native-author-v1", "series_id": series_id,
                       "issue_date": day, **occurrence, "author_profile": profile,
                       "author_job_id": job_id, "writer_session": f"hermes:{sid}",
                       "artifact_file": str(source), "artifact_sha256": _digest(raw)}
            return binding, raw, content
    return None


def fetch_native(series_id: str, issue_key: str, output_root: Path) -> dict[str, Any]:
    root = Path(output_root).expanduser().absolute()
    if root != native_output_root().absolute() or any(part.is_symlink() for part in (root, *root.parents)):
        raise PublicationHandoffError("native output root must be the fixed publication root")
    found = native_content_binding(series_id, issue_key)
    if found is None:
        return {"status": "waiting_author", "available": False}
    binding, raw, content = found
    fields = publication_system_fields(content, series_id)
    from backend.services.knowledge_publication_store import SERIES
    from backend.services.publication_editorial import make_editorial_contract, validate_editorial
    contract = make_editorial_contract(content["body"], format=SERIES[series_id].get("format", "chapter"),
        writer_sessions=[binding["writer_session"]], revision=1, **fields)
    reasons = [reason for reason in validate_editorial(content["body"], contract) if reason.startswith("quality.")]
    if reasons:
        feedback_dir = root / f"{series_id}-{issue_key.replace(':', '')}"
        if feedback_dir.is_symlink():
            raise PublicationHandoffError("native feedback directory is unsafe")
        feedback_dir.mkdir(parents=True, exist_ok=True)
        feedback_path = feedback_dir / "native-content-feedback.json"
        previous = json.loads(editorial.read(feedback_path)) if feedback_path.exists() else {}
        history = previous.get("submissions", [])
        if not isinstance(history, list) or any(not isinstance(item, dict) for item in history):
            raise PublicationHandoffError("native revision feedback is invalid")
        if binding["artifact_sha256"] not in {item.get("artifact_sha256") for item in history}:
            if len(history) >= 3:
                raise PublicationHandoffError("native content revision budget exhausted")
            history.append({"writer_session": binding["writer_session"], "artifact_sha256": binding["artifact_sha256"], "reasons": reasons})
        feedback = {"source": "deterministic_preflight", "series_id": series_id, "issue_key": issue_key,
                    "status": "blocked" if len(history) >= 3 else "waiting_author", "submissions": history,
                    "reasons": reasons, "revision_count": len(history), "max_submissions": 3,
                    "instruction": "请按确定性质量门禁补足真实正文及证据；禁止重复段落凑字数。保持内容协议，提交新的原生最终回执。"}
        editorial.save(feedback_path, feedback)
        if len(history) >= 3:
            raise PublicationHandoffError("native content revision budget exhausted: " + ",".join(reasons))
        return {"status": "waiting_author", "available": False, "reason": "deterministic_preflight",
                "reasons": reasons, "feedback_file": str(feedback_path), "revision_count": len(history)}
    target = root / f"{series_id}-native-{binding['artifact_sha256'][:24]}-{issue_key.replace(':', '')}"
    if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
        raise PublicationHandoffError("native content directory is unsafe")
    if (target / "draft-manifest.json").is_file():
        manifest = json.loads(editorial.read(target / "draft-manifest.json"))
        if any(item.get("status") == "rejected" for item in manifest.get("items", [])):
            return {"status": "waiting_author", "available": False, "reason": "native_content_rejected"}
    state = {**binding, "status": "waiting_assets"}
    expected = {"native-author.json": canonical_json(binding), "native-content-state.json": canonical_json(state),
                "native-content.json": raw, "body.md": content["body"].encode("utf-8")}
    groups = {"source_files": [], "execution_files": []}
    for field, docs, prefix in (("source_files", content["source_documents"], "source"),
                                ("execution_files", content["execution_documents"], "execution")):
        for index, document in enumerate(docs, 1):
            name = f"inputs/{prefix}-{index:02d}.txt"
            expected[name] = document["content"].encode("utf-8")
            groups[field].append({"kind": document["kind"], "path": name})
    groups["source_files"].extend([{"kind": "native_author_binding", "path": "native-author.json"},
                                   {"kind": "native_author_content", "path": "native-content.json"}])
    expected["content-submission.json"] = canonical_json({"title": content["title"], "summary": content["summary"], **fields, **groups})
    root.mkdir(parents=True, exist_ok=True)
    if target.exists():
        for name, data in expected.items():
            path = target / name
            if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
                raise PublicationHandoffError("existing native content output conflicts")
    else:
        temporary = Path(tempfile.mkdtemp(prefix=".native-content-", dir=root))
        try:
            (temporary / "inputs").mkdir()
            for name, data in expected.items():
                _write(temporary / name, data)
            os.rename(temporary, target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return {"status": "waiting_assets", "output_directory": str(target), **binding}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-file")
    parser.add_argument("--known-hosts-file")
    commands = parser.add_subparsers(dest="action", required=True)
    author = commands.add_parser("author-input")
    author.add_argument("--job-id", required=True)
    author.add_argument("--profile", required=True, choices=("default", "story"))
    commands.add_parser("assets-input")
    native = commands.add_parser("fetch-native")
    native.add_argument("--series-id", required=True)
    native.add_argument("--issue-key", required=True)
    native.add_argument("--output-root", required=True, type=Path)
    fetch = commands.add_parser("fetch")
    fetch.add_argument("--series-id", default="ai-toolkit")
    fetch.add_argument("--issue-key")
    fetch.add_argument("--output-root", required=True, type=Path)
    acknowledge = commands.add_parser("acknowledge")
    acknowledge.add_argument("--manifest", required=True, type=Path)
    revision = commands.add_parser("request-revision")
    revision.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "assets-input":
            print(assets_input())
            return 0
        if args.action == "fetch-native":
            print(json.dumps(fetch_native(args.series_id, args.issue_key, args.output_root), ensure_ascii=False, sort_keys=True))
            return 0
        identity, known_hosts = transport._trust(args)
        remote = editorial.Remote(identity, known_hosts)
        if args.action == "author-input":
            print(author_input(args.job_id, args.profile, remote))
            return 0
        if args.action == "fetch":
            schedule_id = configured_handoff_schedule(args.series_id)
            result = materialize_export(
                remote.operator("export-workflow-handoff", "--series-id", args.series_id,
                                *(("--issue-key", args.issue_key) if args.issue_key else ())), args.output_root,
                expected_schedule_id=schedule_id, expected_series_id=args.series_id,
                expected_issue_key=args.issue_key,
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
