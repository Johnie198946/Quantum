"""Isolated synthetic workflow tests; no production keys or native sessions."""
import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.services.knowledge_publication_store import PublicationError, PublicationStore
from scripts import publication_editorial_remote as relay
from test_daily_publication import add_covers, at, bundle, ready
from test_publication_editorial import synthetic_brief


def head_publication_store():
    root = Path(__file__).parents[1]
    source = subprocess.run(
        ["git", "show", "92d7d273fc94052a696183ebc36dedc8cd7093d4:backend/services/knowledge_publication_store.py"],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout
    module = types.ModuleType("head_knowledge_publication_store")
    module.__file__ = str(root / "backend/services/knowledge_publication_store.py")
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module.PublicationStore


@pytest.mark.parametrize("state", ["await_review", "approved"])
@pytest.mark.parametrize("restored_contract", [False, True])
def test_head_v1_attempt_remains_idempotent_after_upgrade(tmp_path, state, restored_contract):
    from publication_editorial_fixture import approve_fixture

    legacy_store = head_publication_store()(tmp_path)
    value = (draft(legacy_store) if state == "await_review"
             else ready(legacy_store, bundle(), editorial=False))
    value["assets"] = [asset for asset in value["assets"] if asset.get("role") in {"shelf_cover", "reader_cover"}]
    if state == "approved":
        approve_fixture(legacy_store, value)
        contract = value["quality_contract"]
    else:
        contract = legacy_store.prepare_editorial(value)["quality_contract"]
    draft_contract = {key: copy.deepcopy(contract[key]) for key in (
        "format", "writer_sessions", "learning_objectives", "editorial_brief", "research_gaps",
    )}

    with sqlite3.connect(tmp_path / "publication.sqlite3") as db:
        assert db.execute(
            "SELECT state FROM editorial_attempts WHERE attempt_id=?", (contract["attempt_id"],)
        ).fetchone()[0] == state

    value["quality_contract"] = contract if restored_contract else draft_contract
    recovered = PublicationStore(tmp_path).prepare_editorial(value)
    assert recovered["attempt_id"] == contract["attempt_id"]
    assert recovered["revision"] == contract["revision"]


def test_existing_edition_schema_migrates_without_losing_frozen_rows(tmp_path):
    db_path = tmp_path / "publication.sqlite3"
    with sqlite3.connect(db_path) as db:
        db.execute("""CREATE TABLE editions (
          edition_id TEXT PRIMARY KEY, publication_id TEXT NOT NULL, issue_id TEXT NOT NULL, issue_key TEXT NOT NULL,
          series_id TEXT NOT NULL, issue_date TEXT NOT NULL, edition INTEGER NOT NULL, content_hash TEXT NOT NULL,
          source_snapshot_hash TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL, author TEXT NOT NULL,
          institution TEXT NOT NULL, release_at TEXT NOT NULL, actual_release_at TEXT, state TEXT NOT NULL,
          body_ref TEXT NOT NULL, bundle_json TEXT NOT NULL, blocked_reasons TEXT NOT NULL, created_at TEXT NOT NULL,
          withdrawn_at TEXT, UNIQUE(series_id, issue_key, edition), UNIQUE(issue_id, content_hash))""")
        db.execute(
            "INSERT INTO editions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("edition-old", "publication-old", "issue-old", "2026-09-08", "series-old", "2026-09-08", 1,
             "a" * 64, "", "title", "summary", "author", "institution", "2026-09-08T04:00:00+00:00",
             "2026-09-08T04:00:00+00:00", "published", "artifacts/old.md", "{}", "[]",
             "2026-09-08T03:00:00+00:00", None),
        )

    store = PublicationStore(tmp_path)
    db = store._connect()
    try:
        assert db.execute("SELECT edition_id FROM editions").fetchone()[0] == "edition-old"
        schema = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='editions'").fetchone()[0]
        assert "UNIQUE(issue_id, content_hash)" not in schema
    finally:
        db.close()


def draft(store, body=None):
    # Explicitly short draft: intake only, never an approved fixture.
    value = ready(store, bundle(body=body or "## 待补研\n\n合成短稿。"), editorial=False)
    value["quality_contract"] = {"format": "chapter", "writer_sessions": ["hermes:synthetic-writer"],
        "learning_objectives": ["仅供合成测试验证契约结构，不代表真实内容质量"],
        "editorial_brief": synthetic_brief(), "research_gaps": []}
    return value


def editorial_manifest(tmp_path):
    body = b"# synthetic body\n"
    (tmp_path / "body.md").write_bytes(body)
    (tmp_path / "bundle.json").write_text(json.dumps({
        "series_id": "ai-history", "body_hash": relay.sha(body),
    }))
    item = {
        "bundle_file": "bundle.json", "body_file": "body.md", "body_sha256": relay.sha(body),
        "source_files": [], "rights_files": [], "execution_files": [],
        "review_file": "review.json", "proof_file": "proof.json", "status": "prepared",
    }
    for role in ("shelf_cover", "reader_cover", "illustration_01", "illustration_02", "illustration_03"):
        path = tmp_path / f"{role}.png"
        path.write_bytes(role.encode())
        item[f"{role}_file"] = path.name
        item[f"{role}_sha256"] = relay.sha(path.read_bytes())
    path = tmp_path / "draft-manifest.json"
    relay.save(path, {"version": relay.VERSION, "items": [item]})
    return path


@pytest.mark.parametrize("field", [
    "illustration_01_file", "illustration_02_sha256", "illustration_03_file",
])
def test_daily_editorial_manifest_requires_all_illustration_file_hash_pairs(tmp_path, field):
    path = editorial_manifest(tmp_path)
    value = json.loads(path.read_text())
    value["items"][0].pop(field)
    relay.save(path, value)
    with pytest.raises(ValueError, match="illustration|media"):
        relay.load_manifest(path)


def test_editorial_manifest_rejects_illustration_hash_and_path_conflicts(tmp_path):
    path = editorial_manifest(tmp_path)
    value = json.loads(path.read_text())
    item = value["items"][0]
    item["illustration_02_sha256"] = "0" * 64
    relay.save(path, value)
    with pytest.raises(ValueError, match="hash"):
        relay.load_manifest(path)

    path = editorial_manifest(tmp_path)
    value = json.loads(path.read_text())
    item = value["items"][0]
    item["illustration_02_file"] = item["illustration_01_file"]
    item["illustration_02_sha256"] = item["illustration_01_sha256"]
    relay.save(path, value)
    with pytest.raises(ValueError, match="overlap|conflict"):
        relay.load_manifest(path)


def test_remote_arguments_upload_three_manifest_illustrations_only_for_stage(tmp_path):
    path = editorial_manifest(tmp_path)
    _, value = relay.load_manifest(path)
    item = value["items"][0]
    item["batch"] = "a" * 32

    class Remote:
        def upload(self, _batch, raw, ext):
            return f"/remote/{relay.sha(raw)}{ext}"

    bundle_value = json.loads((tmp_path / item["bundle_file"]).read_text())
    assert "--illustration-file" not in relay.arguments(Remote(), tmp_path, item, bundle_value)
    args = relay.arguments(Remote(), tmp_path, item, bundle_value, stage=True)
    indexes = [index for index, value in enumerate(args) if value == "--illustration-file"]
    assert [args[index + 1].split("=", 1)[0] for index in indexes] == [
        "illustration_01", "illustration_02", "illustration_03",
    ]


def reject(store, value, attempt):
    value = {**value, "quality_contract": attempt["quality_contract"]}
    review = {"content_hash": value["body_hash"], "decision": "rejected", "revision": attempt["revision"],
              "editorial_target_hash": attempt["target_hash"], "research_gaps": [
                  {"id": "mechanism", "question": "需要补充说明该机制如何影响具体实例结果"}]}
    path = store.root / "fixture-inputs" / "reject.json"
    path.write_text(json.dumps(review), encoding="utf-8")
    return store.record_editorial_review(value, path)


def test_prepare_idempotent_transactional_revision_and_revert(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    with ThreadPoolExecutor(max_workers=6) as pool:
        attempts = list(pool.map(lambda _: store.prepare_editorial(value), range(10)))
    assert len({a["attempt_id"] for a in attempts}) == 1
    first = attempts[0]
    other = draft(store, "## 待补研\n\n不同的合成短稿。")
    with pytest.raises(PublicationError, match="terminal review"):
        store.prepare_editorial(other)
    reject(store, value, first)
    second = store.prepare_editorial(other)
    reject(store, other, second)
    third = store.prepare_editorial(value)
    assert [first["revision"], second["revision"], third["revision"]] == [1, 2, 3]
    assert first["target_hash"] != third["target_hash"]
    assert first["attempt_id"] != third["attempt_id"]


def test_editorial_approval_does_not_ingest_daily_media(tmp_path):
    store = PublicationStore(tmp_path)
    from publication_editorial_fixture import approve_fixture
    value = approve_fixture(store, ready(store, bundle(), editorial=False), record=False)
    review_path = store.root / "fixture-inputs" / (value["quality_contract"]["attempt_id"] + ".json")
    value["assets"] = []
    assert store.record_editorial_review(value, review_path)["state"] == "approved"


def test_rejection_four_times_terminal_and_gaps_persist(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    for revision in range(1, 5):
        attempt = store.prepare_editorial(value)
        assert attempt["revision"] == revision
        result = reject(store, value, attempt)
        assert result["state"] == "rejected"
        assert reject(store, value, attempt)["state"] == "rejected"
    with pytest.raises(PublicationError, match="retry limit"):
        store.prepare_editorial(value)
    report = store.status_report()
    assert len(report["editorial_attempts"]) == 4
    assert "mechanism" in {g["id"] for g in report["open_gaps"]}


def test_retry_budget_resets_after_latest_approval_and_stays_issue_scoped(tmp_path):
    from publication_editorial_fixture import approve_fixture

    store = PublicationStore(tmp_path)
    value = ready(store, bundle(series="concept-fables"), editorial=False)
    options = {"format": "chapter", "writer_sessions": ["hermes:historical-writer"],
        "learning_objectives": ["验证批准前历史失败不会耗尽下一审核周期的重试预算"],
        "editorial_brief": synthetic_brief(), "research_gaps": []}
    value["quality_contract"] = options
    for _ in range(3):
        rejected = reject(store, value, store.prepare_editorial(value))

    approved_options = copy.deepcopy(options)
    approved_options["research_gaps"] = [{
        **gap, "state": "resolved", "resolution": "本条合成回归补充了足够长度的机制解释与实例证据，并形成新的已批准审核周期基线。",
        "source_urls": ["https://example.com/source"],
    } for gap in rejected["gaps"] if gap["state"] == "open"]
    approved = approve_fixture(store, value, draft=approved_options)
    assert approved["quality_contract"]["revision"] == 4
    assert store.stage(approved, now=at(3))["state"] == "scheduled"
    assert store.release_due(now=at(4))["released"]

    next_value = ready(store, bundle(series="concept-fables", body=value["body"] + "\n\n新视觉资产版次。"), editorial=False)
    next_value["quality_contract"] = {**options, "writer_sessions": ["hermes:visual-assets-writer"]}
    for revision in range(5, 9):
        attempt = store.prepare_editorial(next_value)
        assert attempt["revision"] == revision
        reject(store, next_value, attempt)
    with pytest.raises(PublicationError, match="retry limit"):
        store.prepare_editorial(next_value)

    other = ready(store, bundle(series="concept-fables", day="2026-09-09"), editorial=False)
    other["quality_contract"] = {**options, "writer_sessions": ["hermes:other-issue-writer"]}
    other_attempt = store.prepare_editorial(other)
    assert other_attempt["revision"] == 1
    attempts = store.status_report()["editorial_attempts"]
    assert sum(attempt["issue_id"] == approved["quality_contract"]["issue_id"] for attempt in attempts) == 8
    assert sum(attempt["issue_id"] == other_attempt["issue_id"] for attempt in attempts) == 1


@pytest.mark.parametrize("claimed_state", ["open", "resolved"])
def test_retry_limit_cannot_be_bypassed_by_changed_body_and_gap_claims(tmp_path, claimed_state):
    store = PublicationStore(tmp_path)
    value = draft(store)
    for _ in range(4):
        last = reject(store, value, store.prepare_editorial(value))
    changed = draft(store, "## 修订稿\n\n改变正文不代表审核已经解决了原来的证据要求。")
    changed["quality_contract"]["research_gaps"] = [
        {**gap, "state": claimed_state,
         "resolution": "程序或作者声称已经补齐全部证据不能替代独立审核，也不能解锁重试预算。",
         "source_urls": ["https://example.org/source"]}
        for gap in last["gaps"]
    ]
    with pytest.raises(PublicationError, match="retry limit"):
        store.prepare_editorial(changed)


def test_gaps_cannot_be_dropped_or_reworded(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    reject(store, value, store.prepare_editorial(value))
    next_attempt = store.prepare_editorial(value)
    assert "mechanism" in {g["id"] for g in next_attempt["quality_contract"]["research_gaps"]}
    assert store.status_report()["open_gaps"]
    reject(store, value, next_attempt)
    value["quality_contract"]["research_gaps"] = [{"id": "mechanism", "question": "替换为另一个完全无关的问题以逃避原审稿要求"}]
    with pytest.raises(PublicationError, match="cannot be replaced"):
        store.prepare_editorial(value)


def test_caller_cannot_assign_revision(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    value["quality_contract"]["revision"] = 99
    value["quality_contract"]["learning_objectives"] = ["不同目标防止被当前目标幂等返回"]
    with pytest.raises(PublicationError, match="caller-assigned"):
        store.prepare_editorial(value)


def test_editorial_brief_evidence_must_be_a_declared_reference(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    value["quality_contract"]["editorial_brief"]["evidence_urls"] = ["https://example.org/not-declared"]
    with pytest.raises(PublicationError, match="invalid editorial draft options"):
        store.prepare_editorial(value)


def test_new_pending_invalidates_prior_approved_and_reversion(tmp_path):
    store = PublicationStore(tmp_path)
    value = ready(store, bundle())
    edition = store.stage(value, now=at(3))
    next_value = draft(store, "## 新稿\n\n未通过审核的新稿。")
    next_attempt = store.prepare_editorial(next_value)
    assert store.status()[0]["state"] == "blocked"
    assert store.release_due(now=at(4))["released"] == []
    assert "editorial_attempt_not_current" in store.stage(value, now=at(3))["blocked_reasons"]
    reject(store, next_value, next_attempt)
    reverted = {**value, "quality_contract": {k: value["quality_contract"][k] for k in
        ("format", "writer_sessions", "learning_objectives", "editorial_brief", "research_gaps")}}
    attempt = store.prepare_editorial(reverted)
    assert attempt["state"] == "await_review" and attempt["revision"] == 3
    reverted["quality_contract"] = attempt["quality_contract"]
    assert store.stage(reverted, now=at(3))["state"] == "blocked"
    assert edition["edition_id"] == store.status()[0]["edition_id"]


@pytest.mark.parametrize("tamper", ["proof", "review", "contract", "key"])
@pytest.mark.parametrize("prior_gap", [False, True])
def test_release_rechecks_proof_review_and_contract(tmp_path, tamper, prior_gap):
    store = PublicationStore(tmp_path)
    if prior_gap:
        from publication_editorial_fixture import approve_fixture
        previous = draft(store)
        reject(store, previous, store.prepare_editorial(previous))
        value = approve_fixture(store, ready(store, bundle(), editorial=False))
        assert value["quality_contract"]["research_gaps"][0]["state"] == "open"
    else:
        value = ready(store, bundle())
    edition = store.stage(value, now=at(3))
    if tamper == "proof":
        Path(value["editorial_proof_file"]).write_text("{}")
    elif tamper == "review":
        (store.evidence / (value["review"]["receipt"]["sha256"] + ".bin")).write_text("{}")
    elif tamper == "key":
        (store.root / "editorial-review-public.pem").unlink()
    else:
        changed = copy.deepcopy(edition["bundle"])
        changed["quality_contract"]["format"] = "book"
        db = store._connect()
        db.execute("UPDATE editions SET bundle_json=?", (json.dumps(changed),))
        db.close()
    result = store.release_due(now=at(4))
    assert result["released"] == [] and result["blocked"]
    if tamper != "contract":
        assert store.stage(value, now=at(4))["state"] == "blocked"


def test_legacy_published_is_readable_pending_is_not_and_restage_frozen(tmp_path):
    store = PublicationStore(tmp_path)
    value = ready(store, bundle())
    value.pop("quality_contract")
    value.pop("editorial_proof_file")
    value.pop("editorial_proof_sha256")
    item = store.stage(value, now=at(3))
    assert item["state"] == "blocked"
    # Explicit legacy DB migration fixture, not a production admission bypass.
    db = store._connect()
    db.execute("UPDATE editions SET state='scheduled',blocked_reasons='[]'")
    db.close()
    assert store.release_due(now=at(4))["blocked"][0]["reasons"] == ["editorial_contract_required"]
    db = store._connect()
    db.execute("UPDATE editions SET state='published',actual_release_at=?,blocked_reasons='[]'", (at(4).isoformat(),))
    # Recreate pre-migration state; migration freezes only this initial snapshot.
    db.execute("DELETE FROM publication_migrations WHERE name='editorial-v1'")
    db.close()
    original = store.get_published(item["publication_id"], now=at(4))
    assert original and original["publication_format"] == "article"
    amended = ready(store, bundle())
    with pytest.raises(PublicationError, match="frozen edition"):
        store.stage(amended, now=at(4))
    assert store.get_published(item["publication_id"], now=at(4))["bundle"] == original["bundle"]
    store.prepare_editorial(draft(store, "## 不可发布\n\n仍在补研。"))
    assert store.get_published(item["publication_id"], now=at(4))


def test_unsigned_approval_fails_terminally(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    attempt = store.prepare_editorial(value)
    value["quality_contract"] = attempt["quality_contract"]
    path = store.root / "fixture-inputs" / "forged.json"
    path.write_text(json.dumps({"decision": "approved", "content_hash": value["body_hash"],
        "editorial_target_hash": attempt["target_hash"], "revision": attempt["revision"],
        "reviewed_at": at(3).isoformat(), "reviewer_session": "hermes:attacker", "research_gaps": []}))
    result = store.record_editorial_review(value, path)
    assert result["state"] == "failed" and result["gaps"]
    assert store.stage(value, now=at(3))["state"] == "blocked"


def test_cli_signed_approval_ingests_proof_and_releases(tmp_path):
    from publication_editorial_fixture import approve_fixture
    store = PublicationStore(tmp_path)
    value = approve_fixture(store, ready(store, bundle(), editorial=False), record=False)
    review_path = store.root / "fixture-inputs" / (value["quality_contract"]["attempt_id"] + ".json")
    path = tmp_path / "bundle-cli.json"
    path.write_text(json.dumps(value))
    command = [sys.executable, "scripts/publication_operator.py", "--root", str(tmp_path)]
    run = subprocess.run([*command, "record-editorial-review", str(path), "--review-file", str(review_path),
                          "--proof-file", value["editorial_proof_file"]], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(run.stdout)["result"]
    assert result["state"] == "approved"
    assert result["editorial_proof_file"].startswith("evidence/")
    value["review"] = result["review"]
    value["editorial_proof_file"] = result["editorial_proof_file"]
    path.write_text(json.dumps(value))
    run = subprocess.run([*command, "stage", str(path), "--review-file", str(review_path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout)["result"]["state"] == "scheduled"
    assert store.release_due(now=at(4))["released"]
    assert store.published(now=at(4))[0]["publication_format"] == "chapter"
    store.prepare_editorial(draft(store, "## 新稿\n\n补研等待中。"))
    assert store.published(now=at(4))  # frozen approved attempt, not current draft


def test_cli_stage_ingests_named_covers_without_exposing_paths(tmp_path):
    store = PublicationStore(tmp_path)
    value = add_covers(store, ready(store, bundle(series="ai-toolkit")))
    cover_paths = {asset["role"]: store.root / "fixture-inputs" / f"{asset['role']}.png"
                   for asset in value["assets"]}
    value["assets"] = []
    bundle_path = tmp_path / "cover-bundle.json"
    bundle_path.write_text(json.dumps(value), encoding="utf-8")

    run = subprocess.run([
        sys.executable, "scripts/publication_operator.py", "--root", str(tmp_path), "stage", str(bundle_path),
        "--shelf-cover-file", str(cover_paths["shelf_cover"]),
        "--reader-cover-file", str(cover_paths["reader_cover"]),
        *sum((["--illustration-file", f"{role}={cover_paths[role].resolve()}"]
              for role in ("illustration_01", "illustration_02", "illustration_03")), []),
    ], capture_output=True, text=True)

    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(run.stdout)["result"]
    assert result["state"] == "scheduled"
    assets = result["bundle"]["assets"]
    assert {asset["role"] for asset in assets} == {
        "shelf_cover", "reader_cover", "illustration_01", "illustration_02", "illustration_03",
    }
    assert all(set(asset) == {"role", "receipt", "media_type", "width", "height"} for asset in assets)
    assert "shelf_cover.png" not in run.stdout and "reader_cover.png" not in run.stdout


def test_research_resolution_reaudit_then_publish(tmp_path):
    from publication_editorial_fixture import approve_fixture
    store = PublicationStore(tmp_path)
    value = draft(store)
    rejected = reject(store, value, store.prepare_editorial(value))
    options = copy.deepcopy(value["quality_contract"])
    options["research_gaps"] = [{**g, "state": "resolved", "resolution": "本条为合成测试补研记录，补充了足够长度的机制解释与实例证据以验证复审状态机。",
                                "source_urls": ["https://example.com/source"]} for g in rejected["gaps"]]
    revised = approve_fixture(store, ready(store, bundle(), editorial=False), draft=options)
    assert revised["quality_contract"]["revision"] == 2
    assert store.status_report()["open_gaps"] == []
    assert store.stage(revised, now=at(3))["state"] == "scheduled"
    assert store.release_due(now=at(4))["released"]
    assert store.status_report()["editorial_attempts"][0]["state"] == "rejected"


@pytest.mark.parametrize("submission", ["omit", "resolved"])
def test_unapproved_prior_resolved_gap_cannot_be_dropped_by_direct_prepare(tmp_path, submission):
    store = PublicationStore(tmp_path)
    value = draft(store)
    value["quality_contract"]["research_gaps"] = [{
        "id": "old-topic", "question": "旧选题的证据边界应如何核验并避免迁移到新选题？",
        "state": "resolved", "resolution": "旧选题已按当时来源完成核验，历史记录保留在不可变的上一版审稿合同中。",
        "source_urls": ["https://example.com/old-topic"],
    }]
    rejected = reject(store, value, store.prepare_editorial(value))
    next_value = draft(store, body="## 全新主题\n\n" + "新的独立教程内容。" * 400)
    next_value["quality_contract"]["research_gaps"] = [{
        **gap, "state": "resolved", "resolution": "新稿已按审稿意见补齐机制、证据和完整示例并重新提交独立复核。",
        "source_urls": ["https://example.com/new-topic"],
    } for gap in rejected["gaps"]] if submission == "resolved" else []
    attempt = store.prepare_editorial(next_value)
    gaps = attempt["quality_contract"]["research_gaps"]
    assert {gap["id"] for gap in gaps} == {"old-topic", "mechanism"}
    assert all(gap["state"] == "open" and gap["source_urls"] == [] for gap in gaps)
    assert "旧选题已按当时来源完成核验" in next(gap["resolution"] for gap in gaps if gap["id"] == "old-topic")


def test_new_published_cannot_acquire_legacy_exemption(tmp_path):
    store = PublicationStore(tmp_path)
    value = ready(store, bundle(), editorial=False)
    item = store.stage(value, now=at(3))
    db = store._connect()
    db.execute("UPDATE editions SET state='published'")
    db.close()
    assert store.get_published(item["publication_id"], now=at(4)) is None
    db = store._connect()
    assert db.execute("SELECT COUNT(*) FROM legacy_published_editions").fetchone()[0] == 0
    db.close()


def test_terminal_review_cannot_change_decision(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    attempt = store.prepare_editorial(value)
    reject(store, value, attempt)
    path = store.root / "fixture-inputs" / "reject.json"
    review = json.loads(path.read_text())
    review.update(decision="approved", reviewed_at=at(3).isoformat(), reviewer_session="hermes:synthetic-reviewer")
    path.write_text(json.dumps(review))
    value["quality_contract"] = attempt["quality_contract"]
    with pytest.raises(PublicationError, match="cannot be overwritten"):
        store.record_editorial_review(value, path)


def test_cli_prepare_record_and_body_hash_guard(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    illustration = (store.root / "fixture-inputs" / "illustration_01.png").resolve()
    value["assets"] = [asset for asset in value["assets"] if asset["role"] != "illustration_01"]
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(value))
    command = [sys.executable, "scripts/publication_operator.py", "--root", str(tmp_path)]
    run = subprocess.run([*command, "prepare-editorial", str(path),
                          "--illustration-file", f"illustration_01={illustration}"], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    attempt = json.loads(run.stdout)["result"]
    value["quality_contract"] = attempt["quality_contract"]
    path.write_text(json.dumps(value))
    review_path = tmp_path / "reject-cli.json"
    review_path.write_text(json.dumps({"decision": "rejected", "content_hash": value["body_hash"],
        "editorial_target_hash": attempt["target_hash"], "revision": attempt["revision"], "research_gaps": []}))
    run = subprocess.run([*command, "record-editorial-review", str(path), "--review-file", str(review_path),
                          "--illustration-file", f"illustration_01={illustration}"], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout)["result"]["state"] == "rejected"
    body = tmp_path / "wrong.md"
    body.write_text("wrong")
    run = subprocess.run([*command, "prepare-editorial", "--bundle", str(path), "--body-file", str(body)], capture_output=True, text=True)
    assert run.returncode == 2 and "body_hash mismatch" in run.stdout


def test_legacy_raw_review_clock_envelope_still_releases_and_is_readable(tmp_path):
    store = PublicationStore(tmp_path)
    value = ready(store, bundle())
    review_raw = (store.evidence / (value["review"]["receipt"]["sha256"] + ".bin")).read_bytes()
    legacy_time = json.loads(review_raw)["reviewed_at"]
    assert value["review"]["reviewed_at"] != legacy_time
    value["review"]["reviewed_at"] = legacy_time
    staged = store.stage(value, now=at(3))
    assert staged["state"] == "scheduled"
    assert store.release_due(now=at(4))["released"]
    published = store.get_published(staged["publication_id"], now=at(4))
    assert published["bundle"]["review"]["reviewed_at"] == legacy_time
    assert (store.evidence / (value["review"]["receipt"]["sha256"] + ".bin")).read_bytes() == review_raw
    with sqlite3.connect(tmp_path / "publication.sqlite3") as db:
        frozen = db.execute("SELECT bundle_json FROM editions WHERE edition_id=?", (staged["edition_id"],)).fetchone()[0]
    review_file = store.evidence / (value["review"]["receipt"]["sha256"] + ".bin")
    retry = store.record_editorial_review(value, review_file)
    assert retry["review"]["reviewed_at"] == legacy_time
    value["review"] = retry["review"]
    assert store.stage(value, now=at(4))["state"] == "published"
    with sqlite3.connect(tmp_path / "publication.sqlite3") as db:
        assert db.execute("SELECT bundle_json FROM editions WHERE edition_id=?", (staged["edition_id"],)).fetchone()[0] == frozen
