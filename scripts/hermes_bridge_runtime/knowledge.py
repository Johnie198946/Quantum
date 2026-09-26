from __future__ import annotations

import ast
import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
import contextvars
import hashlib
import inspect
import traceback
import ipaddress
import json
import os
import queue
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Literal, Optional

import httpx
from fastapi import Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.services.reasoning_extractor import extract_steps
from backend.services.knowledge_policy import KnowledgeScopeDenied, verify_capability
from backend.services.client_context_capability import (
    ClientContextDenied, QWSBusinessContextDenied, context_digest,
    verify_client_context_capability, verify_qws_business_context_capability,
)
from backend.services.tenant_hermes_sandbox import (
    TenantHermesSandbox, delete_sandbox_skill, ensure_tenant_sandbox,
    list_sandbox_skills, persist_agent_snapshot, read_sandbox_skill,
    write_sandbox_skill,
)
from backend.services.chat_triage import CASUAL, GENERAL_QA, PROFESSIONAL_TASK
from backend.services.agent_capabilities import SAFE_GLOBAL_TOOLS
from backend.services.html_illustration import (
    embed_illustration, illustration_prompt_instruction,
    select_illustration_context, validate_illustration_prompt,
    validate_illustration_svg,
)
from backend.services.html_tool_renderer import secure_html_tool
from backend.services.tenant_coder_tools import (
    patch_text as tenant_coder_patch, read_text as tenant_coder_read,
    run_command as tenant_coder_run, search_text as tenant_coder_search,
    write_text as tenant_coder_write,
)
from scripts.chat_run_store import DurableChatRunStore


class _PropagatedRequestContext:
    def __init__(self, name: str):
        self._value = contextvars.ContextVar(name, default=None)

    @property
    def value(self):
        return self._value.get()

    @value.setter
    def value(self, next_value) -> None:
        self._value.set(next_value)


_knowledge_tool_context = _PropagatedRequestContext("qws_knowledge_tool_context")


_knowledge_tool_registration_lock = threading.Lock()


_knowledge_tool_registered = False


_sandbox_tool_context = _PropagatedRequestContext("qws_sandbox_tool_context")


_skill_route_context = _PropagatedRequestContext("qws_skill_route_context")


_sandbox_tool_registration_lock = threading.Lock()


_sandbox_tool_registered = False


_tenant_coder_tool_registration_lock = threading.Lock()


_tenant_coder_tools_registered = False


_client_context_tool_context = _PropagatedRequestContext("qws_client_context_tool_context")


_client_context_tool_registration_lock = threading.Lock()


_client_context_tools_registered = False


_knowledge_workspace_tool_registration_lock = threading.Lock()


_knowledge_workspace_tools_registered = False


_FULL_KNOWLEDGE_CATEGORY_RE = re.compile(
    r"^knowledge/(?:[A-Za-z0-9][A-Za-z0-9._-]*/)+"
    r"(?:public|entitlement/[A-Za-z0-9][A-Za-z0-9._-]*)$"
)


_REVISION_REQUEST_RE = re.compile(
    r"(?:不满意|不对|不行|重写|改写|重新写|换一版|换个版本|再来一版|再写|再改|"
    r"上一版|这一版|这版|语气再|风格再|调整|修改|补充|不要.{0,12}(?:一样|重复))",
    re.IGNORECASE,
)


def _requires_browser_fallback(goal: str) -> bool:
    """Keep browser access fail-closed to known extractor-hostile public URLs."""
    return bool(re.search(r"https?://mp\.weixin\.qq\.com/", str(goal or ""), re.I))


def _is_revision_request(goal: str) -> bool:
    return bool(_REVISION_REQUEST_RE.search(str(goal or "")))


def _fallback_note_title(markdown: str) -> str:
    for line in str(markdown or "").splitlines():
        title = re.sub(r"^#{1,6}\s*", "", line.strip()).strip()
        if title:
            return title[:200]
    return "会话笔记"


def _explicit_knowledge_category_scope(args: dict[str, Any]) -> list[str] | None:
    """Return only complete governed category paths selected by Hermes.

    Model shorthand such as ``green`` or a company/category name is not an
    authorization scope.  Ignoring it lets the signed capability supply every
    category that the current tenant may actually read.
    """
    raw_scope = args.get("category_scope")
    if not isinstance(raw_scope, list) or not raw_scope:
        return None
    normalized = [str(item).strip() for item in raw_scope]
    if any(
        not item or not _FULL_KNOWLEDGE_CATEGORY_RE.fullmatch(item)
        for item in normalized
    ):
        return None
    return list(dict.fromkeys(normalized))


def _knowledge_fallback_payload(error: str, *, query: str) -> dict[str, Any]:
    """Tell Hermes how to continue without performing AI routing in Bridge."""
    return {
        "success": False,
        "error": error,
        "retrieval_status": "error",
        "query": query,
        "fallback_recommended": True,
        "fallback_source": "public_web",
        "fallback_instruction": (
            "If web_search is authorized, search the public web with this query, "
            "cite URLs, and label the result as public information rather than "
            "tenant _knowledge. Never infer or reconstruct restricted _knowledge."
        ),
    }


def _knowledge_search_tool(args: dict[str, Any], **_kwargs) -> str:
    """Hermes-facing knowledge_search handler backed by the platform Gateway."""
    query = str((args or {}).get("query") or "").strip()
    wiki_request = {key: args[key] for key in ("entities", "topics", "paths") if key in (args or {})}
    book_request = {key: args[key] for key in ("book_id", "content_version", "operation", "section", "page")
                    if key in (args or {})}
    if not query:
        return json.dumps(
            {"success": False, "error": "query_required"}, ensure_ascii=False
        )
    context = getattr(_knowledge_tool_context, "value", None)
    if not isinstance(context, dict) or not context.get("capability"):
        return json.dumps(
            ({"success": False, "error": "knowledge_scope_unavailable", "fallback_recommended": False}
             if book_request else _knowledge_fallback_payload("knowledge_scope_unavailable", query=query)),
            ensure_ascii=False,
        )
    explicit_scope = _explicit_knowledge_category_scope(args or {})
    requested_scope = set(explicit_scope or [])
    gateway_options: dict[str, Any] = {}
    if "gateway_timeout" in _kwargs:
        gateway_options["timeout_seconds"] = float(_kwargs["gateway_timeout"])
    try:
        docs = _persistence._knowledge_gateway_search(
            str(context["capability"]),
            query=query,
            category_scope=(
                sorted(requested_scope) if explicit_scope is not None else None
            ),
            sources=["tenant_knowledge"],
            limit=max(1, min(10, int((args or {}).get("limit") or 5))),
            # New intent-search is lightweight; explicit follow-up paths read bodies.
            # Preserve legacy query-only and selected-book response behavior.
            include_content=bool(book_request or not wiki_request or wiki_request.get("paths")),
            **({"book_request": book_request} if book_request else {}),
            **({"wiki_request": wiki_request} if wiki_request else {}),
            with_status=True,
            **gateway_options,
        )
    except PermissionError:
        if book_request:
            return json.dumps({"success": False, "error": "book_scope_denied", "fallback_recommended": False})
        return json.dumps(
            _knowledge_fallback_payload("knowledge_scope_denied", query=query),
            ensure_ascii=False,
        )
    except (httpx.TimeoutException, TimeoutError):
        if book_request:
            return json.dumps({"success": False, "error": "book_gateway_timeout", "fallback_recommended": False})
        return json.dumps(
            _knowledge_fallback_payload("knowledge_gateway_timeout", query=query),
            ensure_ascii=False,
        )
    except Exception as exc:
        if book_request:
            error = "book_gateway_unavailable"
            if isinstance(exc, httpx.HTTPStatusError):
                try:
                    error = exc.response.json().get("detail", error)
                except ValueError:
                    pass
            return json.dumps({"success": False, "error": error, "fallback_recommended": False}, ensure_ascii=False)
        payload = _knowledge_fallback_payload(
            "knowledge_gateway_unavailable", query=query
        )
        payload["detail"] = str(exc)[:160]
        return json.dumps(payload, ensure_ascii=False)
    if book_request:
        return json.dumps(docs, ensure_ascii=False)
    gateway_status = docs.get("retrieval_status") if isinstance(docs, dict) else None
    if isinstance(docs, dict):
        docs = docs.get("docs", [])
    if gateway_status in {"denied", "error"}:
        return json.dumps({
            "success": False,
            "error": f"knowledge_gateway_{gateway_status}",
            "retrieval_status": gateway_status,
            "query": query,
            "fallback_recommended": False,
            "docs": [],
        }, ensure_ascii=False)
    # An exact acronym absent from every result is a deterministic coverage gap,
    # not semantic proof that an entity-only hit answers the question.
    required_acronyms = re.findall(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9-]{1,23}(?![A-Za-z0-9])", query)
    evidence_text = "\n".join(str(item.get(key) or "") for item in docs
                              for key in ("title", "snippet", "markdown", "path"))
    acronym_gap = any(not re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", evidence_text, re.I)
                      for term in required_acronyms)
    insufficient = gateway_status == "insufficient" or bool(docs) and (acronym_gap or not any(
        item.get("match_basis") in {"entry", "selected_path"}
        and item.get("content_status") not in {"truncated", "unavailable", "revoked", "budget_exhausted"}
        for item in docs))
    return json.dumps(
        {
            "success": True,
            "query": query,
            "retrieval_status": "insufficient" if insufficient else "no_match" if not docs else "matched",
            "evidence_sufficiency": "not_assessed",
            "fallback_recommended": not docs or insufficient,
            "fallback_source": "public_web" if not docs or insufficient else None,
            "fallback_instruction": (
                "Authorized Wiki evidence is missing or insufficient. Refine entities/topics, "
                "read task-relevant Wiki links via paths; if web_search is authorized, "
                "search public sources and label URLs separately. Do not reconstruct restricted details."
                if not docs or insufficient else None
            ),
            "docs": [
                {
                    "path": item.get("path", ""),
                    "title": item.get("title", ""),
                    "snippet": str(item.get("snippet") or "")[:500],
                    "markdown": str(item.get("markdown") or "")[:20_000],
                    "content_status": item.get("content_status", "not_requested"),
                    "category": item.get("category", ""),
                    "freshness": item.get("freshness", "unknown"),
                    "knowledge_id": item.get("knowledge_id", ""),
                    "version": item.get("version", ""),
                    "citation": item.get("citation", ""),
                    "source_kind": item.get("source_kind", "governed_wiki"),
                    "match_basis": item.get("match_basis", "unknown"),
                    "wikilinks": item.get("wikilinks") or [],
                    "confidence": item.get("confidence", "unknown"),
                    "quality_status": item.get("quality_status", "unrated"),
                    "disclosure_granularity": item.get("disclosure_granularity", "detail"),
                    "conditions": item.get("conditions") or [],
                    "effective_at": item.get("effective_at"),
                }
                for item in docs
            ],
        },
        ensure_ascii=False,
    )


def _inline_user_note_matches(
    query: str,
    notes: list[dict[str, Any]],
    limit: int,
    *,
    active_document_note_id: str | None = None,
) -> list[dict[str, Any]]:
    """Find same-account notes supplied in the signed iOS context.

    This is a deterministic recall fallback for local-first notes that have
    not reached the Gateway yet. Hermes still decides the semantic query and
    whether the returned notes are genuinely mergeable. An authenticated
    active-document id deterministically selects the current upload before
    lexical ranking, so referential questions do not lose their attachment.
    """
    if active_document_note_id:
        for raw in notes:
            if not isinstance(raw, dict):
                continue
            note_id = str(raw.get("id") or "").strip()[:128]
            if note_id != active_document_note_id:
                continue
            markdown = str(raw.get("markdown") or "")[:20_000]
            return [{
                "id": note_id,
                "title": str(raw.get("title") or "无标题").strip()[:200],
                "snippet": markdown[:1_000],
                "markdown": markdown,
                "updated_at": raw.get("updated_at"),
                "content_hash": raw.get("content_hash"),
                "category": "user_notes",
                "source": "user_notes",
            }]
    stop = {"笔记", "总结", "整理", "保存", "入库", "相关", "内容", "一下", "会话"}
    terms = [term for term in re.findall(r"[a-z0-9][a-z0-9_.-]{1,}|[\u4e00-\u9fff]{2,}", query.casefold()) if term not in stop]
    if not terms:
        return []
    ranked: list[tuple[int, dict[str, Any]]] = []
    for raw in notes:
        if not isinstance(raw, dict):
            continue
        note_id = str(raw.get("id") or "").strip()[:128]
        title = str(raw.get("title") or "无标题").strip()[:200]
        markdown = str(raw.get("markdown") or "")[:20_000]
        haystack = f"{title}\n{markdown}".casefold()
        score = sum((haystack.count(term) * (8 if term in title.casefold() else 2)) for term in terms)
        if score <= 0 or not note_id:
            continue
        ranked.append((score, {
            "id": note_id,
            "title": title,
            "snippet": markdown[:1_000],
            "markdown": markdown,
            "updated_at": raw.get("updated_at"),
            "content_hash": raw.get("content_hash"),
            "category": "user_notes",
            "source": "user_notes",
        }))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:limit]]


def _user_note_search_tool(args: dict[str, Any], **_kwargs) -> str:
    """Search only the authenticated user's synced notes through the Gateway."""
    context = getattr(_knowledge_tool_context, "value", None)
    if not isinstance(context, dict) or not context.get("capability"):
        return json.dumps(
            {"success": False, "error": "knowledge_scope_unavailable"},
            ensure_ascii=False,
        )
    if "user_notes" not in set(context.get("sources") or []):
        return json.dumps(
            {"success": False, "error": "knowledge_source_denied"},
            ensure_ascii=False,
        )
    query = str((args or {}).get("query") or "").strip()
    if not query:
        return json.dumps({"success": False, "error": "query_required"})
    client_context = getattr(_client_context_tool_context, "value", None)
    inline_notes = []
    if isinstance(client_context, dict):
        inline_notes = client_context.get("inline_notes") or []
    active_document_note_id = (
        str(client_context.get("active_document_note_id") or "").strip()[:128]
        if isinstance(client_context, dict)
        else ""
    )
    inline_docs = _inline_user_note_matches(
        query,
        inline_notes,
        max(1, min(10, int((args or {}).get("limit") or 5))),
        active_document_note_id=active_document_note_id or None,
    )
    try:
        docs = _persistence._knowledge_gateway_search(
            str(context["capability"]),
            query=query,
            category_scope=[],
            sources=["user_notes"],
            limit=max(1, min(10, int((args or {}).get("limit") or 5))),
            **({
                "include_content": True,
                "note_ids": [active_document_note_id],
            } if active_document_note_id else {}),
        )
    except PermissionError:
        return json.dumps(
            {"success": False, "error": "knowledge_source_denied"},
            ensure_ascii=False,
        )
    except Exception as exc:
        if not inline_docs:
            return json.dumps(
                {
                    "success": False,
                    "error": "knowledge_gateway_unavailable",
                    "detail": str(exc)[:160],
                },
                ensure_ascii=False,
            )
        docs = []
    merged_docs = []
    seen_ids: set[str] = set()
    # The authenticated Gateway owns the complete durable source. Inline data
    # is a bounded offline fallback and must never shadow a fuller same-id row.
    for item in (docs if isinstance(docs, list) else []) + inline_docs:
        note_id = str(item.get("id") or "")
        if note_id and note_id not in seen_ids:
            seen_ids.add(note_id)
            merged_docs.append(item)
    docs = merged_docs[: max(1, min(10, int((args or {}).get("limit") or 5)))]
    if isinstance(client_context, dict):
        validated_docs: dict[str, dict[str, Any]] = {}
        for item in docs:
            if not isinstance(item, dict):
                continue
            note_id = str(item.get("id") or "").strip()[:128]
            if not note_id:
                continue
            validated_docs[note_id] = {
                "id": note_id,
                "title": str(item.get("title") or "无标题")[:200],
                "snippet": str(item.get("snippet") or item.get("markdown") or "")[:500],
                "updated_at": item.get("updated_at"),
                "content_hash": item.get("content_hash"),
            }
        client_context["user_note_search_results"] = validated_docs
        client_context["user_note_search_completed"] = True
    return json.dumps(
        {"success": True, "query": query, "docs": docs}, ensure_ascii=False
    )


def _tenant_skill_read_tool(args: dict[str, Any], **_kwargs) -> str:
    sandbox = getattr(_sandbox_tool_context, "value", None)
    if not isinstance(sandbox, TenantHermesSandbox):
        return json.dumps({"success": False, "error": "sandbox_unavailable"})
    name = str((args or {}).get("name") or "").strip()
    route = getattr(_skill_route_context, "value", None)
    if isinstance(route, dict) and route.get("enforced"):
        allowed = {str(item) for item in route.get("allowed") or []}
        if name not in allowed:
            return json.dumps({
                "success": False,
                "error": "skill_not_shortlisted",
                "allowed_candidates": sorted(allowed),
            }, ensure_ascii=False)
    content = read_sandbox_skill(sandbox, name)
    if not content:
        return json.dumps({"success": False, "error": "skill_not_found"})
    if isinstance(route, dict):
        route["decision"] = {
            "status": "selected",
            "requested_skill": name,
            "loaded_skill": name,
        }
    return json.dumps(
        {"success": True, "name": name, "instructions": content},
        ensure_ascii=False,
    )


def _tenant_skill_manage_tool(args: dict[str, Any], **_kwargs) -> str:
    try:
        from backend.services.capability_projection import (
            get_runtime_capability_selection,
        )

        selection = get_runtime_capability_selection()
    except (ImportError, RuntimeError):
        selection = {}
    if not (
        selection.get("validated") is True
        and selection.get("skill_id") == "skill-authoring"
    ):
        return json.dumps({
            "success": False,
            "error": "skill_authoring_not_selected",
        })
    sandbox = getattr(_sandbox_tool_context, "value", None)
    if not isinstance(sandbox, TenantHermesSandbox):
        return json.dumps({"success": False, "error": "sandbox_unavailable"})
    action = str((args or {}).get("action") or "create").strip().lower()
    name = str((args or {}).get("name") or "").strip()
    try:
        if action == "delete":
            prior = read_sandbox_skill(sandbox, name)
            digest = (
                hashlib.sha256(prior.encode("utf-8")).hexdigest()
                if prior is not None
                else None
            )
            prepared = {
                "success": False,
                "phase": "prepared",
                "action": action,
                "name": name,
                "scope": "tenant_private",
                "decision_id": selection.get("decision_id"),
                "catalog_version": selection.get("catalog_version"),
                "policy_version": selection.get("policy_version"),
                "sha256": digest,
            }
            _append_tenant_skill_audit(sandbox, prepared)
            changed = delete_sandbox_skill(sandbox, name)
            receipt = {
                **prepared,
                "success": changed,
                "phase": "committed" if changed else "no_change",
            }
            try:
                _append_tenant_skill_audit(sandbox, receipt)
            except OSError:
                if changed and prior is not None:
                    write_sandbox_skill(sandbox, name, prior, replace=False)
                raise
            return json.dumps(receipt, ensure_ascii=False)
        if action not in {"create", "update"}:
            return json.dumps({"success": False, "error": "unsupported_action"})
        content = str((args or {}).get("content") or "")
        prior = read_sandbox_skill(sandbox, name)
        prepared = {
            "success": False,
            "phase": "prepared",
            "action": action,
            "name": name,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "scope": "tenant_private",
            "decision_id": selection.get("decision_id"),
            "catalog_version": selection.get("catalog_version"),
            "policy_version": selection.get("policy_version"),
        }
        _append_tenant_skill_audit(sandbox, prepared)
        path = write_sandbox_skill(
            sandbox,
            name,
            content,
            replace=action == "update",
        )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt = {
            **prepared,
            "success": True,
            "phase": "committed",
            "sha256": digest,
        }
        try:
            _append_tenant_skill_audit(sandbox, receipt)
        except OSError:
            if prior is None:
                delete_sandbox_skill(sandbox, name)
            else:
                write_sandbox_skill(sandbox, name, prior, replace=True)
            raise
        return json.dumps(receipt, ensure_ascii=False)
    except (ValueError, FileExistsError, OSError) as error:
        return json.dumps(
            {"success": False, "error": str(error)[:300]}, ensure_ascii=False
        )


def _append_tenant_skill_audit(
    sandbox: TenantHermesSandbox,
    receipt: dict[str, Any],
) -> None:
    """Append a content-free audit receipt inside the isolated profile."""
    audit_dir = sandbox.hermes_home / "audit"
    audit_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    record = {
        "event": "tenant_skill_manage",
        "tenant_namespace": sandbox.tenant_namespace,
        "user_namespace": sandbox.user_namespace,
        **receipt,
    }
    target = audit_dir / "tenant-skill-actions.jsonl"
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _ensure_knowledge_gateway_tool_registered() -> None:
    """Register the platform-owned tool once in Hermes' process-global registry."""
    global _knowledge_tool_registered
    if _knowledge_tool_registered:
        return
    with _knowledge_tool_registration_lock:
        if _knowledge_tool_registered:
            return
        from tools.registry import registry

        registry.register(
            name="knowledge_search",
            toolset="knowledge_gateway",
            schema={
                "name": "knowledge_search",
                "description": (
                    "Search tenant-authorized AI Lab knowledge through the platform "
                    "Knowledge Gateway. For a selected book, pass book_id and content_version "
                    "from chat context; operation=toc lists sections, operation=read reads complete "
                    "text in bounded character pages (not printed page numbers). Follow next until "
                    "truncated=false. Section accepts an exact id or title, including Chinese numerals. "
                    "Omit section to read the entire book sequentially. Never substitute web evidence for selected-book text."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Original knowledge need. First identify entities and required topics; do not conflate a company with its process.",
                        },
                        "entities": {"type": "array", "items": {"type": "string"}, "maxItems": 8,
                                     "description": "Entity/title/alias entry hints, e.g. Huawei or 超聚变. Not permission scopes."},
                        "topics": {"type": "array", "items": {"type": "string"}, "maxItems": 8,
                                   "description": "Required literal topics, all must occur in live title/aliases/body, e.g. IPD. Not synonyms inferred by the server."},
                        "paths": {"type": "array", "items": {"type": "string"}, "maxItems": 10,
                                  "description": "Exact authorized Wiki paths for task-relevant follow-up reads (wiki/<link>.md). Links and Matrix are locators, not evidence; do not expand all links."},
                        "book_id": {"type": "string", "description": "Selected book id from authorized chat context."},
                        "content_version": {"type": "string", "description": "Exact selected edition version from chat context."},
                        "operation": {"type": "string", "enum": ["toc", "read"], "default": "read"},
                        "section": {"type": "string", "description": "Exact section id or full title; omit for entire book."},
                        "page": {"type": "integer", "minimum": 1, "default": 1},
                        "category_scope": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Omit by default so the signed capability supplies all authorized "
                                "categories. Only pass a complete path such as "
                                "knowledge/product/public or "
                                "knowledge/methodology/entitlement/premium."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
            handler=lambda args, **kwargs: _knowledge_search_tool(args, **kwargs),
        )
        registry.register(
            name="user_note_search",
            toolset="user_notes_gateway",
            schema={
                "name": "user_note_search",
                "description": (
                    "Search only the authenticated current user's synced Markdown notes. "
                    "Never use this for another user or for platform Wiki facts."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {
                            "type": "integer", "minimum": 1, "maximum": 10,
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
            handler=lambda args, **kwargs: _user_note_search_tool(args, **kwargs),
        )
        _knowledge_tool_registered = True


def _ensure_tenant_skill_tool_registered() -> None:
    global _sandbox_tool_registered
    if _sandbox_tool_registered:
        return
    with _sandbox_tool_registration_lock:
        if _sandbox_tool_registered:
            return
        from tools.registry import registry

        registry.register(
            name="tenant_skill_read",
            toolset="tenant_skill_reader",
            schema={
                "name": "tenant_skill_read",
                "description": (
                    "Read one Agent/Skill instruction copy from the authenticated "
                    "tenant Hermes sandbox."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
            handler=lambda args, **kwargs: _tenant_skill_read_tool(args, **kwargs),
        )
        registry.register(
            name="tenant_skill_manage",
            toolset="tenant_skill_authoring",
            schema={
                "name": "tenant_skill_manage",
                "description": (
                    "Create, update, or delete one Skill only inside the authenticated "
                    "tenant/user Hermes sandbox. SKILL.md must include governed routing "
                    "frontmatter, trigger phrases, and negative phrases."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["create", "update", "delete"],
                        },
                        "name": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["action", "name"],
                },
            },
            handler=lambda args, **kwargs: _tenant_skill_manage_tool(args, **kwargs),
        )
        _sandbox_tool_registered = True


def _tenant_coder_dispatch(operation: str, args: dict[str, Any]) -> str:
    sandbox = getattr(_sandbox_tool_context, "value", None)
    if not isinstance(sandbox, TenantHermesSandbox):
        return json.dumps({"success": False, "error": "sandbox_unavailable"})
    try:
        if operation == "read":
            result = tenant_coder_read(sandbox, str(args.get("path") or ""))
        elif operation == "write":
            result = tenant_coder_write(sandbox, str(args.get("path") or ""), str(args.get("content") or ""))
        elif operation == "patch":
            result = tenant_coder_patch(sandbox, str(args.get("path") or ""), str(args.get("old_string") or ""), str(args.get("new_string") or ""))
        elif operation == "search":
            result = tenant_coder_search(sandbox, str(args.get("pattern") or ""), file_glob=str(args.get("file_glob") or "*"))
        elif operation == "terminal":
            result = tenant_coder_run(sandbox, str(args.get("command") or ""), timeout=int(args.get("timeout") or 180))
        else:
            raise ValueError("unsupported_tenant_coder_operation")
        return json.dumps({"success": True, **result}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)[:500]}, ensure_ascii=False)


def _ensure_tenant_coder_tools_registered() -> None:
    global _tenant_coder_tools_registered
    if _tenant_coder_tools_registered:
        return
    with _tenant_coder_tool_registration_lock:
        if _tenant_coder_tools_registered:
            return
        from tools.registry import registry

        registry.register(name="tenant_read_file", toolset="tenant_coder", schema={"name": "tenant_read_file", "description": "Read a UTF-8 text file only from the authenticated tenant coding workspace.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}, handler=lambda args, **_kwargs: _tenant_coder_dispatch("read", args))
        registry.register(name="tenant_write_file", toolset="tenant_coder", schema={"name": "tenant_write_file", "description": "Write a UTF-8 text file only inside the authenticated tenant coding workspace.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}, handler=lambda args, **_kwargs: _tenant_coder_dispatch("write", args))
        registry.register(name="tenant_patch_file", toolset="tenant_coder", schema={"name": "tenant_patch_file", "description": "Replace one unique text occurrence in a tenant workspace file.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}}, "required": ["path", "old_string", "new_string"]}}, handler=lambda args, **_kwargs: _tenant_coder_dispatch("patch", args))
        registry.register(name="tenant_search_files", toolset="tenant_coder", schema={"name": "tenant_search_files", "description": "Regex-search text files only inside the tenant coding workspace.", "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "file_glob": {"type": "string"}}, "required": ["pattern"]}}, handler=lambda args, **_kwargs: _tenant_coder_dispatch("search", args))
        registry.register(name="tenant_terminal", toolset="tenant_coder", schema={"name": "tenant_terminal", "description": "Run a shell command in a disposable networkless container with only the current tenant workspace mounted. Host, shared platform, deployment and other tenant paths are absent.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer", "minimum": 1, "maximum": 300}}, "required": ["command"]}}, handler=lambda args, **_kwargs: _tenant_coder_dispatch("terminal", args))
        _tenant_coder_tools_registered = True


def _session_context_read_tool(args: dict[str, Any], **_kwargs) -> str:
    context = getattr(_client_context_tool_context, "value", None)
    if not isinstance(context, dict) or not isinstance(context.get("transcript"), dict):
        return json.dumps({"success": False, "error": "client_context_unavailable"})
    transcript = context["transcript"]
    context["read"] = True
    messages = transcript.get("messages") if isinstance(transcript.get("messages"), list) else []
    source_sessions = (
        transcript.get("source_sessions")
        if isinstance(transcript.get("source_sessions"), list) else []
    )
    return json.dumps(
        {
            "success": True,
            "session_id": transcript.get("session_id"),
            "truncated": bool(transcript.get("truncated")),
            "messages": messages,
            "source_sessions": source_sessions,
        },
        ensure_ascii=False,
    )


def _note_draft_tool(args: dict[str, Any], **_kwargs) -> str:
    context = getattr(_client_context_tool_context, "value", None)
    if not isinstance(context, dict) or not context.get("hermes_session_id"):
        return json.dumps(
            {"success": False, "error": "hermes_session_required"},
            ensure_ascii=False,
        )
    if not context.get("user_note_search_completed"):
        return json.dumps(
            {"success": False, "error": "user_note_search_required"},
            ensure_ascii=False,
        )
    title = str((args or {}).get("title") or "").strip()[:200]
    markdown = str((args or {}).get("markdown") or "").strip()[:100_000]
    if not title or not markdown:
        return json.dumps(
            {"success": False, "error": "title_and_markdown_required"},
            ensure_ascii=False,
        )
    tags = [str(item).strip()[:50] for item in (args or {}).get("tags") or []]
    tags = [item for item in tags if item][:12]
    note_kind = str((args or {}).get("note_kind") or "standard").strip().lower()
    if note_kind not in {"standard", "daily"}:
        return json.dumps(
            {"success": False, "error": "unsupported_note_kind"},
            ensure_ascii=False,
        )
    if note_kind == "daily" and "daily" not in {item.casefold() for item in tags}:
        tags = (tags + ["daily"])[:12]
    allowed_source_ids = {
        str(item)[:100] for item in context.get("hermes_message_ids") or []
    }
    source_ids = [
        str(item)[:100]
        for item in (args or {}).get("source_message_ids") or []
        if str(item)[:100] in allowed_source_ids
    ][:200]
    searched = context.get("user_note_search_results")
    searched = searched if isinstance(searched, dict) else {}
    operation = str((args or {}).get("operation") or "create").strip().lower()
    if operation not in {"create", "update"}:
        return json.dumps(
            {"success": False, "error": "unsupported_note_operation"},
            ensure_ascii=False,
        )
    target_note_id = str((args or {}).get("target_note_id") or "").strip()[:128]
    target_note = searched.get(target_note_id) if target_note_id else None
    if operation == "update" and not isinstance(target_note, dict):
        return json.dumps(
            {"success": False, "error": "target_note_not_in_current_user_search"},
            ensure_ascii=False,
        )
    if operation == "create":
        target_note_id = ""
        target_note = None
    requested_candidates = (args or {}).get("merge_candidate_ids") or []
    merge_candidates = []
    seen_candidate_ids: set[str] = set()
    for requested_id in requested_candidates:
        note_id = str(requested_id)
        candidate = searched.get(note_id)
        if (
            not isinstance(candidate, dict)
            or note_id == target_note_id
            or bool(candidate.get("archived"))
            or note_id in seen_candidate_ids
        ):
            continue
        seen_candidate_ids.add(note_id)
        merge_candidates.append(candidate)
        if len(merge_candidates) == 8:
            break
    merged_title = str((args or {}).get("merged_title") or "").strip()[:200]
    merged_markdown = str((args or {}).get("merged_markdown") or "").strip()[:200_000]
    merged_tags = [
        str(item).strip()[:50] for item in (args or {}).get("merged_tags") or []
    ]
    merged_tags = [item for item in merged_tags if item][:12]
    if operation == "update" and merge_candidates:
        # ``markdown`` is the complete, user-targeted revision for an update.
        # Never replace it with a second model payload that may only summarize it.
        merged_title = title
        merged_markdown = markdown
        merged_tags = list(dict.fromkeys(tags + merged_tags))[:12]
    if merge_candidates and (not merged_title or not merged_markdown):
        return json.dumps(
            {"success": False, "error": "merged_draft_required_for_candidates"},
            ensure_ascii=False,
        )
    if not merge_candidates:
        merged_title = ""
        merged_markdown = ""
        merged_tags = []
    seed = (
        f"{context.get('request_id')}\0{operation}\0{target_note_id}"
        f"\0{title}\0{markdown}"
    ).encode()
    draft_id = "draft-" + hashlib.sha256(seed).hexdigest()[:24]
    event = {
        "type": "note_draft",
        "draft_id": draft_id,
        "title": title,
        "markdown": markdown,
        "tags": tags,
        "note_kind": note_kind,
        "source_session_id": context.get("client_session_id"),
        "source_message_ids": source_ids,
        "account_scope": context.get("account_scope"),
        "merge_candidates": merge_candidates,
        "merged_title": merged_title or None,
        "merged_markdown": merged_markdown or None,
        "merged_tags": merged_tags,
        "operation": operation,
        "target_note_id": target_note_id or None,
        "target_note_title": (
            str(target_note.get("title") or "无标题")[:200]
            if isinstance(target_note, dict) else None
        ),
        "target_content_hash": (
            str(target_note.get("content_hash") or "") or None
            if isinstance(target_note, dict) else None
        ),
    }
    context["draft_emitted"] = True
    emitter = context.get("emit")
    if callable(emitter):
        emitter(event)
    return json.dumps(
        {
            "success": True,
            "draft_id": draft_id,
            "status": "awaiting_user_confirmation",
            "saved": False,
            "operation": operation,
            "target_note_id": target_note_id or None,
            "merge_candidate_count": len(merge_candidates),
        },
        ensure_ascii=False,
    )


_KNOWLEDGE_MUTATION_KINDS = {
    "create_note", "create_daily_note", "update_note", "rename_note",
    "set_tags", "set_pinned", "add_wikilink", "remove_wikilink",
    "merge_notes", "archive_note", "restore_note", "move_to_trash",
}


_KNOWLEDGE_NAV_DESTINATIONS = {
    "knowledge_home", "note", "daily_note", "search", "archive",
}


_KNOWLEDGE_MERGE_DIRECTIVE = (
    "\n个人知识整理规则：合并主题不等于目标笔记。主题依次取用户明确主题、明确目标标题，"
    "否则只从保存指令前最近五轮提取唯一主要实质主题；仍有多个主题时必须询问。"
    "围绕主题依次搜索精确主题、关键实体/别名、上层主题；搜索结果只用于定位，先看摘要，"
    "再 read 真正候选的完整正文。目标依次取用户明确指定、主题完全同名、职责明确且已有匹配"
    "章节的上层笔记；独立专题和上层总笔记等多个合理去向会改变知识结构时必须询问用户，"
    "不得按相关度静默选择；无目标才提议新建。"
    "直接使用当前 Hermes Session 内容，禁止先写临时笔记。只吸收与主题直接相关的内容块；"
    "背景/依据保留原笔记并在正文就近添加 [[双链]]，无关内容排除，冲突双方保留并标注待核对。"
    "只有全文职责被完整替代的来源才可列入 merge_notes 的 source_note_ids 归档；部分吸收、"
    "仅作引用或无法确定的来源必须保留。最多归档 16 篇，超出部分留待基于目标最新版本分批确认。"
    "更新或合并必须输出目标笔记的完整 Markdown 新版本：保留原用途、结构、无关但有效的内容和"
    "用户写作习惯；事实去重，不编造输入中没有的事实、数字或结论，并保留/补充 frontmatter 中"
    "的 source_message_ids 与 source_session_ids。当前相关消息 ID 减去目标已有 source_message_ids"
    "才是本次 Session 增量；差集为空且候选版本无变化时不要提案，只回复‘没有新增内容’。"
    "确认卡 summary、before_preview、after_preview、markdown_diff 必须说明合并主题、目标是新建"
    "还是更新、吸收内容、归档来源、保留并链接的来源、冲突和待核对项。"
)


def _workspace_notes(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in context.get("inline_notes") or []
        if isinstance(item, dict) and item.get("id")
    ]


def _knowledge_workspace_read_tool(args: dict[str, Any], **_kwargs) -> str:
    context = getattr(_client_context_tool_context, "value", None)
    if not isinstance(context, dict) or not context.get("knowledge_action_v1"):
        return json.dumps({"success": False, "error": "knowledge_workspace_denied"})
    operation = str((args or {}).get("operation") or "list").strip().lower()
    context["knowledge_workspace_read_completed"] = True
    notes = _workspace_notes(context)
    if operation == "read":
        note_id = str((args or {}).get("note_id") or "").strip()
        note = next((item for item in notes if str(item.get("id")) == note_id), None)
        if note is None:
            return json.dumps({"success": False, "error": "note_not_found"})
        return json.dumps({"success": True, "note": note}, ensure_ascii=False)
    if operation == "search":
        query = str((args or {}).get("query") or "").strip().casefold()
        if not query:
            return json.dumps({"success": False, "error": "query_required"})
        # The signed private-note capability is authoritative. Inline notes are
        # only an offline/cache fallback and must not cap discovery to one device.
        gateway_result = json.loads(_user_note_search_tool({"query": query, "limit": 10}))
        gateway_docs = gateway_result.get("docs") if gateway_result.get("success") else []
        if gateway_docs:
            existing = {str(item.get("id")): item for item in notes}
            for doc in gateway_docs:
                note_id = str(doc.get("id") or "").strip()
                if not note_id:
                    continue
                existing[note_id] = {
                    "id": note_id,
                    "title": str(doc.get("title") or "无标题")[:200],
                    "markdown": str(doc.get("markdown") or doc.get("snippet") or "")[:500_000],
                    "updated_at": doc.get("updated_at"),
                    "content_hash": doc.get("content_hash"),
                    "tags": doc.get("tags") or [],
                    "aliases": doc.get("aliases") or [],
                    "archived": bool(doc.get("archived")),
                }
            context["inline_notes"] = list(existing.values())
            notes = list(existing.values())
            return json.dumps({
                "success": True,
                "notes": [{
                    "id": item.get("id"), "title": item.get("title"),
                    "snippet": str(item.get("markdown") or "")[:1_000],
                    "updated_at": item.get("updated_at"),
                    "content_hash": item.get("content_hash"),
                    "tags": item.get("tags") or [], "aliases": item.get("aliases") or [],
                    "archived": bool(item.get("archived")),
                } for item in notes[:10]],
            }, ensure_ascii=False)
        terms = [item for item in re.split(r"\s+", query) if item]
        notes = [
            item for item in notes
            if all(term in (str(item.get("title") or "") + "\n" + str(item.get("markdown") or "")).casefold()
                   for term in terms)
        ]
    elif operation == "archive":
        notes = [item for item in notes if bool(item.get("archived"))]
    elif operation == "tags":
        tags = sorted({str(tag) for item in notes for tag in item.get("tags") or [] if tag})
        return json.dumps({"success": True, "tags": tags}, ensure_ascii=False)
    elif operation == "relationships":
        note_id = str((args or {}).get("note_id") or "").strip()
        selected = next((item for item in notes if str(item.get("id")) == note_id), None)
        if selected is None:
            return json.dumps({"success": False, "error": "note_not_found"})
        title = str(selected.get("title") or "")
        markdown = str(selected.get("markdown") or "")
        outgoing = re.findall(r"(?<!!)\[\[([^\]|#]+)", markdown)
        embeds = re.findall(r"!\[\[([^\]|#]+)", markdown)
        backlinks = [
            {"id": item.get("id"), "title": item.get("title")}
            for item in notes
            if f"[[{title}" in str(item.get("markdown") or "")
        ]
        known_titles = {str(item.get("title") or "").casefold() for item in notes}
        unresolved = [name for name in outgoing + embeds if name.casefold() not in known_titles]
        return json.dumps({
            "success": True, "outgoing": outgoing, "embeds": embeds,
            "backlinks": backlinks, "unresolved": unresolved,
        }, ensure_ascii=False)
    elif operation != "list":
        return json.dumps({"success": False, "error": "unsupported_read_operation"})
    limit = max(1, min(100, int((args or {}).get("limit") or 30)))
    if operation == "search":
        notes = [{
            "id": item.get("id"), "title": item.get("title"),
            "snippet": str(item.get("markdown") or "")[:1_000],
            "updated_at": item.get("updated_at"),
            "content_hash": item.get("content_hash"),
            "tags": item.get("tags") or [], "aliases": item.get("aliases") or [],
            "archived": bool(item.get("archived")),
        } for item in notes]
    return json.dumps({"success": True, "notes": notes[:limit]}, ensure_ascii=False)


def _knowledge_action_propose_tool(args: dict[str, Any], **_kwargs) -> str:
    context = getattr(_client_context_tool_context, "value", None)
    if not isinstance(context, dict) or not context.get("knowledge_action_v1"):
        return json.dumps({"success": False, "error": "knowledge_workspace_denied"})
    raw_steps = (args or {}).get("steps") or []
    if not isinstance(raw_steps, list) or not raw_steps or len(raw_steps) > 32:
        return json.dumps({"success": False, "error": "action_steps_required"})
    creates_only = all(
        isinstance(step, dict)
        and str(step.get("kind") or "").strip() in {"create_note", "create_daily_note"}
        for step in raw_steps
    )
    if not creates_only and not context.get("knowledge_workspace_read_completed"):
        return json.dumps({"success": False, "error": "knowledge_workspace_read_required"})
    notes = {str(item.get("id")): item for item in _workspace_notes(context)}
    normalized: list[dict[str, Any]] = []
    for raw in raw_steps:
        if not isinstance(raw, dict):
            return json.dumps({"success": False, "error": "invalid_action_step"})
        kind = str(raw.get("kind") or "").strip()
        if kind not in _KNOWLEDGE_MUTATION_KINDS:
            return json.dumps({"success": False, "error": "unsupported_action_kind"})
        target_id = str(raw.get("target_note_id") or "").strip()[:128]
        if kind == "merge_notes" and not isinstance(raw.get("source_note_ids", []), list):
            return json.dumps({"success": False, "error": "invalid_merge_sources"})
        source_ids = [str(item)[:128] for item in raw.get("source_note_ids") or []][:16]
        referenced_ids = ([target_id] if target_id else []) + source_ids
        # A merge updates an explicitly selected existing object. Source-only
        # legacy requests must not reach clients which synthesize a new ID.
        if kind == "merge_notes":
            if not target_id:
                return json.dumps({"success": False, "error": "merge_target_required"})
            if str(raw.get("target_note_id")) != target_id or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", target_id
            ):
                return json.dumps({"success": False, "error": "invalid_merge_target"})
            raw_sources = raw.get("source_note_ids", [])
            if not isinstance(raw_sources, list) or raw_sources != source_ids or any(
                not isinstance(value, str) or not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value
                ) for value in raw_sources
            ):
                return json.dumps({"success": False, "error": "invalid_merge_sources"})
            if notes.get(target_id, {}).get("archived"):
                return json.dumps({"success": False, "error": "merge_target_archived"})
            if target_id in source_ids:
                return json.dumps({"success": False, "error": "merge_target_is_source"})
            if len(source_ids) != len(set(source_ids)):
                return json.dumps({"success": False, "error": "duplicate_merge_source"})
            for note_id in referenced_ids:
                note = notes.get(note_id)
                if note is not None and not re.fullmatch(
                    r"[0-9a-f]{64}", str(note.get("content_hash") or "")
                ):
                    return json.dumps({"success": False, "error": "merge_version_required"})
                if note is not None and note.get("archived"):
                    return json.dumps({"success": False, "error": "merge_source_archived"})
        if kind not in {"create_note", "create_daily_note"} and not referenced_ids:
            return json.dumps({"success": False, "error": "target_note_required"})
        if any(note_id not in notes for note_id in referenced_ids):
            return json.dumps({"success": False, "error": "target_not_in_personal_workspace"})
        markdown = str(raw.get("markdown") or "").strip()[:500_000]
        if kind in {"create_note", "create_daily_note", "update_note", "merge_notes"} and not markdown:
            return json.dumps({"success": False, "error": "complete_markdown_required"})
        step = {
            "kind": kind,
            "target_note_id": target_id or None,
            "source_note_ids": source_ids,
            "title": str(raw.get("title") or "").strip()[:200] or None,
            "markdown": markdown or None,
            "tags": [str(item).strip()[:50] for item in raw.get("tags") or [] if str(item).strip()][:64],
            "pinned": raw.get("pinned") if isinstance(raw.get("pinned"), bool) else None,
            "link_title": str(raw.get("link_title") or "").strip()[:200] or None,
            "original_content_hash": (
                raw.get("original_content_hash")
                if "original_content_hash" in raw
                else notes.get(target_id, {}).get("content_hash") if target_id else None
            ),
            "source_content_hashes": (
                raw.get("source_content_hashes")
                if "source_content_hashes" in raw
                else {
                    note_id: notes.get(note_id, {}).get("content_hash")
                    for note_id in source_ids
                }
            ),
        }
        normalized.append(step)
    summary = str((args or {}).get("summary") or "").strip()[:500]
    if not summary:
        return json.dumps({"success": False, "error": "summary_required"})
    before_preview = str((args or {}).get("before_preview") or "").strip()[:2000]
    after_preview = str((args or {}).get("after_preview") or "").strip()[:4000]
    markdown_diff = str((args or {}).get("markdown_diff") or "").strip()[:20_000]
    navigation = (args or {}).get("suggested_navigation") or {"destination": "knowledge_home"}
    if not isinstance(navigation, dict) or navigation.get("destination") not in _KNOWLEDGE_NAV_DESTINATIONS:
        return json.dumps({"success": False, "error": "invalid_navigation_destination"})
    immutable = {
        "summary": summary,
        "steps": normalized,
        "before_preview": before_preview,
        "after_preview": after_preview,
        "markdown_diff": markdown_diff,
        "suggested_navigation": navigation,
    }
    seed = json.dumps(
        {"request_id": context.get("request_id"), **immutable},
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode()
    action_id = "ka-" + hashlib.sha256(seed).hexdigest()[:28]
    event = {
        "type": "knowledge_action_draft",
        "action_id": action_id,
        **immutable,
        "risk_level": "medium" if any(
            item["kind"] in {"merge_notes", "archive_note", "move_to_trash"}
            for item in normalized
        ) else "low",
        "confirmation_status": "unsigned",
    }
    context["knowledge_action_emitted"] = True
    emitter = context.get("emit")
    if callable(emitter):
        emitter(event)
    return json.dumps({
        "success": True, "action_id": action_id,
        "status": "awaiting_user_confirmation", "applied": False,
    }, ensure_ascii=False)


def _knowledge_ui_navigate_tool(args: dict[str, Any], **_kwargs) -> str:
    context = getattr(_client_context_tool_context, "value", None)
    if not isinstance(context, dict) or not context.get("knowledge_action_v1"):
        return json.dumps({"success": False, "error": "knowledge_workspace_denied"})
    destination = str((args or {}).get("destination") or "").strip()
    if destination not in _KNOWLEDGE_NAV_DESTINATIONS:
        return json.dumps({"success": False, "error": "invalid_navigation_destination"})
    event = {
        "type": "knowledge_navigation", "destination": destination,
        "note_id": str((args or {}).get("note_id") or "").strip()[:128] or None,
        "query": str((args or {}).get("query") or "").strip()[:200] or None,
    }
    emitter = context.get("emit")
    if callable(emitter):
        emitter(event)
    return json.dumps({"success": True, **event}, ensure_ascii=False)


def _ensure_knowledge_workspace_tools_registered() -> None:
    global _knowledge_workspace_tools_registered
    if _knowledge_workspace_tools_registered:
        return
    with _knowledge_workspace_tool_registration_lock:
        if _knowledge_workspace_tools_registered:
            return
        from tools.registry import registry

        registry.register(
            name="knowledge_workspace_read", toolset="knowledge_workspace",
            schema={
                "name": "knowledge_workspace_read",
                "description": "List, search or read only the authenticated user's personal notes, tags and links.",
                "parameters": {"type": "object", "properties": {
                    "operation": {"type": "string", "enum": ["list", "search", "read", "tags", "relationships", "archive"]},
                    "query": {"type": "string"}, "note_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                }, "required": ["operation"]},
            }, handler=lambda args, **kwargs: _knowledge_workspace_read_tool(args, **kwargs),
        )
        registry.register(
            name="knowledge_action_propose", toolset="knowledge_workspace",
            schema={
                "name": "knowledge_action_propose",
                "description": (
                    "Propose one atomic, user-confirmed personal knowledge action. Never writes. "
                    "For content changes return the complete Obsidian-compatible Markdown."
                ),
                "parameters": {"type": "object", "properties": {
                    "summary": {"type": "string"},
                    "steps": {"type": "array", "items": {"type": "object", "properties": {
                        "kind": {"type": "string", "enum": sorted(_KNOWLEDGE_MUTATION_KINDS)},
                        "target_note_id": {"type": "string"},
                        "source_note_ids": {"type": "array", "items": {"type": "string"}},
                        "title": {"type": "string"}, "markdown": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "pinned": {"type": "boolean"}, "link_title": {"type": "string"},
                    }, "required": ["kind"]}},
                    "before_preview": {"type": "string"}, "after_preview": {"type": "string"},
                    "markdown_diff": {"type": "string"},
                    "suggested_navigation": {"type": "object", "properties": {
                        "destination": {"type": "string", "enum": sorted(_KNOWLEDGE_NAV_DESTINATIONS)},
                        "note_id": {"type": "string"}, "query": {"type": "string"},
                    }, "required": ["destination"]},
                }, "required": ["summary", "steps", "suggested_navigation"]},
            }, handler=lambda args, **kwargs: _knowledge_action_propose_tool(args, **kwargs),
        )
        registry.register(
            name="knowledge_ui_navigate", toolset="knowledge_workspace",
            schema={
                "name": "knowledge_ui_navigate",
                "description": "Navigate the iOS knowledge UI using a controlled destination; never simulates taps.",
                "parameters": {"type": "object", "properties": {
                    "destination": {"type": "string", "enum": sorted(_KNOWLEDGE_NAV_DESTINATIONS)},
                    "note_id": {"type": "string"}, "query": {"type": "string"},
                }, "required": ["destination"]},
            }, handler=lambda args, **kwargs: _knowledge_ui_navigate_tool(args, **kwargs),
        )
        _knowledge_workspace_tools_registered = True


def _ensure_client_context_tools_registered() -> None:
    global _client_context_tools_registered
    if _client_context_tools_registered:
        return
    with _client_context_tool_registration_lock:
        if _client_context_tools_registered:
            return
        from tools.registry import registry

        registry.register(
            name="session_context_read",
            toolset="client_context",
            schema={
                "name": "session_context_read",
                "description": (
                    "Read the authenticated current iOS conversation transcript. "
                    "Call this before summarizing what was discussed in this chat."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
            handler=lambda args, **kwargs: _session_context_read_tool(args, **kwargs),
        )
        registry.register(
            name="note_draft",
            toolset="client_context",
            schema={
                "name": "note_draft",
                "description": (
                    "Create a Markdown note draft for the iOS client to confirm. "
                    "Use operation=update with a target_note_id returned by "
                    "user_note_search when the user explicitly asks to improve an "
                    "existing note. This tool never saves by itself."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "markdown": {
                            "type": "string",
                            "description": (
                                "Complete Obsidian-compatible Markdown. Supported constructs include "
                                "headings, #tags, tasks, [[wikilinks]], ![[embeds]], > [!tip] callouts, "
                                "quotes, tables, fenced code blocks and ordinary Markdown. For update, "
                                "preserve unrelated existing content and return the complete revised note."
                            ),
                        },
                        "note_kind": {
                            "type": "string",
                            "enum": ["standard", "daily"],
                            "default": "standard",
                            "description": "Use daily for a dated journal note; the bridge adds the daily tag.",
                        },
                        "format_features": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "heading", "tag", "task", "wikilink", "embed",
                                    "callout", "quote", "table", "code_block"
                                ],
                            },
                            "description": "Optional declaration of note constructs used in markdown.",
                        },
                        "operation": {
                            "type": "string",
                            "enum": ["create", "update"],
                            "default": "create",
                        },
                        "target_note_id": {
                            "type": "string",
                            "description": "Required for update; must come from user_note_search in this request.",
                        },
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "source_message_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "merge_candidate_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Only IDs returned by user_note_search in this request.",
                        },
                        "merged_title": {"type": "string"},
                        "merged_markdown": {"type": "string"},
                        "merged_tags": {
                            "type": "array", "items": {"type": "string"},
                        },
                    },
                    "required": ["title", "markdown", "source_message_ids"],
                },
            },
            handler=lambda args, **kwargs: _note_draft_tool(args, **kwargs),
        )
        _client_context_tools_registered = True


async def list_skills(
    x_knowledge_capability: str = Header(default=""),
):
    """List only Skill copies selected by a signed tenant/user capability."""
    try:
        claims = verify_capability(x_knowledge_capability)
    except KnowledgeScopeDenied as exc:
        raise HTTPException(status_code=403, detail="sandbox_identity_denied") from exc
    if str(claims.get("entry_point") or "") != "skills":
        raise HTTPException(status_code=403, detail="sandbox_identity_denied")
    sandbox = _persistence._tenant_sandbox_from_claims(
        subject_id=str(claims.get("subject_id") or "skills"),
        knowledge_claims=claims,
        client_claims=None,
    )
    return {
        "skills": _contracts._routed_skill_catalog(sandbox),
        "tenant_namespace": sandbox.tenant_namespace,
        "template_version": sandbox.template_version,
    }


async def delete_skill(
    name: str,
    x_knowledge_capability: str = Header(default=""),
    x_idempotency_key: str = Header(default=""),
):
    """Delete only a custom Skill in the signed tenant sandbox."""
    if x_idempotency_key and len(x_idempotency_key) > 160:
        raise HTTPException(status_code=400, detail="invalid_idempotency_key")
    sandbox = _skill_sandbox(x_knowledge_capability)
    try:
        deleted = delete_sandbox_skill(sandbox, name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="tenant_skill_not_found")
    remaining = _contracts._routed_skill_catalog(sandbox)
    if any(
        item.get("scope") == "tenant" and item.get("name") == name
        for item in remaining
    ):
        raise HTTPException(status_code=500, detail="tenant_skill_delete_not_verified")
    return {"deleted": True, "name": name, "verified": True}


from . import contracts as _contracts, persistence as _persistence  # noqa: E402


def _app_capability_search_tool(args: dict[str, Any], **_kwargs) -> str:
    from backend.services.capability_catalog import catalog_digest, search_capabilities

    query = str((args or {}).get("query") or "").strip()[:200]
    limit = max(1, min(10, int((args or {}).get("limit") or 5)))
    return json.dumps({
        "success": True, "protocol": "qcp", "catalog_digest": catalog_digest(),
        "items": search_capabilities(query, limit=limit),
    }, ensure_ascii=False)



def _app_capability_describe_tool(args: dict[str, Any], **_kwargs) -> str:
    from backend.services.capability_catalog import describe_capability

    capability_id = str((args or {}).get("capability_id") or "").strip()
    capability = describe_capability(capability_id)
    return json.dumps(
        {"success": capability is not None, "capability": capability,
         **({} if capability is not None else {"error": "capability_not_found"})},
        ensure_ascii=False,
    )



def _app_capability_invoke_tool(args: dict[str, Any], **_kwargs) -> str:
    """Route model intent to existing semantic tools; never accepts authority."""
    from backend.services.capability_catalog import (
        CapabilityContractError, describe_capability, validate_instance,
    )

    capability_id = str((args or {}).get("capability_id") or "").strip()
    data = (args or {}).get("input")
    capability = describe_capability(capability_id)
    if capability is None:
        return json.dumps({"success": False, "error": "capability_not_found"})
    if capability["implementation_status"] != "implemented":
        return json.dumps({"success": False, "error": "capability_not_executable"})
    if not isinstance(data, dict):
        return json.dumps({"success": False, "error": "input_object_required"})
    try:
        validate_instance(data, capability["input_schema"])
    except CapabilityContractError as exc:
        return json.dumps({"success": False, "error": "contract_invalid", "detail": str(exc)[:200]})
    if capability_id == "knowledge.note.search":
        return _knowledge_workspace_read_tool({"operation": "search", **data})
    if capability_id == "knowledge.note.read":
        return _knowledge_workspace_read_tool({"operation": "read", **data})
    if capability_id == "knowledge.navigation":
        return _knowledge_ui_navigate_tool(data)
    kind = {
        "knowledge.note.create": "create_note",
        "knowledge.note.update": "update_note",
        "knowledge.note.merge": "merge_notes",
        "knowledge.note.archive": "archive_note",
        "knowledge.note.restore": "restore_note",
    }.get(capability_id)
    if kind:
        target_id = str(data.get("note_id") or data.get("target_note_id") or "")
        if kind != "create_note":
            read = json.loads(_knowledge_workspace_read_tool({
                "operation": "read", "note_id": target_id,
            }))
            if not read.get("success"):
                return json.dumps(read, ensure_ascii=False)
        step = {
            "kind": kind,
            "target_note_id": target_id or None,
            "source_note_ids": list((data.get("source_versions") or {}).keys()),
            "markdown": data.get("markdown") or data.get("revised_content"),
            "original_content_hash": data.get("base_hash") or data.get("target_base_hash"),
            "source_content_hashes": data.get("source_versions"),
        }
        return _knowledge_action_propose_tool({
            "summary": f"执行 {capability_id}", "steps": [step],
            "suggested_navigation": {
                "destination": "note" if target_id else "knowledge_home",
                **({"note_id": target_id} if target_id else {}),
            },
        })
    if capability["confirmation"] == "required":
        context = getattr(_client_context_tool_context, "value", None)
        identity = context.get("identity") if isinstance(context, dict) else None
        request_id = str((context or {}).get("request_id") or "")
        session_id = str((context or {}).get("client_session_id") or "")
        if (
            not isinstance(identity, dict)
            or not str(identity.get("tenant_key") or "")
            or not str(identity.get("user_id") or "")
            or len(request_id) < 8
            or not session_id
        ):
            return json.dumps({"success": False, "error": "trusted_invocation_context_required"})
        assert isinstance(context, dict)
        input_digest = hashlib.sha256(json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode()).hexdigest()
        stable_key = "bridge-" + hashlib.sha256(
            f"{capability_id}:{request_id}:{input_digest}".encode()
        ).hexdigest()
        from backend.services.capability_gateway import create_capability_proposal
        proposal = create_capability_proposal(
            capability_id,
            data,
            payload=dict(identity),
            session_id=session_id,
            request_id=request_id,
            idempotency_key=stable_key,
            resource_versions=data.get("resource_versions") or {},
            renderer_version="qcp-ios@1",
        )
        try:
            result = _contracts._run_bridge_coroutine(
                proposal,
                timeout=_contracts.CAPABILITY_DISPATCH_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return json.dumps({"success": False, "error": "async_dispatch_timeout"})
        except Exception:
            traceback.print_exc()
            if inspect.getcoroutinestate(proposal) == inspect.CORO_CREATED:
                proposal.close()
            return json.dumps({"success": False, "error": "proposal_persistence_failed"})
        emit = context.get("emit")
        if callable(emit):
            for event in result.get("events") or []:
                emit(event)
        return json.dumps(result, ensure_ascii=False)
    if capability_id not in {
        "workflow.create", "workflow.open", "workflow.status", "workflow.start",
        "presentation.create_from_document", "artifact.open", "artifact.download",
        "artifact.consume_structured",
    }:
        return json.dumps({"success": False, "error": "bridge_execution_unavailable"})
    context = getattr(_client_context_tool_context, "value", None)
    identity = context.get("identity") if isinstance(context, dict) else None
    request_id = str((context or {}).get("request_id") or "")
    if (
        not isinstance(identity, dict)
        or not str(identity.get("tenant_key") or "")
        or not str(identity.get("user_id") or "")
        or len(request_id) < 8
    ):
        return json.dumps({"success": False, "error": "trusted_invocation_context_required"})
    from backend.api.tenant import current_tenant
    from backend.services.capability_catalog import invoke_capability

    tenant_token = current_tenant.set(str(identity["tenant_key"]))
    try:
        input_digest = hashlib.sha256(json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode()).hexdigest()
        stable_key = (
            "bridge-" + hashlib.sha256(
                f"{capability_id}:{request_id}:{input_digest}".encode()
            ).hexdigest()
            if capability.get("idempotency") == "required"
            else None
        )
        invocation = invoke_capability(
            capability_id,
            data,
            payload=dict(identity),
            idempotency_key=stable_key,
        )
        try:
            result = _contracts._run_bridge_coroutine(
                invocation,
                timeout=_contracts.CAPABILITY_DISPATCH_TIMEOUT_SECONDS,
            )
        except RuntimeError:
            invocation.close()
            return json.dumps({"success": False, "error": "async_dispatch_unavailable"})
        except TimeoutError:
            return json.dumps({"success": False, "error": "async_dispatch_timeout"})
        except Exception:
            return json.dumps({"success": False, "error": "async_dispatch_failed"})
    finally:
        current_tenant.reset(tenant_token)
    emit = context.get("emit")
    if callable(emit):
        for event in result.get("events") or []:
            emit(event)
    return json.dumps(result, ensure_ascii=False)


from . import contracts as _contracts


def _app_capability_native_tool_name(capability_id: str) -> str:
    """Compile one stable provider-safe Hermes tool name from a QCP id."""
    normalized = re.sub(r"[^a-z0-9_]+", "_", capability_id.casefold()).strip("_")
    name = f"app_{normalized}"
    if not normalized or len(name) > 64:
        raise ValueError(f"invalid native capability tool name: {capability_id}")
    return name



def _app_capability_native_tool_schema(capability: dict[str, Any]) -> dict[str, Any]:
    """Compile the governed capability contract into a native Hermes tool."""
    name = _app_capability_native_tool_name(str(capability["id"]))
    use_when = "; ".join(str(item) for item in capability.get("positive_examples") or [])
    exclude_when = "; ".join(str(item) for item in capability.get("negative_examples") or [])
    description_parts = [str(capability["description"]).strip()]
    if use_when:
        description_parts.append(f"Use when: {use_when}")
    if exclude_when:
        description_parts.append(f"Do not use when: {exclude_when}")
    if capability.get("confirmation") == "required":
        description_parts.append(
            "This tool only proposes the action; the authenticated app must confirm it."
        )
    return {
        "name": name,
        "description": " ".join(description_parts),
        "parameters": json.loads(json.dumps(capability["input_schema"])),
    }



def _app_capability_native_handler(capability_id: str) -> Callable[..., str]:
    """Bind a native Hermes tool to exactly one immutable capability id."""
    def handler(args: dict[str, Any], **kwargs) -> str:
        return _app_capability_invoke_tool(
            {"capability_id": capability_id, "input": dict(args or {})}, **kwargs
        )

    return handler



def _ensure_app_capability_tools_registered() -> None:
    global _app_capability_tools_registered
    if _app_capability_tools_registered:
        return
    with _app_capability_tool_registration_lock:
        if _app_capability_tools_registered:
            return
        from backend.services.capability_catalog import load_catalog
        from tools.registry import registry

        compiled_names: set[str] = set()
        for capability in load_catalog()["capabilities"]:
            if capability.get("implementation_status") != "implemented":
                continue
            schema = _app_capability_native_tool_schema(capability)
            name = schema["name"]
            if name in compiled_names:
                raise RuntimeError(f"duplicate native capability tool: {name}")
            compiled_names.add(name)
            registry.register(
                name=name,
                toolset="app_capabilities",
                schema=schema,
                handler=_app_capability_native_handler(str(capability["id"])),
            )
        _app_capability_tools_registered = True



class SkillCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    content: str = Field(..., min_length=1, max_length=200_000)



class SkillUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, max_length=200_000)



def _skill_sandbox(capability: str) -> TenantHermesSandbox:
    try:
        claims = verify_capability(capability)
    except KnowledgeScopeDenied as exc:
        raise HTTPException(status_code=403, detail="sandbox_identity_denied") from exc
    if str(claims.get("entry_point") or "") != "skills":
        raise HTTPException(status_code=403, detail="sandbox_identity_denied")
    return _persistence._tenant_sandbox_from_claims(
        subject_id=str(claims.get("subject_id") or "skills"),
        knowledge_claims=claims,
        client_claims=None,
    )


from . import persistence as _persistence


def _write_skill_and_verify(
    sandbox: TenantHermesSandbox, *, name: str, content: str, replace: bool
) -> dict[str, Any]:
    catalog = _contracts._routed_skill_catalog(sandbox)
    owned = {
        str(item.get("name")): item
        for item in catalog
        if item.get("scope") == "tenant"
    }
    if replace and name not in owned:
        raise HTTPException(status_code=404, detail="tenant_skill_not_found")
    if not replace and any(item.get("name") == name for item in catalog):
        raise HTTPException(status_code=409, detail="skill_exists")
    try:
        path = write_sandbox_skill(sandbox, name, content, replace=replace)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="skill_exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    record = next((
        item for item in _contracts._routed_skill_catalog(sandbox)
        if item.get("scope") == "tenant" and item.get("name") == name
    ), None)
    if (
        record is None
        or record.get("sha256") != digest
        or read_sandbox_skill(sandbox, name) != content
    ):
        raise HTTPException(status_code=500, detail="tenant_skill_write_not_verified")
    return {"name": name, "sha256": digest, "scope": "tenant", "verified": True}



async def create_skill(
    body: SkillCreateRequest,
    x_knowledge_capability: str = Header(default=""),
    x_idempotency_key: str = Header(default=""),
):
    if not x_idempotency_key.strip() or len(x_idempotency_key) > 160:
        raise HTTPException(status_code=400, detail="idempotency_key_required")
    return _write_skill_and_verify(
        _skill_sandbox(x_knowledge_capability),
        name=body.name,
        content=body.content,
        replace=False,
    )



async def update_skill(
    name: str,
    body: SkillUpdateRequest,
    x_knowledge_capability: str = Header(default=""),
    x_idempotency_key: str = Header(default=""),
):
    if not x_idempotency_key.strip() or len(x_idempotency_key) > 160:
        raise HTTPException(status_code=400, detail="idempotency_key_required")
    return _write_skill_and_verify(
        _skill_sandbox(x_knowledge_capability),
        name=name,
        content=body.content,
        replace=True,
    )


_app_capability_tool_registration_lock = threading.Lock()
_app_capability_tools_registered = False
