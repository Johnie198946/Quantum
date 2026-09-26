"""Narrow native-Hermes review attestation. No model calls or session writes.

The local operator and pinned Ed25519 key are trusted. This proves a completed
native session acknowledged this exact review artifact; it does not prove the
semantic quality of the review or resist an administrator changing the DB/key.
Only hashes of native messages leave the local machine, never private transcripts.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from backend.services.publication_editorial import editorial_target_hash

REQUEST_START = "PUBLICATION_REVIEW_REQUEST\n"
REQUEST_END = "\nEND_PUBLICATION_REVIEW_REQUEST"
IDENTITY_FIELDS = ("issue_id", "revision", "attempt_id", "editorial_target_hash")
STORY_REVIEW_POLICY = "story-supervision-v2"


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _assets(value: list[dict]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("invalid publication assets")
    normalized = []
    identities = set()
    for item in value:
        if not isinstance(item, dict) or len(item) != 2 or "sha256" not in item:
            raise ValueError("invalid publication assets")
        identity = "role" if "role" in item else "url" if "url" in item else None
        locator, digest = item.get(identity) if identity else None, item.get("sha256")
        if (identity is None or set(item) != {identity, "sha256"}
                or not isinstance(locator, str) or not locator
                or not isinstance(digest, str) or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                or (identity, locator) in identities):
            raise ValueError("invalid publication assets")
        identities.add((identity, locator))
        normalized.append({identity: locator, "sha256": digest})
    return sorted(normalized, key=lambda item: _canonical(item))


def publication_material_hash(target_hash: str, assets: list[dict]) -> str:
    if (not isinstance(target_hash, str) or len(target_hash) != 64
            or any(character not in "0123456789abcdef" for character in target_hash)):
        raise ValueError("invalid publication material hashes")
    return _sha(_canonical({"editorial_target_hash": target_hash,
                            "assets": _assets(assets)}))


def _request(content: str) -> dict:
    lines = content.splitlines()
    starts = [i for i, line in enumerate(lines) if line == REQUEST_START.strip()]
    ends = [i for i, line in enumerate(lines) if line == REQUEST_END.strip()]
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        raise ValueError("native review must have one explicit review request")
    raw = "\n".join(lines[starts[0] + 1:ends[0]])
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("invalid native review request")
    return value


def attest_native_review(db_path: Path, review_path: Path, private_key_pem: bytes, *,
                         profile: str = "default", user_id: str | None = None,
                         writer_profile: str | None = None,
                         writer_db_path: Path | None = None) -> dict:
    """Read only the review's exact session. Reject unrelated/unfinished outputs."""
    cross_profile = writer_profile is not None or writer_db_path is not None
    if cross_profile and (profile, writer_profile) != ("supervision", "story"):
        raise ValueError("unsupported native review profiles")
    if cross_profile != (writer_db_path is not None):
        raise ValueError("cross-profile writer database required")
    raw_review = review_path.read_bytes()
    review = json.loads(raw_review)
    reviewer = review.get("reviewer_session", "")
    if not isinstance(reviewer, str) or not reviewer.startswith("hermes:"):
        raise ValueError("native reviewer_session required")
    sid = reviewer.removeprefix("hermes:")
    # URI quoting prevents path metacharacters from altering readonly mode.
    uri = db_path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        session = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if session is None or session["profile_name"] != profile or session["user_id"] != user_id:
            raise ValueError("native owner/profile mismatch")
        if session["source"] not in {"desktop", "cli", "cron"}:
            raise ValueError("unsupported native review surface")
        if not session["ended_at"] or session["end_reason"] not in {"agent_close", "cli_close", "cron_complete"}:
            raise ValueError("native review is not completed")
        first = db.execute("SELECT * FROM messages WHERE session_id=? AND role='user' AND active=1 AND compacted=0 ORDER BY id LIMIT 1", (sid,)).fetchone()
        final = db.execute("SELECT * FROM messages WHERE session_id=? AND active=1 AND compacted=0 ORDER BY id DESC LIMIT 1", (sid,)).fetchone()
        if first is None or final is None or final["role"] != "assistant" or final["finish_reason"] != "stop" or final["tool_calls"]:
            raise ValueError("native review has no successful final output")
        request = _request(first["content"] or "")
        try:
            result = json.loads(final["content"] or "")["publication_review_result"]
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("native final must contain exact publication_review_result JSON") from exc
        if not isinstance(result, dict):
            raise ValueError("invalid native final review receipt")
        for field in IDENTITY_FIELDS:
            if result.get(field) != request.get(field) or request.get(field) is None:
                raise ValueError("native request/final target mismatch")
        if (request.get("purpose") != "publication_editorial_review"
                or request.get("owner") != "local_owner"):
            raise ValueError("native review scope mismatch")
        if cross_profile:
            if set(request) & {"state_db", "state_db_path", "writer_db", "writer_db_path",
                               "reviewer_db", "reviewer_db_path", "owner_user_id"}:
                raise ValueError("native request cannot select authority paths or owner")
            expected_scope = {"review_policy": STORY_REVIEW_POLICY,
                              "writer_profile": "story", "reviewer_profile": "supervision",
                              "writer_role": "story_author", "reviewer_role": "supervision_reviewer"}
            if any(request.get(field) != value for field, value in expected_scope.items()):
                raise ValueError("native review scope mismatch")
        elif request.get("profile") != profile:
            raise ValueError("native review scope mismatch")
        if (result.get("review_file_hash") != _sha(raw_review)
                or result.get("reviewer_session") != reviewer
                or result.get("decision") != review.get("decision")
                or result.get("editorial_target_hash") != review.get("editorial_target_hash")
                or result.get("revision") != review.get("revision")
                or result.get("decision") not in {"approved", "rejected"}):
            raise ValueError("native final does not bind actual review bytes")
        writers = request.get("writer_sessions")
        if not isinstance(writers, list) or not writers or reviewer in writers:
            raise ValueError("native reviewer is not independent")
        manuscript, contract = request.get("manuscript"), request.get("quality_contract")
        chunks = request.get("manuscript_gzip_b64_chunks")
        compressed = request.get("manuscript_gzip_b64")
        if manuscript is None and chunks is not None:
            if (not isinstance(chunks, list) or not chunks
                    or any(not isinstance(chunk, str) or not chunk or len(chunk) > 12 for chunk in chunks)):
                raise ValueError("native request lacks actual review material")
            compressed = "".join(chunks)
        if manuscript is None and isinstance(compressed, str):
            try:
                manuscript = gzip.decompress(base64.b64decode(compressed, validate=True)).decode()
            except (ValueError, OSError, UnicodeDecodeError) as exc:
                raise ValueError("native request lacks actual review material") from exc
        elif manuscript is None and isinstance(request.get("manuscript_b64"), str):
            try:
                manuscript = base64.b64decode(request["manuscript_b64"], validate=True).decode()
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError("native request lacks actual review material") from exc
        if not isinstance(manuscript, str) or not isinstance(contract, dict):
            raise ValueError("native request lacks actual review material")
        if (contract.get("writer_sessions") != writers
                or _sha(manuscript.encode()) != review.get("content_hash")
                or editorial_target_hash(manuscript, contract, request.get("source_receipts")) != request["editorial_target_hash"]):
            raise ValueError("native actual review material mismatch")
        if cross_profile:
            assets = _assets(request.get("assets"))
            material_hash = publication_material_hash(request["editorial_target_hash"], assets)
            if (request.get("publication_material_hash") != material_hash
                    or result.get("publication_material_hash") != material_hash
                    or review.get("publication_material_hash") != material_hash):
                raise ValueError("native actual publication material mismatch")
        author_path = writer_db_path if cross_profile else db_path
        author_uri = Path(author_path).resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(author_uri, uri=True) as author_db:
            author_db.row_factory = sqlite3.Row
            author_db.execute("BEGIN")
            for writer in writers:
                if (not isinstance(writer, str) or not writer.startswith("hermes:")
                        or writer == reviewer):
                    raise ValueError("invalid or non-independent native writer session")
                author = author_db.execute("SELECT profile_name,user_id,source FROM sessions WHERE id=?", (writer[7:],)).fetchone()
                expected_profile = writer_profile if cross_profile else profile
                local_owner_bridge = (not cross_profile and user_id is None and profile == "default"
                                      and author is not None and author["source"] in {"feishu", "lark"})
                if (author is None or author["profile_name"] != expected_profile
                        or (author["user_id"] != user_id and not local_owner_bridge)):
                    raise ValueError("native writer owner/profile mismatch")
        payload = {
            "proof_version": "native-editorial-review-v2" if cross_profile else "native-editorial-review-v1",
            "purpose": "quantumn-production-publication",
            **{field: request[field] for field in IDENTITY_FIELDS},
            "review_file_hash": _sha(raw_review), "reviewer_session": reviewer,
            "writer_sessions": writers, "decision": review["decision"],
            "owner": "local_owner", "profile": profile,
            "native_source": session["source"], "native_end_reason": session["end_reason"],
            "native_finish_reason": "stop", "material_body_hash": _sha(manuscript.encode()),
            "native_started_at": session["started_at"], "native_ended_at": session["ended_at"],
            "native_request_id": first["id"], "native_request_hash": _sha((first["content"] or "").encode()),
            "native_final_id": final["id"], "native_final_hash": _sha((final["content"] or "").encode()),
        }
        if cross_profile:
            payload.update({
                "review_policy": STORY_REVIEW_POLICY,
                "writer_profile": "story", "reviewer_profile": "supervision",
                "writer_role": "story_author", "reviewer_role": "supervision_reviewer",
                "assets": assets,
                "publication_material_hash": material_hash,
            })
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Ed25519 signing key required")
    return {**payload, "signature": base64.b64encode(key.sign(_canonical(payload))).decode()}


def verify_review_proof(proof, public_key_pem: bytes, *, issue_id, revision, attempt_id,
                        target_hash, review_file_hash, reviewer_session, writer_sessions,
                        required_policy=None, assets=None, now=None) -> list[str]:
    """Pinned-key verification at the existing trusted publication ingress."""
    if not isinstance(proof, dict):
        return ["provenance.invalid"]
    try:
        payload = {key: value for key, value in proof.items() if key != "signature"}
        key = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(key, Ed25519PublicKey):
            return ["provenance.key_type"]
        key.verify(base64.b64decode(proof["signature"], validate=True), _canonical(payload))
    except (ValueError, TypeError, KeyError, InvalidSignature):
        return ["provenance.signature"]
    version = "native-editorial-review-v2" if required_policy == STORY_REVIEW_POLICY else "native-editorial-review-v1"
    expected = {
        "proof_version": version, "issue_id": issue_id,
        "purpose": "quantumn-production-publication",
        "revision": revision, "attempt_id": attempt_id, "editorial_target_hash": target_hash,
        "review_file_hash": review_file_hash, "reviewer_session": reviewer_session,
        "writer_sessions": writer_sessions, "owner": "local_owner",
        "profile": "supervision" if version.endswith("v2") else "default",
        "native_finish_reason": "stop",
    }
    if version.endswith("v2"):
        expected.update({"review_policy": STORY_REVIEW_POLICY,
                         "writer_profile": "story", "reviewer_profile": "supervision",
                         "writer_role": "story_author", "reviewer_role": "supervision_reviewer"})
    reasons = [f"provenance.{field}" for field, value in expected.items() if payload.get(field) != value]
    if payload.get("decision") not in {"approved", "rejected"}:
        reasons.append("provenance.decision")
    if reviewer_session in writer_sessions:
        reasons.append("provenance.independence")
    if payload.get("native_source") not in {"desktop", "cli", "cron"}:
        reasons.append("provenance.source")
    if payload.get("native_end_reason") not in {"agent_close", "cli_close", "cron_complete"}:
        reasons.append("provenance.native_terminal")
    start, end = payload.get("native_started_at"), payload.get("native_ended_at")
    if (not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start):
        reasons.append("provenance.native_terminal")
    if version.endswith("v2"):
        try:
            signed_assets = _assets(payload["assets"])
            material_hash = publication_material_hash(target_hash, signed_assets)
            if payload.get("publication_material_hash") != material_hash:
                reasons.append("provenance.publication_material_hash")
            if assets is not None and _assets(assets) != signed_assets:
                reasons.append("provenance.assets")
        except (KeyError, TypeError, ValueError):
            reasons.append("provenance.publication_material_hash")
    return sorted(set(reasons))
