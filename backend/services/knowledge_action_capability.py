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
    illustration_action = capability_id.removeprefix("knowledge.note.illustration.") if capability_id.startswith("knowledge.note.illustration.") else None
    if illustration_action in {"generate", "cancel", "apply", "undo", "configure"}:
        kind = "illustrate_note"
    if kind is None:
        return None
    presentation = {key: data[key] for key in ("title", "tags", "layout", "automatic_illustrations") if key in data}
    if kind == "illustrate_note":
        presentation.update(illustration_action=illustration_action,
                            illustration_anchor=data.get("anchor", ""), illustration_brief=data.get("brief", ""))
        if "insert" in data or not data.get("retry_run_id"):
            presentation["illustration_insert"] = data.get("insert", False)
        if data.get("retry_run_id"):
            presentation["illustration_action"] = "retry"
        if data.get("run_id") or data.get("retry_run_id"):
            presentation["illustration_run_id"] = data.get("run_id") or data["retry_run_id"]
        if "enabled" in data:
            presentation["automatic_illustrations"] = data["enabled"]
    return {
        **presentation,
        "kind": kind,
        "target_note_id": data.get("note_id") or data.get("target_note_id"),
        "source_note_ids": list((data.get("source_versions") or {}).keys()),
        "markdown": data.get("markdown") or data.get("revised_content"),
        "original_content_hash": data.get("base_hash") or data.get("target_base_hash"),
        "source_content_hashes": data.get("source_versions") or {},
    }




def note_action_summary(step: dict[str, Any]) -> str:
    action = step.get("illustration_action")
    if action == "configure":
        return "开启本篇自动配图" if step.get("automatic_illustrations") else "关闭本篇自动配图"
    if action == "retry" and "illustration_insert" not in step:
        return "重试原配图任务，保留原插入方式"
    if action in {"generate", "retry"}:
        return ("重试" if action == "retry" else "生成") + ("插图并插入笔记" if step.get("illustration_insert") else "插图供预览")
    if action:
        return {"cancel": "停止本篇配图", "apply": "将候选插图插入笔记", "undo": "撤销本批配图"}[action]
    if step.get("layout") == "travel":
        return "保存旅行笔记"
    return {"merge_notes": "合并笔记", "archive_note": "归档笔记", "restore_note": "恢复笔记"}.get(step.get("kind"), "保存笔记")


def note_presentation_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate the additive note UI fields before signing any proposal."""
    from backend.services.capability_catalog import validate_instance, CapabilityContractError
    schema = {"type": "object", "properties": {
        "layout": {"type": "string", "enum": ["standard", "travel"]},
        "automatic_illustrations": {"type": "boolean"},
        "illustration_action": {"type": "string", "enum": ["generate", "retry", "cancel", "apply", "undo", "configure"]},
        "illustration_anchor": {"type": "string", "maxLength": 16000},
        "illustration_brief": {"type": "string", "maxLength": 2000},
        "illustration_run_id": {"type": "string", "pattern": r"^[a-f0-9]{32}$"},
        "illustration_insert": {"type": "boolean"},
    }, "additionalProperties": False}
    value = {key: raw[key] for key in schema["properties"] if key in raw and raw[key] is not None}
    validate_instance(value, schema)
    action = value.get("illustration_action")
    if raw.get("kind") == "illustrate_note" and not action:
        raise CapabilityContractError("illustration_action_required")
    if action and raw.get("kind") != "illustrate_note":
        raise CapabilityContractError("illustration_step_required")
    if action and (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", str(raw.get("target_note_id") or ""))
                   or not re.fullmatch(r"[a-f0-9]{64}", str(raw.get("original_content_hash") or ""))):
        raise CapabilityContractError("illustration_target_version_required")
    if action in {"retry", "cancel", "apply", "undo"} and not value.get("illustration_run_id"):
        raise CapabilityContractError("illustration_run_required")
    if action == "configure" and "automatic_illustrations" not in value:
        raise CapabilityContractError("illustration_preference_required")
    if action == "generate" and value.get("illustration_anchor") and not value.get("illustration_brief", "").strip():
        raise CapabilityContractError("illustration_brief_required")
    if value.get("layout") and raw.get("kind") not in {"create_note", "update_note"}:
        raise CapabilityContractError("layout_requires_note_content")
    return value


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
