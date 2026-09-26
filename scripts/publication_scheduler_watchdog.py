#!/usr/bin/env python3
"""Conservatively recover one item-scoped phase of today's publication flow.

This component is intentionally not scheduled by this repository.  It derives
progress from validated editorial manifests and production readback, never from
job completion timestamps.  Every dispatch is protected by a durable,
item/material-scoped idempotency claim.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterator, Sequence
from zoneinfo import ZoneInfo

STATUS_CLIENT = Path(__file__).with_name("publication_release_remote.py")
EDITORIAL_CLIENT = Path(__file__).with_name("publication_editorial_remote.py")
HANDOFF_CLIENT = Path(__file__).with_name("publication_workflow_handoff.py")
OUTPUT_ROOT = Path.home() / ".hermes/outputs/quantumn-editorial-v2"
EXECUTIONS_DB = Path.home() / ".hermes/cron/executions.db"
DISPATCH_CONFIRM_SECONDS = 30.0
DISPATCH_POLL_SECONDS = 0.25
RECOVERY_DB = Path.home() / ".hermes/cron/publication-recovery.db"
LOCK_FILE = Path.home() / ".hermes/cron/publication-scheduler-watchdog.lock"
_SOURCE_ROOT = Path(__file__).resolve().parents[1]
if not (_SOURCE_ROOT / "backend/services/knowledge_publication_store.py").is_file():
    _SOURCE_ROOT = Path.cwd().resolve()
sys.path.insert(0, str(_SOURCE_ROOT))
from backend.services.knowledge_publication_store import SERIES as PUBLICATION_SERIES

SERIES = {name: spec for name, spec in PUBLICATION_SERIES.items()
          if spec.get("kind") == "daily" and spec.get("enabled", True)}
AUTHOR_JOBS = {name: spec.get("author_job_id") for name, spec in SERIES.items()}
PLATFORM_AUTHOR_SERIES = frozenset(name for name, spec in SERIES.items()
                                  if spec.get("workflow_schedule_id") or (spec.get("assets_job_id") and not spec.get("author_job_id")))
REVIEW_JOB = next((spec.get("review_job_id") for spec in SERIES.values() if spec.get("review_job_id")), None)
PREREQUISITE_JOB = next((spec.get("prerequisite_job_id") for spec in SERIES.values() if spec.get("prerequisite_job_id")), None)
TARGET_JOBS = tuple(dict.fromkeys(spec[field] for spec in SERIES.values()
    for field in ("author_job_id", "assets_job_id", "review_job_id", "prerequisite_job_id") if spec.get(field)))
JOBS_FILE = Path.home() / ".hermes/cron/jobs.json"
PROFILES_ROOT = Path.home() / ".hermes/profiles"
ROLE_PROFILES = {"author": {"default", "story"}, "review": {"default", "supervision"},
                 "assets": {"default"}, "prerequisite": {"default"}}


def _role_profile(series: str, phase: str) -> str:
    profile = SERIES[series].get(f"{phase}_profile", "default")
    profile = "default" if profile == "main" else profile
    if profile not in ROLE_PROFILES[phase]:
        raise ActionFailure("job_profile_not_allowed_for_role")
    return profile


def _action_profile(action: Action) -> str:
    profiles = {_role_profile(barrier.series, action.phase) for barrier in action.barriers}
    if len(profiles) != 1:
        raise ActionFailure("ambiguous_job_profile")
    return next(iter(profiles))


def _profile_job_key(profile: str, job_id: str) -> str:
    return job_id if profile == "default" else f"{profile}/{job_id}"



def _schedule_id(series: str) -> str:
    return SERIES[series].get("workflow_schedule_id") or (
        os.environ.get("PUBLICATION_AI_TOOLKIT_SCHEDULE_ID", "") if series == "ai-toolkit" else ""
    )


HASH = re.compile(r"[0-9a-f]{64}\Z")
MEDIA_ROLES = ("shelf_cover", "reader_cover", "illustration_01", "illustration_02", "illustration_03")
EVIDENCE_GROUPS = ("source_files", "rights_files", "execution_files")
PHASE_ORDER = {
    "finalize": 0,
    "handoff_acknowledge": 1,
    "handoff_revision": 1,
    "review": 2,
    "prepare": 3,
    "assets": 4,
    "handoff_fetch": 5,
    "native_fetch": 5,
    "author": 6,
    "prerequisite": 7,
}


@dataclass(frozen=True)
class Item:
    manifest: Path
    series: str
    day: str
    material_hash: str
    status: str
    review_ready: bool = False
    issue_key: str = ""


@dataclass(frozen=True)
class Handoff:
    directory: Path
    day: str
    artifact_id: str
    material_hash: str
    status: str
    series: str = "ai-toolkit"
    issue_key: str = ""
    native: bool = False


@dataclass(frozen=True)
class Barrier:
    series: str
    material_hash: str
    issue_key: str = ""


@dataclass(frozen=True)
class Action:
    phase: str
    barriers: tuple[Barrier, ...]
    job_id: str | None = None
    manifest: Path | None = None


class ActionFailure(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class ActionPending(RuntimeError):
    def __init__(self, reason: str, details: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}


def _default_profile_only() -> None:
    profile = os.environ.get("HERMES_PROFILE", "default")
    home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser().resolve()
    if profile != "default" or home != (Path.home() / ".hermes").resolve():
        raise RuntimeError("publication recovery is restricted to the default Hermes profile")
    if any(part == "profiles" for part in RECOVERY_DB.expanduser().resolve().parts):
        raise RuntimeError("cross-profile recovery state is forbidden")


def _status() -> dict:
    completed = subprocess.run(
        [str(STATUS_CLIENT), "--status-only"], text=True, capture_output=True,
        timeout=180, check=False, env=_default_env(),
    )
    if completed.returncode:
        raise RuntimeError("status command failed")
    try:
        value = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError("status command returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("status command returned invalid JSON")
    return value


def _default_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("HERMES_PROFILE", None)
    env["HERMES_HOME"] = str(Path.home() / ".hermes")
    # Recovery may use only the default profile's owner-controlled publication
    # transport.  Never inherit a Story/profile credential override.
    for name in tuple(env):
        if name.startswith("STORY_"):
            env.pop(name)
    source_root = Path(__file__).resolve().parents[1]
    if not (source_root / "backend/services/publication_editorial.py").is_file():
        source_root = Path.cwd().resolve()
    if not (source_root / "backend/services/publication_editorial.py").is_file():
        raise RuntimeError("publication repository root is unavailable")
    # The editorial client imports the sibling backend package. Replace, do
    # not extend, inherited PYTHONPATH so scheduler state cannot inject code.
    env["PYTHONPATH"] = str(source_root)
    return env


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def _material_hash(item: dict) -> str:
    hashes: list[tuple[str, object]] = [("body", item.get("body_sha256"))]
    hashes.extend((role, item.get(f"{role}_sha256")) for role in MEDIA_ROLES)
    for group in EVIDENCE_GROUPS:
        entries = item.get(group)
        if not isinstance(entries, list):
            raise ValueError("manifest evidence list missing")
        hashes.extend(
            (f"{group}:{entry.get('kind')}", entry.get("sha256"))
            for entry in entries if isinstance(entry, dict)
        )
    if any(not isinstance(digest, str) or not HASH.fullmatch(digest) for _, digest in hashes):
        raise ValueError("material hash input missing")
    encoded = json.dumps(sorted(hashes), ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _manifest_items(root: Path = OUTPUT_ROOT) -> list[Item]:
    try:
        from scripts.publication_editorial_remote import load_manifest
    except ImportError:
        from publication_editorial_remote import load_manifest

    if not root.is_dir() or root.is_symlink():
        raise ValueError("editorial root must be a real directory")
    found: list[Item] = []
    paths = sorted(set(root.rglob("draft-manifest.json")) | set(root.rglob("*.manifest.json")))
    for candidate in paths:
        try:
            path, value = load_manifest(candidate)
        except (OSError, ValueError, json.JSONDecodeError):
            # Preserve a fail-closed marker when even a minimally safe read
            # identifies a daily item. Invalid unrelated historical files do
            # not poison today's recovery, but an invalid daily candidate must
            # never be treated as if no material existed.
            try:
                raw = _read_json(candidate)
                for row in raw.get("items", []):
                    name = row.get("bundle_file") if isinstance(row, dict) else None
                    bundle_path = (candidate.parent / name).resolve() if isinstance(name, str) else None
                    if bundle_path is None or candidate.parent.resolve() not in bundle_path.parents:
                        continue
                    bundle = _read_json(bundle_path)
                    series, day = bundle.get("series_id"), bundle.get("issue_date")
                    if series in AUTHOR_JOBS and isinstance(day, str):
                        marker = hashlib.sha256(str(candidate.resolve()).encode()).hexdigest()
                        found.append(Item(candidate.resolve(), series, day, marker, "invalid", issue_key=bundle.get("issue_key", "")))
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            continue
        for row in value["items"]:
            bundle = _read_json(path.parent / row["bundle_file"])
            series, day = bundle.get("series_id"), bundle.get("issue_date")
            if series not in AUTHOR_JOBS or not isinstance(day, str):
                continue
            review_ready = False
            if row["status"] == "await_review":
                review_path = path.parent / row["review_file"]
                if review_path.is_file() and not review_path.is_symlink():
                    try:
                        review_ready = _read_json(review_path).get("decision") in {"approved", "rejected"}
                    except (OSError, ValueError, json.JSONDecodeError):
                        review_ready = False
            found.append(Item(path, series, day, _material_hash(row), row["status"], review_ready, bundle.get("issue_key", "")))
    return found


def _handoff_items(root: Path = OUTPUT_ROOT) -> list[Handoff]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("editorial root must be a real directory")
    found: list[Handoff] = []
    for state_path in sorted(root.glob("*/workflow-handoff-state.json")):
        directory = state_path.parent.resolve()
        value: dict = {}
        try:
            if state_path.is_symlink() or root.resolve() not in directory.parents:
                raise ValueError("workflow handoff state path is unsafe")
            value = _read_json(state_path)
            if value.get("series_id") not in PLATFORM_AUTHOR_SERIES:
                continue
            artifact_id = value.get("artifact_id")
            artifact_hash = value.get("artifact_sha256")
            envelope_hash = value.get("envelope_sha256")
            status = value.get("status")
            if (
                value.get("version") != "publication-workflow-consumption-v1"
                or value.get("series_id") not in PLATFORM_AUTHOR_SERIES
                or not isinstance(value.get("issue_date"), str)
                or not isinstance(artifact_id, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", artifact_id) is None
                or not isinstance(artifact_hash, str)
                or HASH.fullmatch(artifact_hash) is None
                or not isinstance(envelope_hash, str)
                or HASH.fullmatch(envelope_hash) is None
                or status not in {"waiting_assets", "revision_requested", "acknowledged"}
            ):
                raise ValueError("workflow handoff state is invalid")
            material_hash = hashlib.sha256(
                f"{artifact_id}:{artifact_hash}:{envelope_hash}".encode()
            ).hexdigest()
            found.append(
                Handoff(directory, value["issue_date"], artifact_id, material_hash, status, value["series_id"], value.get("issue_key", ""))
            )
        except (OSError, ValueError, json.JSONDecodeError):
            marker = hashlib.sha256(str(state_path.resolve()).encode()).hexdigest()
            candidate_day = value.get("issue_date")
            invalid_day = (
                candidate_day
                if isinstance(candidate_day, str)
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate_day)
                else ""
            )
            found.append(Handoff(directory, invalid_day, "invalid", marker, "invalid", value.get("series_id", "ai-toolkit"), value.get("issue_key", "")))
    for state_path in sorted(root.glob("*/native-content-state.json")):
        value = {}
        directory = state_path.parent.resolve()
        try:
            if state_path.is_symlink() or root.resolve() not in directory.parents:
                raise ValueError("unsafe native content state")
            value = _read_json(state_path)
            if (value.get("series_id") not in SERIES or value.get("status") != "waiting_assets"
                or not isinstance(value.get("issue_date"), str)
                or not isinstance(value.get("issue_key"), str)
                or not HASH.fullmatch(value.get("artifact_sha256", ""))):
                raise ValueError("invalid native content state")
            found.append(Handoff(directory, value["issue_date"], "native", value["artifact_sha256"],
                                 "waiting_assets", value["series_id"], value["issue_key"], True))
        except (OSError, ValueError, TypeError):
            found.append(Handoff(directory, value.get("issue_date", ""), "invalid",
                                 hashlib.sha256(str(state_path).encode()).hexdigest(), "invalid",
                                 value.get("series_id", ""), value.get("issue_key", ""), True))
    return found


def _missing(summary: dict, day: str) -> set[str]:
    today, issues = summary.get("today"), summary.get("issues")
    if not isinstance(today, dict) or not isinstance(issues, dict) or today.get("date") != day:
        raise ValueError("invalid or wrong-day status summary")
    by_series, missing_rows = today.get("by_series"), issues.get("missing")
    active_series = {name: spec for name, spec in SERIES.items() if spec.get("starts_on", day) <= day}
    expected = sum(len(spec.get("release_times", ["12:00"])) for spec in active_series.values())
    if today.get("expected") != expected or not isinstance(by_series, dict) or set(by_series) != set(active_series):
        raise ValueError("unexpected publication series")
    if not isinstance(missing_rows, list):
        raise ValueError("invalid missing publication rows")
    inferred: set[str] = set()
    published_total = 0
    for name, item in by_series.items():
        count = len(SERIES[name].get("release_times", ["12:00"]))
        if not isinstance(item, dict) or type(item.get("published")) is not int or not 0 <= item["published"] <= count:
            raise ValueError("invalid publication status")
        published_total += item["published"]
        slots = item.get("slots")
        if slots is not None:
            expected_keys = {day if slot == "12:00" else f"{day}T{slot}" for slot in SERIES[name].get("release_times", ["12:00"])}
            if (not isinstance(slots, list) or len(slots) != count
                or {slot.get("issue_key") for slot in slots} != expected_keys
                or any(slot.get("published") not in {0, 1} for slot in slots)
                or sum(slot["published"] for slot in slots) != item["published"]):
                raise ValueError("invalid publication slots")
        elif count != 1:
            raise ValueError("multi-slot publication requires slot readback")
        if item["published"] < count:
            inferred.add(name)
    reported = {row.get("series_id") for row in missing_rows if isinstance(row, dict) and row.get("issue_date") == day}
    if None in reported or not reported <= inferred or today.get("published") != published_total:
        raise ValueError("contradictory publication status")

    return inferred


def _absent_hash(day: str, series: str, terminal: Sequence[Item]) -> str:
    payload = {"day": day, "series": series, "terminal_materials": sorted(i.material_hash for i in terminal)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _toolkit_prerequisite_barrier(day: str) -> Barrier | None:
    receipt = OUTPUT_ROOT / "prerequisites" / "ai-toolkit" / f"{day}.json"
    if receipt.is_file() and not receipt.is_symlink():
        try:
            value = _read_json(receipt)
        except (OSError, ValueError, json.JSONDecodeError):
            return Barrier("ai-toolkit", hashlib.sha256(receipt.read_bytes()).hexdigest())
        selected = value.get("selected_candidates")
        content_available = (
            value.get("status") in {"CONTENT_AVAILABLE", "READY_FOR_AI_TOOLKIT"}
            and value.get("usable_content_available") is True
            and isinstance(selected, list)
            and bool(selected)
        )
        if content_available:
            return None
        return Barrier("ai-toolkit", hashlib.sha256(receipt.read_bytes()).hexdigest())
    marker = OUTPUT_ROOT / f"{day}-ai-toolkit-blocked" / "blocked-tutorial-prerequisite.json"
    if not marker.is_file() or marker.is_symlink():
        return None
    try:
        value = _read_json(marker)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if value.get("status") != "BLOCKED_TUTORIAL_PREREQUISITE":
        return None
    return Barrier("ai-toolkit", hashlib.sha256(marker.read_bytes()).hexdigest())


def _plan(
    day: str,
    missing: set[str],
    items: Sequence[Item],
    prerequisite: Barrier | None = None,
    handoffs: Sequence[Handoff] = (),
    platform_enabled: bool = False,
    issue_key: str = "",
) -> tuple[Action | None, str]:
    today = [item for item in items if item.day == day and item.series in SERIES
             and (not issue_key or (item.issue_key or item.day) == issue_key)]
    if any(item.status == "invalid" and item.day in {"", day} and item.series in missing for item in handoffs):
        return None, "invalid_workflow_handoff"
    today_handoffs = [item for item in handoffs if item.day == day
                      and (not issue_key or (item.issue_key or item.day) == issue_key)]
    desired: dict[str, Action] = {}
    invalid_series: set[str] = set()
    for series in sorted(missing):
        rows = [item for item in today if item.series == series]
        if any(item.status == "invalid" for item in rows):
            invalid_series.add(series)
            continue
        linked = {
            item.directory: item
            for item in today_handoffs
            if item.series == series and item.status in {"waiting_assets", "revision_requested", "acknowledged"}
        }
        if series in PLATFORM_AUTHOR_SERIES and (bool(_schedule_id(series)) or platform_enabled):
            workflow_rows = [item for item in rows if item.manifest.parent.resolve() in linked]
            if len(workflow_rows) != len(rows):
                return None, "workflow_handoff_binding_missing"
            rejected = [
                item for item in workflow_rows
                if item.status == "rejected"
                and linked[item.manifest.parent.resolve()].status == "waiting_assets"
            ]
            if len(rejected) > 1:
                return None, "ambiguous_manifests"
            if rejected:
                item = rejected[0]
                desired[series] = Action(
                    "handoff_revision",
                    (Barrier(series, item.material_hash, issue_key),),
                    manifest=item.manifest,
                )
                continue
        active = [item for item in rows if item.status in {"prepared", "await_review", "staged"}]
        groups = {item.material_hash for item in active}
        if len(groups) > 1:
            return None, "ambiguous_manifests"
        if active and any((item.status, item.review_ready) != (active[0].status, active[0].review_ready) for item in active[1:]):
            return None, "ambiguous_manifests"
        barrier = Barrier(series, next(iter(groups)) if groups else _absent_hash(issue_key or day, series, rows), issue_key)
        if active:
            item = active[0]
            if item.status == "prepared":
                desired[series] = Action("prepare", (barrier,), manifest=item.manifest)
            elif item.status == "await_review" and not item.review_ready:
                desired[series] = Action("review", (barrier,), job_id=SERIES[series].get("review_job_id"), manifest=item.manifest)
            elif item.status == "await_review":
                desired[series] = Action("finalize", (barrier,), manifest=item.manifest)
            elif series in PLATFORM_AUTHOR_SERIES and (bool(_schedule_id(series)) or platform_enabled):
                state = linked.get(item.manifest.parent.resolve())
                if state is None:
                    return None, "workflow_handoff_binding_missing"
                if state.status == "waiting_assets":
                    desired[series] = Action(
                        "handoff_acknowledge", (barrier,), manifest=item.manifest
                    )
            # Staged non-Workflow items, and acknowledged Workflow items, remain
            # owned by the existing deterministic release job.
        elif series in PLATFORM_AUTHOR_SERIES and (bool(_schedule_id(series)) or platform_enabled):
            waiting = [item for item in today_handoffs if item.series == series and item.status == "waiting_assets"]
            if len(waiting) > 1:
                return None, "ambiguous_workflow_handoffs"
            if waiting:
                item = waiting[0]
                desired[series] = Action(
                    "assets",
                    (Barrier(series, item.material_hash, issue_key),),
                    job_id=SERIES[series].get("assets_job_id"),
                )
            else:
                desired[series] = Action(
                    "handoff_fetch", (barrier,), manifest=None
                )
        elif SERIES[series].get("author_job_id") and SERIES[series].get("assets_job_id"):
            rejected_directories = {item.manifest.parent.resolve() for item in rows if item.status == "rejected"}
            waiting = [item for item in today_handoffs if item.native and item.series == series
                       and item.directory not in rejected_directories]
            if len(waiting) > 1:
                return None, "ambiguous_native_handoffs"
            if waiting:
                desired[series] = Action("assets", (Barrier(series, waiting[0].material_hash, issue_key),),
                                         job_id=SERIES[series]["assets_job_id"])
            else:
                desired[series] = Action("native_fetch", (Barrier(series, barrier.material_hash, issue_key or day),))
        elif not active and series == "ai-toolkit" and prerequisite is not None:
            desired[series] = Action("prerequisite", (prerequisite,), job_id=SERIES[series].get("prerequisite_job_id"))
        elif not active and series in PLATFORM_AUTHOR_SERIES:
            continue
        elif not active:
            desired[series] = Action("author", (barrier,), job_id=AUTHOR_JOBS[series])
    if not desired:
        if invalid_series:
            return None, "invalid_manifest"
        if set(missing) & PLATFORM_AUTHOR_SERIES:
            return None, "awaiting_platform_author"
        return None, "awaiting_release" if missing else "complete"
    phase = min((action.phase for action in desired.values()), key=PHASE_ORDER.__getitem__)
    phase_actions = [action for action in desired.values() if action.phase == phase]
    if phase == "author":
        first = phase_actions[0]
        same_job = [a for a in phase_actions if a.job_id == first.job_id and _action_profile(a) == _action_profile(first)]
        # A shared author job can touch every series in its declared scope.
        # Claim every series that actually needs author work; prepared,
        # await-review, and staged siblings are immutable handoffs and excluded.
        scope_missing = {
            series for series, candidate in desired.items()
            if candidate.phase == "author" and candidate.job_id == first.job_id and _action_profile(candidate) == _action_profile(first)
        }
        claimed = {b.series for a in same_job for b in a.barriers}
        if claimed != scope_missing:
            return None, "ambiguous_author_scope"
        return Action("author", tuple(b for a in same_job for b in a.barriers), job_id=first.job_id), "ready"
    action = phase_actions[0]
    if phase == "review":
        global_pending = sorted(
            (i for i in items if i.status == "await_review" and not i.review_ready
             and i.series in SERIES and _role_profile(i.series, "review") == _action_profile(action)
             and SERIES[i.series].get("review_job_id") == action.job_id),
            key=lambda item: str(item.manifest),
        )
        if not global_pending:
            return None, "review_scope_not_unique"
        first = global_pending[0]
        matching = [
            candidate for candidate in phase_actions
            if candidate.manifest == first.manifest
            and candidate.barriers[0].material_hash == first.material_hash
        ]
        # publication_review_input scans sorted manifests and consumes at most
        # one. Claim exactly that same first item; an older/out-of-scope pending
        # item must be reconciled rather than silently crossed.
        if len(matching) != 1:
            return None, "review_scope_not_unique"
        action = matching[0]
    return action, "ready"


def _owner_alive(pid: int, process_started_at: int | None) -> bool | None:
    if not isinstance(pid, int) or pid <= 0 or not isinstance(process_started_at, int):
        return None
    completed = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="], text=True, capture_output=True,
        timeout=5, check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return False
    try:
        started = datetime.strptime(completed.stdout.strip(), "%a %b %d %H:%M:%S %Y").timestamp()
    except ValueError:
        return None
    # Hermes records process creation in centiseconds.  A PID reused by a new
    # process is not the live owner of the old execution.
    return abs(round(started * 100) - process_started_at) <= 100


def _execution_blockers(
    day: str,
    database: Path | None = None,
    owner_alive: Callable[[int, int | None], bool | None] = _owner_alive,
    target_jobs: Sequence[str] | None = None,
) -> list[str]:
    if database is None:
        routes: dict[str, set[str]] = {}
        for series, spec in SERIES.items():
            for phase in ROLE_PROFILES:
                job_id = spec.get(f"{phase}_job_id")
                if job_id:
                    routes.setdefault(_role_profile(series, phase), set()).add(job_id)
        result = []
        for profile, jobs in routes.items():
            path = EXECUTIONS_DB if profile == "default" else PROFILES_ROOT / profile / "cron/executions.db"
            try:
                rows = _execution_blockers(day, path, owner_alive, sorted(jobs))
            except sqlite3.Error:
                rows = [f"{job_id}:registry:unverified" for job_id in sorted(jobs)]
            result.extend(entry if profile == "default" else f"{profile}/{entry}" for entry in rows)
        return sorted(result)
    target_jobs = TARGET_JOBS if target_jobs is None else target_jobs
    if not target_jobs:
        return []
    uri = database.expanduser().resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            f"SELECT id,job_id,status,pid,process_started_at,claimed_at,finished_at FROM executions WHERE job_id IN ({','.join('?' * len(target_jobs))}) AND status IN ('claimed','running','unknown')",
            target_jobs,
        ).fetchall()
    blockers: list[str] = []
    for execution_id, job_id, status, pid, started, claimed_at, finished_at in rows:
        # An unknown row with a persisted finish timestamp is terminal by
        # definition: the scheduler already recorded that its owner exited.
        # Its old/reused PID must never keep recovery blocked.
        alive = False if status == "unknown" and finished_at else owner_alive(pid, started)
        if status == "unknown":
            if isinstance(claimed_at, str) and claimed_at[:10] == day:
                suffix = "live" if alive is True else "unverified" if alive is None else "dead"
                blockers.append(f"{job_id}:{execution_id}:unknown-{suffix}")
            continue
        if alive is not False:
            blockers.append(f"{job_id}:{execution_id}:{'live' if alive else 'unverified'}")
    return sorted(blockers)


class Claims:
    # Six bounded attempts survive transient scheduler restarts without
    # turning a durable claim into a permanent dead letter before noon.
    MAX_ATTEMPTS = 6
    DISPATCH_RETRY_AFTER = timedelta(minutes=15)

    def __init__(self, path: Path = RECOVERY_DB):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE IF NOT EXISTS recovery_claims (
            idempotency_key TEXT PRIMARY KEY, day TEXT NOT NULL, series TEXT NOT NULL,
            material_hash TEXT NOT NULL, phase TEXT NOT NULL, state TEXT NOT NULL,
            owner_pid INTEGER NOT NULL, owner_started_at INTEGER NOT NULL,
            created_at TEXT NOT NULL, finished_at TEXT, attempts INTEGER NOT NULL DEFAULT 1
        )""")
        columns = {row[1] for row in db.execute("PRAGMA table_info(recovery_claims)")}
        if "attempts" not in columns:
            db.execute("ALTER TABLE recovery_claims ADD COLUMN attempts INTEGER NOT NULL DEFAULT 1")
        if "rearm_history" not in columns:
            db.execute("ALTER TABLE recovery_claims ADD COLUMN rearm_history TEXT NOT NULL DEFAULT '[]'")
        return db

    @staticmethod
    def key(day: str, phase: str, barrier: Barrier) -> str:
        return f"publication-recovery-v1:{barrier.issue_key or day}:{barrier.series}:{barrier.material_hash}:{phase}"

    def exhausted(self, day: str, action: Action) -> list[str]:
        exhausted = []
        with self._connect() as db:
            for barrier in action.barriers:
                key = self.key(day, action.phase, barrier)
                row = db.execute("SELECT state,owner_pid,owner_started_at,finished_at FROM recovery_claims WHERE idempotency_key=? AND attempts>=? AND state!='completed'",
                                 (key, self.MAX_ATTEMPTS)).fetchone()
                if row is None:
                    continue
                state, pid, started, finished_at = row
                if state == "running" and _owner_alive(pid, started) is not False:
                    continue
                if state == "dispatched":
                    try:
                        if datetime.now(ZoneInfo("Asia/Shanghai")) - datetime.fromisoformat(finished_at) < self.DISPATCH_RETRY_AFTER:
                            continue
                    except (TypeError, ValueError):
                        pass
                exhausted.append(key)
        return exhausted

    def rearm(self, key: str, expected_attempts: int, material_hash: str, reason: str,
              blockers: Callable[[str], list[str]] = _execution_blockers) -> dict:
        if not reason.strip() or not HASH.fullmatch(material_hash) or expected_attempts < 1:
            raise ValueError("rearm requires exact material, attempts and audit reason")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM recovery_claims WHERE idempotency_key=?", (key,)).fetchone()
            if row is None or row["material_hash"] != material_hash or row["attempts"] != expected_attempts:
                raise ValueError("rearm compare-and-set mismatch")
            if row["state"] != "failed" or _owner_alive(row["owner_pid"], row["owner_started_at"]) is not False:
                raise ValueError("rearm requires failed claim with proven-dead owner")
            if any(not entry.endswith(":unknown-dead") for entry in blockers(row["day"])):
                raise ValueError("rearm blocked by live or unverified execution")
            history = json.loads(row["rearm_history"])
            history.append({"at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                            "reason": reason, "previous": {k: row[k] for k in row.keys() if k != "rearm_history"}})
            db.execute("UPDATE recovery_claims SET attempts=0,rearm_history=? WHERE idempotency_key=?",
                       (json.dumps(history, sort_keys=True), key))
            db.commit()
        return {"ok": True, "action": "rearmed", "idempotency_key": key, "previous_attempts": expected_attempts}

    def claim(self, day: str, action: Action) -> bool:
        now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
        completed = subprocess.run(
            ["ps", "-p", str(os.getpid()), "-o", "lstart="], text=True, capture_output=True,
            timeout=5, check=False,
        )
        try:
            owner_started = round(datetime.strptime(completed.stdout.strip(), "%a %b %d %H:%M:%S %Y").timestamp() * 100)
        except ValueError as exc:
            raise RuntimeError("cannot establish recovery claim owner identity") from exc
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            keys = [self.key(day, action.phase, barrier) for barrier in action.barriers]
            rows = {
                key: db.execute(
                    "SELECT state,owner_pid,owner_started_at,attempts,finished_at FROM recovery_claims WHERE idempotency_key=?",
                    (key,),
                ).fetchone()
                for key in keys
            }
            for row in rows.values():
                if row is None:
                    continue
                state, pid, started, attempts, finished_at = row
                if state == "completed" or attempts >= self.MAX_ATTEMPTS:
                    db.rollback()
                    return False
                if state == "dispatched":
                    try:
                        finished = datetime.fromisoformat(finished_at)
                    except (TypeError, ValueError):
                        db.rollback()
                        return False
                    if datetime.now(ZoneInfo("Asia/Shanghai")) - finished < self.DISPATCH_RETRY_AFTER:
                        db.rollback()
                        return False
                if state == "running" and _owner_alive(pid, started) is not False:
                    db.rollback()
                    return False
            for key, barrier in zip(keys, action.barriers, strict=True):
                row = rows[key]
                if row is None:
                    db.execute(
                        "INSERT INTO recovery_claims (idempotency_key,day,series,material_hash,phase,state,owner_pid,owner_started_at,created_at,finished_at,attempts) VALUES (?,?,?,?,?,'running',?,?,?,NULL,1)",
                        (key, day, barrier.series, barrier.material_hash, action.phase, os.getpid(), owner_started, now),
                    )
                else:
                    db.execute(
                        "UPDATE recovery_claims SET state='running',owner_pid=?,owner_started_at=?,created_at=?,finished_at=NULL,attempts=attempts+1 WHERE idempotency_key=?",
                        (os.getpid(), owner_started, now, key),
                    )
            db.commit()
        return True

    def finish(self, day: str, action: Action, state: str) -> None:
        if state not in {"completed", "dispatched", "failed"}:
            raise ValueError("invalid claim terminal state")
        now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for barrier in action.barriers:
                db.execute(
                    "UPDATE recovery_claims SET state=?,finished_at=? WHERE idempotency_key=? AND state='running'",
                    (state, now, self.key(day, action.phase, barrier)),
                )
            db.commit()


def _run_action(action: Action) -> None:
    if action.phase in {"author", "assets", "review"}:
        assert action.job_id is not None
        _dispatch_job(action.job_id, _action_profile(action))
        return
    elif action.phase == "prerequisite":
        assert action.job_id is not None
        _dispatch_job(action.job_id, _action_profile(action))
        return
    elif action.phase in {"handoff_fetch", "native_fetch"}:
        commands = [[str(HANDOFF_CLIENT), "fetch-native" if action.phase == "native_fetch" else "fetch", "--output-root", str(OUTPUT_ROOT)]]
        barrier = action.barriers[0]
        commands[0].extend(["--series-id", barrier.series])
        if barrier.issue_key:
            commands[0].extend(["--issue-key", barrier.issue_key])
        timeout = 600
    elif action.phase in {"handoff_acknowledge", "handoff_revision"}:
        assert action.manifest is not None
        command = "acknowledge" if action.phase == "handoff_acknowledge" else "request-revision"
        commands = [[str(HANDOFF_CLIENT), command, "--manifest", str(action.manifest)]]
        timeout = 600
    elif action.phase == "prepare":
        assert action.manifest is not None
        commands = [[str(EDITORIAL_CLIENT), "prepare", "--manifest", str(action.manifest)]]
        timeout = 600
    elif action.phase == "finalize":
        assert action.manifest is not None
        commands = [[str(EDITORIAL_CLIENT), "finalize", "--root", str(action.manifest.parent)]]
        timeout = 600
    else:
        raise ValueError("unsupported recovery phase")
    for command in commands:
        try:
            completed = subprocess.run(
                command, text=True, capture_output=True, timeout=timeout,
                check=False, env=_default_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ActionFailure("action_timeout") from exc
        if completed.returncode:
            if action.phase == "native_fetch" and "native content revision budget exhausted" in completed.stderr:
                raise ActionFailure("native_content_revision_exhausted")
            raise ActionFailure("action_exit_nonzero")
        if action.phase in {"handoff_fetch", "native_fetch"}:
            try:
                result = json.loads(completed.stdout.strip().splitlines()[-1])
            except (IndexError, json.JSONDecodeError) as exc:
                raise ActionFailure("handoff_fetch_invalid_result") from exc
            if isinstance(result, dict) and result.get("status") == "waiting_author":
                raise ActionPending("awaiting_native_author", {key: result[key] for key in
                                    ("reason", "reasons", "feedback_file", "revision_count") if key in result})
            if isinstance(result, dict) and result.get("status") in {"waiting_workflow", "preflight_revision_requested"}:
                raise ActionPending("awaiting_platform_schedule")
            if not isinstance(result, dict) or result.get("status") != "waiting_assets":
                raise ActionFailure("handoff_fetch_invalid_result")


def _job_preflight(action: Action) -> None:
    if action.phase not in {"author", "assets", "review", "prerequisite"}:
        return
    profile = _action_profile(action)
    if not action.job_id:
        raise ActionFailure("job_not_configured")
    try:
        jobs_file = JOBS_FILE if profile == "default" else PROFILES_ROOT / profile / "cron/jobs.json"
        jobs = _read_json(jobs_file).get("jobs", [])
        if isinstance(jobs, dict):
            jobs = [dict(value, id=key) for key, value in jobs.items()]
        matches = [job for job in jobs if isinstance(job, dict) and job.get("id") == action.job_id]
    except (OSError, ValueError, TypeError):
        raise ActionFailure("job_registry_unavailable")
    if len(matches) != 1:
        raise ActionFailure("job_missing" if not matches else "job_ambiguous")
    job = matches[0]
    if job.get("state") == "paused" or job.get("paused_at"):
        raise ActionFailure("job_paused")
    if not job.get("enabled", True):
        raise ActionFailure("job_disabled")


def _dispatch_job(job_id: str, profile: str = "default") -> None:
    if profile not in {"default", "story", "supervision"}:
        raise ActionFailure("job_profile_not_allowed")
    started = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    command = ["hermes", *(["-p", profile] if profile != "default" else []), "cron", "run", job_id]
    # `hermes cron run` remains attached for the full Agent execution. Killing
    # it at the dispatch-confirmation deadline also kills the execution owner
    # and leaves an `unknown` row. Detach it, then return only after the native
    # execution ledger proves that the scheduler accepted a live execution.
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        env=_default_env(),
    )
    database = EXECUTIONS_DB if profile == "default" else PROFILES_ROOT / profile / "cron/executions.db"
    uri = database.expanduser().resolve().as_uri() + "?mode=ro"
    deadline = time.monotonic() + DISPATCH_CONFIRM_SECONDS
    while True:
        try:
            with sqlite3.connect(uri, uri=True) as connection:
                row = connection.execute(
                    "SELECT status FROM executions WHERE job_id=? AND started_at>=? "
                    "ORDER BY started_at DESC LIMIT 1",
                    (job_id, started),
                ).fetchone()
        except sqlite3.Error as exc:
            process.terminate()
            raise ActionFailure("dispatch_readback_failed") from exc
        if row and row[0] in {"claimed", "running", "completed"}:
            return
        returncode = process.poll()
        if returncode is not None:
            if returncode:
                raise ActionFailure("action_exit_nonzero")
            raise ActionFailure("dispatch_not_persisted")
        if time.monotonic() >= deadline:
            process.terminate()
            raise ActionFailure("action_timeout")
        time.sleep(DISPATCH_POLL_SECONDS)


def supervise(
    day: str,
    *,
    status: Callable[[], dict] = _status,
    load_items: Callable[[], list[Item]] = _manifest_items,
    load_handoffs: Callable[[], list[Handoff]] | None = None,
    blockers: Callable[[str], list[str]] = _execution_blockers,
    prerequisite: Callable[[str], Barrier | None] = _toolkit_prerequisite_barrier,
    run_action: Callable[[Action], None] = _run_action,
    preflight: Callable[[Action], None] = _job_preflight,
    claims: Claims | None = None,
) -> dict:
    _default_profile_only()
    input_feedback = {}
    snapshot = status()
    missing = _missing(snapshot, day)
    items = load_items()
    if load_handoffs is not None:
        handoffs = load_handoffs()
    elif load_items is _manifest_items:
        handoffs = _handoff_items()
    else:
        handoffs = []
    # Legacy single-slot summaries keep grouped author dispatch. Explicit slot
    # summaries are planned separately so published siblings cannot hide work.
    plans = []
    for series in sorted(missing):
        slots = snapshot["today"]["by_series"][series].get("slots")
        if slots is not None:
            for slot in slots:
                if not slot["published"]:
                    plans.append(_plan(day, {series}, items, prerequisite(day), handoffs,
                                       platform_enabled=bool(_schedule_id(series)), issue_key=slot["issue_key"]))
    if not plans:
        plans = [_plan(day, missing, items, prerequisite(day), handoffs,
                       platform_enabled=False)]
    if len(plans) == 1 and len(missing) > 1 and not any(
        snapshot["today"]["by_series"][name].get("slots") is not None for name in missing
    ):
        plans.extend(_plan(day, {name}, items, prerequisite(day), handoffs,
                           platform_enabled=bool(_schedule_id(name))) for name in sorted(missing))
    errors = []
    eligible = []
    ledger = claims or Claims()
    for candidate, candidate_reason in plans:
        if candidate is None:
            continue
        try:
            preflight(candidate)
        except ActionFailure as exc:
            errors.append({"ok": False, "action": "none", "reason": exc.reason,
                           "phase": candidate.phase, "job_id": candidate.job_id})
            continue
        if candidate.phase not in {"handoff_fetch", "native_fetch"}:
            exhausted = ledger.exhausted(day, candidate)
            if exhausted:
                errors.append({"ok": False, "action": "none", "reason": "retry_exhausted", "phase": candidate.phase,
                               "idempotency_keys": exhausted, "next_action": "repair_cause_then_rearm_exact_key"})
                continue
        eligible.append(candidate)
    action = min(eligible, key=lambda candidate: PHASE_ORDER[candidate.phase]) if eligible else None
    if action is not None and action.phase == "author":
        same_job = [candidate for candidate in eligible if candidate.phase == "author" and candidate.job_id == action.job_id and _action_profile(candidate) == _action_profile(action)]
        action = Action("author", tuple(dict.fromkeys(barrier for candidate in same_job for barrier in candidate.barriers)), job_id=action.job_id)
    reason = next((reason for candidate, reason in plans if candidate is None
                   and reason not in {"complete", "awaiting_release", "awaiting_platform_author"}), plans[0][1])
    if action is None and errors:
        return errors[0]
    if action is None:
        return {"ok": reason in {"complete", "awaiting_release", "awaiting_platform_author"}, "action": "none", "reason": reason, "missing": sorted(missing)}
    active = blockers(day)
    relevant_jobs = {_profile_job_key(_role_profile(b.series, phase), SERIES[b.series][f"{phase}_job_id"])
                     for b in action.barriers for phase in ROLE_PROFILES if SERIES[b.series].get(f"{phase}_job_id")}
    hard_blockers = [entry for entry in active if not entry.endswith(":unknown-dead")
                     and entry.split(":", 1)[0] in relevant_jobs]
    # Dead unknown executions are reconciled from immutable item/production
    # state. The durable dispatch claim supplies the bounded retry cooldown;
    # live or unverifiable owners block their own publication job scope.
    if hard_blockers:
        return {"ok": True, "action": "none", "reason": "execution_blocked", "executions": sorted(set(hard_blockers))}
    if action.phase in {"handoff_fetch", "native_fetch"}:
        # Immutable materialization makes input polling safe without a claim.
        try:
            run_action(action)
        except ActionPending as exc:
            if action.phase == "native_fetch" and exc.reason == "awaiting_native_author":
                input_feedback = {"author_feedback": exc.details} if exc.details else {}
                action = Action("author", action.barriers, job_id=SERIES[action.barriers[0].series].get("author_job_id"))
            else:
                return {"ok": True, "action": "none", "reason": exc.reason, "phase": action.phase}
        except Exception as exc:
            reason = exc.reason if isinstance(exc, ActionFailure) else "action_exception"
            return {"ok": False, "action": "none", "reason": reason, "phase": action.phase}
        else:
            return {"ok": True, "action": "triggered", "phase": action.phase,
                    "series": [barrier.series for barrier in action.barriers]}
    try:
        preflight(action)
    except ActionFailure as exc:
        return {"ok": False, "action": "none", "reason": exc.reason,
                "phase": action.phase, "job_id": action.job_id}
    if not ledger.claim(day, action):
        exhausted = ledger.exhausted(day, action)
        if exhausted:
            return {"ok": False, "action": "none", "reason": "retry_exhausted", "phase": action.phase,
                    "idempotency_keys": exhausted, "next_action": "repair_cause_then_rearm_exact_key", **input_feedback}
        return {"ok": True, "action": "none", "reason": "already_claimed", "phase": action.phase, **input_feedback}
    try:
        run_action(action)
    except Exception as exc:
        try:
            missing_after = _missing(status(), day)
        except Exception:
            missing_after = set(SERIES)
        if all(barrier.series not in missing_after for barrier in action.barriers):
            ledger.finish(day, action, "completed")
            return {
                "ok": True,
                "action": "reconciled",
                "phase": action.phase,
                "series": sorted(barrier.series for barrier in action.barriers),
            }
        ledger.finish(day, action, "failed")
        reason = exc.reason if isinstance(exc, ActionFailure) else "action_exception"
        return {"ok": False, "action": "none", "reason": reason, "phase": action.phase}
    ledger.finish(
        day,
        action,
        "dispatched" if action.phase in {"author", "assets", "review", "prerequisite"} else "completed",
    )
    return {
        "ok": True, "action": "triggered", "phase": action.phase,
        "series": sorted(barrier.series for barrier in action.barriers),
        "material_hashes": sorted(barrier.material_hash for barrier in action.barriers),
        **({"blocked": errors} if errors else {}),
        **input_feedback,
    }


@contextmanager
def _exclusive_lock(path: Path = LOCK_FILE) -> Iterator[bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rearm-key")
    parser.add_argument("--expected-attempts", type=int)
    parser.add_argument("--material-hash")
    parser.add_argument("--reason")
    args = parser.parse_args(argv)
    if args.rearm_key and (args.expected_attempts is None or not args.material_hash or not args.reason):
        parser.error("rearm requires --expected-attempts, --material-hash and --reason")
    try:
        _default_profile_only()
        with _exclusive_lock() as acquired:
            if not acquired:
                result = {"ok": True, "action": "none", "reason": "locked"}
            else:
                day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
                result = (Claims().rearm(args.rearm_key, args.expected_attempts, args.material_hash, args.reason)
                          if args.rearm_key else supervise(day))
    except ValueError as exc:
        result = {"ok": False, "action": "none", "reason": "rearm_rejected" if args.rearm_key else "invalid_state", "detail": str(exc)}
    except Exception:
        result = {"ok": False, "action": "none", "reason": "error"}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
