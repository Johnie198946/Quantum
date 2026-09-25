#!/usr/bin/env python3
"""Advance at most one phase of the daily publication pipeline."""
from __future__ import annotations

import fcntl
import json
import sqlite3
import subprocess
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator
from zoneinfo import ZoneInfo

STATUS_CLIENT = Path(__file__).with_name("publication_release_remote.py")
EXECUTIONS_DB = Path.home() / ".hermes/cron/executions.db"
LOCK_FILE = Path.home() / ".hermes/cron/publication-scheduler-watchdog.lock"
AUTHOR_JOBS = {
    "ai-history": "5a3f2a2eb988",
    "ai-practice": "5a3f2a2eb988",
    "concept-fables": "5a3f2a2eb988",
    "ai-toolkit": "171a125ddb63",
}
REVIEW_JOB = "fbd1cd1217d7"
RELEASE_JOB = "1ad93e85cec2"
TARGET_JOBS = (*dict.fromkeys(AUTHOR_JOBS.values()), REVIEW_JOB, RELEASE_JOB)
MAX_ROUNDS = 3


def _status() -> dict:
    completed = subprocess.run(
        [str(STATUS_CLIENT), "--status-only"], text=True, capture_output=True,
        timeout=180, check=False,
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


def _executions(day: str) -> tuple[dict[str, int], list[str]]:
    uri = EXECUTIONS_DB.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as database:
        rows = database.execute(
            f"SELECT job_id, status, claimed_at FROM executions WHERE job_id IN ({','.join('?' * len(TARGET_JOBS))})",
            TARGET_JOBS,
        ).fetchall()
    active = sorted(job_id for job_id, status, _ in rows if status in {"claimed", "running"})
    counts = {job_id: 0 for job_id in TARGET_JOBS}
    for job_id, status, claimed_at in rows:
        if status in {"completed", "failed"} and isinstance(claimed_at, str) and claimed_at[:10] == day:
            counts[job_id] += 1
    return counts, active


def _run_job(job_id: str) -> None:
    completed = subprocess.run(
        ["hermes", "cron", "run", job_id], text=True, capture_output=True,
        timeout=1800, check=False,
    )
    if completed.returncode:
        raise RuntimeError("cron run failed")


def _missing(summary: dict, day: str) -> set[str]:
    today = summary.get("today")
    issues = summary.get("issues")
    if not isinstance(today, dict) or not isinstance(issues, dict) or today.get("date") != day:
        raise ValueError("invalid status summary")
    by_series = today.get("by_series")
    missing_rows = issues.get("missing")
    series = set(AUTHOR_JOBS)
    if today.get("expected") != len(series) or not isinstance(by_series, dict) or set(by_series) != series:
        raise ValueError("unexpected publication series")
    inferred = set()
    for name, item in by_series.items():
        if not isinstance(item, dict) or item.get("published") not in {0, 1}:
            raise ValueError("invalid publication status")
        if item["published"] == 0:
            inferred.add(name)
    if today.get("published") != len(series) - len(inferred) or not isinstance(missing_rows, list):
        raise ValueError("contradictory publication status")
    reported = {
        row.get("series_id") for row in missing_rows
        if isinstance(row, dict) and row.get("issue_date") == day
    }
    if None in reported or reported != inferred:
        raise ValueError("contradictory missing series")
    return inferred


def _next_phase(missing: set[str], counts: dict[str, int]) -> tuple[str, int, list[str]] | None:
    author_jobs = list(dict.fromkeys(AUTHOR_JOBS[series] for series in AUTHOR_JOBS if series in missing))
    for round_number in range(1, MAX_ROUNDS + 1):
        due = [job_id for job_id in author_jobs if counts[job_id] < round_number]
        if due:
            return "author", round_number, due
        if counts[REVIEW_JOB] < round_number:
            return "review", round_number, [REVIEW_JOB]
        if counts[RELEASE_JOB] < round_number:
            return "release", round_number, [RELEASE_JOB]
    return None


def supervise(
    day: str,
    status: Callable[[], dict] = _status,
    executions: Callable[[str], tuple[dict[str, int], list[str]]] = _executions,
    run_job: Callable[[str], None] = _run_job,
) -> dict:
    summary = status()
    missing = _missing(summary, day)
    counts, active = executions(day)
    if set(counts) != set(TARGET_JOBS) or any(not isinstance(value, int) or value < 0 for value in counts.values()):
        raise ValueError("invalid execution counts")
    if active:
        return {"ok": True, "action": "none", "reason": "active", "job_ids": active}
    if not missing:
        return {"ok": True, "action": "none", "reason": "complete"}
    planned = _next_phase(missing, counts)
    if planned is None:
        return {"ok": True, "action": "none", "reason": "round_limit", "missing": sorted(missing)}
    phase, round_number, job_ids = planned
    triggered = []
    for job_id in job_ids:
        try:
            run_job(job_id)
            triggered.append(job_id)
        except Exception:
            return {
                "ok": False, "action": "partial" if triggered else "none", "reason": "trigger_failed",
                "phase": phase, "round": round_number, "job_ids": triggered,
            }
    return {
        "ok": True, "action": "triggered", "phase": phase, "round": round_number,
        "job_ids": triggered, "missing": sorted(missing),
    }


@contextmanager
def _exclusive_lock(path: Path = LOCK_FILE) -> Iterator[bool]:
    with path.open("a+", encoding="utf-8") as lock:
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
    result: dict
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
