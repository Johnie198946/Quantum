"""Isolated synthetic fixtures; fake SSH executes real intake/operator locally.
Never a production review, publication, credential, or network operation.
"""

import base64
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time

import pytest
from PIL import Image
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import publication_editorial_remote as relay
from scripts import publication_release_remote as transport
from backend.services.publication_editorial import (
    BOOK_CHECKS,
    CHAPTER_CHECKS,
    editorial_metrics,
)
from test_publication_editorial import synthetic_brief, synthetic_fixture


class NativeDatabases(dict):
    def __fspath__(self):
        return str(self["supervision"])

    def read_bytes(self):
        return self["supervision"].read_bytes()


def fixture_bundle():
    body = synthetic_fixture("chapter")[0] + "\n[来源](https://example.com/source)\n"
    digest = relay.sha(body.encode())
    return {
        "series_id": "ai-history",
        "source_publication_id": "",
        "issue_date": "2026-09-08",
        "title": "合成测试期",
        "summary": "仅用于自动化测试的合成概要。",
        "body": body,
        "author": "Quantumn",
        "institution": "Quantumn",
        "authored_by": "quantumn_editorial",
        "content_kind": "commentary",
        "rights_scope": "local_owner_original",
        "rights_reference": "synthetic operator attestation",
        "rights_valid_until": None,
        "rights_perpetual": False,
        "rights_evidence": [],
        "rights_evidence_status": "operator_attested",
        "owner_policy_id": "fixture-policy",
        "release_at": "2026-09-08T12:00:00+08:00",
        "state": "scheduled",
        "is_test": True,
        "source_snapshot_hash": "",
        "source_receipts": [],
        "body_hash": digest,
        "body_receipt": {},
        "references": [{"title": "合成来源", "url": "https://example.com/source"}],
        "wiki_references": [],
        "assets": [],
        "completeness": "full",
        "review": {},
        "execution_claim": "not_run",
        "execution_evidence": [],
        "warnings": [],
    }


@pytest.fixture
def flow(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "default")
    local = tmp_path / "local"
    local.mkdir()
    intake = tmp_path / "intake"
    store = tmp_path / "store"
    store.mkdir()
    calls = []

    def ssh(identity, hosts, command, *, input_text=None):
        words = shlex.split(command)
        assert words[:12] == list(transport.OPERATOR[:12])
        calls.append(words[12:])
        if words[12] == "-c":
            script = words[13].replace(
                "/app/data/runtime/publication-intake", str(intake)
            )
            done = subprocess.run(
                [sys.executable, "-c", script, *words[14:]],
                input=input_text,
                capture_output=True,
                text=True,
            )
            done.stdout = done.stdout.replace(
                str(intake), "/app/data/runtime/publication-intake"
            )
            return done
        assert words[12] == "/app/scripts/publication_operator.py"
        args = [
            a.replace("/app/data/runtime/publication-intake", str(intake)).replace(
                "/app/data/runtime/publications", str(store)
            )
            for a in words[13:]
        ]
        return subprocess.run(
            [sys.executable, "-m", "scripts.publication_operator", *args],
            capture_output=True,
            text=True,
        )

    monkeypatch.setattr(transport, "_ssh", ssh)
    body = fixture_bundle()
    raw = body.pop("body").encode()
    (local / "body.md").write_bytes(raw)
    (local / "source.json").write_text('{"synthetic":true}')
    (local / "rights.json").write_text(
        json.dumps(
            {
                "policy_id": body["owner_policy_id"],
                "status": "operator_attested",
                "content_hashes": [body["body_hash"]],
                "body_sha256": body["body_hash"],
                "bound_files": ["body.md"],
                "attested_by": "local_owner_policy",
            }
        )
    )
    body["review"] = {
        "content_hash": "",
        "decision": "pending",
        "reviewed_by": "",
        "reviewed_at": "",
        "receipt": None,
    }
    body["quality_contract"] = {
        "format": "chapter",
        "writer_sessions": ["hermes:writer"],
        "learning_objectives": ["仅用于自动测试的独立原生会话与完整稿件绑定协议"],
        "editorial_brief": synthetic_brief(),
        "research_gaps": [],
    }
    relay.save(local / "bundle.json", body)
    item = {
        "bundle_file": "bundle.json",
        "body_file": "body.md",
        "body_sha256": relay.sha(raw),
        "source_files": [
            {
                "kind": "source_snapshot",
                "path": "source.json",
                "sha256": relay.sha((local / "source.json").read_bytes()),
            }
        ],
        "rights_files": [
            {
                "kind": "owner_attestation",
                "path": "rights.json",
                "sha256": relay.sha((local / "rights.json").read_bytes()),
            }
        ],
        "execution_files": [],
        "asset_files": [],
        "review_file": "review.json",
        "proof_file": "proof.json",
        "status": "prepared",
    }
    for role, size in (
        ("shelf_cover", (1440, 2560)), ("reader_cover", (2560, 1440)),
        ("illustration_01", (1600, 900)), ("illustration_02", (1600, 900)),
        ("illustration_03", (1600, 900)),
    ):
        path = local / f"{role}.jpg"
        Image.new("RGB", size, "#335577").save(path, format="JPEG")
        item[f"{role}_file"] = path.name
        item[f"{role}_sha256"] = relay.sha(path.read_bytes())
    manifest = local / "issue.manifest.json"
    relay.save(manifest, {"version": relay.VERSION, "items": [item]})
    key = Ed25519PrivateKey.generate()
    keypath = local / "TEST-ONLY-key.pem"
    keypath.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    keypath.chmod(0o600)
    (store / "editorial-review-public.pem").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return (
        local,
        manifest,
        relay.Remote("TEST-ONLY", "TEST-ONLY"),
        calls,
        keypath,
        store,
        intake,
    )


def native(flow, decision="approved", ended=True):
    local, manifest, remote, _, key, _, _ = flow
    relay.prepare(manifest, remote, review_policy="story-supervision-v2")
    from unittest.mock import patch
    with patch.dict("os.environ", {"HERMES_PROFILE": "supervision"}):
        request = relay.review_input(local, remote)
    request_value = json.loads(request.split("PUBLICATION_REVIEW_REQUEST\n", 1)[1].split("\nEND_PUBLICATION_REVIEW_REQUEST", 1)[0])
    item = json.loads(manifest.read_text())["items"][0]
    c = item["quality_contract"]
    review = {
        "content_hash": item["body_sha256"],
        "decision": decision,
        "reviewed_at": "2026-09-08T03:00:00+00:00",
        "editorial_target_hash": c["target_hash"],
        "publication_material_hash": request_value["publication_material_hash"],
        "revision": c["revision"],
        "reviewer_session": "hermes:reviewer",
        "research_gaps": [],
        "chapters": [],
        "book_checks": {
            name: {
                "decision": "approved",
                "finding": "合成测试说明，不是真实审核。仅用于检查字段、长度与签名绑定是否满足测试约定。",
            }
            for name in BOOK_CHECKS
        },
    }
    for chapter in editorial_metrics((local / "body.md").read_text())["chapters"]:
        review["chapters"].append(
            {
                "id": chapter["id"],
                "body_hash": chapter["body_hash"],
                "decision": "approved",
                "checks": {
                    name: {
                        "quote": chapter["paragraphs"][0][:30],
                        "finding": "合成测试说明，不是真实审核。仅用于检查字段、长度与签名绑定是否满足测试约定。",
                    }
                    for name in CHAPTER_CHECKS
                },
            }
        )
    if decision == "rejected":
        review["research_gaps"] = [
            {
                "id": "need-primary",
                "question": "需要查阅一手原始来源以补充缺少的历史证据",
            }
        ]
    relay.save(local / "review.json", review)
    result = {
        "issue_id": c["issue_id"],
        "revision": c["revision"],
        "attempt_id": c["attempt_id"],
        "editorial_target_hash": c["target_hash"],
        "publication_material_hash": request_value["publication_material_hash"],
        "review_file_hash": relay.sha((local / "review.json").read_bytes()),
        "reviewer_session": "hermes:reviewer",
        "decision": decision,
    }
    now = time.time()
    writer_db = local / "TEST-ONLY-story-state.db"
    reviewer_db = local / "TEST-ONLY-supervision-state.db"
    schema = "CREATE TABLE sessions(id TEXT PRIMARY KEY, profile_name TEXT, user_id TEXT, source TEXT, ended_at REAL, end_reason TEXT, started_at REAL); CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, tool_calls TEXT, finish_reason TEXT, active INTEGER DEFAULT 1, compacted INTEGER DEFAULT 0);"
    with sqlite3.connect(writer_db) as conn:
        conn.executescript(schema)
        conn.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)", ("writer", "story", None, "cron", now, "cron_complete", now - 10))
    with sqlite3.connect(reviewer_db) as conn:
        conn.executescript(
            schema
        )
        conn.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)", (
            "reviewer", "supervision", None, "cron", now if ended else None,
            "cron_complete" if ended else None, now - 10,
        ))
        conn.execute(
            "INSERT INTO messages VALUES(1,'reviewer','user',?,NULL,NULL,1,0)",
            (request,),
        )
        conn.execute(
            "INSERT INTO messages VALUES(2,'reviewer','assistant',?,NULL,'stop',1,0)",
            (json.dumps({"publication_review_result": result}),),
        )
    return NativeDatabases(story=writer_db, supervision=reviewer_db), key


def test_prepare_is_private_intake_and_request_contains_full_material(flow, monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "supervision")
    local, manifest, remote, calls, *_ = flow
    result = relay.prepare(manifest, remote, review_policy="story-supervision-v2")
    assert result["statuses"] == ["await_review"]
    assert all("stage" not in c and "release-due" not in c for c in calls)
    request = json.loads(
        relay.review_input(local, remote)
        .split("PUBLICATION_REVIEW_REQUEST\n")[1]
        .split("\nEND_PUBLICATION_REVIEW_REQUEST")[0]
    )
    chunks = request["manuscript_gzip_b64_chunks"]
    assert chunks and all(0 < len(chunk) <= 12 for chunk in chunks)
    assert "manuscript_gzip_b64" not in request
    assert gzip.decompress(base64.b64decode(
        "".join(chunks), validate=True
    )).decode() == (local / "body.md").read_text()
    frozen = json.loads(manifest.read_text())["items"][0]["bundle_file"]
    assert (
        request["quality_contract"]
        == json.loads((local / frozen).read_text())["quality_contract"]
    )
    assert (
        request["source_receipts"]
        == json.loads((local / frozen).read_text())["source_receipts"]
    )
    frozen_bundle = json.loads((local / frozen).read_text())
    assert {asset["role"] for asset in frozen_bundle["assets"]} == set(relay.MEDIA_ROLES)
    assert all(asset["receipt"]["sha256"] for asset in frozen_bundle["assets"])
    assert request["writer_sessions"] == request["quality_contract"]["writer_sessions"]
    assert request["review_policy"] == request["quality_contract"]["review_policy"] == "story-supervision-v2"
    assert request["writer_profile"] == "story"
    assert request["reviewer_profile"] == "supervision"
    assert request["writer_role"] == "story_author"
    assert request["reviewer_role"] == "supervision_reviewer"
    assert request["publication_material_hash"]
    assert not (local / "proof.json").exists()


def test_prepare_ingests_manifest_bound_inline_image_bytes(flow, monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "supervision")
    local, manifest, remote, *_ = flow
    image_url = "https://example.com/figure.png"
    body_path = local / "body.md"
    body_path.write_text(body_path.read_text() + f'\n![结构示意]({image_url} "审定图注")\n')
    body_hash = relay.sha(body_path.read_bytes())
    bundle = json.loads((local / "bundle.json").read_text())
    bundle["body_hash"] = body_hash
    relay.save(local / "bundle.json", bundle)
    rights = json.loads((local / "rights.json").read_text())
    rights["content_hashes"] = [body_hash]
    relay.save(local / "rights.json", rights)
    image = local / "figure.png"
    Image.new("RGB", (640, 360), "#335577").save(image)
    value = json.loads(manifest.read_text())
    item = value["items"][0]
    item["body_sha256"] = body_hash
    item["bundle_sha256"] = relay.sha((local / "bundle.json").read_bytes())
    item["rights_files"][0]["sha256"] = relay.sha((local / "rights.json").read_bytes())
    item["asset_files"] = [{"url": image_url, "path": image.name, "sha256": relay.sha(image.read_bytes())}]
    relay.save(manifest, value)

    relay.prepare(manifest, remote, review_policy="story-supervision-v2")

    frozen = json.loads(manifest.read_text())["items"][0]["bundle_file"]
    asset = next(asset for asset in json.loads((local / frozen).read_text())["assets"] if "url" in asset)
    assert asset["url"] == image_url
    assert asset["receipt"]["sha256"] == relay.sha(image.read_bytes())
    assert (asset["media_type"], asset["width"], asset["height"]) == ("image/png", 640, 360)
    envelope = json.loads(
        relay.review_input(local, remote).split("\nPUBLICATION_REVIEW_REQUEST\n", 1)[0]
    )
    assert str(image.resolve()) in envelope["read_only_inputs"]["assets"]
    assert "visual tools" in envelope["instruction"]
    assert "not substitutes for visual inspection" in envelope["instruction"]


def test_default_prepare_and_review_input_keep_v1_contract(flow):
    local, manifest, remote, *_ = flow
    relay.prepare(manifest, remote)
    request = json.loads(
        relay.review_input(local, remote)
        .split("PUBLICATION_REVIEW_REQUEST\n", 1)[1]
        .split("\nEND_PUBLICATION_REVIEW_REQUEST", 1)[0]
    )
    assert request["profile"] == "default"
    assert "review_policy" not in request["quality_contract"]
    assert "publication_material_hash" not in request


def test_global_review_scan_skips_locally_reviewed_stale_attempt_before_remote_readback(flow, monkeypatch):
    local, manifest, remote, *_ = flow
    relay.prepare(manifest, remote)
    item = json.loads(manifest.read_text())["items"][0]
    (manifest.parent / item["review_file"]).write_text("{}", encoding="utf-8")

    def unexpected_attempt(*_args, **_kwargs):
        raise AssertionError("reviewed historical attempt must not block the global scan")

    monkeypatch.setattr(relay, "attempt", unexpected_attempt)
    assert json.loads(relay.review_input(local, remote)) == {"status": "no_await_review"}


def test_global_review_scan_ignores_invalid_noncandidate_history(tmp_path):
    stale = tmp_path / "historical" / "draft-manifest.json"
    stale.parent.mkdir()
    stale.write_text(
        json.dumps({"version": "legacy", "items": [{"status": "prepared", "batch": "invalid legacy batch"}]}),
        encoding="utf-8",
    )

    assert json.loads(relay.review_input(tmp_path, object())) == {"status": "no_await_review"}


def test_global_review_scan_isolates_invalid_pending_manifest(flow):
    local, manifest, remote, *_ = flow
    relay.prepare(manifest, remote)
    poisoned = local.parent / "00-poisoned" / "draft-manifest.json"
    poisoned.parent.mkdir()
    poisoned.write_text(
        json.dumps({"version": relay.VERSION, "items": [{"status": "await_review"}]}),
        encoding="utf-8",
    )

    envelope = json.loads(relay.review_input(local.parent, remote).split("\nPUBLICATION_REVIEW_REQUEST\n", 1)[0])

    assert envelope["manifest"] == str(manifest)


def test_global_finalize_isolates_invalid_pending_manifest(flow):
    local, manifest, remote, *_ = flow
    relay.prepare(manifest, remote, review_policy="story-supervision-v2")
    poisoned = local.parent / "00-poisoned-finalize" / "draft-manifest.json"
    poisoned.parent.mkdir()
    poisoned.write_text(
        json.dumps({"version": relay.VERSION, "items": [{"status": "await_review"}]}),
        encoding="utf-8",
    )
    db, key = native(flow)

    result = relay.finalize(local.parent, remote, db=db, key=key)

    assert result["items"][0]["status"] == "staged"
    assert json.loads(poisoned.read_text())["items"][0]["status"] == "await_review"


def test_global_finalize_isolates_valid_sibling_runtime_failure(flow):
    local, manifest, remote, *_ = flow
    relay.prepare(manifest, remote, review_policy="story-supervision-v2")
    sibling = local.parent / "a-valid-sibling" / manifest.name
    db, key = native(flow)
    shutil.copytree(local, sibling.parent)
    sibling_value = json.loads(sibling.read_text())
    sibling_item = sibling_value["items"][0]
    sibling_review = sibling.parent / sibling_item["review_file"]
    sibling_review_value = json.loads(sibling_review.read_text())
    sibling_review_value["reviewer_session"] = "hermes:cron-nonexistent"
    sibling_review.write_bytes(relay.encoded(sibling_review_value))
    result = relay.finalize(local.parent, remote, db=db, key=key)
    assert any(entry["status"] == "staged" for entry in result["items"])
    sibling_after = json.loads(sibling.read_text())["items"][0]
    assert sibling_after["status"] == "await_review"


def test_finalize_revalidates_immutable_legacy_failed_approval(flow):
    local, manifest, remote, _, _, store, _ = flow
    relay.prepare(manifest, remote, review_policy="story-supervision-v2")
    db, key = native(flow)
    item = json.loads(manifest.read_text())["items"][0]
    relay.save(local / item["proof_file"], relay.native_attest(db, local / item["review_file"], key))
    review_hash = relay.sha((local / item["review_file"]).read_bytes())
    with sqlite3.connect(store / "publication.sqlite3") as connection:
        connection.execute(
            "UPDATE editorial_attempts SET state='failed',review_hash=?,gaps_json=?,closed_at=? WHERE attempt_id=?",
            (
                review_hash,
                json.dumps([
                    {"id": "legacy.control", "question": "旧验证器控制面失败标记，不代表正文缺口。",
                     "state": "open", "resolution": "", "source_urls": []}
                ]),
                "2026-09-08T01:00:00+00:00",
                item["quality_contract"]["attempt_id"],
            ),
        )

    result = relay.finalize(local, remote, db=db, key=key)

    assert result["items"][0]["status"] == "staged"
    with sqlite3.connect(store / "publication.sqlite3") as connection:
        state = connection.execute(
            "SELECT state FROM editorial_attempts WHERE attempt_id=?",
            (item["quality_contract"]["attempt_id"],),
        ).fetchone()[0]
    assert state == "approved"


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_real_native_signature_record_and_readback(flow, decision):
    local, manifest, remote, calls, _, store_root, intake = flow
    db, key = native(flow, decision)
    before = relay.sha(db.read_bytes())
    result = relay.finalize(local, remote, db=db, key=key)
    assert relay.sha(db.read_bytes()) == before
    expected = "staged" if decision == "approved" else "rejected"
    assert result["items"][0]["status"] == expected
    item = json.loads(manifest.read_text())["items"][0]
    assert item["status"] == expected
    if decision == "rejected":
        assert "need-primary" in [g["id"] for g in item["receipt"]["gaps"]]
        assert "review.rejected" not in [g["id"] for g in item["receipt"]["gaps"]]
        assert not any("stage" in c for c in calls)
    record_call = next(call for call in calls if "record-editorial-review" in call)
    assert remote.operator(*record_call[1:])["state"] == decision
    with sqlite3.connect(store_root / "publication.sqlite3") as conn:
        assert conn.execute(
            "SELECT proof_json FROM editorial_attempts WHERE attempt_id=?",
            (item["quality_contract"]["attempt_id"],),
        ).fetchone()[0]
    proof_index = record_call.index("--proof-file") + 1
    proof_path = Path(record_call[proof_index].replace(
        "/app/data/runtime/publication-intake", str(intake)
    ))
    tampered = json.loads(proof_path.read_text())
    tampered["signature"] = "invalid"
    proof_path.write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match="remote command failed"):
        remote.operator(*record_call[1:])
    assert not any("release-due" in c for c in calls)
    assert relay.finalize(local, remote, db=db, key=key) == {"items": []}
    assert "manuscript" not in json.loads((local / "proof.json").read_text())


def test_approved_finalize_explicitly_promotes_author_draft_to_staged(flow):
    local, manifest, remote, _, _, store, _ = flow
    value = json.loads(manifest.read_text())
    bundle_path = local / value["items"][0]["bundle_file"]
    bundle = json.loads(bundle_path.read_text())
    bundle["state"] = "draft"
    relay.save(bundle_path, bundle)
    value["items"][0]["bundle_sha256"] = relay.sha(bundle_path.read_bytes())
    relay.save(manifest, value)

    db, key = native(flow)
    result = relay.finalize(local, remote, db=db, key=key)

    assert result["items"][0]["status"] == "staged"
    from backend.services.knowledge_publication_store import PublicationStore
    staged = PublicationStore(store).status()
    assert len(staged) == 1 and staged[0]["state"] == "staged"


def test_approved_stage_uploads_manifest_bound_daily_media(flow):
    local, manifest, remote, calls, *_ = flow
    value = json.loads(manifest.read_text())
    item = value["items"][0]
    for role, size in (("shelf_cover", (1440, 2560)), ("reader_cover", (2560, 1440))):
        path = local / f"{role}.jpg"
        Image.new("RGB", size, "#335577").save(path, format="JPEG")
        item[f"{role}_file"] = path.name
        item[f"{role}_sha256"] = relay.sha(path.read_bytes())
    relay.save(manifest, value)

    db, key = native(flow)
    result = relay.finalize(local, remote, db=db, key=key)

    assert result["items"][0]["status"] == "staged"
    stage_call = next(call for call in calls if "stage" in call)
    assert "--shelf-cover-file" in stage_call
    assert "--reader-cover-file" in stage_call
    assert stage_call.count("--illustration-file") == 3


def test_cover_changed_after_review_invalidates_signed_approval(flow):
    local, manifest, remote, calls, *_ = flow
    value = json.loads(manifest.read_text())
    item = value["items"][0]
    cover = local / "shelf_cover.jpg"
    Image.new("RGB", (1440, 2560), "#335577").save(cover, format="JPEG")
    item["shelf_cover_file"] = cover.name
    item["shelf_cover_sha256"] = relay.sha(cover.read_bytes())
    relay.save(manifest, value)
    db, key = native(flow)

    Image.new("RGB", (1440, 2560), "#773355").save(cover, format="JPEG")
    value = json.loads(manifest.read_text())
    value["items"][0]["shelf_cover_sha256"] = relay.sha(cover.read_bytes())
    relay.save(manifest, value)

    with pytest.raises(ValueError, match="signed proof does not bind manifest"):
        relay.finalize(local, remote, db=db, key=key)
    assert not any("stage" in call for call in calls)


def test_cover_only_change_creates_new_attempt_and_old_proof_is_rejected(flow):
    import shutil

    local, manifest, remote, _, _, store_root, _ = flow
    value = json.loads(manifest.read_text())
    cover = local / "shelf_cover.jpg"
    Image.new("RGB", (1440, 2560), "#335577").save(cover, format="JPEG")
    value["items"][0].update(
        shelf_cover_file=cover.name,
        shelf_cover_sha256=relay.sha(cover.read_bytes()),
    )
    relay.save(manifest, value)
    db, key = native(flow)
    relay.finalize(local, remote, db=db, key=key)
    old = json.loads(manifest.read_text())["items"][0]

    from backend.services.knowledge_publication_store import PublicationStore

    store = PublicationStore(store_root)
    released = store.release_due(now=datetime(2026, 9, 8, 4, tzinfo=timezone.utc))
    assert len(released["released"]) == 1
    old_edition = store.status()[0]
    old_bundle = old_edition["bundle"]

    next_dir = local / "cover-revision"
    next_dir.mkdir()
    for name in ("bundle.json", "body.md", "source.json", "rights.json"):
        shutil.copyfile(local / name, next_dir / name)
    for role in relay.MEDIA_ROLES:
        if role != "shelf_cover":
            shutil.copyfile(local / old[f"{role}_file"], next_dir / old[f"{role}_file"])
    changed_cover = next_dir / cover.name
    Image.new("RGB", (1440, 2560), "#773355").save(changed_cover, format="JPEG")
    item = {
        key: value for key, value in old.items()
        if key not in {"bundle_sha256", "batch", "quality_contract", "receipt", "error"}
    }
    item.update(
        bundle_file="bundle.json", status="prepared",
        shelf_cover_sha256=relay.sha(changed_cover.read_bytes()),
    )
    next_manifest = next_dir / "draft-manifest.json"
    relay.save(next_manifest, {"version": relay.VERSION, "items": [item]})

    relay.prepare(next_manifest, remote, review_policy="story-supervision-v2")
    new = json.loads(next_manifest.read_text())["items"][0]
    assert new["status"] == "await_review"
    assert new["quality_contract"]["revision"] == old["quality_contract"]["revision"] + 1
    assert new["quality_contract"]["attempt_id"] != old["quality_contract"]["attempt_id"]

    shutil.copyfile(local / "review.json", next_dir / "review.json")
    shutil.copyfile(local / "proof.json", next_dir / "proof.json")
    with pytest.raises(ValueError, match="signed proof does not bind manifest"):
        relay.finalize(next_dir, remote, db=db, key=key)
    (next_dir / "review.json").unlink()
    (next_dir / "proof.json").unlink()

    relay.prepare(next_manifest, remote, review_policy="story-supervision-v2")
    assert json.loads(next_manifest.read_text())["items"][0]["quality_contract"] == new["quality_contract"]
    next_flow = (next_dir, next_manifest, *flow[2:])
    next_db, next_key = native(next_flow)
    relay.finalize(next_dir, remote, db=next_db, key=next_key)
    released = store.release_due(now=datetime(2026, 9, 8, 4, tzinfo=timezone.utc))
    assert len(released["released"]) == 1

    editions = {item["edition_id"]: item for item in store.status()}
    assert len(editions) == 2
    assert editions[old_edition["edition_id"]]["state"] == "withdrawn"
    assert editions[old_edition["edition_id"]]["bundle"] == old_bundle
    published = store.get_published(old_edition["publication_id"])
    assert published["edition_id"] != old_edition["edition_id"]
    assert store.get_published_cover(old_edition["publication_id"], "shelf_cover")[0] == changed_cover.read_bytes()


def test_published_v2_body_and_cover_remain_readable_after_review_time(flow):
    local, manifest, remote, _, _, store_root, _ = flow
    value = json.loads(manifest.read_text())
    cover = local / "shelf_cover.jpg"
    Image.new("RGB", (1440, 2560), "#335577").save(cover, format="JPEG")
    value["items"][0].update(
        shelf_cover_file=cover.name,
        shelf_cover_sha256=relay.sha(cover.read_bytes()),
    )
    relay.save(manifest, value)
    db, key = native(flow)
    relay.finalize(local, remote, db=db, key=key)

    from backend.services.knowledge_publication_store import PublicationStore

    store = PublicationStore(store_root)
    assert store.release_due(now=datetime(2026, 9, 8, 4, tzinfo=timezone.utc))["released"]
    proof = json.loads((local / "proof.json").read_text())
    assert "approval_expires_at" not in proof
    publication_id = store.status()[0]["publication_id"]
    assert store.get_published(publication_id, now=datetime(2027, 9, 8, 4, tzinfo=timezone.utc))
    assert store.get_published_cover(
        publication_id, "shelf_cover", now=datetime(2027, 9, 8, 4, tzinfo=timezone.utc)
    )


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_v2_review_without_valid_proof_is_not_recorded(flow, monkeypatch, decision):
    local, manifest, remote, _, _, _, intake = flow
    db, key = native(flow, decision)
    operator = remote.operator

    def tamper(action, *args):
        if action == "record-editorial-review":
            proof = Path(args[args.index("--proof-file") + 1].replace(
                "/app/data/runtime/publication-intake", str(intake)
            ))
            value = json.loads(proof.read_text())
            value["signature"] = "invalid"
            proof.write_text(json.dumps(value))
        return operator(action, *args)

    monkeypatch.setattr(remote, "operator", tamper)
    with pytest.raises(ValueError, match="remote command failed|attempt ID/hash/state readback mismatch"):
        relay.finalize(local, remote, db=db, key=key)
    item = json.loads(manifest.read_text())["items"][0]
    assert item["status"] == "await_review"
    assert relay.attempt(remote, item["quality_contract"], {"await_review"})["state"] == "await_review"


def test_running_native_is_pending_without_upload(flow):
    local, manifest, remote, calls, *_ = flow
    db, key = native(flow, ended=False)
    n = len(calls)
    assert (
        relay.finalize(local, remote, db=db, key=key)["items"][0]["status"] == "pending"
    )
    assert len(calls) == n
    assert not (local / "proof.json").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "body",
        "source",
        "unknown",
        "nohash",
        "escape",
        "symlink",
        "output_exists",
        "output_alias",
    ],
)
def test_manifest_rejects_unsafe_inputs_before_ssh(flow, mutation):
    local, manifest, remote, calls, *_ = flow
    value = json.loads(manifest.read_text())
    item = value["items"][0]
    if mutation in {"body", "source"}:
        (local / ("body.md" if mutation == "body" else "source.json")).write_text(
            "changed"
        )
    elif mutation == "unknown":
        item["upload_files"] = ["TEST-ONLY-key.pem"]
    elif mutation == "nohash":
        item.pop("body_sha256")
    elif mutation == "escape":
        item["body_file"] = "../outside.md"
    elif mutation == "symlink":
        (local / "alias.md").symlink_to(local / "body.md")
        item["body_file"] = "alias.md"
    elif mutation == "output_exists":
        (local / "review.json").write_text("{}")
    elif mutation == "output_alias":
        item["review_file"] = "body.md"
    relay.save(manifest, value)
    with pytest.raises(ValueError):
        relay.prepare(manifest, remote)
    assert calls == []


def test_remote_exclusive_conflict_and_idempotent_upload(flow):
    _, _, remote, _, _, _, intake = flow
    batch, raw = "a" * 32, b"TEST ONLY"
    remote.upload(batch, raw, ".bin")
    remote.upload(batch, raw, ".bin")
    target = intake / batch / (relay.sha(raw) + ".bin")
    target.write_bytes(b"CONFLICT")
    with pytest.raises(ValueError, match="remote command failed"):
        remote.upload(batch, raw, ".bin")
    assert target.read_bytes() == b"CONFLICT"


def test_admission_failure_never_stages_and_retry_is_fail_closed(flow, monkeypatch):
    local, manifest, remote, calls, *_ = flow
    db, key = native(flow)
    operator = remote.operator

    def fail(action, *args):
        if action == "record-editorial-review":
            raise ValueError("admission test failure")
        return operator(action, *args)

    monkeypatch.setattr(remote, "operator", fail)
    with pytest.raises(ValueError, match="admission"):
        relay.finalize(local, remote, db=db, key=key)
    assert not any("stage" in c for c in calls)
    assert json.loads(manifest.read_text())["items"][0]["status"] == "await_review"
    monkeypatch.setattr(remote, "operator", operator)
    assert (
        relay.finalize(local, remote, db=db, key=key)["items"][0]["status"] == "staged"
    )


def test_stage_readback_failure_is_not_reported_as_success(flow, monkeypatch):
    local, manifest, remote, _, *_ = flow
    db, key = native(flow)
    operator = remote.operator
    staged = False

    def broken(action, *args):
        nonlocal staged
        result = operator(action, *args)
        if action == "stage":
            staged = True
        if action == "status" and staged:
            result["items"] = []
        return result

    monkeypatch.setattr(remote, "operator", broken)
    with pytest.raises(ValueError, match="stage readback"):
        relay.finalize(local, remote, db=db, key=key)
    assert json.loads(manifest.read_text())["items"][0]["status"] == "await_review"
    monkeypatch.setattr(remote, "operator", operator)
    assert (
        relay.finalize(local, remote, db=db, key=key)["items"][0]["status"] == "staged"
    )


def test_native_forgery_and_body_change_cannot_stage(flow):
    local, _, remote, calls, *_ = flow
    db, key = native(flow)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE messages SET content='{}' WHERE id=2")
    with pytest.raises(ValueError):
        relay.finalize(local, remote, db=db, key=key)
    assert not any("stage" in c for c in calls)


@pytest.mark.parametrize("size", [110_000, 2 * 1024 * 1024])
def test_large_files_use_single_bounded_stdin_stream_and_exact_readback(flow, size):
    _, _, remote, calls, _, _, intake = flow
    raw = (bytes(range(256)) * ((size + 255) // 256))[:size]
    remote.upload("b" * 32, raw, ".md")
    assert (intake / ("b" * 32) / (relay.sha(raw) + ".md")).read_bytes() == raw
    assert len(calls) == 1
    assert max(len(shlex.join(call)) for call in calls) < 40_000
    assert calls[-1][-1] == ".md"


def test_draft_manifest_name_and_long_full_manuscript(flow):
    local, old, remote, _, *_ = flow
    value = json.loads(old.read_text())
    item = value["items"][0]
    body = (
        synthetic_fixture("book")[0]
        + "\n附录\n"
        + "仅用于合成测试的大正文传输。" * 2500
    )
    (local / "body.md").write_text(body)
    bundle = json.loads((local / "bundle.json").read_text())
    bundle["body_hash"] = item["body_sha256"] = relay.sha(body.encode())
    bundle["quality_contract"]["format"] = "book"
    relay.save(local / "bundle.json", bundle)
    manifest = local / "draft-manifest.json"
    relay.save(manifest, value)
    old.unlink()
    relay.prepare(manifest, remote)
    assert relay.manifests(local) == [manifest]
    request = json.loads(
        relay.review_input(local, remote)
        .split("PUBLICATION_REVIEW_REQUEST\n", 1)[1]
        .split("\nEND_PUBLICATION_REVIEW_REQUEST", 1)[0]
    )
    assert len(body.encode()) > 105_000
    assert gzip.decompress(base64.b64decode(
        "".join(request["manuscript_gzip_b64_chunks"]), validate=True
    )).decode() == body
    assert len("".join(request["manuscript_gzip_b64_chunks"])) < len(body.encode())


def test_ended_failed_native_is_error_not_pending(flow):
    local, _, remote, _, *_ = flow
    db, key = native(flow)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET end_reason='error' WHERE id='reviewer'")
    with pytest.raises(ValueError, match="not completed"):
        relay.finalize(local, remote, db=db, key=key)


def test_input_mutation_after_prepare_is_rejected(flow):
    local, _, remote, calls, *_ = flow
    db, key = native(flow)
    (local / "body.md").write_text("changed after preparation")
    count = len(calls)
    with pytest.raises(ValueError, match="hash mismatch"):
        relay.finalize(local, remote, db=db, key=key)
    assert len(calls) == count


def test_rejected_research_gaps_survive_next_revision(flow):
    import shutil

    local, manifest, remote, _, *_ = flow
    db, key = native(flow, "rejected")
    relay.finalize(local, remote, db=db, key=key)
    old = json.loads(manifest.read_text())["items"][0]
    next_dir = local / "next"
    next_dir.mkdir()
    for name in (
        "bundle.json", "body.md", "source.json", "rights.json", "shelf_cover.jpg",
        "reader_cover.jpg", "illustration_01.jpg", "illustration_02.jpg", "illustration_03.jpg",
    ):
        shutil.copyfile(local / name, next_dir / name)
    item = {
        k: v
        for k, v in old.items()
        if k not in {"bundle_sha256", "batch", "quality_contract", "receipt", "error"}
    }
    item.update(bundle_file="bundle.json", status="prepared")
    next_manifest = next_dir / "draft-manifest.json"
    relay.save(next_manifest, {"version": relay.VERSION, "items": [item]})
    relay.prepare(next_manifest, remote)
    new = json.loads(next_manifest.read_text())["items"][0]
    assert (
        new["quality_contract"]["revision"] == old["quality_contract"]["revision"] + 1
    )
    assert new["batch"] != old["batch"]
    assert "need-primary" in [g["id"] for g in new["quality_contract"]["research_gaps"]]


def test_content_only_revision_builds_and_prepares_all_platform_fields(flow, tmp_path):
    local, manifest, remote, _, *_ = flow
    db, key = native(flow, "rejected")
    relay.finalize(local, remote, db=db, key=key)
    old = json.loads(manifest.read_text())["items"][0]
    old_body = (local / "body.md").read_text()
    revised_body = tmp_path / "revised-body.md"
    revised_body.write_text(
        old_body + "\n### 审稿缺口修订\n本段补充一手来源核验方法，并明确由下一轮独立审稿确认是否满足证据要求。\n",
        encoding="utf-8",
    )

    revision_manifest = relay.build_revision(
        manifest, revised_body, writer_session="cron_revision_session"
    )
    revision_dir = revision_manifest.parent
    pending = json.loads(revision_manifest.read_text())["items"][0]
    bundle = json.loads((revision_dir / pending["bundle_file"]).read_text())
    rights = json.loads(
        (revision_dir / pending["rights_files"][0]["path"]).read_text()
    )

    assert pending["status"] == "prepared"
    assert pending["body_sha256"] == relay.sha(revised_body.read_bytes())
    assert pending["bundle_sha256"] == relay.sha(
        (revision_dir / pending["bundle_file"]).read_bytes()
    )
    assert not {"revision", "attempt_id", "issue_id", "target_hash"} & set(
        bundle["quality_contract"]
    )
    assert bundle["quality_contract"]["writer_sessions"][-1] == "hermes:cron_revision_session"
    assert "need-primary" in {
        gap["id"] for gap in bundle["quality_contract"]["research_gaps"]
    }
    assert all(
        gap["state"] == "resolved"
        for gap in bundle["quality_contract"]["research_gaps"]
    )
    assert rights["body_sha256"] == pending["body_sha256"]
    assert rights["content_hashes"] == [pending["body_sha256"]]
    assert not (revision_dir / pending["review_file"]).exists()
    assert not (revision_dir / pending["proof_file"]).exists()
    assert all(
        pending[f"{role}_sha256"] == old[f"{role}_sha256"]
        for role in relay.MEDIA_ROLES
    )

    result = relay.prepare(revision_manifest, remote)
    assert result["statuses"] == ["await_review"]
    prepared = json.loads(revision_manifest.read_text())["items"][0]
    assert prepared["quality_contract"]["revision"] == old["quality_contract"]["revision"] + 1
    assert prepared["quality_contract"]["previous_body_hash"] == old["body_sha256"]


def test_content_only_revision_rejects_unchanged_body(flow):
    local, manifest, remote, _, *_ = flow
    db, key = native(flow, "rejected")
    relay.finalize(local, remote, db=db, key=key)

    with pytest.raises(ValueError, match="materially change"):
        relay.build_revision(manifest, local / "body.md", writer_session="revision")


def test_content_only_revision_rejects_visual_gap(flow, tmp_path):
    local, manifest, remote, _, *_ = flow
    db, key = native(flow, "rejected")
    relay.finalize(local, remote, db=db, key=key)
    review = json.loads((local / "review.json").read_text())
    review["research_gaps"][0]["required_evidence"] = "重新生成与正文匹配的封面和插图"
    relay.save(local / "review.json", review)
    revised_body = tmp_path / "revised.md"
    revised_body.write_text((local / "body.md").read_text() + "\n实质修订内容。\n")

    with pytest.raises(ValueError, match="replacement media"):
        relay.build_revision(manifest, revised_body, writer_session="revision")


def test_prepare_wrong_server_target_readback_is_failure(flow, monkeypatch):
    _, manifest, remote, calls, *_ = flow
    operator = remote.operator

    def corrupt(action, *args):
        result = operator(action, *args)
        if action == "status":
            result["editorial_attempts"][0]["target_hash"] = "0" * 64
        return result

    monkeypatch.setattr(remote, "operator", corrupt)
    with pytest.raises(ValueError, match="ID/hash/state"):
        relay.prepare(manifest, remote)
    assert json.loads(manifest.read_text())["items"][0]["status"] == "prepared"
    assert not any("stage" in c for c in calls)


def test_remote_symlink_batch_is_rejected(flow):
    local, _, remote, _, _, _, intake = flow
    intake.mkdir()
    (intake / ("c" * 32)).symlink_to(local, target_is_directory=True)
    with pytest.raises(ValueError, match="remote command failed"):
        remote.upload("c" * 32, b"TEST", ".bin")
    assert not (local / (relay.sha(b"TEST") + ".bin")).exists()


def test_upload_transport_empty_stdout_is_not_json_error(flow, monkeypatch):
    _, _, remote, *_ = flow
    monkeypatch.setattr(
        transport,
        "_ssh",
        lambda *a, **kw: subprocess.CompletedProcess([], 255, "", "TEST connection failed"),
    )
    with pytest.raises(ValueError, match="exit 255"):
        remote.upload("a" * 32, b"x", ".bin")


def initial_submission(tmp_path):
    body_dir = tmp_path / "initial"
    body_dir.mkdir()
    body = synthetic_fixture("chapter")[0] + "\n[来源](https://example.com/source)\n"
    (body_dir / "body.md").write_text(body, encoding="utf-8")
    (body_dir / "source.json").write_text('{"source":"synthetic"}', encoding="utf-8")
    (body_dir / "execution.log").write_text("synthetic execution passed", encoding="utf-8")
    for role, (_, width, height) in relay.MEDIA_CONTRACT.items():
        Image.new("RGB", (width, height), "#445566").save(body_dir / f"{role}.jpg", "JPEG")
    submission = {
        "title": "内容作者提交的合成标题",
        "summary": "内容作者提交的合成摘要，仅用于自动化测试。",
        "editorial_brief": synthetic_brief(),
        "learning_objectives": ["验证初稿作者只提交内容和真实材料而不填写控制字段"],
        "source_files": [{"kind": "source_snapshot", "path": "source.json"}],
        "execution_files": [{"kind": "execution_log", "path": "execution.log"}],
    }
    path = body_dir / "content-submission.json"
    path.write_text(json.dumps(submission, ensure_ascii=False), encoding="utf-8")
    return body_dir, path


def test_content_only_initial_builder_generates_and_prepares_control_fields(flow, tmp_path):
    _, _, remote, _, *_ = flow
    body_dir, submission = initial_submission(tmp_path)

    manifest = relay.build_initial(
        submission, body_dir, series_id="ai-toolkit", issue_date="2026-09-24", issue_slot="12:00",
        format="chapter", owner_policy_id="synthetic-owner-policy",
        writer_session="initial-writer",
    )
    before = manifest.read_bytes()
    item = json.loads(before)["items"][0]
    bundle = json.loads((body_dir / item["bundle_file"]).read_text())
    rights = json.loads((body_dir / item["rights_files"][0]["path"]).read_text())

    assert item["status"] == "prepared"
    assert item["body_sha256"] == relay.sha((body_dir / "body.md").read_bytes())
    assert item["bundle_sha256"] == relay.sha((body_dir / "candidate-bundle.json").read_bytes())
    assert all(item[f"{role}_sha256"] for role in relay.MEDIA_ROLES)
    assert rights["content_hashes"] == [item["body_sha256"]]
    assert rights["attested_by"] == "local_owner_policy"
    assert bundle["quality_contract"] == {
        "format": "chapter", "writer_sessions": ["hermes:initial-writer"],
        "learning_objectives": ["验证初稿作者只提交内容和真实材料而不填写控制字段"],
        "editorial_brief": synthetic_brief(), "research_gaps": [],
    }
    assert bundle["execution_claim"] == "success"
    assert not ({"revision", "issue_id", "attempt_id", "target_hash"}
                & set(bundle["quality_contract"]))
    assert relay.build_initial(
        submission, body_dir, series_id="ai-toolkit", issue_date="2026-09-24", issue_slot="12:00",
        format="chapter", owner_policy_id="synthetic-owner-policy",
        writer_session="initial-writer",
    ).read_bytes() == before

    assert relay.prepare(manifest, remote)["statuses"] == ["await_review"]
    assert relay.prepare(manifest, remote)["statuses"] == ["await_review"]
    assert relay.build_initial(
        submission, body_dir, series_id="ai-toolkit", issue_date="2026-09-24", issue_slot="12:00",
        format="chapter", owner_policy_id="synthetic-owner-policy",
        writer_session="retry-in-another-session",
    ) == manifest


def test_start_cli_builds_then_uses_existing_prepare_path(flow, tmp_path, monkeypatch, capsys):
    _, _, remote, _, *_ = flow
    body_dir, submission = initial_submission(tmp_path)
    monkeypatch.setenv("HERMES_SESSION_ID", "cli-initial-writer")
    monkeypatch.setattr(transport, "_trust", lambda _args: ("TEST-ONLY", "TEST-ONLY"))
    monkeypatch.setattr(relay, "Remote", lambda *_args: remote)
    args = [
        "start", "--submission", str(submission), "--body-dir", str(body_dir),
        "--series-id", "ai-toolkit", "--issue-date", "2026-09-24", "--issue-slot", "12:00",
        "--format", "chapter", "--owner-policy-id", "synthetic-owner-policy",
    ]

    assert relay.main(args) == 0
    assert json.loads(capsys.readouterr().out)["statuses"] == ["await_review"]
    monkeypatch.setenv("HERMES_SESSION_ID", "cli-retry-writer")
    assert relay.main(args) == 0
    assert json.loads(capsys.readouterr().out)["statuses"] == ["await_review"]


@pytest.mark.parametrize("forbidden", [
    "revision", "issue_id", "attempt_id", "target_hash", "body_sha256",
    "rights_evidence", "review", "state", "publication_id", "execution_claim",
])
def test_content_submission_rejects_author_control_fields(tmp_path, forbidden):
    body_dir, submission = initial_submission(tmp_path)
    value = json.loads(submission.read_text())
    value[forbidden] = "author-controlled"
    submission.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="forbidden"):
        relay.build_initial(
            submission, body_dir, series_id="ai-history", issue_date="2026-09-24",
            format="chapter", owner_policy_id="synthetic-owner-policy",
            writer_session="initial-writer",
        )


@pytest.mark.parametrize("mutation", ["escape", "source_hash", "missing_media", "bad_dimensions"])
def test_content_only_initial_builder_rejects_unsafe_or_invalid_material(tmp_path, mutation):
    body_dir, submission = initial_submission(tmp_path)
    value = json.loads(submission.read_text())
    if mutation == "escape":
        outside = tmp_path / "outside.json"
        outside.write_text("{}")
        value["source_files"][0]["path"] = "../outside.json"
        submission.write_text(json.dumps(value), encoding="utf-8")
    elif mutation == "source_hash":
        value["source_files"][0]["sha256"] = "0" * 64
        submission.write_text(json.dumps(value), encoding="utf-8")
    elif mutation == "missing_media":
        (body_dir / "illustration_03.jpg").unlink()
    else:
        Image.new("RGB", (100, 100), "#445566").save(body_dir / "reader_cover.jpg", "JPEG")

    with pytest.raises(ValueError):
        relay.build_initial(
            submission, body_dir, series_id="ai-history", issue_date="2026-09-24",
            format="chapter", owner_policy_id="synthetic-owner-policy",
            writer_session="initial-writer",
        )


def test_four_field_content_submission_derives_history_system_fields(tmp_path):
    body_dir, path = initial_submission(tmp_path)
    value = json.loads(path.read_text())
    value.pop("editorial_brief")
    value.pop("learning_objectives")
    (body_dir / "source.json").write_text('{"source":"https://example.com/history"}')
    relay.save(path, value)
    manifest = relay.build_initial(path, body_dir, series_id="ai-history", issue_date="2026-09-24",
        format="chapter", owner_policy_id="synthetic-policy", writer_session="original-author")
    item = json.loads(manifest.read_text())["items"][0]
    bundle = json.loads((body_dir / item["bundle_file"]).read_text())
    contract = bundle["quality_contract"]
    assert contract["editorial_brief"]["genre"] == relay.SERIES["ai-history"]["genre"]
    assert contract["editorial_brief"]["evidence_urls"] == ["https://example.com/history"]
    assert contract["learning_objectives"]
    assert "教程" not in contract["editorial_brief"]["thesis"]


@pytest.mark.parametrize("mutation", [None, "writer", "body", "title", "summary"])
def test_v2_initial_builder_preserves_original_author_and_exact_content(tmp_path, monkeypatch, mutation):
    from backend.services.publication_workflow_handoff import canonical_json
    body_dir, path = initial_submission(tmp_path)
    value = json.loads(path.read_text())
    artifact = {"schema_version": "publication-content-v1", "title": value["title"],
                "summary": value["summary"], "body": (body_dir / "body.md").read_text(),
                "source_documents": [{"kind": "source_snapshot", "content": "https://example.com/history"}],
                "execution_documents": []}
    raw = canonical_json(artifact)
    (body_dir / "workflow-artifact.json").write_bytes(raw)
    envelope = {"version": "publication-workflow-handoff-v2", "series_id": "ai-history",
                "issue_date": "2026-09-24", "issue_key": "2026-09-24", "issue_slot": "12:00",
                "release_at": "2026-09-24T12:00:00+08:00", "artifact_sha256": relay.sha(raw),
                "writer_session": "original-author"}
    envelope_raw = canonical_json(envelope)
    (body_dir / "workflow-envelope.json").write_bytes(envelope_raw)
    relay.save(body_dir / "workflow-handoff-state.json", {"envelope_sha256": relay.sha(envelope_raw)})
    monkeypatch.setenv("HERMES_SESSION_ID", "asset-generator")
    if mutation == "body":
        (body_dir / "body.md").write_text(artifact["body"] + "\n未经作者确认的新正文。\n")
    elif mutation in {"title", "summary"}:
        value[mutation] += "未经作者确认的变化"
        relay.save(path, value)
    kwargs = dict(series_id="ai-history", issue_date="2026-09-24", format="chapter", owner_policy_id="synthetic-policy")
    if mutation == "writer":
        kwargs["writer_session"] = "asset-generator"
    if mutation:
        with pytest.raises(ValueError, match="cannot be replaced|content conflicts"):
            relay.build_initial(path, body_dir, **kwargs)
        assert not (body_dir / "candidate-bundle.json").exists()
    else:
        manifest = relay.build_initial(path, body_dir, **kwargs)
        item = json.loads(manifest.read_text())["items"][0]
        bundle = json.loads((body_dir / item["bundle_file"]).read_text())
        assert bundle["quality_contract"]["writer_sessions"] == ["hermes:original-author"]
        assert bundle["body"] == artifact["body"]


def test_review_input_does_not_offer_story_request_to_default_profile(flow, monkeypatch):
    local, manifest, remote, *_ = flow
    relay.prepare(manifest, remote, review_policy="story-supervision-v2")
    monkeypatch.setenv("HERMES_PROFILE", "default")
    assert json.loads(relay.review_input(local, remote)) == {"status": "no_await_review"}
    monkeypatch.setenv("HERMES_PROFILE", "supervision")
    assert "PUBLICATION_REVIEW_REQUEST" in relay.review_input(local, remote)


def test_review_input_does_not_offer_default_request_to_supervision(flow, monkeypatch):
    local, manifest, remote, *_ = flow
    relay.prepare(manifest, remote)
    monkeypatch.setenv("HERMES_PROFILE", "supervision")
    assert json.loads(relay.review_input(local, remote)) == {"status": "no_await_review"}


def test_rejected_native_content_enters_revision_two_and_independent_approval(flow, tmp_path, monkeypatch):
    from backend.services.knowledge_publication_store import SERIES
    from scripts import publication_workflow_handoff as handoff
    local, old_manifest, remote, calls, key, store, intake = flow
    databases, _ = native(flow, "rejected")
    relay.finalize(local, remote, db=databases, key=key)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setitem(SERIES, "ai-history", {**SERIES["ai-history"], "author_job_id": "historyjob", "author_profile": "story"})
    root = handoff.native_output_root()
    root.mkdir(parents=True)
    shutil.copytree(local, root / "prior-rejected")
    body = (local / "body.md").read_text() + "\n### 证据补充\n补充核验一手来源，澄清历史背景，并由独立审稿重新确认缺口得到解决。\n"
    content = {"schema_version": "publication-content-v1", "title": "修订后的合成历史文章",
        "summary": "合成测试内容，用于核验真实拒稿进入下一轮审核。", "body": body,
        "source_documents": [{"kind": "source_snapshot", "content": "https://example.com/source"}], "execution_documents": []}
    artifact = root / "revised-content.json"
    artifact.write_bytes(handoff.canonical_json(content))
    db_path = tmp_path / ".hermes/profiles/story/state.db"
    db_path.parent.mkdir(parents=True)
    shutil.copyfile(databases["story"], db_path)
    sid = "cron_historyjob_revised"
    request = {"series_id": "ai-history", "issue_date": "2026-09-08", "issue_slot": "12:00",
        "issue_key": "2026-09-08", "release_at": "2026-09-08T12:00:00+08:00", "author_job_id": "historyjob"}
    packet = "PUBLICATION_CONTENT_REQUEST\n" + json.dumps(request) + "\nEND_PUBLICATION_CONTENT_REQUEST"
    result = {"publication_content_result": {"series_id": "ai-history", "issue_date": "2026-09-08",
        "issue_slot": "12:00", "artifact_file": str(artifact)}}
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)", (sid, "story", None, "cron", 100, "cron_complete", 90))
        db.execute("INSERT INTO messages VALUES(1,?,'user',?,NULL,NULL,1,0)", (sid, packet))
        db.execute("INSERT INTO messages VALUES(2,?,'assistant',?,NULL,'stop',1,0)", (sid, json.dumps(result)))
    material = handoff.fetch_native("ai-history", "2026-09-08", root)
    base = Path(material["output_directory"])
    for role in relay.MEDIA_ROLES:
        shutil.copyfile(local / f"{role}.jpg", base / f"{role}.jpg")
    manifest = relay.build_initial(base / "content-submission.json", base, series_id="ai-history",
        issue_date="2026-09-08", issue_slot="12:00", format="chapter", owner_policy_id="fixture-policy")
    item = json.loads(manifest.read_text())["items"][0]
    bundle = json.loads((base / item["bundle_file"]).read_text())
    assert bundle["quality_contract"]["research_gaps"][0]["id"] == "need-primary"
    assert bundle["quality_contract"]["research_gaps"][0]["state"] == "resolved"
    assert bundle["quality_contract"]["writer_sessions"] == ["hermes:writer", f"hermes:{sid}"]
    new_flow = (base, manifest, remote, calls, key, store, intake)
    review_dbs, _ = native(new_flow)
    current_item = json.loads(manifest.read_text())["items"][0]
    shutil.copyfile(base / "review.json", base / current_item["review_file"])
    with sqlite3.connect(review_dbs["story"]) as db:
        db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)", (sid, "story", None, "cron", 100, "cron_complete", 90))
    assert json.loads(manifest.read_text())["items"][0]["quality_contract"]["revision"] == 2
    assert relay.finalize(base, remote, db=review_dbs, key=key)["items"][0]["status"] == "staged"
