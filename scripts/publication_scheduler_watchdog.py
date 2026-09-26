#!/usr/bin/env python3
"""Conservatively recover one item-scoped phase of today's publication flow.

This component is intentionally not scheduled by this repository.  It derives
progress from validated editorial manifests and production readback, never from
job completion timestamps.  Every dispatch is protected by a durable,
item/material-scoped idempotency claim.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterator, Sequence
from zoneinfo import ZoneInfo

STATUS_CLIENT = Path(__file__).with_name("publication_release_remote.py")
EDITORIAL_CLIENT = Path(__file__).with_name("publication_editorial_remote.py")
OUTPUT_ROOT = Path.home() / ".hermes/outputs/quantumn-editorial-v2"
EXECUTIONS_DB = Path.home() / ".hermes/cron/executions.db"
DISPATCH_CONFIRM_SECONDS = 30.0
DISPATCH_POLL_SECONDS = 0.25
RECOVERY_DB = Path.home() / ".hermes/cron/publication-recovery.db"
LOCK_FILE = Path.home() / ".hermes/cron/publication-scheduler-watchdog.lock"
AUTHOR_JOBS = {
    "ai-history": "5a3f2a2eb988",
    "ai-practice": "5a3f2a2eb988",
    "concept-fables": "5a3f2a2eb988",
    "ai-toolkit": "171a125ddb63",
}
REVIEW_JOB = "fbd1cd1217d7"
PREREQUISITE_JOB = "b8c4c5e40bb1"
TARGET_JOBS = (*dict.fromkeys(AUTHOR_JOBS.values()), REVIEW_JOB)
SERIES = tuple(AUTHOR_JOBS)
HASH = re.compile(r"[0-9a-f]{64}\Z")
MEDIA_ROLES = ("shelf_cover", "reader_cover", "illustration_01", "illustration_02", "illustration_03")
EVIDENCE_GROUPS = ("source_files", "rights_files", "execution_files")
PHASE_ORDER = {"finalize": 0, "review": 1, "prepare": 2, "author": 3, "prerequisite": 4}


@dataclass(frozen=True)
class Item:
    manifest: Path
    series: str
    day: str
    material_hash: str
    status: str
    review_ready: bool = False


@dataclass(frozen=True)
class Barrier:
    series: str
    material_hash: str


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
                        found.append(Item(candidate.resolve(), series, day, marker, "invalid"))
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
            found.append(Item(path, series, day, _material_hash(row), row["status"], review_ready))
    return found


def _missing(summary: dict, day: str) -> set[str]:
    today, issues = summary.get("today"), summary.get("issues")
    if not isinstance(today, dict) or not isinstance(issues, dict) or today.get("date") != day:
        raise ValueError("invalid or wrong-day status summary")
    by_series, missing_rows = today.get("by_series"), issues.get("missing")
    if today.get("expected") != len(SERIES) or not isinstance(by_series, dict) or set(by_series) != set(SERIES):
        raise ValueError("unexpected publication series")
    if not isinstance(missing_rows, list):
        raise ValueError("invalid missing publication rows")
    inferred: set[str] = set()
    for name, item in by_series.items():
        if not isinstance(item, dict) or item.get("published") not in {0, 1}:
            raise ValueError("invalid publication status")
        if item["published"] == 0:
            inferred.add(name)
    reported = {row.get("series_id") for row in missing_rows if isinstance(row, dict) and row.get("issue_date") == day}
    # `issues.missing` intentionally excludes an unpublished item once it is
    # staged. `by_series.published` remains the complete publication truth,
    # so the issue list may be a subset but must never contradict it.
    if None in reported or not reported <= inferred or today.get("published") != len(SERIES) - len(inferred):
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
) -> tuple[Action | None, str]:
    today = [item for item in items if item.day == day and item.series in SERIES]
    desired: dict[str, Action] = {}
    invalid_series: set[str] = set()
    for series in sorted(missing):
        rows = [item for item in today if item.series == series]
        if any(item.status == "invalid" for item in rows):
            invalid_series.add(series)
            continue
        active = [item for item in rows if item.status in {"prepared", "await_review", "staged"}]
        groups = {item.material_hash for item in active}
        if len(groups) > 1:
            return None, "ambiguous_manifests"
        if active and any((item.status, item.review_ready) != (active[0].status, active[0].review_ready) for item in active[1:]):
            return None, "ambiguous_manifests"
        barrier = Barrier(series, next(iter(groups)) if groups else _absent_hash(day, series, rows))
        if not active and series == "ai-toolkit" and prerequisite is not None:
            desired[series] = Action("prerequisite", (prerequisite,), job_id=PREREQUISITE_JOB)
        elif not active:
            desired[series] = Action("author", (barrier,), job_id=AUTHOR_JOBS[series])
        else:
            item = active[0]
            if item.status == "prepared":
                desired[series] = Action("prepare", (barrier,), manifest=item.manifest)
            elif item.status == "await_review" and not item.review_ready:
                desired[series] = Action("review", (barrier,), job_id=REVIEW_JOB, manifest=item.manifest)
            elif item.status == "await_review":
                desired[series] = Action("finalize", (barrier,), manifest=item.manifest)
            else:
                # Staged items have passed five-image and signed editorial gates.
                # The normal deterministic release job remains the only publisher;
                # recovery must not start a second publisher.
                continue
    if not desired:
        if invalid_series:
            return None, "invalid_manifest"
        return None, "awaiting_release" if missing else "complete"
    phase = min((action.phase for action in desired.values()), key=PHASE_ORDER.__getitem__)
    phase_actions = [action for action in desired.values() if action.phase == phase]
    if phase == "author":
        first = phase_actions[0]
        same_job = [a for a in phase_actions if a.job_id == first.job_id]
        # A shared author job can touch every series in its declared scope.
        # Claim every series that actually needs author work; prepared,
        # await-review, and staged siblings are immutable handoffs and excluded.
        scope_missing = {
            series for series, candidate in desired.items()
            if candidate.phase == "author" and candidate.job_id == first.job_id
        }
        claimed = {b.series for a in same_job for b in a.barriers}
        if claimed != scope_missing:
            return None, "ambiguous_author_scope"
        return Action("author", tuple(b for a in same_job for b in a.barriers), job_id=first.job_id), "ready"
    action = phase_actions[0]
    if phase == "review":
        global_pending = sorted(
            (i for i in items if i.status == "await_review" and not i.review_ready),
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
    database: Path = EXECUTIONS_DB,
    owner_alive: Callable[[int, int | None], bool | None] = _owner_alive,
) -> list[str]:
    uri = database.expanduser().resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            f"SELECT id,job_id,status,pid,process_started_at,claimed_at,finished_at FROM executions WHERE job_id IN ({','.join('?' * len(TARGET_JOBS))}) AND status IN ('claimed','running','unknown')",
            TARGET_JOBS,
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
        return db

    @staticmethod
    def key(day: str, phase: str, barrier: Barrier) -> str:
        return f"publication-recovery-v1:{day}:{barrier.series}:{barrier.material_hash}:{phase}"

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
                        "INSERT INTO recovery_claims VALUES (?,?,?,?,?,'running',?,?,?,NULL,1)",
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
    if action.phase in {"author", "review"}:
        assert action.job_id is not None
        _dispatch_job(action.job_id)
        return
    elif action.phase == "prerequisite":
        _dispatch_job(PREREQUISITE_JOB)
        return
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
            raise ActionFailure("action_exit_nonzero")


def _dispatch_job(job_id: str) -> None:
    started = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    command = ["hermes", "cron", "run", job_id]
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
    uri = EXECUTIONS_DB.expanduser().resolve().as_uri() + "?mode=ro"
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
    blockers: Callable[[str], list[str]] = _execution_blockers,
    prerequisite: Callable[[str], Barrier | None] = _toolkit_prerequisite_barrier,
    run_action: Callable[[Action], None] = _run_action,
    claims: Claims | None = None,
) -> dict:
    _default_profile_only()
    missing = _missing(status(), day)
    items = load_items()
    action, reason = _plan(day, missing, items, prerequisite(day))
    if action is None:
        return {"ok": True, "action": "none", "reason": reason, "missing": sorted(missing)}
    active = blockers(day)
    hard_blockers = [entry for entry in active if not entry.endswith(":unknown-dead")]
    # Dead unknown executions are reconciled from immutable item/production
    # state. The durable dispatch claim supplies the bounded retry cooldown;
    # live or unverifiable owners still block every action.
    if hard_blockers:
        return {"ok": True, "action": "none", "reason": "execution_blocked", "executions": sorted(set(hard_blockers))}
    ledger = claims or Claims()
    if not ledger.claim(day, action):
        return {"ok": True, "action": "none", "reason": "already_claimed", "phase": action.phase}
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
    ledger.finish(day, action, "dispatched" if action.phase in {"author", "review", "prerequisite"} else "completed")
    return {
        "ok": True, "action": "triggered", "phase": action.phase,
        "series": sorted(barrier.series for barrier in action.barriers),
        "material_hashes": sorted(barrier.material_hash for barrier in action.barriers),
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


def main() -> int:
    try:
        with _exclusive_lock() as acquired:
            if not acquired:
                result = {"ok": True, "action": "none", "reason": "locked"}
            else:
                day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
                result = supervise(day)
    except Exception:
        result = {"ok": False, "action": "none", "reason": "error"}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
