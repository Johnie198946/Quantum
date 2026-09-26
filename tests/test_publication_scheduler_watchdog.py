from __future__ import annotations

import copy
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

ACTIVATED_SERIES = copy.deepcopy(watchdog.SERIES)
DAY = "2026-09-25"
DIGESTS = {name: format(index, "064x") for index, name in enumerate(watchdog.SERIES, 1)}


def install_catalog(monkeypatch, catalog):
    # Independent dictionaries prevent tests mutating the application catalog.
    catalog = copy.deepcopy(catalog)
    monkeypatch.setattr(watchdog, "SERIES", catalog)
    monkeypatch.setattr(watchdog, "AUTHOR_JOBS", {name: spec.get("author_job_id") for name, spec in catalog.items()})
    monkeypatch.setattr(watchdog, "PLATFORM_AUTHOR_SERIES", frozenset(
        name for name, spec in catalog.items()
        if spec.get("workflow_schedule_id") or (spec.get("assets_job_id") and not spec.get("author_job_id"))))
    monkeypatch.setattr(watchdog, "TARGET_JOBS", tuple(dict.fromkeys(
        spec[field] for spec in catalog.values()
        for field in ("author_job_id", "assets_job_id", "review_job_id", "prerequisite_job_id") if spec.get(field))))


@pytest.fixture(autouse=True)
def runnable_job_registry(tmp_path, monkeypatch):
    # Explicit historical baseline; production topics, dates and routing evolve.
    baseline = {name: {"kind": "daily", "enabled": True, "release_times": ["12:00"],
                       "author_job_id": "5a3f2a2eb988", "review_job_id": "fbd1cd1217d7"}
                for name in ("ai-history", "ai-practice", "concept-fables", "ai-toolkit")}
    baseline["ai-toolkit"].update(author_job_id="", assets_job_id="171a125ddb63", prerequisite_job_id="b8c4c5e40bb1")
    install_catalog(monkeypatch, baseline)
    monkeypatch.setattr(watchdog, "REVIEW_JOB", "fbd1cd1217d7")
    monkeypatch.setattr(watchdog, "PREREQUISITE_JOB", "b8c4c5e40bb1")
    monkeypatch.delenv("PUBLICATION_AI_TOOLKIT_SCHEDULE_ID", raising=False)
    monkeypatch.delenv("HERMES_PROFILE", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"jobs": [{"id": job_id, "enabled": True} for job_id in watchdog.TARGET_JOBS]}))
    monkeypatch.setattr(watchdog, "JOBS_FILE", path)
    monkeypatch.setattr(watchdog, "PROFILES_ROOT", tmp_path / "profiles")


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


def test_staged_item_may_be_absent_from_missing_issue_rows():
    value = summary(*watchdog.SERIES)
    value["issues"]["missing"] = [
        row for row in value["issues"]["missing"]
        if row["series_id"] != "concept-fables"
    ]
    assert watchdog._missing(value, DAY) == set(watchdog.SERIES)


def test_missing_issue_row_cannot_claim_a_published_series():
    value = summary("ai-history")
    value["issues"]["missing"].append({
        "issue_date": DAY,
        "series_id": "concept-fables",
        "status": "overdue_missing",
    })
    with pytest.raises(ValueError, match="contradictory publication status"):
        watchdog._missing(value, DAY)


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
    assert ledger.MAX_ATTEMPTS == 6
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


def test_default_env_pins_repository_and_removes_profile_overrides(monkeypatch):
    monkeypatch.chdir(SCRIPT.parents[1])
    monkeypatch.setenv("PYTHONPATH", "/tmp/untrusted")
    monkeypatch.setenv("STORY_PUBLICATION_OPERATOR_IDENTITY_FILE", "/tmp/story-key")
    env = watchdog._default_env()
    assert env["PYTHONPATH"] == str(SCRIPT.parents[1])
    assert env["HERMES_HOME"] == str(Path.home() / ".hermes")
    assert "HERMES_PROFILE" not in env
    assert "STORY_PUBLICATION_OPERATOR_IDENTITY_FILE" not in env


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


def test_detached_dispatch_returns_after_persisted_live_execution(tmp_path, monkeypatch):
    database = tmp_path / "executions.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE executions (id TEXT, job_id TEXT, status TEXT, started_at TEXT)")
        db.execute(
            "INSERT INTO executions VALUES (?,?,?,?)",
            ("dispatch-1", watchdog.REVIEW_JOB, "running", "9999-01-01T00:00:00+08:00"),
        )
    monkeypatch.setattr(watchdog, "EXECUTIONS_DB", database)
    class Process:
        def poll(self):
            return None

        def terminate(self):
            raise AssertionError("persisted owner must not be terminated")

    monkeypatch.setattr(watchdog.subprocess, "Popen", lambda command, **kwargs: Process())
    watchdog._dispatch_job(watchdog.REVIEW_JOB)


def test_zero_exit_without_persisted_execution_fails_closed(tmp_path, monkeypatch):
    database = tmp_path / "executions.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE executions (id TEXT, job_id TEXT, status TEXT, started_at TEXT)")
    monkeypatch.setattr(watchdog, "EXECUTIONS_DB", database)
    class Process:
        def poll(self):
            return 0

        def terminate(self):
            raise AssertionError("exited process need not be terminated")

    monkeypatch.setattr(watchdog.subprocess, "Popen", lambda command, **kwargs: Process())
    with pytest.raises(watchdog.ActionFailure, match="dispatch_not_persisted"):
        watchdog._dispatch_job(watchdog.REVIEW_JOB)


def test_unknown_execution_is_not_accepted_as_dispatch_success(tmp_path, monkeypatch):
    database = tmp_path / "executions.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE executions (id TEXT, job_id TEXT, status TEXT, started_at TEXT)")
        db.execute(
            "INSERT INTO executions VALUES (?,?,?,?)",
            ("dispatch-unknown", watchdog.REVIEW_JOB, "unknown", "9999-01-01T00:00:00+08:00"),
        )
    monkeypatch.setattr(watchdog, "EXECUTIONS_DB", database)

    class Process:
        def poll(self):
            return 0

        def terminate(self):
            raise AssertionError("exited process need not be terminated")

    monkeypatch.setattr(watchdog.subprocess, "Popen", lambda command, **kwargs: Process())
    with pytest.raises(watchdog.ActionFailure, match="dispatch_not_persisted"):
        watchdog._dispatch_job(watchdog.REVIEW_JOB)


def test_action_timeout_is_classified_for_bounded_retry(tmp_path):
    claims = watchdog.Claims(tmp_path / "claims.db")

    def timeout(_action):
        raise watchdog.ActionFailure("action_timeout")

    result = watchdog.supervise(
        DAY,
        status=lambda: summary("ai-history"),
        load_items=lambda: [item("ai-history", "prepared")],
        blockers=lambda _: [],
        run_action=timeout,
        claims=claims,
    )
    assert result == {
        "ok": False,
        "action": "none",
        "reason": "action_timeout",
        "phase": "prepare",
    }
    with sqlite3.connect(claims.path) as db:
        assert db.execute("SELECT state,attempts FROM recovery_claims").fetchone() == ("failed", 1)


def test_regular_revision_precedes_toolkit_prerequisite_retry(tmp_path):
    barrier = watchdog.Barrier("ai-toolkit", "f" * 64)
    calls = []
    result = watchdog.supervise(
        DAY,
        status=lambda: summary(*watchdog.SERIES),
        load_items=lambda: [
            item("ai-history", "staged"),
            item("ai-practice", "rejected"),
            item("concept-fables", "staged"),
        ],
        blockers=lambda _: [],
        prerequisite=lambda _: barrier,
        run_action=lambda action: calls.append(action),
        claims=watchdog.Claims(tmp_path / "claims.db"),
    )
    assert result["phase"] == "author"
    assert result["series"] == ["ai-practice"]
    assert calls[0].job_id == watchdog.AUTHOR_JOBS["ai-practice"]


def test_toolkit_blocked_prerequisite_recovers_supply_before_author(tmp_path, monkeypatch):
    barrier = watchdog.Barrier("ai-toolkit", "f" * 64)
    calls = []
    database = tmp_path / "executions.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE executions (id TEXT, job_id TEXT, status TEXT, started_at TEXT)")
        db.execute(
            "INSERT INTO executions VALUES (?,?,?,?)",
            ("dispatch-prerequisite", watchdog.PREREQUISITE_JOB, "running", "9999-01-01T00:00:00+08:00"),
        )

    def fake_run(command, **kwargs):
        if command[0] == "ps":
            return subprocess.CompletedProcess(command, 0, "Thu Sep 25 09:00:00 2026\n", "")
        raise AssertionError(command)

    class Process:
        def poll(self):
            return None

        def terminate(self):
            raise AssertionError("persisted owner must not be terminated")

    def fake_popen(command, **kwargs):
        calls.append(command)
        return Process()

    monkeypatch.setattr(watchdog, "EXECUTIONS_DB", database)
    monkeypatch.setattr(watchdog.subprocess, "run", fake_run)
    monkeypatch.setattr(watchdog.subprocess, "Popen", fake_popen)
    result = watchdog.supervise(
        DAY,
        status=lambda: summary("ai-toolkit"),
        load_items=lambda: [],
        blockers=lambda _: [],
        prerequisite=lambda _: barrier,
        run_action=watchdog._run_action,
        claims=watchdog.Claims(tmp_path / "claims.db"),
    )
    assert result["phase"] == "prerequisite"
    assert calls[-1:] == [
        ["hermes", "cron", "run", watchdog.PREREQUISITE_JOB],
    ]


def test_toolkit_collection_requires_one_usable_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(watchdog, "OUTPUT_ROOT", tmp_path)
    receipt = tmp_path / "prerequisites/ai-toolkit" / f"{DAY}.json"
    receipt.parent.mkdir(parents=True)
    value = {
        "status": "CONTENT_AVAILABLE",
        "usable_content_available": False,
        "selected_candidates": [],
    }
    receipt.write_text(json.dumps(value), encoding="utf-8")
    assert watchdog._toolkit_prerequisite_barrier(DAY) is not None

    value["usable_content_available"] = True
    value["selected_candidates"] = [{"id": "selected-one"}]
    receipt.write_text(json.dumps(value), encoding="utf-8")
    assert watchdog._toolkit_prerequisite_barrier(DAY) is None


def test_toolkit_collection_does_not_require_unselected_categories_or_compilation(tmp_path, monkeypatch):
    monkeypatch.setattr(watchdog, "OUTPUT_ROOT", tmp_path)
    receipt = tmp_path / "prerequisites/ai-toolkit" / f"{DAY}.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({
        "status": "CONTENT_AVAILABLE",
        "usable_content_available": True,
        "selected_candidates": [{"id": "selected-one"}],
        "non_blocking_unselected": [{"id": "failed-two", "status": "failed"}],
        "compilation_readback": {"compile_verified": False, "wiki_compiled": False},
    }), encoding="utf-8")
    assert watchdog._toolkit_prerequisite_barrier(DAY) is None


def test_toolkit_author_is_owned_by_platform_workflow_not_local_cron(tmp_path):
    result, calls = run(tmp_path, summary("ai-toolkit"), [])
    assert result["reason"] == "awaiting_platform_author"
    assert result["action"] == "none"
    assert calls == []


def workflow_handoff(tmp_path: Path, status: str = "waiting_assets"):
    directory = tmp_path / "ai-toolkit-artifact-1"
    return watchdog.Handoff(directory, DAY, "wfa_artifact1", "f" * 64, status)


def workflow_item(tmp_path: Path, status: str, *, review_ready: bool = False):
    return watchdog.Item(
        tmp_path / "ai-toolkit-artifact-1/draft-manifest.json",
        "ai-toolkit",
        DAY,
        "e" * 64,
        status,
        review_ready,
    )


def test_handoff_state_scan_is_strict_and_material_bound(tmp_path):
    directory = tmp_path / "ai-toolkit-artifact-1"
    directory.mkdir()
    state = {
        "version": "publication-workflow-consumption-v1",
        "status": "waiting_assets",
        "execution_id": "wfe_execution1",
        "schedule_id": "wfsched_schedule1",
        "series_id": "ai-toolkit",
        "issue_date": DAY,
        "artifact_id": "wfa_artifact1",
        "artifact_sha256": "a" * 64,
        "envelope_sha256": "b" * 64,
        "next_action": "assets",
    }
    path = directory / "workflow-handoff-state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    rows = watchdog._handoff_items(tmp_path)
    assert len(rows) == 1 and rows[0].status == "waiting_assets"
    first_hash = rows[0].material_hash

    state["artifact_sha256"] = "c" * 64
    path.write_text(json.dumps(state), encoding="utf-8")
    assert watchdog._handoff_items(tmp_path)[0].material_hash != first_hash

    state["artifact_sha256"] = "not-a-hash"
    path.write_text(json.dumps(state), encoding="utf-8")
    assert watchdog._handoff_items(tmp_path)[0].status == "invalid"


def test_enabled_platform_chain_fetches_then_dispatches_only_assets(tmp_path):
    action, reason = watchdog._plan(
        DAY, {"ai-toolkit"}, [], handoffs=[], platform_enabled=True
    )
    assert reason == "ready"
    assert action is not None and action.phase == "handoff_fetch"

    handoff = workflow_handoff(tmp_path)
    action, reason = watchdog._plan(
        DAY, {"ai-toolkit"}, [], handoffs=[handoff], platform_enabled=True
    )
    assert reason == "ready"
    assert action is not None and action.phase == "assets"
    assert action.job_id == watchdog.SERIES["ai-toolkit"]["assets_job_id"]


@pytest.mark.parametrize(
    ("manifest_status", "review_ready", "expected_phase"),
    [
        ("prepared", False, "prepare"),
        ("await_review", False, "review"),
        ("await_review", True, "finalize"),
        ("staged", False, "handoff_acknowledge"),
        ("rejected", True, "handoff_revision"),
    ],
)
def test_enabled_platform_chain_preserves_review_and_workflow_gates(
    tmp_path, manifest_status, review_ready, expected_phase
):
    row = workflow_item(tmp_path, manifest_status, review_ready=review_ready)
    action, reason = watchdog._plan(
        DAY,
        {"ai-toolkit"},
        [row],
        handoffs=[workflow_handoff(tmp_path)],
        platform_enabled=True,
    )
    assert reason == "ready"
    assert action is not None and action.phase == expected_phase
    assert action.manifest == row.manifest


def test_revision_requested_handoff_polls_for_replacement_artifact(tmp_path):
    rejected = workflow_item(tmp_path, "rejected", review_ready=True)
    action, reason = watchdog._plan(
        DAY,
        {"ai-toolkit"},
        [rejected],
        handoffs=[workflow_handoff(tmp_path, "revision_requested")],
        platform_enabled=True,
    )
    assert reason == "ready"
    assert action is not None and action.phase == "handoff_fetch"


def test_fetch_waiting_for_platform_is_nonfatal_and_does_not_consume_claim(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PUBLICATION_AI_TOOLKIT_SCHEDULE_ID", "wfsched_schedule1")
    calls = []

    def pending(action):
        calls.append(action)
        raise watchdog.ActionPending("awaiting_platform_schedule")

    result = watchdog.supervise(
        DAY,
        status=lambda: summary("ai-toolkit"),
        load_items=lambda: [],
        load_handoffs=lambda: [],
        blockers=lambda _: [],
        prerequisite=lambda _: None,
        run_action=pending,
        claims=watchdog.Claims(tmp_path / "claims.db"),
    )
    assert result == {
        "ok": True,
        "action": "none",
        "reason": "awaiting_platform_schedule",
        "phase": "handoff_fetch",
    }
    assert len(calls) == 1
    assert not (tmp_path / "claims.db").exists()


def test_handoff_fetch_parser_distinguishes_waiting_from_invalid_result(monkeypatch):
    action = watchdog.Action(
        "handoff_fetch", (watchdog.Barrier("ai-toolkit", "f" * 64),)
    )
    monkeypatch.setattr(
        watchdog.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, '{"available":false,"status":"waiting_workflow"}\n', ""
        ),
    )
    with pytest.raises(watchdog.ActionPending, match="awaiting_platform_schedule"):
        watchdog._run_action(action)

    monkeypatch.setattr(
        watchdog.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "{}\n", ""),
    )
    with pytest.raises(watchdog.ActionFailure, match="handoff_fetch_invalid_result"):
        watchdog._run_action(action)


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
    assert watchdog.main([]) == 1
    assert json.loads(capsys.readouterr().out) == {"action": "none", "ok": False, "reason": "error"}


@pytest.mark.parametrize(("patch", "reason"), [
    ({"state": "paused", "enabled": True}, "job_paused"),
    ({"paused_at": "2026-09-25T08:00:00+08:00"}, "job_paused"),
    ({"enabled": False}, "job_disabled"),
])
def test_native_pause_flags_prevent_claim_and_dispatch(tmp_path, patch, reason):
    watchdog.JOBS_FILE.write_text(json.dumps({"jobs": [{"id": watchdog.REVIEW_JOB, **patch}]}))
    result, calls = run(tmp_path, summary("ai-history"), [item("ai-history", "await_review")])
    assert result["ok"] is False and result["reason"] == reason
    assert calls == []
    assert not (tmp_path / "claims.db").exists()


def test_missing_cron_job_is_structured_before_claim(tmp_path):
    watchdog.JOBS_FILE.write_text('{"jobs":[]}')
    result, calls = run(tmp_path, summary("ai-history"), [item("ai-history", "await_review")])
    assert result["reason"] == "job_missing" and result["job_id"] == watchdog.REVIEW_JOB
    assert calls == []


def test_exhaustion_is_actionable_and_exact_rearm_preserves_history(tmp_path, monkeypatch):
    ledger = watchdog.Claims(tmp_path / "claims.db")
    row = item("ai-history", "await_review")
    action, _ = watchdog._plan(DAY, {"ai-history"}, [row])
    for _ in range(ledger.MAX_ATTEMPTS):
        assert ledger.claim(DAY, action)
        ledger.finish(DAY, action, "failed")
    result, calls = run(tmp_path, summary("ai-history"), [row])
    assert result["ok"] is False and result["reason"] == "retry_exhausted"
    assert calls == []
    key = result["idempotency_keys"][0]
    monkeypatch.setattr(watchdog, "_owner_alive", lambda *_: False)
    with pytest.raises(ValueError, match="compare-and-set"):
        ledger.rearm(key, 5, row.material_hash, "fixed configuration", lambda _: [])
    with pytest.raises(ValueError, match="compare-and-set"):
        ledger.rearm(key, 6, "f" * 64, "fixed configuration", lambda _: [])
    ledger.rearm(key, 6, row.material_hash, "fixed job configuration", lambda _: [])
    result, calls = run(tmp_path, summary("ai-history"), [row])
    assert result["action"] == "triggered" and len(calls) == 1
    with sqlite3.connect(ledger.path) as db:
        attempts, history = db.execute("SELECT attempts,rearm_history FROM recovery_claims").fetchone()
    assert attempts == 1
    audit = json.loads(history)[0]
    assert audit["previous"]["attempts"] == 6 and audit["previous"]["state"] == "failed"
    assert audit["reason"] == "fixed job configuration"


@pytest.mark.parametrize("state", ["running", "dispatched", "completed"])
def test_rearm_rejects_active_or_completed_claim(tmp_path, monkeypatch, state):
    ledger = watchdog.Claims(tmp_path / "claims.db")
    action = watchdog.Action("review", (watchdog.Barrier("ai-history", "a" * 64),))
    assert ledger.claim(DAY, action)
    if state != "running":
        ledger.finish(DAY, action, state)
    monkeypatch.setattr(watchdog, "_owner_alive", lambda *_: False)
    with pytest.raises(ValueError, match="failed claim"):
        ledger.rearm(ledger.key(DAY, "review", action.barriers[0]), 1, "a" * 64, "repair", lambda _: [])


def test_rearm_rejects_live_failed_owner_and_execution(tmp_path, monkeypatch):
    ledger = watchdog.Claims(tmp_path / "claims.db")
    action = watchdog.Action("review", (watchdog.Barrier("ai-history", "a" * 64),))
    assert ledger.claim(DAY, action)
    ledger.finish(DAY, action, "failed")
    key = ledger.key(DAY, "review", action.barriers[0])
    monkeypatch.setattr(watchdog, "_owner_alive", lambda *_: True)
    with pytest.raises(ValueError, match="proven-dead"):
        ledger.rearm(key, 1, "a" * 64, "repair", lambda _: [])
    monkeypatch.setattr(watchdog, "_owner_alive", lambda *_: False)
    with pytest.raises(ValueError, match="execution"):
        ledger.rearm(key, 1, "a" * 64, "repair", lambda _: ["job:execution:live"])


def test_exhausted_item_does_not_block_unrelated_preparation(tmp_path):
    ledger = watchdog.Claims(tmp_path / "claims.db")
    first = item("ai-history", "await_review", review_ready=True)
    other = item("ai-practice", "prepared")
    action, _ = watchdog._plan(DAY, {"ai-history"}, [first])
    for _ in range(ledger.MAX_ATTEMPTS):
        assert ledger.claim(DAY, action)
        ledger.finish(DAY, action, "failed")
    result, calls = run(tmp_path, summary("ai-history", "ai-practice"), [first, other])
    assert result["phase"] == "prepare" and calls[0].manifest == other.manifest


def test_paused_author_does_not_block_another_series(tmp_path, monkeypatch):
    monkeypatch.setitem(watchdog.SERIES, "ai-practice", {**watchdog.SERIES["ai-practice"], "author_job_id": "new-author"})
    monkeypatch.setitem(watchdog.AUTHOR_JOBS, "ai-practice", "new-author")
    watchdog.JOBS_FILE.write_text(json.dumps({"jobs": [
        {"id": watchdog.AUTHOR_JOBS["ai-history"], "state": "paused"},
        {"id": "new-author", "enabled": True},
    ]}))
    result, calls = run(tmp_path, summary("ai-history", "ai-practice"), [])
    assert result["phase"] == "author" and calls[0].job_id == "new-author"


def test_multi_slot_readback_and_claim_identity(tmp_path, monkeypatch):
    monkeypatch.setitem(watchdog.SERIES, "ai-history", {**watchdog.SERIES["ai-history"], "release_times": ["09:00", "12:00", "18:00"]})
    value = summary("ai-history")
    value["today"].update(expected=6, published=4)
    value["today"]["by_series"]["ai-history"] = {"published": 1, "expected": 3, "slots": [
        {"issue_key": DAY + "T09:00", "published": 1},
        {"issue_key": DAY, "published": 0},
        {"issue_key": DAY + "T18:00", "published": 0},
    ]}
    rows = [watchdog.Item(Path("/noon/draft-manifest.json"), "ai-history", DAY, "a" * 64, "staged", issue_key=DAY),
            watchdog.Item(Path("/evening/draft-manifest.json"), "ai-history", DAY, "b" * 64, "prepared", issue_key=DAY + "T18:00")]
    result, calls = run(tmp_path, value, rows)
    assert result["phase"] == "prepare" and calls[0].manifest == rows[1].manifest
    assert calls[0].barriers[0].issue_key == DAY + "T18:00"
    with sqlite3.connect(tmp_path / "claims.db") as db:
        assert DAY + "T18:00" in db.execute("SELECT idempotency_key FROM recovery_claims").fetchone()[0]


def test_disallowed_role_profile_is_blocked_not_sent_to_default_cron(tmp_path, monkeypatch):
    monkeypatch.setitem(watchdog.SERIES, "ai-history", {**watchdog.SERIES["ai-history"], "author_profile": "supervision"})
    with pytest.raises(watchdog.ActionFailure, match="job_profile_not_allowed_for_role"):
        run(tmp_path, summary("ai-history"), [])
    calls = []
    assert calls == [] and not (tmp_path / "claims.db").exists()


def test_future_enabled_series_does_not_block_todays_recovery(tmp_path, monkeypatch):
    value = summary("ai-history")
    monkeypatch.setitem(watchdog.SERIES, "future-topic", {
        "kind": "daily", "enabled": True, "starts_on": "2099-01-01", "release_times": ["09:00", "18:00"],
    })
    assert watchdog._missing(value, DAY) == {"ai-history"}
    result, calls = run(tmp_path, value, [item("ai-history", "prepared")])
    assert result["phase"] == "prepare" and len(calls) == 1


def test_final_dispatched_attempt_is_pending_during_cooldown(tmp_path):
    ledger = watchdog.Claims(tmp_path / "claims.db")
    row = item("ai-history", "await_review")
    action, _ = watchdog._plan(DAY, {"ai-history"}, [row])
    for _ in range(ledger.MAX_ATTEMPTS - 1):
        assert ledger.claim(DAY, action)
        ledger.finish(DAY, action, "failed")
    assert ledger.claim(DAY, action)
    ledger.finish(DAY, action, "dispatched")
    result, calls = run(tmp_path, summary("ai-history"), [row])
    assert result["ok"] is True and result["reason"] == "already_claimed"
    assert calls == []


@pytest.mark.parametrize(("phase", "profile"), [("author", "story"), ("review", "supervision")])
def test_profile_preflight_uses_own_registry(tmp_path, monkeypatch, phase, profile):
    monkeypatch.setitem(watchdog.SERIES, "ai-history", {**watchdog.SERIES["ai-history"], f"{phase}_profile": profile})
    job_id = watchdog.SERIES["ai-history"][f"{phase}_job_id"]
    action = watchdog.Action(phase, (watchdog.Barrier("ai-history", "a" * 64),), job_id=job_id)
    path = watchdog.PROFILES_ROOT / profile / "cron/jobs.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"jobs": [{"id": job_id, "state": "paused"}]}))
    with pytest.raises(watchdog.ActionFailure, match="job_paused"):
        watchdog._job_preflight(action)
    path.write_text(json.dumps({"jobs": [{"id": job_id, "enabled": True}]}))
    watchdog.JOBS_FILE.write_text('{"jobs":[]}')
    watchdog._job_preflight(action)


@pytest.mark.parametrize("profile", ["story", "supervision"])
def test_dispatch_selects_profile_and_reads_its_execution_ledger(tmp_path, monkeypatch, profile):
    job_id = "profile-job"
    path = watchdog.PROFILES_ROOT / profile / "cron/executions.db"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE executions (id TEXT,job_id TEXT,status TEXT,started_at TEXT)")
        db.execute("INSERT INTO executions VALUES (?,?,?,?)", ("run", job_id, "running", "9999-01-01T00:00:00+08:00"))
    calls = []
    class Process:
        def poll(self):
            return None
        def terminate(self):
            raise AssertionError("Accepted owner must keep running")
    monkeypatch.setenv("STORY_API_KEY", "must-not-copy")
    monkeypatch.setattr(watchdog.subprocess, "Popen", lambda command, **kw: calls.append((command, kw)) or Process())
    watchdog._dispatch_job(job_id, profile)
    assert calls[0][0] == ["hermes", "-p", profile, "cron", "run", job_id]
    assert "STORY_API_KEY" not in calls[0][1]["env"]
    assert calls[0][1]["env"]["HERMES_HOME"] == str(Path.home() / ".hermes")


def test_profile_execution_blockers_cannot_collide_with_default_job_ids(tmp_path, monkeypatch):
    monkeypatch.setitem(watchdog.SERIES, "ai-history", {**watchdog.SERIES["ai-history"], "author_profile": "story"})
    job_id = watchdog.SERIES["ai-history"]["author_job_id"]
    default = tmp_path / "default-executions.db"
    execution_db(default, [])
    monkeypatch.setattr(watchdog, "EXECUTIONS_DB", default)
    path = watchdog.PROFILES_ROOT / "story/cron/executions.db"
    path.parent.mkdir(parents=True)
    execution_db(path, [("live", job_id, "running", 123, 100, DAY + "T10:00:00+08:00", None)])
    blockers = watchdog._execution_blockers(DAY, owner_alive=lambda *_: True)
    assert blockers == [f"story/{job_id}:live:live"]


def test_native_fetch_waiting_author_dispatches_through_profile(tmp_path, monkeypatch):
    monkeypatch.setitem(watchdog.SERIES, "ai-history", {**watchdog.SERIES["ai-history"], "author_profile": "story", "assets_job_id": "assets-job"})
    job_id = watchdog.SERIES["ai-history"]["author_job_id"]
    path = watchdog.PROFILES_ROOT / "story/cron/jobs.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"jobs": [{"id": job_id, "enabled": True}]}))
    calls = []
    def run_action(action):
        calls.append(action)
        if action.phase == "native_fetch":
            raise watchdog.ActionPending("awaiting_native_author")
    result = watchdog.supervise(DAY, status=lambda: summary("ai-history"), load_items=lambda: [],
                                 blockers=lambda _: [], run_action=run_action,
                                 claims=watchdog.Claims(tmp_path / "claims.db"))
    assert result["phase"] == "author"
    assert [action.phase for action in calls] == ["native_fetch", "author"]
    assert watchdog._action_profile(calls[-1]) == "story"


def test_native_content_state_advances_assets_without_workflow_ack(tmp_path, monkeypatch):
    monkeypatch.setitem(watchdog.SERIES, "ai-history", {**watchdog.SERIES["ai-history"], "assets_job_id": "assets-job"})
    directory = tmp_path / "native-one"
    directory.mkdir()
    (directory / "native-content-state.json").write_text(json.dumps({
        "status": "waiting_assets", "series_id": "ai-history", "issue_date": DAY,
        "issue_key": DAY, "artifact_sha256": "a" * 64,
    }))
    handoffs = watchdog._handoff_items(tmp_path)
    assert handoffs[0].native is True
    action, reason = watchdog._plan(DAY, {"ai-history"}, [], handoffs=handoffs, issue_key=DAY)
    assert action.phase == "assets" and action.job_id == "assets-job"
    staged = watchdog.Item(directory / "draft-manifest.json", "ai-history", DAY, "a" * 64, "staged", issue_key=DAY)
    action, reason = watchdog._plan(DAY, {"ai-history"}, [staged], handoffs=handoffs, issue_key=DAY)
    assert action is None and reason == "awaiting_release"


def test_review_queue_is_filtered_to_configured_reviewer_profile(tmp_path, monkeypatch):
    monkeypatch.setitem(watchdog.SERIES, "ai-history", {**watchdog.SERIES["ai-history"], "review_profile": "supervision", "review_job_id": "story-review"})
    current = item("ai-history", "await_review")
    older_default = item("ai-practice", "await_review", day="2026-09-24")
    action, reason = watchdog._plan(DAY, {"ai-history"}, [current, older_default])
    assert reason == "ready" and action.job_id == "story-review"
    assert watchdog._action_profile(action) == "supervision"


def test_same_job_id_in_two_profiles_never_forms_shared_claim(tmp_path, monkeypatch):
    monkeypatch.setitem(watchdog.SERIES, "ai-history", {**watchdog.SERIES["ai-history"], "author_profile": "story"})
    assert watchdog.AUTHOR_JOBS["ai-history"] == watchdog.AUTHOR_JOBS["ai-practice"]
    action, reason = watchdog._plan(DAY, {"ai-history", "ai-practice"}, [])
    assert reason == "ready"
    assert len(action.barriers) == 1 and action.barriers[0].series == "ai-history"
    assert watchdog._action_profile(action) == "story"


def test_activated_catalog_routes_current_main_and_story_without_workflow(monkeypatch):
    install_catalog(monkeypatch, ACTIVATED_SERIES)
    day = "2026-09-27"
    active = {name: spec for name, spec in watchdog.SERIES.items() if spec.get("starts_on", day) <= day}
    by_series = {name: {"expected": len(spec["release_times"]), "published": 0,
                       "slots": [{"issue_key": day if slot == "12:00" else f"{day}T{slot}", "published": 0}
                                 for slot in spec["release_times"]]} for name, spec in active.items()}
    value = {"today": {"date": day, "expected": sum(row["expected"] for row in by_series.values()),
                       "published": 0, "by_series": by_series}, "issues": {"missing": []}}
    assert watchdog._missing(value, day) == set(active)
    assert {"ai-toolkit", "tang-history"} <= set(active)
    for name in ("ai-toolkit", "tang-history"):
        key = by_series[name]["slots"][0]["issue_key"]
        action, reason = watchdog._plan(day, {name}, [], issue_key=key)
        assert reason == "ready" and action.phase == "native_fetch"
        author = watchdog.Action("author", action.barriers, job_id=active[name]["author_job_id"])
        assert watchdog._action_profile(author) == ("story" if name == "tang-history" else "default")
    assert watchdog._role_profile("tang-history", "review") == "supervision"
    assert ACTIVATED_SERIES == {name: spec for name, spec in watchdog.PUBLICATION_SERIES.items()
                                if spec.get("kind") == "daily" and spec.get("enabled", True)}


def test_native_preflight_feedback_survives_author_dispatch(tmp_path, monkeypatch):
    monkeypatch.setitem(watchdog.SERIES, "ai-history", {**watchdog.SERIES["ai-history"], "assets_job_id": "assets"})
    feedback = {"reason": "deterministic_preflight", "reasons": ["quality.body_too_short"],
                "revision_count": 1, "feedback_file": "/safe/native-content-feedback.json"}
    def action_runner(action):
        if action.phase == "native_fetch":
            raise watchdog.ActionPending("awaiting_native_author", feedback)
    result = watchdog.supervise(DAY, status=lambda: summary("ai-history"), load_items=lambda: [],
                                blockers=lambda _: [], run_action=action_runner,
                                claims=watchdog.Claims(tmp_path / "claims.db"))
    assert result["phase"] == "author" and result["author_feedback"] == feedback


def test_obsolete_workflow_state_does_not_block_native_route(tmp_path, monkeypatch):
    install_catalog(monkeypatch, ACTIVATED_SERIES)
    directory = tmp_path / "ai-toolkit-old-workflow"
    directory.mkdir()
    (directory / "workflow-handoff-state.json").write_text(json.dumps({
        "series_id": "ai-toolkit", "issue_date": "2026-09-27", "status": "waiting_assets",
    }))
    assert watchdog._handoff_items(tmp_path) == []


def test_native_revision_budget_failure_is_actionable(monkeypatch):
    action = watchdog.Action("native_fetch", (watchdog.Barrier("ai-history", "a" * 64, DAY),))
    monkeypatch.setattr(watchdog.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], 1, "", "publication workflow handoff failed: native content revision budget exhausted"))
    with pytest.raises(watchdog.ActionFailure, match="native_content_revision_exhausted"):
        watchdog._run_action(action)
