"""Signed, short-lived authorization for a single personal-knowledge action."""

from __future__ import annotations

import base64
import difflib
import re
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any


KNOWLEDGE_ACTION_TTL_SECONDS = int(
    os.environ.get("KNOWLEDGE_ACTION_CAPABILITY_TTL_SECONDS", "600")
)
KNOWLEDGE_ACTION_SECRET = os.environ.get(
    "KNOWLEDGE_ACTION_CAPABILITY_SECRET",
    os.environ.get("KNOWLEDGE_CAPABILITY_SECRET", "dev-knowledge-action-secret"),
)


class KnowledgeActionDenied(ValueError):
    code = "knowledge_action_denied"


def note_capability_step(capability_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """Project the existing PCM note contract onto the local-first executor."""
    kind = {
        "knowledge.note.create": "create_note", "knowledge.note.update": "update_note",
        "knowledge.note.merge": "merge_notes", "knowledge.note.archive": "archive_note",
        "knowledge.note.restore": "restore_note",
    }.get(capability_id)
    if kind is None:
        return None
    return {
        "kind": kind,
        "target_note_id": data.get("note_id") or data.get("target_note_id"),
        "source_note_ids": list((data.get("source_versions") or {}).keys()),
        "markdown": data.get("markdown") or data.get("revised_content"),
        "original_content_hash": data.get("base_hash") or data.get("target_base_hash"),
        "source_content_hashes": data.get("source_versions") or {},
    }


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def action_digest(event: dict[str, Any]) -> str:
    """Digest only immutable proposal fields; transport/state fields are excluded."""
    immutable = {
        key: value
        for key, value in event.items()
        if key
        not in {
            "knowledge_action_capability",
            "expires_at",
            "confirmation_status",
            "state",
        }
    }
    return canonical_digest(immutable)


def mint_knowledge_action_capability(
    *,
    tenant_key: str,
    user_id: str,
    session_id: str,
    request_id: str,
    policy_version: str,
    action_id: str,
    action_hash: str,
    target_hashes: dict[str, str | None],
    vault_revision: str,
    ttl_seconds: int | None = None,
) -> tuple[str, int]:
    now = int(time.time())
    expiry = now + (ttl_seconds or KNOWLEDGE_ACTION_TTL_SECONDS)
    payload = {
        "v": 1,
        "aud": "knowledge-action",
        "tenant_key": tenant_key,
        "user_id": user_id,
        "session_id": session_id,
        "request_id": request_id,
        "policy_version": policy_version,
        "action_id": action_id,
        "action_hash": action_hash,
        "target_hashes": target_hashes,
        "vault_revision": vault_revision,
        "nonce": secrets.token_urlsafe(18),
        "iat": now,
        "exp": expiry,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = hmac.new(KNOWLEDGE_ACTION_SECRET.encode(), encoded, hashlib.sha256).digest()
    token = (
        f"{encoded.decode()}."
        f"{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"
    )
    return token, expiry


def verify_knowledge_action_capability(token: str) -> dict[str, Any]:
    try:
        encoded_text, signature_text = token.split(".", 1)
        encoded = encoded_text.encode()
        expected = hmac.new(
            KNOWLEDGE_ACTION_SECRET.encode(), encoded, hashlib.sha256
        ).digest()
        signature = base64.urlsafe_b64decode(
            signature_text + "=" * (-len(signature_text) % 4)
        )
        if not hmac.compare_digest(expected, signature):
            raise ValueError("signature mismatch")
        raw = base64.urlsafe_b64decode(encoded_text + "=" * (-len(encoded_text) % 4))
        payload = json.loads(raw)
        if payload.get("aud") != "knowledge-action":
            raise ValueError("audience mismatch")
        if int(payload.get("exp") or 0) <= int(time.time()):
            raise ValueError("capability expired")
        return payload
    except Exception as exc:
        raise KnowledgeActionDenied("knowledge action capability denied") from exc


def note_action_diff(steps: list[dict[str, Any]], notes: list[dict[str, Any]]) -> str:
    snapshots = {str(note.get("id")): note for note in notes if isinstance(note, dict)}
    changes = []
    for step in steps:
        if step.get("kind") not in {"create_note", "update_note", "merge_notes"} or not isinstance(step.get("markdown"), str):
            continue
        target = str(step.get("target_note_id") or "new")
        note = snapshots.get(target)
        if step.get("kind") != "create_note" and (not note or hashlib.sha256(str(note.get("markdown", "")).encode()).hexdigest() != step.get("original_content_hash")):
            # A partial/missing snapshot cannot substantiate a content diff.
            continue
        changes.append("".join(difflib.unified_diff(
            str((note or {}).get("markdown", "")).splitlines(keepends=True),
            step["markdown"].splitlines(keepends=True), fromfile=f"{target}:before", tofile=f"{target}:after",
        )))
    return "\n".join(changes)[:20_000]


def note_merge_preview(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Exact paragraph comparison; changed wording always needs a human choice."""
    if target["id"] == source["id"] or any(note.get("archived") for note in (target, source)):
        raise KnowledgeActionDenied("comparison requires two distinct active notes")
    for note in (target, source):
        if len(note["markdown"]) > 120_000 or hashlib.sha256(note["markdown"].encode()).hexdigest() != note["content_hash"]:
            raise KnowledgeActionDenied("comparison snapshot invalid or incomplete")
    def blocks(text: str) -> list[str]:
        from markdown_it import MarkdownIt

        lines = text.splitlines(keepends=True)
        # Keep top-level Markdown blocks intact, including fenced code and lists.
        starts = sorted({0, len(lines)} | {
            token.map[0] for token in MarkdownIt("commonmark").parse(text)
            if token.level == 0 and token.map
        })
        return ["".join(lines[a:b]) for a, b in zip(starts, starts[1:])]

    from backend.services.user_note_context import _frontmatter_value

    def body(note: dict[str, Any]) -> str:
        text = note["markdown"]
        header = re.match(r"\A---\r?\n.*?\r?\n---(?:\r?\n|$)", text, re.S)
        # Only remove our identified note metadata, never an arbitrary Markdown divider.
        if header and _frontmatter_value(text, "id") == note["id"]:
            return text[header.end():].lstrip("\r\n")
        return text

    target_body, source_body = body(target), body(source)
    before, after = blocks(target_body), blocks(source_body)
    # ponytail: bound quadratic matching; very fragmented documents use one explicit choice.
    coarse = max(len(before), len(after)) > 256
    if coarse:
        before, after = [target_body], [source_body]
    segments = []
    for kind, a, b, c, d in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        left, right = "".join(before[a:b]), "".join(after[c:d])
        left_runs, right_runs = [], []
        if kind == "replace" and max(len(left), len(right)) <= 2000:
            for tag, i, j, k, m in difflib.SequenceMatcher(None, left, right).get_opcodes():
                if i != j:
                    left_runs.append({"text": left[i:j], "changed": tag != "equal"})
                if k != m:
                    right_runs.append({"text": right[k:m], "changed": tag != "equal"})
        else:
            left_runs = [{"text": left, "changed": kind != "equal"}] if left else []
            right_runs = [{"text": right, "changed": kind != "equal"}] if right else []
        segments.append({"id": str(len(segments)), "kind": kind, "before": left, "after": right,
                         "before_runs": left_runs, "after_runs": right_runs,
                         "target_blocks": b - a, "source_blocks": d - c})
    return {"target_note_id": target["id"], "source_note_id": source["id"],
            "target_hash": target["content_hash"], "source_hash": source["content_hash"],
            "coarse": coarse, "segments": segments}
