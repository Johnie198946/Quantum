#!/usr/bin/env python3
"""Explicit file-only relay for the existing writer/reviewer/no-agent issuer.

No model calls, scheduler, session writes, SCP, or release operation. Manifests
must be named draft-manifest.json or *.manifest.json for root discovery. Initial items use `prepared`;
all input hashes are required (bundle_sha256 is added when initially absent).
Files are limited to 2 MiB each (single authenticated stdin stream), 64 evidence files/item
and 64 items/manifest. The server independently enforces its body size policy.
Transport and signing credentials are operator-owned, never manifest fields.

``start`` accepts a directory containing ``body.md``, five role-named images,
declared source/execution files, and ``content-submission.json`` with exactly:
title, summary, editorial_brief, learning_objectives, source_files and
execution_files. Publication controls are CLI/operator inputs, not author JSON.
"""
from __future__ import annotations

import argparse
import base64
from datetime import date, datetime
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sqlite3
import sys
import uuid
from collections.abc import Mapping

from PIL import Image, UnidentifiedImageError

try:
    from scripts import publication_release_remote as transport
except ImportError:
    import publication_release_remote as transport

VERSION = "editorial-workflow-v2"
LIMIT = 2 * 1024 * 1024

HASH = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = {"bundle_file", "bundle_sha256", "body_file", "body_sha256", "source_files",
          "rights_files", "execution_files", "review_file", "proof_file", "status",
          "batch", "quality_contract", "receipt", "error", "shelf_cover_file",
          "shelf_cover_sha256", "reader_cover_file", "reader_cover_sha256",
          "illustration_01_file", "illustration_01_sha256", "illustration_02_file",
          "illustration_02_sha256", "illustration_03_file", "illustration_03_sha256", "asset_files"}
STATES = {"prepared", "await_review", "staged", "rejected", "blocked"}
GROUPS = {"source_files": "--source-file", "rights_files": "--rights-file", "execution_files": "--execution-file"}
MEDIA_ROLES = ("shelf_cover", "reader_cover", "illustration_01", "illustration_02", "illustration_03")
MEDIA_CONTRACT = {
    "shelf_cover": ("publication_shelf_cover", 1440, 2560),
    "reader_cover": ("publication_reader_cover", 2560, 1440),
    "illustration_01": ("publication_illustration", 1600, 900),
    "illustration_02": ("publication_illustration", 1600, 900),
    "illustration_03": ("publication_illustration", 1600, 900),
}
from backend.services.knowledge_publication_store import SERIES, publication_slot

DAILY_SERIES = {key for key, value in SERIES.items() if value["kind"] == "daily"}
CONTENT_SUBMISSION_FIELDS = {"title", "summary", "source_files", "execution_files"}
SUBMISSION_FIELDS = {
    "title", "summary", "editorial_brief", "learning_objectives",
    "source_files", "execution_files",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    raise ValueError("unsupported publication media extension")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def local_path(base, value, *, output=False):
    if not isinstance(value, str) or not value:
        raise ValueError("explicit local path required")
    path = Path(value).expanduser()
    path = path if path.is_absolute() else base / path
    if ".." in path.parts or not path.is_relative_to(base):
        raise ValueError("file escapes manifest directory")
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError("symlink forbidden")
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("regular unlinked-alias-free file required")
        if info.st_size > LIMIT:
            raise ValueError("file exceeds 2 MiB limit")
    elif not output or not path.parent.is_dir():
        raise ValueError("file missing")
    return path


def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("regular file required")
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("file exceeds 2 MiB limit")
    return raw


def save(path, value):
    raw = encoded(value)
    if len(raw) > LIMIT:
        raise ValueError("JSON exceeds 2 MiB limit")
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_bytes(path: Path, raw: bytes) -> None:
    if len(raw) > LIMIT:
        raise ValueError("file exceeds 2 MiB limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != raw:
            raise ValueError("deterministic output conflict")
        return
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _submission_entry(base: Path, entry, *, group: str) -> tuple[dict, Path]:
    if (not isinstance(entry, dict) or set(entry) != {"kind", "path"}
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", entry.get("kind", ""))):
        raise ValueError(f"invalid {group} entry")
    path = local_path(base, entry["path"])
    return {"kind": entry["kind"], "path": entry["path"], "sha256": sha(read(path))}, path


def _validate_media(path: Path, role: str) -> None:
    expected_type = media_type(path)
    _, width, height = MEDIA_CONTRACT[role]
    try:
        with Image.open(path) as image:
            actual_type = Image.MIME.get(image.format)
            actual_size = image.size
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"invalid {role} image") from exc
    if actual_type != expected_type or actual_size != (width, height):
        raise ValueError(f"invalid {role} image format or dimensions")


def _initial_item(base: Path, body_raw: bytes, source_files: list[dict],
                  execution_files: list[dict]) -> dict:
    item = {
        "bundle_file": "candidate-bundle.json", "bundle_sha256": None,
        "body_file": "body.md", "body_sha256": sha(body_raw),
        "source_files": source_files, "rights_files": [],
        "execution_files": execution_files,
        "review_file": "editorial-review.json", "proof_file": "editorial-proof.json",
        "status": "prepared",
    }
    for role in MEDIA_ROLES:
        matches = [base / f"{role}{suffix}" for suffix in (".jpg", ".jpeg", ".png")
                   if (base / f"{role}{suffix}").exists()]
        if len(matches) != 1:
            raise ValueError(f"exactly one {role} image is required")
        path = local_path(base, matches[0].name)
        _validate_media(path, role)
        item[f"{role}_file"] = path.name
        item[f"{role}_sha256"] = sha(read(path))
    return item


def _same_initial_item(existing: dict, expected: dict) -> bool:
    fields = {
        "body_file", "body_sha256", "source_files", "rights_files", "execution_files",
        "review_file", "proof_file", *(f"{role}_{suffix}" for role in MEDIA_ROLES
                                        for suffix in ("file", "sha256")),
    }
    return all(existing.get(field) == expected.get(field) for field in fields)


def build_initial(submission_file: Path, body_dir: Path, *, series_id: str,
                  issue_date: str, format: str, owner_policy_id: str,
                  writer_session: str | None = None, issue_slot: str | None = None) -> Path:
    """Build one initial draft from content-only author files.

    Publication identity, dates, format and policy are operator inputs. The
    submission itself cannot set workflow, provenance, hash, rights, review,
    publication, stage or execution-claim fields.
    """
    base = Path(body_dir).expanduser().absolute()
    if not base.is_dir() or base.is_symlink():
        raise ValueError("body directory must be a real directory")
    submission_path = Path(submission_file).expanduser().absolute()
    if submission_path.name != "content-submission.json" or submission_path.parent != base:
        raise ValueError("content-submission.json must be directly inside body directory")
    submission = json.loads(read(local_path(base, str(submission_path))))
    if not isinstance(submission, dict) or set(submission) not in (SUBMISSION_FIELDS, CONTENT_SUBMISSION_FIELDS):
        raise ValueError("content submission has missing, unknown or forbidden fields")
    if series_id not in DAILY_SERIES or not SERIES[series_id].get("enabled", True):
        raise ValueError("initial builder requires an enabled daily editorial series")
    try:
        parsed_issue_date = date.fromisoformat(issue_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("issue date must be YYYY-MM-DD") from exc
    if parsed_issue_date.isoformat() != issue_date:
        raise ValueError("issue date must be YYYY-MM-DD")
    if format not in {"book", "chapter"}:
        raise ValueError("format must be book or chapter")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", owner_policy_id):
        raise ValueError("invalid owner policy id")
    for field in ("title", "summary"):
        if not isinstance(submission[field], str) or not submission[field].strip():
            raise ValueError(f"nonempty {field} required")
    occurrence = publication_slot(series_id, issue_date, issue_slot)
    if set(submission) == CONTENT_SUBMISSION_FIELDS:
        from backend.services.publication_workflow_handoff import publication_system_fields
        documents = []
        for entry in submission["source_files"]:
            normalized, source_path = _submission_entry(base, entry, group="source_files")
            documents.append({"kind": normalized["kind"], "content": read(source_path).decode("utf-8")})
        submission.update(publication_system_fields(
            {"title": submission["title"], "source_documents": documents}, series_id=series_id))
    # A Workflow author identity must come from the verified content envelope,
    # never from the later asset-generation session.
    envelope_path = base / "workflow-envelope.json"
    workflow_writer = None
    workflow_content = None
    if envelope_path.exists():
        envelope = json.loads(read(local_path(base, "workflow-envelope.json")))
        if envelope.get("version") == "publication-workflow-handoff-v2":
            state = json.loads(read(local_path(base, "workflow-handoff-state.json")))
            if (state.get("envelope_sha256") != sha(read(envelope_path))
                    or envelope.get("series_id") != series_id
                    or envelope.get("issue_date") != issue_date
                    or envelope.get("issue_key") != occurrence["issue_key"]
                    or envelope.get("release_at") != occurrence["release_at"]
                    or envelope.get("artifact_sha256") != sha(read(local_path(base, "workflow-artifact.json")))):
                raise ValueError("workflow author binding conflicts")
            if not isinstance(envelope.get("writer_session"), str) or not envelope["writer_session"].strip():
                raise ValueError("workflow author session missing")
            from backend.services.publication_workflow_handoff import validate_publication_artifact
            workflow_content = validate_publication_artifact(read(local_path(base, "workflow-artifact.json")))
            workflow_writer = _writer_session(envelope["writer_session"])
            if writer_session is not None and _writer_session(writer_session) != workflow_writer:
                raise ValueError("workflow author cannot be replaced by asset session")
    native_path = base / "native-author.json"
    if native_path.exists():
        if workflow_writer is not None:
            raise ValueError("publication has conflicting author authorities")
        try:
            from scripts.publication_workflow_handoff import native_content_binding
        except ImportError:
            from publication_workflow_handoff import native_content_binding
        native_binding = json.loads(read(local_path(base, "native-author.json")))
        found = native_content_binding(series_id, occurrence["issue_key"], writer_session=native_binding.get("writer_session"))
        if found is None or found[0] != native_binding or read(local_path(base, "native-content.json")) != found[1]:
            raise ValueError("native author binding conflicts with terminal session")
        workflow_content = found[2]
        from backend.services.publication_workflow_handoff import publication_system_fields
        expected_fields = publication_system_fields(workflow_content, series_id)
        if any(submission.get(key) != value for key, value in expected_fields.items()):
            raise ValueError("native content system fields conflict")
        native_receipts = [{"kind": "native_author_binding", "path": "native-author.json"},
                           {"kind": "native_author_content", "path": "native-content.json"}]
        if submission["source_files"][-2:] != native_receipts:
            raise ValueError("native author source receipts missing")
        for field, content_key in (("source_files", "source_documents"), ("execution_files", "execution_documents")):
            documents = []
            entries = submission[field][:-2] if field == "source_files" else submission[field]
            for entry in entries:
                normalized, source_path = _submission_entry(base, entry, group=field)
                documents.append({"kind": normalized["kind"], "content": read(source_path).decode("utf-8")})
            if documents != workflow_content[content_key]:
                raise ValueError("native content source evidence conflicts")
        workflow_writer = native_binding["writer_session"]
        if writer_session is not None and _writer_session(writer_session) != workflow_writer:
            raise ValueError("native author cannot be replaced by asset session")
    objectives = submission["learning_objectives"]
    if (not isinstance(objectives, list) or not objectives
            or any(not isinstance(value, str) or len(value.strip()) < 10 for value in objectives)):
        raise ValueError("invalid learning objectives")
    brief = submission["editorial_brief"]
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.services.publication_editorial import validate_editorial_brief
    if validate_editorial_brief(brief):
        raise ValueError("invalid editorial brief")
    body_path = local_path(base, "body.md")
    body_raw = read(body_path)
    try:
        body = body_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("body must be UTF-8") from exc
    if workflow_content is not None and (body != workflow_content["body"]
            or any(submission[field] != workflow_content[field] for field in ("title", "summary"))):
        raise ValueError("publication content conflicts with workflow artifact")
    research_gaps = []
    expected_writers = [workflow_writer] if workflow_writer is not None else None
    if native_path.exists():
        prior_revision = _native_rejected_revision(base, series_id, occurrence["issue_key"], sha(body_raw), brief)
        if prior_revision is not None:
            prior_contract, research_gaps = prior_revision
            expected_writers = list(dict.fromkeys([*prior_contract["writer_sessions"], workflow_writer]))
    groups = {}
    input_paths = {submission_path, body_path}
    for field in ("source_files", "execution_files"):
        entries = submission[field]
        if not isinstance(entries, list) or len(entries) > 64 or (field == "source_files" and not entries):
            raise ValueError(f"invalid {field}")
        groups[field] = []
        for entry in entries:
            normalized, path = _submission_entry(base, entry, group=field)
            if path in input_paths:
                raise ValueError("submission input paths must be unique")
            input_paths.add(path)
            groups[field].append(normalized)
    image_manifest = base / "image-manifest.json"
    if image_manifest.exists() or image_manifest.is_symlink():
        entry, path = _submission_entry(base, {"kind": "publication_image_generation",
                                             "path": "image-manifest.json"}, group="source_files")
        if path in input_paths:
            raise ValueError("image generation evidence must be separate from author inputs")
        input_paths.add(path)
        groups["source_files"].append(entry)
    item = _initial_item(base, body_raw, groups["source_files"], groups["execution_files"])
    media_paths = {local_path(base, item[f"{role}_file"]) for role in MEDIA_ROLES}
    if input_paths & media_paths or len(media_paths) != len(MEDIA_ROLES):
        raise ValueError("publication media paths must be unique")

    digest = sha(body_raw)
    rights = {
        "policy_id": owner_policy_id, "status": "operator_attested",
        "content_hashes": [digest], "body_sha256": digest,
        "bound_files": ["body.md"], "attested_by": "local_owner_policy",
        "hard_boundaries": [
            "private source text is not publication-authorized by default",
            "third-party material requires evidence and limited quotation",
            "author cannot review, stage or publish the submission",
        ],
        "note": "This attestation binds the submitted body; it is not editorial approval.",
    }
    rights_path = base / "rights-policy.json"
    write_bytes(rights_path, encoded(rights))
    item["rights_files"] = [{"kind": "owner_attestation", "path": rights_path.name,
                             "sha256": sha(read(rights_path))}]
    candidate_path = base / "candidate-bundle.json"
    manifest_path = base / "draft-manifest.json"
    existing = None
    if manifest_path.exists():
        _, existing = load_manifest(manifest_path)
        if len(existing["items"]) != 1 or not _same_initial_item(existing["items"][0], item):
            raise ValueError("existing initial manifest conflicts with submission")
        if not candidate_path.exists():
            raise ValueError("existing initial candidate is missing")
        prior_candidate = json.loads(read(candidate_path))
        writer_sessions = prior_candidate.get("quality_contract", {}).get("writer_sessions")
        if (not isinstance(writer_sessions, list) or not writer_sessions
                or any(not isinstance(value, str) or not value.startswith("hermes:")
                       for value in writer_sessions)):
            raise ValueError("existing initial writer session is invalid")
        assigned = existing["items"][0].get("quality_contract")
        if assigned is not None and assigned.get("writer_sessions") != writer_sessions:
            raise ValueError("existing initial writer session conflicts with server contract")
    else:
        writer_sessions = expected_writers or [_writer_session(writer_session)]
    if expected_writers is not None and writer_sessions != expected_writers:
        raise ValueError("existing manifest conflicts with workflow author")
    references = [{"title": f"Evidence {index}", "url": url}
                  for index, url in enumerate(brief["evidence_urls"], 1)]
    bundle = {
        "series_id": series_id, "source_publication_id": "", "issue_date": issue_date,
        "title": submission["title"], "summary": submission["summary"], "body": body,
        "author": "Quantumn", "institution": "Quantumn",
        "authored_by": "quantumn_editorial", "content_kind": "commentary",
        "rights_scope": "local_owner_original", "rights_reference": owner_policy_id,
        "rights_valid_until": None, "rights_perpetual": True, "rights_evidence": [],
        "rights_evidence_status": "operator_attested", "owner_policy_id": owner_policy_id,
        "release_at": occurrence["release_at"], "state": "draft", "is_test": True,
        "source_snapshot_hash": "0" * 64, "source_receipts": [], "body_hash": digest,
        "body_receipt": {"artifact_id": f"receipt-publication_body-{digest}",
                         "sha256": digest, "kind": "publication_body"},
        "references": references, "wiki_references": [], "assets": [], "completeness": "full",
        "review": {"content_hash": "", "decision": "pending", "reviewed_by": "",
                   "reviewed_at": "", "receipt": None},
        "execution_claim": ("success" if SERIES[series_id].get("execution_enabled", False)
                            and groups["execution_files"] else "not_run"),
        "execution_evidence": [], "warnings": [],
        "quality_contract": {"format": format, "writer_sessions": writer_sessions,
                             "learning_objectives": objectives, "editorial_brief": brief,
                             "research_gaps": research_gaps},
    }
    if issue_slot is not None:
        bundle["issue_slot"] = occurrence["issue_slot"]
    write_bytes(candidate_path, encoded(bundle))
    item["bundle_sha256"] = sha(read(candidate_path))
    if existing is not None:
        return manifest_path
    write_bytes(manifest_path, encoded({"version": VERSION, "items": [item]}))
    load_manifest(manifest_path)
    return manifest_path


def load_manifest(path):
    path = Path(path).expanduser().absolute()
    if path.name != "draft-manifest.json" and not path.name.endswith(".manifest.json"):
        raise ValueError("manifest must be draft-manifest.json or *.manifest.json")
    local_path(path.parent, str(path))
    value = json.loads(read(path))
    if not isinstance(value, dict) or set(value) != {"version", "items"} or value["version"] != VERSION:
        raise ValueError("explicit editorial-workflow-v2 manifest required")
    if not isinstance(value["items"], list) or not 1 <= len(value["items"]) <= 64:
        raise ValueError("invalid manifest items")
    paths = set()
    outputs = set()
    for item in value["items"]:
        if not isinstance(item, dict) or set(item) - FIELDS or item.get("status") not in STATES:
            raise ValueError("unknown manifest fields or invalid status")
        inputs = [(item.get("bundle_file"), item.get("bundle_sha256")),
                  (item.get("body_file"), item.get("body_sha256"))]
        for role in MEDIA_ROLES:
            name, digest = item.get(f"{role}_file"), item.get(f"{role}_sha256")
            if (name is None) != (digest is None):
                raise ValueError(f"{role} file and hash must be provided together")
            if name is not None:
                inputs.append((name, digest))
        for group in GROUPS:
            entries = item.get(group)
            if not isinstance(entries, list) or len(entries) > 64:
                raise ValueError("explicit bounded evidence lists required")
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) != {"kind", "path", "sha256"} or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", entry.get("kind", "")):
                    raise ValueError("invalid evidence entry")
                inputs.append((entry["path"], entry["sha256"]))
        assets = item.setdefault("asset_files", [])
        if not isinstance(assets, list) or len(assets) > 50:
            raise ValueError("explicit bounded asset list required")
        if len({entry.get("url") for entry in assets if isinstance(entry, dict)}) != len(assets):
            raise ValueError("duplicate inline asset url")
        for entry in assets:
            if (not isinstance(entry, dict) or set(entry) != {"url", "path", "sha256"}
                    or not isinstance(entry.get("url"), str)):
                raise ValueError("invalid inline asset entry")
            inputs.append((entry["path"], entry["sha256"]))
        for index, (name, digest) in enumerate(inputs):
            file = local_path(path.parent, name)
            if index == 0 and digest is None and item["status"] == "prepared":
                digest = item["bundle_sha256"] = sha(read(file))
            if not isinstance(digest, str) or not HASH.fullmatch(digest) or sha(read(file)) != digest:
                raise ValueError("input hash mismatch or missing hash")
            if file == path or file in paths or file in outputs:
                raise ValueError("input overlaps manifest, another input or output")
            paths.add(file)
        for field in ("review_file", "proof_file"):
            output = local_path(path.parent, item.get(field), output=True)
            if output == path or output in paths:
                raise ValueError("review/proof output overlaps input or other output")
            if item["status"] == "prepared" and output.exists():
                raise ValueError("review/proof must be fresh output paths")
            paths.add(output)
            outputs.add(output)
        if item.get("batch") and not re.fullmatch(r"[0-9a-f]{32}", item["batch"]):
            raise ValueError("invalid intake batch")
        bundle = json.loads(read(local_path(path.parent, item["bundle_file"])))
        if bundle.get("body_hash") != item["body_sha256"]:
            raise ValueError("bundle body hash mismatch")
        if bundle.get("series_id") in DAILY_SERIES and any(item.get(f"{role}_file") is None for role in MEDIA_ROLES):
            raise ValueError("daily editorial manifest requires all five publication media files and hashes")
        if item["status"] != "prepared" and bundle.get("quality_contract") != item.get("quality_contract"):
            raise ValueError("immutable contract mismatch")
    return path, value


def _writer_session(value: str | None = None) -> str:
    session = (value or os.environ.get("HERMES_SESSION_ID") or "").strip()
    if session and not session.startswith("hermes:"):
        session = "hermes:" + session
    if not session.startswith("hermes:") or len(session) <= len("hermes:"):
        raise ValueError("current Hermes writer session unavailable")
    return session


def _copy_revision_input(
    source_base: Path, target_base: Path, relative: str, *, namespace: str
) -> str:
    source = local_path(source_base, relative)
    suffix = source.suffix.lower()
    target = target_base / "inputs" / (namespace + "-" + sha(read(source)) + suffix)
    write_bytes(target, read(source))
    return str(target.relative_to(target_base))


def _resolved_revision_gaps(prior_contract: dict, review_gaps: list, brief: dict) -> list:
    gaps = {
        gap["id"]: dict(gap)
        for gap in prior_contract.get("research_gaps", [])
        if isinstance(gap, dict)
        and isinstance(gap.get("id"), str)
        and gap.get("id") != "review.rejected"
    }
    for gap in review_gaps:
        if not isinstance(gap, dict) or not isinstance(gap.get("id"), str) or not isinstance(gap.get("question"), str):
            raise ValueError("invalid rejected review gap")
        acceptance = str(gap.get("acceptance_criterion") or gap.get("required_evidence") or gap["question"]).strip()
        gaps[gap["id"]] = {
            "id": gap["id"],
            "question": gap["question"],
            "state": "resolved",
            "resolution": "Revised manuscript submitted for independent verification against: " + acceptance,
            "source_urls": list(brief["evidence_urls"]),
        }
    if any(gap.get("state") != "resolved" for gap in gaps.values()):
        raise ValueError("rejected review did not describe every inherited open gap")
    return list(gaps.values())


def _native_rejected_revision(base: Path, series_id: str, issue_key: str, body_hash: str, brief: dict):
    """Reuse the latest genuine rejected attempt for the same native occurrence."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from backend.services.knowledge_publication_store import PublicationStore
    expected_issue_id = PublicationStore.ids(series_id, issue_key, 1)[1]
    candidates = []
    for path in manifests(base.parent):
        if path.parent == base:
            continue
        raw = json.loads(read(path))
        matching = []
        for index, item in enumerate(raw.get("items", [])):
            if not isinstance(item, dict) or item.get("status") != "rejected":
                continue
            contract = item.get("quality_contract")
            # A known same-occurrence contract must reach full validation even
            # when its bundle is missing, corrupt, or relabelled.
            if isinstance(contract, dict) and contract.get("issue_id") == expected_issue_id:
                matching.append(index)
                continue
            prior = json.loads(read(local_path(path.parent, item["bundle_file"])))
            if prior.get("series_id") != series_id or prior.get("issue_date") != issue_key.split("T", 1)[0]:
                continue
            slot = prior.get("issue_slot") or datetime.fromisoformat(prior["release_at"]).astimezone(ZoneInfo("Asia/Shanghai")).strftime("%H:%M")
            if publication_slot(series_id, prior["issue_date"], slot)["issue_key"] == issue_key:
                matching.append(index)
        if not matching:
            continue
        _, manifest = load_manifest(path)
        for index in matching:
            item = manifest["items"][index]
            contract = item.get("quality_contract")
            if (not isinstance(contract, dict) or type(contract.get("revision")) is not int
                    or contract.get("issue_id") != expected_issue_id):
                raise ValueError("rejected manifest contract unavailable or occurrence mismatch")
            candidates.append((contract["revision"], path, item, contract))
    if not candidates:
        return None
    _, path, item, contract = max(candidates, key=lambda value: value[0])
    if body_hash == item["body_sha256"]:
        raise ValueError("revised body must materially change")
    review = json.loads(read(local_path(path.parent, item["review_file"])))
    if (review.get("decision") != "rejected" or review.get("attempt_id") not in {None, contract.get("attempt_id")}
            or review.get("editorial_target_hash") != contract.get("target_hash")
            or review.get("content_hash") != item["body_sha256"]):
        raise ValueError("rejected review does not bind prior contract")
    gaps = _resolved_revision_gaps(contract, review.get("research_gaps", []), brief)
    return contract, gaps


def build_revision(prior_manifest: Path, body_file: Path, *, writer_session: str | None = None) -> Path:
    """Package one rejected manuscript revision from content-only author output.

    The author supplies revised body bytes. Identity, revision, hashes, rights
    rebinding, immutable evidence/media reuse and fresh review outputs are
    deterministic platform responsibilities. Server-assigned fields remain
    absent until ``prepare`` returns the authoritative contract.
    """
    prior_manifest, manifest = load_manifest(prior_manifest)
    if len(manifest["items"]) != 1 or manifest["items"][0]["status"] != "rejected":
        raise ValueError("revision requires exactly one rejected manifest item")
    item = manifest["items"][0]
    prior_base = prior_manifest.parent
    prior_contract = item.get("quality_contract")
    if not isinstance(prior_contract, dict) or not isinstance(prior_contract.get("revision"), int):
        raise ValueError("rejected manifest contract unavailable")
    review = json.loads(read(local_path(prior_base, item["review_file"])))
    if (review.get("decision") != "rejected"
            or review.get("attempt_id") not in {None, prior_contract.get("attempt_id")}
            or review.get("editorial_target_hash") != prior_contract.get("target_hash")):
        raise ValueError("rejected review does not bind prior contract")
    review_gaps = review.get("research_gaps", [])
    visual_text = json.dumps(review_gaps, ensure_ascii=False).lower()
    if any(term in visual_text for term in ("封面", "插图", "配图", "视觉", "image asset", "visual asset")):
        raise ValueError("visual revision requires replacement media, not content-only reuse")
    body_source = Path(body_file).expanduser().absolute()
    body_raw = read(body_source)
    body = body_raw.decode("utf-8")
    body_hash = sha(body_raw)
    if body_hash == item["body_sha256"]:
        raise ValueError("revised body must materially change")
    revision = prior_contract["revision"] + 1
    target_base = prior_base / f"revision-{revision}-{body_hash[:12]}"
    if target_base.is_symlink() or not target_base.resolve().is_relative_to(prior_base.resolve()):
        raise ValueError("revision directory escapes prior manifest")
    target_base.mkdir(mode=0o700, parents=False, exist_ok=True)
    write_bytes(target_base / "body.md", body_raw)

    session = _writer_session(writer_session)
    writers = list(dict.fromkeys([*prior_contract.get("writer_sessions", []), session]))
    brief = prior_contract.get("editorial_brief")
    if not isinstance(brief, dict) or not isinstance(brief.get("evidence_urls"), list) or not brief["evidence_urls"]:
        raise ValueError("revision source URLs unavailable")
    resolved_gaps = _resolved_revision_gaps(prior_contract, review_gaps, brief)
    draft = {key: prior_contract[key] for key in (
        "format", "learning_objectives", "editorial_brief",
    )}
    draft.update(writer_sessions=writers, research_gaps=resolved_gaps)

    prior_bundle = json.loads(read(local_path(prior_base, item["bundle_file"])))
    bundle = dict(prior_bundle)
    bundle.update(
        body=body,
        body_hash=body_hash,
        body_receipt={"artifact_id": f"receipt-publication_body-{body_hash}", "sha256": body_hash,
                      "kind": "publication_body"},
        quality_contract=draft,
        review={"content_hash": "", "decision": "pending", "reviewed_by": "", "reviewed_at": "", "receipt": None},
        state="draft",
        assets=[], source_receipts=[], rights_evidence=[], execution_evidence=[],
        source_snapshot_hash="0" * 64,
    )
    title = next((line[3:].strip() for line in body.splitlines() if line.startswith("## ") and line[3:].strip()), None)
    if title:
        bundle["title"] = title
    bundle.pop("editorial_proof_file", None)
    bundle.pop("editorial_proof_sha256", None)

    new_item = {
        "bundle_file": "candidate-bundle.json", "bundle_sha256": None,
        "body_file": "body.md", "body_sha256": body_hash,
        "source_files": [], "rights_files": [], "execution_files": [],
        "review_file": "editorial-review.json", "proof_file": "editorial-proof.json",
        "status": "prepared",
    }
    for group in GROUPS:
        for index, entry in enumerate(item[group]):
            copied = _copy_revision_input(
                prior_base, target_base, entry["path"], namespace=f"{group}-{index}"
            )
            new_entry = {"kind": entry["kind"], "path": copied, "sha256": sha(read(target_base / copied))}
            if group == "rights_files" and entry["kind"] == "owner_attestation":
                attestation = json.loads(read(target_base / copied))
                if attestation.get("attested_by") != "local_owner_policy":
                    raise ValueError("owner attestation cannot be deterministically rebound")
                attestation.update(body_sha256=body_hash, content_hashes=[body_hash], bound_files=["body.md"])
                rebound = target_base / "inputs" / ("owner-attestation-" + body_hash + ".json")
                save(rebound, attestation)
                new_entry.update(path=str(rebound.relative_to(target_base)), sha256=sha(read(rebound)))
            new_item[group].append(new_entry)
    for role in MEDIA_ROLES:
        copied = _copy_revision_input(
            prior_base, target_base, item[f"{role}_file"], namespace=role
        )
        new_item[f"{role}_file"] = copied
        new_item[f"{role}_sha256"] = sha(read(target_base / copied))
    save(target_base / "candidate-bundle.json", bundle)
    new_item["bundle_sha256"] = sha(read(target_base / "candidate-bundle.json"))
    output = target_base / "draft-manifest.json"
    save(output, {"version": VERSION, "items": [new_item]})
    load_manifest(output)
    return output


# Uploaded bytes are immutable and confined to a unique private intake batch.
# Existing matching content is an idempotent retry, conflicting bytes fail closed.
UPLOAD = '''import os,sys,base64,hashlib,json,stat,tempfile
from pathlib import Path
batch,digest,ext=sys.argv[1:]
def valid(s,n):
 return isinstance(s,str) and len(s)==n and all(c in '0123456789abcdef' for c in s)
assert valid(batch,32) and valid(digest,64)
assert ext in ('.json','.md','.bin')
base=Path('/app/data/runtime/publication-intake')
for p in [*reversed(base.parents),base,base/batch]:
 if not p.exists(): p.mkdir(mode=0o700)
 assert not p.is_symlink() and p.is_dir()
def read(p,limit):
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno())
  assert stat.S_ISREG(s.st_mode) and s.st_nlink==1,'intake conflict'
  raw=f.read(limit+1)
 assert len(raw)<=limit
 return raw
payload=sys.stdin.buffer.read(2796205)
assert len(payload)<=2796204
raw=base64.b64decode(payload,validate=True)
assert len(raw)<=2097152 and hashlib.sha256(raw).hexdigest()==digest
p=base/batch/(digest+ext)
fd,tmp=tempfile.mkstemp(prefix='.upload-',dir=base/batch)
try:
 with os.fdopen(fd,'wb') as f:
  f.write(raw);f.flush();os.fsync(f.fileno())
 try: os.link(tmp,p,follow_symlinks=False)
 except FileExistsError: pass
finally:
 os.unlink(tmp)
assert read(p,2097152)==raw,'intake conflict'
print(json.dumps({'ok':True,'result':{'path':str(p),'sha256':digest}}))
'''


class Remote:
    def __init__(self, identity, known_hosts):
        self.identity, self.known_hosts = identity, known_hosts

    def call(self, words, *, input_text=None):
        result = transport._ssh(
            self.identity,
            self.known_hosts,
            shlex.join(words),
            input_text=input_text,
        )
        if result.returncode:
            raise ValueError(f"remote command failed (exit {result.returncode})")
        ok, value = transport._json(result.stdout, "editorial")
        if ok is not True:
            raise ValueError("remote editorial admission failed")
        return value

    def operator(self, *args):
        return self.call([*transport.OPERATOR, *map(str, args)])

    def upload(self, batch, raw, ext):
        digest = sha(raw)
        if len(raw) > LIMIT:
            raise ValueError("upload exceeds limit")
        payload = base64.b64encode(raw).decode("ascii")
        value = self.call(
            [*transport.OPERATOR[:12], "-c", UPLOAD, batch, digest, ext],
            input_text=payload,
        )
        expected = f"/app/data/runtime/publication-intake/{batch}/{digest}{ext}"
        if value != {"path": expected, "sha256": digest}:
            raise ValueError("upload readback mismatch")
        return expected


def arguments(remote, base, item, bundle, review=None, proof=None, *, stage=False):
    batch = item["batch"]
    args = [remote.upload(batch, encoded(bundle), ".json"), "--body-file",
            remote.upload(batch, read(local_path(base, item["body_file"])), ".md")]
    for group, flag in GROUPS.items():
        for entry in item[group]:
            args += [flag, entry["kind"] + "=" + remote.upload(batch, read(local_path(base, entry["path"])), ".bin")]
    for entry in item["asset_files"]:
        args += ["--asset-file", json.dumps({
            "url": entry["url"],
            "path": remote.upload(batch, read(local_path(base, entry["path"])), ".bin"),
        }, separators=(",", ":"))]
    if review is not None:
        args += ["--review-file", remote.upload(batch, review, ".json")]
    if proof is not None:
        args += ["--proof-file", remote.upload(batch, encoded(proof), ".json")]
    if stage:
        for role in ("shelf_cover", "reader_cover"):
            name = item.get(f"{role}_file")
            if name:
                args += [f"--{role.replace('_', '-')}-file",
                         remote.upload(batch, read(local_path(base, name)), ".bin")]
        for role in ("illustration_01", "illustration_02", "illustration_03"):
            name = item.get(f"{role}_file")
            if name:
                args += ["--illustration-file",
                         role + "=" + remote.upload(batch, read(local_path(base, name)), ".bin")]
    return args


def attempt(remote, contract, states):
    status = remote.operator("status")
    rows = status.get("editorial_attempts")
    if not isinstance(rows, list):
        raise ValueError("status lacks editorial attempts")
    rows = [r for r in rows if r.get("issue_id") == contract["issue_id"]]
    if not rows:
        raise ValueError("attempt readback missing")
    latest = max(rows, key=lambda r: r["revision"])
    if (latest.get("quality_contract") != contract or latest.get("attempt_id") != contract["attempt_id"]
            or latest.get("revision") != contract["revision"] or latest.get("target_hash") != contract["target_hash"]
            or latest.get("state") not in states):
        raise ValueError("attempt ID/hash/state readback mismatch")
    return latest


def prepare(path, remote, *, review_policy=None):
    path, value = load_manifest(path)
    for item in value["items"]:
        if item["status"] != "prepared":
            continue
        item.setdefault("batch", uuid.uuid4().hex)
        save(path, value)  # Stable upload namespace even after transport interruption.
        bundle = json.loads(read(local_path(path.parent, item["bundle_file"])))
        args = arguments(remote, path.parent, item, bundle, stage=True)
        if review_policy is not None:
            args += ["--review-policy", review_policy]
        result = remote.operator("prepare-editorial", *args)
        contract = result.get("quality_contract")
        if not isinstance(contract, dict) or any(key not in contract for key in ("issue_id", "revision", "attempt_id", "target_hash", "writer_sessions")):
            raise ValueError("server contract missing")
        receipt = attempt(remote, contract, {"await_review"})
        for group, field in (("source_files", "source_receipts"), ("rights_files", "rights_evidence"), ("execution_files", "execution_evidence")):
            if item[group]:
                bundle[field] = [{"artifact_id": f"receipt-{e['kind']}-{e['sha256']}", "sha256": e["sha256"], "kind": e["kind"]} for e in item[group]]
        bundle["source_snapshot_hash"] = sha("\n".join(sorted(e["sha256"] for e in bundle.get("source_receipts", []))).encode())
        bundle["assets"] = result.get("assets", bundle.get("assets", []))
        bundle["quality_contract"] = contract
        verify_target(bundle, read(local_path(path.parent, item["body_file"])).decode())
        # Publish a new frozen bundle pointer and manifest atomically; never
        # leave an old manifest hashing newly overwritten input bytes on crash.
        frozen = local_path(path.parent, "prepared-" + item["batch"] + ".json", output=True)
        if frozen.exists() and read(frozen) != encoded(bundle):
            raise ValueError("prepared bundle conflict")
        save(frozen, bundle)
        item.update(bundle_file=frozen.name, quality_contract=contract, bundle_sha256=sha(encoded(bundle)), status="await_review", receipt=receipt)
        save(path, value)
    return {"manifest": str(path), "statuses": [i["status"] for i in value["items"]]}


def manifests(root):
    root = Path(root).expanduser().absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("manifest root must be a real directory")
    return sorted(set(root.rglob("*.manifest.json")) | set(root.rglob("draft-manifest.json")))


def verify_target(bundle, manuscript):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.services.publication_editorial import editorial_target_hash
    contract = bundle["quality_contract"]
    if editorial_target_hash(manuscript, contract, bundle.get("source_receipts", [])) != contract["target_hash"]:
        raise ValueError("full manuscript/contract/source receipt target mismatch")


def material_assets(item, bundle):
    assets = []
    for asset in bundle.get("assets", []):
        identity = "role" if "role" in asset else "url" if "url" in asset else None
        digest = asset.get("receipt", {}).get("sha256") if isinstance(asset, dict) else None
        if identity is None or not isinstance(digest, str) or not HASH.fullmatch(digest):
            raise ValueError("invalid publication asset mapping")
        assets.append({identity: asset[identity], "sha256": digest})
    by_role = {asset["role"]: asset["sha256"] for asset in assets if "role" in asset}
    for role in MEDIA_ROLES:
        if item.get(f"{role}_file") and by_role.get(role) != item.get(f"{role}_sha256"):
            raise ValueError("signed proof does not bind manifest assets")
    return assets


def review_input(root, remote):
    from scripts.publication_scheduler_watchdog import Action, Barrier, Claims, _material_hash
    recovery = Claims(Path.home() / ".hermes/cron/publication-recovery.db")
    profile = os.environ.get("HERMES_PROFILE", "default")
    if profile not in {"default", "supervision"}:
        raise ValueError("unsupported native reviewer profile")
    invalid_pending: list[str] = []
    candidates = []
    for path in manifests(root):
        # Historical output roots can contain pre-v2 or abandoned manifests.
        # They are irrelevant unless they explicitly claim a pending review;
        # avoid letting an invalid non-candidate block today's global scan.
        try:
            raw = json.loads(read(path))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid manifest JSON") from exc
        if not any(
            isinstance(item, dict) and item.get("status") == "await_review"
            for item in raw.get("items", [])
        ):
            continue
        try:
            path, value = load_manifest(path)
        except ValueError:
            # A malformed pending draft must fail its own pipeline, not poison
            # every other valid candidate in the shared output root.
            invalid_pending.append(str(path))
            continue
        for item in value["items"]:
            if item["status"] != "await_review":
                continue
            contract = item["quality_contract"]
            expected_profile = "supervision" if contract.get("review_policy") == "story-supervision-v2" else "default"
            if profile != expected_profile:
                continue
            # A completed local review may precede the deterministic finalizer.
            # Skip it before requiring the remote attempt to remain await_review;
            # otherwise a global scan is blocked by historical manifests whose
            # server state has already advanced to approved or rejected.
            if local_path(path.parent, item["review_file"], output=True).exists():
                continue
            bundle = json.loads(read(local_path(path.parent, item["bundle_file"])))
            release_at = datetime.fromisoformat(bundle["release_at"])
            if release_at.tzinfo is None:
                raise ValueError("publication release_at must include timezone")
            from zoneinfo import ZoneInfo
            issue_key = bundle.get("issue_key") or publication_slot(
                bundle["series_id"], bundle["issue_date"],
                bundle.get("issue_slot") or release_at.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%H:%M"),
            )["issue_key"]
            barrier = Barrier(bundle["series_id"], _material_hash(item), issue_key)
            if recovery.exhausted(bundle["issue_date"], Action(
                "review", (barrier,), job_id=SERIES[bundle["series_id"]].get("review_job_id")
            )):
                continue
            candidates.append((release_at, bundle["series_id"], path, item, bundle))
    if candidates:
        _, _, path, item, bundle = min(candidates, key=lambda candidate: candidate[:2])
        contract = item["quality_contract"]
        attempt(remote, contract, {"await_review"})
        manuscript = read(local_path(path.parent, item["body_file"])).decode()
        verify_target(bundle, manuscript)
        # Cron injects stdout into Markdown and the gateway may redact long
        # token-like strings. Compress first, then split Base64 below the
        # gateway's generic high-entropy-token threshold. Twelve-character
        # JSON strings also prevent a secret-like sequence from existing in
        # any individual string. The reviewer still reads the frozen body_file.
        compressed = base64.b64encode(gzip.compress(manuscript.encode(), mtime=0)).decode()
        request = {"manuscript_gzip_b64_chunks": [compressed[i:i + 12] for i in range(0, len(compressed), 12)], "quality_contract": contract, "source_receipts": bundle.get("source_receipts", []), "purpose": "publication_editorial_review", "owner": "local_owner",
                   **{k: contract[k] for k in ("issue_id", "revision", "attempt_id", "writer_sessions")},
                   "editorial_target_hash": contract["target_hash"]}
        if contract.get("review_policy") == "story-supervision-v2":
            from backend.services.publication_review_provenance import publication_material_hash
            assets = material_assets(item, bundle)
            request.update({"review_policy": "story-supervision-v2", "writer_profile": "story", "reviewer_profile": "supervision",
                            "writer_role": "story_author", "reviewer_role": "supervision_reviewer",
                            "assets": assets, "publication_material_hash": publication_material_hash(contract["target_hash"], assets)})
        else:
            request["profile"] = "default"
        files: dict = {key: str(local_path(path.parent, item[key], output=key == "review_file")) for key in ("bundle_file", "body_file", "review_file")}
        files.update({group: [{**entry, "path": str(local_path(path.parent, entry["path"]))} for entry in item[group]] for group in GROUPS})
        files["assets"] = [str(local_path(path.parent, item[f"{role}_file"]))
                           for role in MEDIA_ROLES if item.get(f"{role}_file")]
        files["assets"] += [str(local_path(path.parent, entry["path"])) for entry in item["asset_files"]]
        visual = "Use visual tools to inspect every actual image in read_only_inputs.assets; hashes and prompts are not substitutes for visual inspection. "
        instruction = ("Read inputs only; " + visual + "write only review_file. Bind publication_material_hash in the review bytes. End with pure JSON {publication_review_result:{issue_id,revision,attempt_id,editorial_target_hash,publication_material_hash,review_file_hash,reviewer_session,decision}}; no tools after final. Do not stage or sign."
                       if contract.get("review_policy") == "story-supervision-v2" else
                       "Read inputs only; " + visual + "write only review_file. End with pure JSON {publication_review_result:{issue_id,revision,attempt_id,editorial_target_hash,review_file_hash,reviewer_session,decision}}; no tools after final. Do not stage or sign.")
        return encoded({"manifest": str(path), "read_only_inputs": files, "instruction": instruction}).decode() + "\nPUBLICATION_REVIEW_REQUEST\n" + encoded(request).decode() + "\nEND_PUBLICATION_REVIEW_REQUEST"
    if invalid_pending:
        raise ValueError(f"{len(invalid_pending)} invalid pending editorial manifest(s)")
    return json.dumps({"status": "no_await_review"})


def native_attest(db, review, key):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.services.publication_review_provenance import attest_native_review
    secure = transport._secure_file(str(key), "editorial signing key", private=True)
    try:
        if isinstance(db, Mapping):
            if set(db) != {"story", "supervision"}:
                raise ValueError("trusted story/supervision databases required")
            return attest_native_review(Path(db["supervision"]).expanduser(), review, Path(secure).read_bytes(),
                                        profile="supervision", writer_profile="story",
                                        writer_db_path=Path(db["story"]).expanduser())
        return attest_native_review(Path(db).expanduser(), review, Path(secure).read_bytes())
    except sqlite3.Error as exc:
        raise ValueError("native review database unavailable or invalid") from exc


def native_running(db, review):
    sid = review.get("reviewer_session", "")
    if not isinstance(sid, str) or not sid.startswith("hermes:"):
        return False
    try:
        path = db["supervision"] if isinstance(db, Mapping) else db
        with sqlite3.connect(Path(path).expanduser().resolve().as_uri() + "?mode=ro", uri=True) as conn:
            row = conn.execute("SELECT ended_at FROM sessions WHERE id=?", (sid[7:],)).fetchone()
        return row is not None and row[0] is None
    except sqlite3.Error as exc:
        raise ValueError("native review database unavailable or invalid") from exc


def finalize(root, remote, *, db=None, key=Path("~/.hermes/config/publication-editorial-private.pem"), attest=native_attest):
    results = []
    invalid_pending: list[tuple[str, str]] = []
    failures: list[dict] = []
    for path in manifests(root):
        try:
            raw_manifest = json.loads(read(path))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid manifest JSON") from exc
        if not any(
            isinstance(item, dict) and item.get("status") == "await_review"
            for item in raw_manifest.get("items", [])
        ):
            continue
        try:
            path, value = load_manifest(path)
        except ValueError as exc:
            invalid_pending.append((str(path), str(exc)))
            continue
        for item in value["items"]:
            if item["status"] != "await_review":
                continue
            review_path = local_path(path.parent, item["review_file"], output=True)
            if not review_path.exists():
                results.append({"status": "pending", "manifest": str(path)})
                continue
            try:
                raw = read(review_path)
                review = json.loads(raw)
                c = item["quality_contract"]
                databases = db
                if databases is None:
                    databases = ({"story": Path("~/.hermes/profiles/story/state.db"),
                                  "supervision": Path("~/.hermes/profiles/supervision/state.db")}
                                 if c.get("review_policy") == "story-supervision-v2"
                                 else Path("~/.hermes/state.db"))
                proof_path = local_path(path.parent, item["proof_file"], output=True)
                if proof_path.exists():
                    proof = json.loads(read(proof_path))
                else:
                    try:
                        proof = attest(databases, review_path, key)
                    except ValueError as exc:
                        if str(exc) == "native review is not completed" and native_running(databases, review):
                            results.append({"status": "pending", "manifest": str(path)})
                            continue
                        raise
                if read(review_path) != raw:
                    raise ValueError("review changed during attestation")
                expected = {"issue_id": c["issue_id"], "revision": c["revision"], "attempt_id": c["attempt_id"],
                            "editorial_target_hash": c["target_hash"], "writer_sessions": c["writer_sessions"],
                            "review_file_hash": sha(raw), "decision": review.get("decision")}
                if c.get("review_policy") == "story-supervision-v2":
                    bundle = json.loads(read(local_path(path.parent, item["bundle_file"])))
                    from backend.services.publication_review_provenance import publication_material_hash
                    expected["publication_material_hash"] = publication_material_hash(
                        c["target_hash"], material_assets(item, bundle))
                if any(proof.get(k) != v for k, v in expected.items()) or proof.get("decision") not in {"approved", "rejected"}:
                    raise ValueError("signed proof does not bind manifest")
                # Revalidate every frozen input after native DB work and before upload.
                load_manifest(path)
                if proof_path.exists() and read(proof_path) != encoded(proof):
                    raise ValueError("proof output conflict")
                save(proof_path, proof)
                bundle = json.loads(read(local_path(path.parent, item["bundle_file"])))
                current = attempt(remote, c, {"await_review", "approved", "rejected", "failed"})
                if current["state"] in {"await_review", "failed"}:
                    remote.operator("record-editorial-review", *arguments(remote, path.parent, item, bundle, raw, proof))
                receipt = attempt(remote, c, {review["decision"]})
                if receipt.get("review_hash") != sha(raw):
                    raise ValueError("recorded review hash mismatch")
                if review["decision"] == "approved":
                    bundle["review"] = {"content_hash": review["content_hash"], "decision": "approved", "reviewed_by": review["reviewer_session"], "reviewed_at": review["reviewed_at"], "receipt": None}
                    # Author bundles may remain in draft while awaiting review.
                    # Staging is an explicit operator transition; never inherit
                    # the author's draft state into the stage request.
                    bundle["state"] = "staged"
                    staged = remote.operator(
                        "stage", *arguments(remote, path.parent, item, bundle, raw, proof, stage=True)
                    )
                    status = remote.operator("status")
                    matches = [r for r in status.get("items", []) if r.get("edition_id") == staged.get("edition_id")]
                    if len(matches) != 1 or not staged.get("edition_id"):
                        raise ValueError("stage readback missing")
                    row = matches[0]
                    if (row.get("state") not in {"staged", "scheduled", "published"} or row.get("content_hash") != item["body_sha256"]
                            or row.get("bundle", {}).get("quality_contract") != c or row.get("issue_id") != c["issue_id"]):
                        raise ValueError("stage ID/hash/state readback mismatch")
                    receipt = {"attempt": receipt, "edition": row}
                item.update(status="staged" if review["decision"] == "approved" else "rejected", receipt=receipt)
                item.pop("error", None)
                save(path, value)
                results.append({"status": item["status"], "manifest": str(path), "attempt_id": c["attempt_id"]})
            except Exception as exc:
                item["error"] = str(exc)
                save(path, value)
                failure = {"status": "failed", "manifest": str(path), "error": str(exc)}
                failures.append(failure)
                results.append(failure)
                continue
    if invalid_pending and not results:
        if len(invalid_pending) == 1:
            raise ValueError(invalid_pending[0][1])
        raise ValueError(f"{len(invalid_pending)} invalid pending editorial manifests")
    if failures and not any(result.get("status") in {"staged", "rejected", "blocked"} for result in results):
        raise ValueError(failures[0]["error"])
    return {"items": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-file")
    parser.add_argument("--known-hosts-file")
    sub = parser.add_subparsers(dest="action", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--manifest", required=True, type=Path)
    prepare_parser.add_argument("--review-policy", choices=("story-supervision-v2",))
    start_parser = sub.add_parser("start")
    start_parser.add_argument("--submission", required=True, type=Path)
    start_parser.add_argument("--body-dir", required=True, type=Path)
    start_parser.add_argument("--series-id", required=True, choices=sorted(DAILY_SERIES))
    start_parser.add_argument("--issue-date", required=True)
    start_parser.add_argument("--issue-slot")
    start_parser.add_argument("--format", required=True, choices=("book", "chapter"))
    start_parser.add_argument("--owner-policy-id", required=True)
    revise_parser = sub.add_parser("revise")
    revise_parser.add_argument("--manifest", required=True, type=Path)
    revise_parser.add_argument("--body-file", required=True, type=Path)
    for name in ("review-input", "finalize"):
        sub.add_parser(name).add_argument("--root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        remote = Remote(*transport._trust(args))
        # Existing Cron jobs are serial; flock also rejects accidental overlap.
        if args.action in {"prepare", "revise"}:
            directory = args.manifest.expanduser().absolute().parent
        elif args.action == "start":
            directory = args.body_dir.expanduser().absolute()
        else:
            directory = args.root.expanduser().absolute()
        lock = directory / ".publication-editorial.lock"
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.action == "prepare":
                result = prepare(args.manifest, remote, review_policy=args.review_policy)
            elif args.action == "start":
                initial_manifest = build_initial(
                    args.submission, args.body_dir, series_id=args.series_id,
                    issue_date=args.issue_date, format=args.format,
                    owner_policy_id=args.owner_policy_id, issue_slot=args.issue_slot,
                )
                result = prepare(initial_manifest, remote, review_policy=SERIES[args.series_id].get("review_policy"))
            elif args.action == "revise":
                revision_manifest = build_revision(args.manifest, args.body_file)
                revision_path, revision_value = load_manifest(revision_manifest)
                revision_bundle = json.loads(read(local_path(revision_path.parent, revision_value["items"][0]["bundle_file"])))
                result = prepare(revision_manifest, remote, review_policy=SERIES[revision_bundle["series_id"]].get("review_policy"))
            elif args.action == "review-input":
                result = review_input(args.root, remote)
            else:
                result = finalize(args.root, remote)
        print(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False), end="" if isinstance(result, str) else "\n")
        return 0
    except Exception as exc:
        print(f"publication editorial failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
