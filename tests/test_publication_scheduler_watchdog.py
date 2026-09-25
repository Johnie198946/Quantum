from __future__ import annotations

import fcntl
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/publication_scheduler_watchdog.py"
SPEC = importlib.util.spec_from_file_location("publication_scheduler_watchdog", SCRIPT)
assert SPEC and SPEC.loader
watchdog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watchdog)

DAY = "2026-09-25"
SERIES = tuple(watchdog.AUTHOR_JOBS)


def summary(*missing: str) -> dict:
    missing_set = set(missing)
    return {
        "today": {
            "date": DAY,
            "expected": 4,
            "published": 4 - len(missing_set),
            "by_series": {
                series: {"published": int(series not in missing_set)} for series in SERIES
            },
        },
        "issues": {
            "missing": [
                {"issue_date": DAY, "series_id": series, "status": "missing"}
                for series in missing
            ],
        },
    }


def counts(**changes: int) -> dict[str, int]:
    value = {job_id: 0 for job_id in watchdog.TARGET_JOBS}
    value.update(changes)
    return value


def timeline(attempts: dict[str, int]) -> dict[str, list[float]]:
    phase_offset = {
        "5a3f2a2eb988": 1.0,
        "171a125ddb63": 1.0,
        watchdog.REVIEW_JOB: 2.0,
        watchdog.RELEASE_JOB: 3.0,
        watchdog.DELIVERY_JOB: 4.0,
    }
    return {
        job_id: [round_number * 10.0 + phase_offset[job_id] for round_number in range(1, count + 1)]
        for job_id, count in attempts.items()
    }


def supervise(
    value: dict,
    attempts: dict[str, int],
    active: list[str] | None = None,
    terminal: dict[str, list[float]] | None = None,
):
    calls = []
    result = watchdog.supervise(
        DAY,
        status=lambda: value,
        executions=lambda _: (attempts, active or [], terminal or timeline(attempts)),
        run_job=lambda job_id: calls.append(job_id),
    )
    return result, calls


def test_complete_and_active_execution_never_trigger():
    delivered = counts(**{watchdog.DELIVERY_JOB: 1})
    result, calls = supervise(summary(), delivered)
    assert (result["reason"], calls) == ("complete", [])

    result, calls = supervise(summary(), counts())
    assert (result["phase"], calls) == ("delivery", [watchdog.DELIVERY_JOB])

    result, calls = supervise(
        summary("ai-history"), counts(), [watchdog.REVIEW_JOB]
    )
    assert (result["reason"], result["job_ids"], calls) == (
        "active", [watchdog.REVIEW_JOB], [],
    )


def test_each_invocation_advances_only_one_phase_and_authors_can_share_it():
    all_missing = summary(*SERIES)
    result, calls = supervise(all_missing, counts())
    assert (result["phase"], result["round"], calls) == (
        "author", 1, ["5a3f2a2eb988", "171a125ddb63"],
    )

    author_once = counts(**{"5a3f2a2eb988": 1, "171a125ddb63": 1})
    result, calls = supervise(all_missing, author_once)
    assert (result["phase"], result["round"], calls) == (
        "review", 1, [watchdog.REVIEW_JOB],
    )

    author_once[watchdog.REVIEW_JOB] = 1
    result, calls = supervise(all_missing, author_once)
    assert (result["phase"], result["round"], calls) == (
        "release", 1, [watchdog.RELEASE_JOB],
    )


def test_missing_series_selects_its_author_group_and_failed_attempts_count():
    attempts = counts(**{"171a125ddb63": 1})
    result, calls = supervise(summary("ai-toolkit"), attempts)
    assert (result["phase"], calls) == ("review", [watchdog.REVIEW_JOB])

    result, calls = supervise(summary("ai-history"), counts())
    assert calls == ["5a3f2a2eb988"]


def test_reviews_before_current_author_do_not_satisfy_review_phase():
    attempts = counts(**{
        "5a3f2a2eb988": 1,
        watchdog.REVIEW_JOB: 3,
        watchdog.RELEASE_JOB: 1,
    })
    terminal = timeline(attempts)
    terminal[watchdog.REVIEW_JOB] = [1.0, 2.0, 3.0]
    terminal[watchdog.RELEASE_JOB] = [4.0]
    terminal["5a3f2a2eb988"] = [5.0]
    result, calls = supervise(summary("ai-history"), attempts, terminal=terminal)
    assert (result["phase"], calls) == ("review", [watchdog.REVIEW_JOB])


def test_three_round_limit_stops_all_work():
    result, calls = supervise(
        summary(*SERIES), {job_id: 3 for job_id in watchdog.TARGET_JOBS}
    )
    assert (result["reason"], calls) == ("round_limit", [])


@pytest.mark.parametrize("mutation", [
    lambda value: value["today"].update(expected=5),
    lambda value: value["issues"].update(missing=[]),
    lambda value: value["today"].update(date="2026-09-24"),
])
def test_invalid_status_fails_closed(mutation):
    value = summary("ai-history")
    mutation(value)
    with pytest.raises(ValueError):
        supervise(value, counts())


def test_trigger_failure_stops_remaining_author_group():
    calls = []

    def fail(job_id: str):
        calls.append(job_id)
        raise RuntimeError("test failure")

    result = watchdog.supervise(
        DAY,
        status=lambda: summary(*SERIES),
        executions=lambda _: (counts(), [], timeline(counts())),
        run_job=fail,
    )
    assert result == {
        "ok": False, "action": "none", "reason": "trigger_failed",
        "phase": "author", "round": 1, "job_ids": [],
    }
    assert calls == ["5a3f2a2eb988"]


def test_commands_are_read_only_status_and_exact_cron_run(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        stdout = json.dumps(summary()) if "--status-only" in command else ""
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(watchdog.subprocess, "run", run)
    assert watchdog._status() == summary()
    watchdog._run_job(watchdog.REVIEW_JOB)
    assert calls[0][0] == [str(watchdog.STATUS_CLIENT), "--status-only"]
    assert calls[1][0] == ["hermes", "cron", "run", watchdog.REVIEW_JOB]


def test_execution_database_is_opened_read_only(tmp_path, monkeypatch):
    database = tmp_path / "executions.db"
    import sqlite3
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE executions (job_id TEXT, status TEXT, claimed_at TEXT, started_at TEXT, finished_at TEXT)"
        )
        connection.executemany("INSERT INTO executions VALUES (?,?,?,?,?)", [
            (watchdog.REVIEW_JOB, "running", DAY + "T10:00:00+08:00", None, None),
            (watchdog.RELEASE_JOB, "failed", DAY + "T09:00:00+08:00", None, DAY + "T09:01:00+08:00"),
            (watchdog.RELEASE_JOB, "completed", "2026-09-24T12:00:00+08:00", None, "2026-09-24T12:01:00+08:00"),
        ])
    monkeypatch.setattr(watchdog, "EXECUTIONS_DB", database)
    attempts, active, terminal = watchdog._executions(DAY)
    assert attempts[watchdog.RELEASE_JOB] == 1
    assert len(terminal[watchdog.RELEASE_JOB]) == 1
    assert active == [watchdog.REVIEW_JOB]


def test_lock_contention_is_non_blocking(tmp_path):
    path = tmp_path / "watchdog.lock"
    with path.open("a+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with watchdog._exclusive_lock(path) as acquired:
            assert acquired is False
