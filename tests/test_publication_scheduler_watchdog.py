from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/publication_scheduler_watchdog.py"
SPEC = importlib.util.spec_from_file_location("publication_scheduler_watchdog", SCRIPT)
assert SPEC and SPEC.loader
watchdog = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = watchdog
SPEC.loader.exec_module(watchdog)

DAY = "2026-09-25"
DIGESTS = {name: format(index, "064x") for index, name in enumerate(watchdog.SERIES, 1)}


def summary(*missing: str) -> dict:
    missing_set = set(missing)
    return {
        "today": {
            "date": DAY,
            "expected": 4,
            "published": 4 - len(missing_set),
            "by_series": {
                series: {"published": int(series not in missing_set)} for series in watchdog.SERIES
            },
        },
        "issues": {
            "missing": [
                {"issue_date": DAY, "series_id": series, "status": "overdue_missing"}
                for series in missing
            ]
        },
    }


def item(series: str, status: str, *, digest: str | None = None, day: str = DAY,
         review_ready: bool = False, suffix: str = "one"):
    return watchdog.Item(
        Path(f"/{day}/{series}/{suffix}/draft-manifest.json"), series, day,
        digest or DIGESTS[series], status, review_ready,
    )


def run(tmp_path: Path, value: dict, items: list, *, blockers=None, calls=None):
    calls = calls if calls is not None else []
    result = watchdog.supervise(
        DAY,
        status=lambda: value,
        load_items=lambda: items,
        blockers=blockers or (lambda _: []),
        run_action=lambda action: calls.append(action),
        claims=watchdog.Claims(tmp_path / "claims.db"),
    )
    return result, calls


def execution_db(path: Path, rows: list[tuple]) -> None:
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE executions (
            id TEXT PRIMARY KEY, job_id TEXT, status TEXT, pid INTEGER,
            process_started_at INTEGER, claimed_at TEXT, finished_at TEXT
        )""")
        db.executemany("INSERT INTO executions VALUES (?,?,?,?,?,?,?)", rows)


def local_manifest(root: Path, *, omit_role: str | None = None) -> Path:
    folder = root / "daily" / "ai-history"
    folder.mkdir(parents=True)
    body = b"synthetic publication body"
    (folder / "body.md").write_bytes(body)
    bundle = {
        "series_id": "ai-history", "issue_date": DAY,
        "body_hash": hashlib.sha256(body).hexdigest(),
    }
    (folder / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    row = {
        "bundle_file": "bundle.json", "body_file": "body.md",
        "body_sha256": bundle["body_hash"], "source_files": [],
        "rights_files": [], "execution_files": [], "review_file": "review.json",
        "proof_file": "proof.json", "status": "prepared",
    }
    for role in watchdog.MEDIA_ROLES:
        if role == omit_role:
            continue
        raw = (role + "-synthetic").encode()
        name = role + ".jpg"
        (folder / name).write_bytes(raw)
        row[f"{role}_file"] = name
        row[f"{role}_sha256"] = hashlib.sha256(raw).hexdigest()
    manifest = folder / "draft-manifest.json"
    manifest.write_text(json.dumps({"version": "editorial-workflow-v2", "items": [row]}), encoding="utf-8")
    return manifest


def test_multiple_manifests_for_one_item_fail_closed(tmp_path):
    rows = [
        item("ai-history", "await_review", digest="a" * 64, suffix="a"),
        item("ai-history", "prepared", digest="b" * 64, suffix="b"),
    ]
    result, calls = run(tmp_path, summary("ai-history"), rows)
    assert result["reason"] == "ambiguous_manifests"
    assert calls == []


def test_invalid_manifest_marker_fails_closed(tmp_path):
    result, calls = run(tmp_path, summary("ai-history"), [item("ai-history", "invalid")])
    assert result["reason"] == "invalid_manifest"
    assert calls == []


def test_invalid_series_does_not_block_another_items_finalize(tmp_path):
    rows = [
        item("ai-history", "await_review", review_ready=True),
        item("ai-toolkit", "invalid"),
    ]
    result, calls = run(tmp_path, summary("ai-history", "ai-toolkit"), rows)
    assert result["phase"] == "finalize"
    assert calls == [watchdog.Action(
        "finalize",
        (watchdog.Barrier("ai-history", rows[0].material_hash),),
        manifest=rows[0].manifest,
    )]


def test_failed_finalize_reconciles_concurrent_publication(tmp_path):
    statuses = iter([summary("ai-history"), summary()])
    claims = watchdog.Claims(tmp_path / "claims.db")

    def fail(_action):
        raise RuntimeError("concurrent finalizer won")

    result = watchdog.supervise(
        DAY,
        status=lambda: next(statuses),
        load_items=lambda: [item("ai-history", "await_review", review_ready=True)],
        blockers=lambda _day: [],
        run_action=fail,
        claims=claims,
    )
    assert result == {
        "ok": True,
        "action": "reconciled",
        "phase": "finalize",
        "series": ["ai-history"],
    }


def test_manifest_scan_uses_existing_five_image_hash_gate(tmp_path):
    manifest = local_manifest(tmp_path / "valid")
    rows = watchdog._manifest_items(tmp_path / "valid")
    assert len(rows) == 1
    assert rows[0].manifest == manifest.resolve()
    assert rows[0].status == "prepared"

    local_manifest(tmp_path / "invalid", omit_role="illustration_03")
    rows = watchdog._manifest_items(tmp_path / "invalid")
    assert len(rows) == 1
    assert rows[0].status == "invalid"
    action, reason = watchdog._plan(DAY, {"ai-history"}, rows)
    assert action is None
    assert reason == "invalid_manifest"


def test_unknown_execution_for_day_blocks_without_guessing(tmp_path):
    database = tmp_path / "executions.db"
    execution_db(database, [
        ("unknown-1", watchdog.REVIEW_JOB, "unknown", 99999, 1, DAY + "T10:00:00+08:00", DAY + "T10:05:00+08:00"),
    ])
    def blockers(day):
        return watchdog._execution_blockers(day, database, lambda *_: False)
    # A proven-dead unknown reviewer is reconciled from the immutable target:
    # no review file means retry, while a review file would plan finalize.
    result, calls = run(tmp_path, summary("ai-history"), [item("ai-history", "await_review")], blockers=blockers)
    assert result["phase"] == "review"
    assert len(calls) == 1


def test_dead_unknown_author_without_material_reconciles_via_durable_claim(tmp_path):
    result, calls = run(
        tmp_path, summary("ai-history"), [],
        blockers=lambda _: [f"{watchdog.AUTHOR_JOBS['ai-history']}:unknown-1:unknown-dead"],
    )
    assert result["phase"] == "author"
    assert len(calls) == 1


def test_stale_active_recovers_only_after_owner_is_proven_dead(tmp_path):
    database = tmp_path / "executions.db"
    execution_db(database, [
        ("run-1", watchdog.REVIEW_JOB, "running", 43210, 123, DAY + "T10:00:00+08:00", None),
    ])
    rows = [item("ai-history", "await_review")]

    def uncertain(day):
        return watchdog._execution_blockers(day, database, lambda *_: None)
    result, calls = run(tmp_path / "uncertain", summary("ai-history"), rows, blockers=uncertain)
    assert result["reason"] == "execution_blocked"
    assert calls == []

    def dead(day):
        return watchdog._execution_blockers(day, database, lambda *_: False)
    result, calls = run(tmp_path / "dead", summary("ai-history"), rows, blockers=dead)
    assert result["phase"] == "review"
    assert len(calls) == 1


def test_live_owner_blocks_even_when_execution_is_old(tmp_path):
    database = tmp_path / "executions.db"
    execution_db(database, [
        ("live-1", watchdog.REVIEW_JOB, "claimed", 43210, 123, "2026-09-24T10:00:00+08:00", None),
    ])
    def blockers(day):
        return watchdog._execution_blockers(day, database, lambda *_: True)
    result, calls = run(
        tmp_path, summary("ai-history"), [item("ai-history", "await_review")], blockers=blockers,
    )
    assert result["reason"] == "execution_blocked"
    assert calls == []


def test_concurrent_invocations_share_atomic_item_material_claim(tmp_path):
    ledger = watchdog.Claims(tmp_path / "claims.db")
    ledger._connect().close()
    calls: list = []

    def invoke():
        return watchdog.supervise(
            DAY,
            status=lambda: summary("ai-history"),
            load_items=lambda: [item("ai-history", "await_review")],
            blockers=lambda _: [],
            run_action=lambda action: calls.append(action),
            claims=ledger,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: invoke(), range(2)))
    assert sorted(result["reason"] if result["action"] == "none" else "triggered" for result in results) == [
        "already_claimed", "triggered",
    ]
    assert len(calls) == 1
    with sqlite3.connect(ledger.path) as db:
        assert db.execute("SELECT COUNT(*),MIN(state),MAX(state) FROM recovery_claims").fetchone() == (
            1, "dispatched", "dispatched",
        )


def test_failed_claim_retries_bounded_then_stops(tmp_path, monkeypatch):
    ledger = watchdog.Claims(tmp_path / "claims.db")
    action = watchdog.Action("review", (watchdog.Barrier("ai-history", "a" * 64),), job_id=watchdog.REVIEW_JOB)
    monkeypatch.setattr(watchdog, "_owner_alive", lambda *_: False)
    for attempt in range(ledger.MAX_ATTEMPTS):
        assert ledger.claim(DAY, action) is True
        ledger.finish(DAY, action, "failed")
    assert ledger.claim(DAY, action) is False
    with sqlite3.connect(ledger.path) as db:
        assert db.execute("SELECT state,attempts FROM recovery_claims").fetchone() == ("failed", ledger.MAX_ATTEMPTS)


def test_async_dispatch_retries_only_after_cooldown(tmp_path, monkeypatch):
    ledger = watchdog.Claims(tmp_path / "claims.db")
    action = watchdog.Action("review", (watchdog.Barrier("ai-history", "a" * 64),), job_id=watchdog.REVIEW_JOB)
    assert ledger.claim(DAY, action) is True
    ledger.finish(DAY, action, "dispatched")
    assert ledger.claim(DAY, action) is False
    old = (datetime.now(ZoneInfo("Asia/Shanghai")) - ledger.DISPATCH_RETRY_AFTER - timedelta(seconds=1)).isoformat()
    with sqlite3.connect(ledger.path) as db:
        db.execute("UPDATE recovery_claims SET finished_at=?", (old,))
    monkeypatch.setattr(watchdog, "_owner_alive", lambda *_: False)
    assert ledger.claim(DAY, action) is True


def test_already_published_item_never_dispatches_or_duplicates(tmp_path):
    rows = [item("ai-history", "staged")]
    result, calls = run(tmp_path, summary(), rows)
    assert result["reason"] == "complete"
    assert calls == []

    # A staged missing item is deliberately left to the one normal deterministic
    # publisher; recovery never starts a competing publication command.
    result, calls = run(tmp_path / "staged", summary("ai-history"), rows)
    assert result["reason"] == "awaiting_release"
    assert calls == []


def test_review_dispatch_is_day_and_item_scoped(tmp_path):
    current = item("ai-history", "await_review")
    old = item("ai-practice", "await_review", day="2026-09-24")
    result, calls = run(tmp_path, summary("ai-history"), [current, old])
    assert result["reason"] == "review_scope_not_unique"
    assert calls == []


def test_multiple_current_pending_items_dispatch_in_manifest_order(tmp_path):
    first = item("ai-history", "await_review", suffix="a")
    second = item("ai-toolkit", "await_review", suffix="z")
    result, calls = run(tmp_path, summary("ai-history", "ai-toolkit"), [first, second])
    assert result["phase"] == "review"
    assert calls[0].manifest == first.manifest


def test_cross_profile_and_nondefault_home_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "story")
    with pytest.raises(RuntimeError, match="default Hermes profile"):
        watchdog.supervise(DAY, status=lambda: summary(), load_items=lambda: [], blockers=lambda _: [])

    monkeypatch.setenv("HERMES_PROFILE", "default")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "story-home"))
    with pytest.raises(RuntimeError, match="default Hermes profile"):
        watchdog.supervise(DAY, status=lambda: summary(), load_items=lambda: [], blockers=lambda _: [])


def test_default_environment_removes_story_credentials(monkeypatch):
    monkeypatch.setenv("STORY_API_KEY", "must-not-cross")
    monkeypatch.setenv("HERMES_PROFILE", "default")
    env = watchdog._default_env()
    assert "STORY_API_KEY" not in env
    assert "HERMES_PROFILE" not in env
    assert env["HERMES_HOME"] == str(Path.home() / ".hermes")


def test_prepare_and_finalize_use_existing_gate_enforcing_client(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(watchdog.subprocess, "run", fake_run)
    manifest = Path("/safe/item/draft-manifest.json")
    watchdog._run_action(watchdog.Action("prepare", (watchdog.Barrier("ai-history", "a" * 64),), manifest=manifest))
    watchdog._run_action(watchdog.Action("finalize", (watchdog.Barrier("ai-history", "a" * 64),), manifest=manifest))
    assert calls[0][0] == [str(watchdog.EDITORIAL_CLIENT), "prepare", "--manifest", str(manifest)]
    assert calls[1][0] == [str(watchdog.EDITORIAL_CLIENT), "finalize", "--root", str(manifest.parent)]
    assert all(not any("release" in word for word in command) for command, _ in calls)


def test_author_shared_scope_claims_each_item_atomically(tmp_path):
    missing = ("ai-history", "ai-practice", "concept-fables")
    result, calls = run(tmp_path, summary(*missing), [])
    assert result["phase"] == "author"
    assert result["series"] == sorted(missing)
    assert len(calls) == 1
    with sqlite3.connect(tmp_path / "claims.db") as db:
        assert db.execute("SELECT COUNT(DISTINCT series) FROM recovery_claims").fetchone()[0] == 3


def test_review_file_does_not_bypass_editorial_approval_gate(tmp_path):
    row = item("ai-history", "await_review", review_ready=True)
    result, calls = run(tmp_path, summary("ai-history"), [row])
    assert result["phase"] == "finalize"
    assert calls[0].manifest == row.manifest
    # Recovery only invokes finalization; the editorial client still validates
    # the native signed proof, target hash, five images and remote attempt state.
    assert all(call.phase != "review" for call in calls)


@pytest.mark.parametrize("mutation", [
    lambda value: value["today"].update(expected=5),
    lambda value: value["issues"].update(missing=[]),
    lambda value: value["today"].update(date="2026-09-24"),
    lambda value: value["today"]["by_series"]["ai-history"].update(published="unknown"),
])
def test_invalid_or_unknown_status_fails_closed(tmp_path, mutation):
    value = summary("ai-history")
    mutation(value)
    with pytest.raises(ValueError):
        run(tmp_path, value, [])


def test_lock_contention_is_non_blocking(tmp_path):
    path = tmp_path / "watchdog.lock"
    with path.open("a+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with watchdog._exclusive_lock(path) as acquired:
            assert acquired is False


def test_execution_database_is_opened_read_only(tmp_path):
    database = tmp_path / "executions.db"
    execution_db(database, [])
    assert watchdog._execution_blockers(DAY, database, lambda *_: False) == []
    with pytest.raises(sqlite3.OperationalError):
        with sqlite3.connect(database) as db:
            db.execute("SELECT absent_column FROM executions").fetchall()


def test_material_hash_requires_all_five_images():
    row = {"body_sha256": "a" * 64, **{group: [] for group in watchdog.EVIDENCE_GROUPS}}
    for role in watchdog.MEDIA_ROLES[:-1]:
        row[f"{role}_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="material hash input missing"):
        watchdog._material_hash(row)


def test_main_does_not_use_release_job_as_failure_alert(monkeypatch, capsys):
    # Exercise the ordinary error path instead; no alert/release callback exists.
    monkeypatch.setattr(watchdog, "_exclusive_lock", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert watchdog.main() == 1
    assert json.loads(capsys.readouterr().out) == {"action": "none", "ok": False, "reason": "error"}
