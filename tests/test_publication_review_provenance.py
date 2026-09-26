"""Isolated synthetic native DB tests; never production review evidence."""
import hashlib
import base64
import gzip
import json
import sqlite3
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.services.publication_review_provenance import (
    REQUEST_END, REQUEST_START, attest_native_review, publication_material_hash,
    native_reviewed_at, verify_review_proof,
)
from backend.services.publication_editorial import editorial_target_hash


@pytest.fixture
def native(tmp_path):
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    manuscript = "## 示例章\n\n这是用于协议测试的隔离合成材料，不是通过质量门禁的真实图书。\n"
    contract = {"writer_sessions": ["hermes:writer"], "revision": 1}
    target = editorial_target_hash(manuscript, contract, [])
    review = {"reviewer_session": "hermes:reviewer", "editorial_target_hash": target, "revision": 1, "decision": "approved",
              "content_hash": hashlib.sha256(manuscript.encode()).hexdigest()}
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    request = {"purpose": "publication_editorial_review", "owner": "local_owner", "profile": "default",
               "issue_id": "ai-practice-2026-09-11", "revision": 1, "attempt_id": "nonce1",
               "editorial_target_hash": target, "writer_sessions": ["hermes:writer"],
               "manuscript": manuscript, "quality_contract": contract, "source_receipts": []}
    result = {**request, "review_file_hash": sha, "reviewer_session": "hermes:reviewer", "decision": "approved"}
    db_path = tmp_path / "state.db"
    with sqlite3.connect(db_path) as db:
        db.executescript("""CREATE TABLE sessions(id TEXT PRIMARY KEY, profile_name TEXT, user_id TEXT, source TEXT, ended_at REAL, end_reason TEXT, started_at REAL);
        CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, tool_calls TEXT, finish_reason TEXT, active INTEGER DEFAULT 1, compacted INTEGER DEFAULT 0);""")
        db.executemany("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)", [(s, "default", None, "desktop", 20.0, "agent_close", 10.0) for s in ("writer", "reviewer")])
        db.execute("INSERT INTO messages VALUES(1,'reviewer','user',?,NULL,NULL,1,0)", (REQUEST_START + json.dumps(request) + REQUEST_END,))
        db.execute("INSERT INTO messages VALUES(2,'reviewer','assistant',?,NULL,'stop',1,0)", (json.dumps({"publication_review_result": result}),))
    expected = {"issue_id": request["issue_id"], "revision": 1, "attempt_id": "nonce1", "target_hash": target,
                "review_file_hash": sha, "reviewer_session": "hermes:reviewer", "writer_sessions": ["hermes:writer"]}
    return db_path, path, private, public, expected


@pytest.fixture
def cross_profile_native(tmp_path):
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    manuscript = "## 示例章\n\n这是用于跨 profile 协议测试的隔离合成材料。\n"
    contract = {"writer_sessions": ["hermes:writer"], "revision": 2,
                "review_policy": "story-supervision-v2"}
    target = editorial_target_hash(manuscript, contract, [])
    assets = [
        {"url": "https://example.com/a.png", "sha256": "a" * 64},
        {"url": "https://example.com/b.png", "sha256": "b" * 64},
    ]
    material_hash = publication_material_hash(target, assets)
    review = {"reviewer_session": "hermes:reviewer", "editorial_target_hash": target,
              "publication_material_hash": material_hash, "revision": 2, "decision": "approved",
              "content_hash": hashlib.sha256(manuscript.encode()).hexdigest()}
    path = tmp_path / "cross-review.json"
    path.write_text(json.dumps(review))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    request = {"purpose": "publication_editorial_review", "owner": "local_owner",
               "review_policy": "story-supervision-v2", "writer_profile": "story",
               "reviewer_profile": "supervision", "writer_role": "story_author",
               "reviewer_role": "supervision_reviewer", "issue_id": "story-2026-09-25",
               "revision": 2, "attempt_id": "nonce2", "editorial_target_hash": target,
               "publication_material_hash": material_hash, "assets": assets,
               "writer_sessions": ["hermes:writer"], "manuscript": manuscript,
               "quality_contract": contract, "source_receipts": []}
    result = {key: request[key] for key in (
        "issue_id", "revision", "attempt_id", "editorial_target_hash",
        "publication_material_hash",
    )}
    result.update(review_file_hash=sha, reviewer_session="hermes:reviewer", decision="approved")
    writer_db, reviewer_db = tmp_path / "story-state.db", tmp_path / "supervision-state.db"
    schema = """CREATE TABLE sessions(id TEXT PRIMARY KEY, profile_name TEXT, user_id TEXT, source TEXT, ended_at REAL, end_reason TEXT, started_at REAL);
    CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, tool_calls TEXT, finish_reason TEXT, active INTEGER DEFAULT 1, compacted INTEGER DEFAULT 0);"""
    now = time.time()
    with sqlite3.connect(writer_db) as db:
        db.executescript(schema)
        db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)", ("writer", "story", None, "desktop", now, "agent_close", now - 10))
    with sqlite3.connect(reviewer_db) as db:
        db.executescript(schema)
        db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)", ("reviewer", "supervision", None, "desktop", now, "agent_close", now - 10))
        db.execute("INSERT INTO messages VALUES(1,'reviewer','user',?,NULL,NULL,1,0)", (REQUEST_START + json.dumps(request) + REQUEST_END,))
        db.execute("INSERT INTO messages VALUES(2,'reviewer','assistant',?,NULL,'stop',1,0)", (json.dumps({"publication_review_result": result}),))
    expected = {"issue_id": request["issue_id"], "revision": 2, "attempt_id": "nonce2",
                "target_hash": target, "review_file_hash": sha,
                "reviewer_session": "hermes:reviewer", "writer_sessions": ["hermes:writer"],
                "required_policy": "story-supervision-v2", "assets": assets}
    return writer_db, reviewer_db, path, private, public, expected


def test_story_author_and_supervision_reviewer_are_attested_across_owned_databases(cross_profile_native):
    writer_db, reviewer_db, review, key, public, expected = cross_profile_native
    proof = attest_native_review(reviewer_db, review, key, profile="supervision",
                                 writer_profile="story", writer_db_path=writer_db)
    assert verify_review_proof(proof, public, **expected) == []
    assert proof["proof_version"] == "native-editorial-review-v2"


@pytest.mark.parametrize("failure", ["unknown_profile", "swapped_db", "path_injection", "wrong_owner", "wrong_reviewer_owner", "self_review"])
def test_cross_profile_attestation_rejects_untrusted_identity_or_database(cross_profile_native, failure):
    writer_db, reviewer_db, review, key, _, _ = cross_profile_native
    kwargs = {"profile": "supervision", "writer_profile": "story", "writer_db_path": writer_db}
    if failure == "unknown_profile":
        kwargs["writer_profile"] = "unknown"
    elif failure == "swapped_db":
        kwargs["writer_db_path"] = reviewer_db
    elif failure == "path_injection":
        with sqlite3.connect(reviewer_db) as db:
            content = db.execute("SELECT content FROM messages WHERE id=1").fetchone()[0]
            request = json.loads(content.split(REQUEST_START, 1)[1].split(REQUEST_END, 1)[0])
            request["writer_db_path"] = "../../default/state.db"
            db.execute("UPDATE messages SET content=? WHERE id=1", (REQUEST_START + json.dumps(request) + REQUEST_END,))
    elif failure == "wrong_owner":
        with sqlite3.connect(writer_db) as db:
            db.execute("UPDATE sessions SET user_id='other-owner'")
    elif failure == "wrong_reviewer_owner":
        with sqlite3.connect(reviewer_db) as db:
            db.execute("UPDATE sessions SET user_id='other-owner'")
    else:
        value = json.loads(review.read_text())
        value["reviewer_session"] = "hermes:writer"
        review.write_text(json.dumps(value))
        with sqlite3.connect(reviewer_db) as db:
            db.execute("UPDATE sessions SET id='writer' WHERE id='reviewer'")
            db.execute("UPDATE messages SET session_id='writer'")
            final = json.loads(db.execute("SELECT content FROM messages WHERE id=2").fetchone()[0])
            final["publication_review_result"]["reviewer_session"] = "hermes:writer"
            final["publication_review_result"]["review_file_hash"] = hashlib.sha256(review.read_bytes()).hexdigest()
            db.execute("UPDATE messages SET content=? WHERE id=2", (json.dumps(final),))
    with pytest.raises(ValueError):
        attest_native_review(reviewer_db, review, key, **kwargs)


def test_cross_profile_approval_does_not_expire_without_material_change(cross_profile_native):
    writer_db, reviewer_db, review, key, public, expected = cross_profile_native
    proof = attest_native_review(reviewer_db, review, key, profile="supervision",
                                 writer_profile="story", writer_db_path=writer_db)
    assert verify_review_proof(proof, public, now=proof["native_ended_at"] + 365 * 86400, **expected) == []


@pytest.mark.parametrize("changed", [
    [
        {"url": "https://example.com/a.png", "sha256": "b" * 64},
        {"url": "https://example.com/b.png", "sha256": "a" * 64},
    ],
    [
        {"role": "shelf_cover", "sha256": "a" * 64},
        {"url": "https://example.com/b.png", "sha256": "b" * 64},
    ],
])
def test_v2_proof_rejects_valid_hashes_reassigned_to_another_asset(cross_profile_native, changed):
    writer_db, reviewer_db, review, key, public, expected = cross_profile_native
    proof = attest_native_review(reviewer_db, review, key, profile="supervision",
                                 writer_profile="story", writer_db_path=writer_db)
    assert "provenance.assets" in verify_review_proof(
        proof, public, **{**expected, "assets": changed}
    )


def test_v1_default_proof_cannot_satisfy_story_supervision_policy(native):
    db, review, key, public, expected = native
    proof = attest_native_review(db, review, key)
    assert "provenance.proof_version" in verify_review_proof(
        proof, public, required_policy="story-supervision-v2", assets=[], **expected
    )


def test_exact_native_completed_output_is_signed_and_readonly(native):
    db, review, key, public, expected = native
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    proof = attest_native_review(db, review, key)
    assert verify_review_proof(proof, public, **expected) == []
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert "content" not in proof


def test_base64_review_material_survives_markdown_fences(native):
    db, review, key, public, expected = native
    with sqlite3.connect(db) as conn:
        first = json.loads(conn.execute("SELECT content FROM messages WHERE id=1").fetchone()[0].split(REQUEST_START, 1)[1].split(REQUEST_END, 1)[0])
        manuscript = first.pop("manuscript")
        first["manuscript_b64"] = base64.b64encode(manuscript.encode()).decode()
        conn.execute("UPDATE messages SET content=? WHERE id=1", (REQUEST_START + json.dumps(first) + REQUEST_END,))
    proof = attest_native_review(db, review, key)
    assert verify_review_proof(proof, public, **expected) == []


def test_gzip_base64_review_material_survives_bounded_transport(native):
    db, review, key, public, expected = native
    with sqlite3.connect(db) as conn:
        content = conn.execute("SELECT content FROM messages WHERE id=1").fetchone()[0]
        first = json.loads(content.split(REQUEST_START, 1)[1].split(REQUEST_END, 1)[0])
        manuscript = first.pop("manuscript")
        first["manuscript_gzip_b64"] = base64.b64encode(
            gzip.compress(manuscript.encode(), mtime=0)
        ).decode()
        conn.execute("UPDATE messages SET content=? WHERE id=1", (
            REQUEST_START + json.dumps(first) + REQUEST_END,
        ))
    proof = attest_native_review(db, review, key)
    assert verify_review_proof(proof, public, **expected) == []


def test_chunked_gzip_base64_survives_token_redaction_boundaries(native):
    db, review, key, public, expected = native
    with sqlite3.connect(db) as conn:
        content = conn.execute("SELECT content FROM messages WHERE id=1").fetchone()[0]
        first = json.loads(content.split(REQUEST_START, 1)[1].split(REQUEST_END, 1)[0])
        manuscript = first.pop("manuscript")
        compressed = base64.b64encode(gzip.compress(manuscript.encode(), mtime=0)).decode()
        first["manuscript_gzip_b64_chunks"] = [
            compressed[i:i + 12] for i in range(0, len(compressed), 12)
        ]
        conn.execute("UPDATE messages SET content=? WHERE id=1", (
            REQUEST_START + json.dumps(first) + REQUEST_END,
        ))
    proof = attest_native_review(db, review, key)
    assert verify_review_proof(proof, public, **expected) == []


@pytest.mark.parametrize("chunks", [[], [""], ["a" * 13], ["valid", 1]])
def test_invalid_chunked_gzip_review_material_is_rejected(native, chunks):
    db, review, key, _, _ = native
    with sqlite3.connect(db) as conn:
        content = conn.execute("SELECT content FROM messages WHERE id=1").fetchone()[0]
        first = json.loads(content.split(REQUEST_START, 1)[1].split(REQUEST_END, 1)[0])
        first.pop("manuscript")
        first["manuscript_gzip_b64_chunks"] = chunks
        conn.execute("UPDATE messages SET content=? WHERE id=1", (
            REQUEST_START + json.dumps(first) + REQUEST_END,
        ))
    with pytest.raises(ValueError, match="lacks actual review material"):
        attest_native_review(db, review, key)


def test_corrupted_gzip_review_material_is_rejected(native):
    db, review, key, _, _ = native
    with sqlite3.connect(db) as conn:
        content = conn.execute("SELECT content FROM messages WHERE id=1").fetchone()[0]
        first = json.loads(content.split(REQUEST_START, 1)[1].split(REQUEST_END, 1)[0])
        first.pop("manuscript")
        first["manuscript_gzip_b64"] = "not-gzip"
        conn.execute("UPDATE messages SET content=? WHERE id=1", (
            REQUEST_START + json.dumps(first) + REQUEST_END,
        ))
    with pytest.raises(ValueError, match="lacks actual review material"):
        attest_native_review(db, review, key)


@pytest.mark.parametrize("sql", [
    "UPDATE sessions SET ended_at=NULL WHERE id='reviewer'",
    "UPDATE sessions SET end_reason='error' WHERE id='reviewer'",
    "UPDATE sessions SET user_id='other-owner' WHERE id='reviewer'",
    "UPDATE sessions SET profile_name='other-profile' WHERE id='reviewer'",
    "UPDATE sessions SET source='cloud' WHERE id='reviewer'",
    "UPDATE sessions SET profile_name='other-profile' WHERE id='writer'",
    "UPDATE messages SET finish_reason='tool_calls' WHERE id=2",
    "UPDATE messages SET content='unrelated successful session' WHERE id=1",
    "UPDATE messages SET content='{}' WHERE id=2",
    "UPDATE messages SET active=0 WHERE id=2",
    "UPDATE messages SET compacted=1 WHERE id=1",
    "UPDATE sessions SET end_reason='cron_incomplete_no_output' WHERE id='reviewer'",
])
def test_wrong_or_unfinished_native_execution_is_rejected(native, sql):
    db, review, key, _, _ = native
    with sqlite3.connect(db) as conn:
        conn.execute(sql)
    with pytest.raises(ValueError):
        attest_native_review(db, review, key)


def test_true_receipt_cannot_attest_other_review_bytes(native):
    db, review, key, _, _ = native
    value = json.loads(review.read_text())
    value["extra"] = "changed after real native final"
    review.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="actual review bytes"):
        attest_native_review(db, review, key)


@pytest.mark.parametrize("field,value", [("revision", 2), ("attempt_id", "nonce2"), ("issue_id", "other"),
                                         ("target_hash", "b" * 64), ("review_file_hash", "b" * 64),
                                         ("reviewer_session", "hermes:writer"), ("writer_sessions", ["hermes:other"])])
def test_signed_proof_cannot_be_replayed_to_another_target(native, field, value):
    db, review, key, public, expected = native
    proof = attest_native_review(db, review, key)
    expected[field] = value
    assert verify_review_proof(proof, public, **expected)


def test_self_supplied_key_and_tampered_signature_are_rejected(native):
    db, review, key, public, expected = native
    proof = attest_native_review(db, review, key)
    other = Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    assert verify_review_proof(proof, other, **expected) == ["provenance.signature"]
    proof["decision"] = "rejected"
    assert verify_review_proof(proof, public, **expected) == ["provenance.signature"]


@pytest.mark.parametrize('source,end_reason', [('cron','cron_complete'), ('desktop','cli_close')])
def test_observed_native_surface_terminal_pairs(native, source, end_reason):
    db, review, key, public, expected = native
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE sessions SET source=?,end_reason=?', (source,end_reason))
    proof = attest_native_review(db, review, key)
    assert verify_review_proof(proof, public, **expected) == []


def test_local_owner_can_review_a_feishu_authored_draft(native):
    db, review, key, public, expected = native
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET source='feishu',user_id='ou_local_owner' WHERE id='writer'")
    proof = attest_native_review(db, review, key)
    assert verify_review_proof(proof, public, **expected) == []


def test_local_owner_bridge_does_not_accept_untrusted_writer_surface(native):
    db, review, key, _, _ = native
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET source='cloud',user_id='other' WHERE id='writer'")
    with pytest.raises(ValueError, match="owner/profile"):
        attest_native_review(db, review, key)


def test_request_and_final_must_bind_same_nonce(native):
    db, review, key, _, _ = native
    with sqlite3.connect(db) as conn:
        value = json.loads(conn.execute("SELECT content FROM messages WHERE id=2").fetchone()[0])
        value["publication_review_result"]["attempt_id"] = "unrelated-nonce"
        conn.execute("UPDATE messages SET content=? WHERE id=2", (json.dumps(value),))
    with pytest.raises(ValueError, match="target mismatch"):
        attest_native_review(db, review, key)


@pytest.mark.parametrize("start,end", [(10, float("nan")), (10, float("inf")), (True, 20),
                                        (10, True), (20, 10), (10, 1000), (-1, 20), (10, 10 ** 500)])
def test_native_review_timestamp_rejects_invalid_or_future_terminal(start, end):
    with pytest.raises(ValueError, match="terminal time"):
        native_reviewed_at({"native_started_at": start, "native_ended_at": end}, now=100)


def test_native_review_timestamp_uses_utc_and_original_future_tolerance(native):
    assert native_reviewed_at({"native_started_at": 10, "native_ended_at": 20}, now=20) == "1970-01-01T00:00:20+00:00"
    assert native_reviewed_at({"native_started_at": 10, "native_ended_at": 320}, now=20)
    db, review, private, public, expected = native
    proof = attest_native_review(db, review, private)
    proof["native_ended_at"] = 321
    key = serialization.load_pem_private_key(private, password=None)
    payload = {k: v for k, v in proof.items() if k != "signature"}
    proof["signature"] = base64.b64encode(key.sign(json.dumps(payload, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode())).decode()
    assert "provenance.native_terminal" in verify_review_proof(proof, public, now=20, **expected)
    proof["native_ended_at"] = 20
    assert "provenance.signature" in verify_review_proof(proof, public, now=20, **expected)
