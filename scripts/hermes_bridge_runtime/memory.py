from __future__ import annotations

import ast
import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
import contextvars
import hashlib
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


def _isolated_agent_context_kwargs() -> dict[str, bool]:
    """Never let a cloud tenant inherit the service account's Hermes profile."""
    return dict(
        skip_context_files=True,
        skip_memory=True,
        load_soul_identity=False,
    )


def _with_sandbox_memory(
    sandbox: TenantHermesSandbox, action: Callable[[Any], Any]
) -> Any:
    """Run one native Hermes memory operation inside its user profile."""
    from hermes_constants import (
        reset_hermes_home_override,
        set_hermes_home_override,
    )
    from tools.memory_tool import MemoryStore

    token = set_hermes_home_override(_sandbox_hermes_home(sandbox))
    try:
        store = MemoryStore()
        store.load_from_disk()
        return action(store)
    finally:
        reset_hermes_home_override(token)


def _sandbox_hermes_home(sandbox: TenantHermesSandbox) -> Path:
    """Resolve the profile path while supporting existing lightweight test doubles."""
    configured = getattr(sandbox, "hermes_home", None)
    if configured is not None:
        return Path(configured)
    return Path(sandbox.state_db).parent / "hermes-home"


def _memory_id(target: str, content: str) -> str:
    return "mem_" + hashlib.sha256(f"{target}\0{content}".encode()).hexdigest()[:24]


def _sandbox_memory_payload(sandbox: TenantHermesSandbox) -> dict[str, Any]:
    def read(store: Any) -> dict[str, Any]:
        items = [
            {"id": _memory_id(target, content), "target": target, "content": content}
            for target in ("user", "memory")
            for content in store._entries_for(target)
        ]
        return {
            "items": items,
            "limits": {"user": store.user_char_limit, "memory": store.memory_char_limit},
            "usage": {
                target: len("\n§\n".join(store._entries_for(target)))
                for target in ("user", "memory")
            },
            "review_interval_turns": 10,
        }

    return _with_sandbox_memory(sandbox, read)


def _mutate_sandbox_memory(
    sandbox: TenantHermesSandbox,
    *,
    action: str,
    target: str | None = None,
    content: str = "",
    memory_id: str = "",
) -> dict[str, Any]:
    def mutate(store: Any) -> None:
        resolved_target = target
        old_content = ""
        if action != "add":
            match = next(
                (
                    (candidate, entry)
                    for candidate in ("user", "memory")
                    for entry in store._entries_for(candidate)
                    if _memory_id(candidate, entry) == memory_id
                ),
                None,
            )
            if match is None:
                raise KeyError(memory_id)
            resolved_target, old_content = match
        if resolved_target not in {"user", "memory"}:
            raise ValueError("invalid_memory_target")
        if action == "add":
            result = store.add(resolved_target, content)
        elif action == "replace":
            result = store.replace(resolved_target, old_content, content)
        elif action == "remove":
            result = store.remove(resolved_target, old_content)
        else:
            raise ValueError("invalid_memory_action")
        if not result.get("success"):
            raise ValueError(str(result.get("error") or "memory_write_rejected"))

    _with_sandbox_memory(sandbox, mutate)
    return _sandbox_memory_payload(sandbox)


class MemoryWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Literal["user", "memory"]
    content: str = Field(..., min_length=1, max_length=2_200)


class MemoryReplaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, max_length=2_200)


def _memory_sandbox(capability: str) -> TenantHermesSandbox:
    try:
        claims = verify_capability(capability)
    except KnowledgeScopeDenied as exc:
        raise HTTPException(status_code=403, detail="sandbox_identity_denied") from exc
    if str(claims.get("entry_point") or "") != "memory":
        raise HTTPException(status_code=403, detail="sandbox_identity_denied")
    return _persistence._tenant_sandbox_from_claims(
        subject_id=str(claims.get("subject_id") or "memory"),
        knowledge_claims=claims,
        client_claims=None,
    )


def _memory_write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail="memory_not_found")
    return HTTPException(
        status_code=409,
        detail={
            "code": "MEMORY_WRITE_REJECTED",
            "message": str(exc)[:500],
            "retryable": False,
        },
    )


async def list_native_memory(x_knowledge_capability: str = Header(default="")):
    return _sandbox_memory_payload(_memory_sandbox(x_knowledge_capability))


async def add_native_memory(
    body: MemoryWriteRequest,
    x_knowledge_capability: str = Header(default=""),
):
    try:
        return _mutate_sandbox_memory(
            _memory_sandbox(x_knowledge_capability),
            action="add",
            target=body.target,
            content=body.content,
        )
    except (KeyError, ValueError) as exc:
        raise _memory_write_error(exc) from exc


async def replace_native_memory(
    memory_id: str,
    body: MemoryReplaceRequest,
    x_knowledge_capability: str = Header(default=""),
):
    try:
        return _mutate_sandbox_memory(
            _memory_sandbox(x_knowledge_capability),
            action="replace",
            content=body.content,
            memory_id=memory_id,
        )
    except (KeyError, ValueError) as exc:
        raise _memory_write_error(exc) from exc


async def delete_native_memory(
    memory_id: str,
    x_knowledge_capability: str = Header(default=""),
):
    try:
        return _mutate_sandbox_memory(
            _memory_sandbox(x_knowledge_capability),
            action="remove",
            memory_id=memory_id,
        )
    except (KeyError, ValueError) as exc:
        raise _memory_write_error(exc) from exc


async def approve_workflow_gate(execution_id: str, body: _contracts.WorkflowGateApprovalRequest, x_hermes_internal_token: str | None = Header(None)):
    _persistence._require_internal(x_hermes_internal_token)
    with _contracts._workflow_runs_lock:
        run = _persistence._workflow_runs.get(execution_id)
        if not run or run.get("status") != "awaiting_approval":
            raise HTTPException(status_code=409, detail="workflow is not awaiting approval")
        state = (run.get("nodes") or {}).get(body.node_id) or {}
        node = next((item for item in run["plan"].get("nodes") or [] if item.get("id") == body.node_id), None)
        if not node or not (node.get("parameters") or {}).get("approval_gate") or state.get("status") != "succeeded" or int(state.get("attempt") or 0) != body.artifact_version:
            raise HTTPException(status_code=409, detail="stale gate approval")
        output = str(state.get("output") or "")
        if hashlib.sha256(output.encode()).hexdigest() != body.expected_hash:
            raise HTTPException(status_code=409, detail="approved artifact hash mismatch")
        if (node.get("parameters") or {}).get("output_format") == "presentation_design":
            from backend.services.presentation_scenario import validate_theme
            try:
                validate_theme(_workflow_artifacts._extract_json_object(output).get("theme"))
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        approved = set(run.get("approved_gates") or [])
        approved.add(body.node_id)
        run["approved_gates"] = sorted(approved)
        run.setdefault("approved_gate_artifacts", {})[body.node_id] = {"artifact_id": body.artifact_id, "content_hash": body.expected_hash, "artifact_version": body.artifact_version}
        run["status"] = "queued"
        _persistence._workflow_event(run, "gate_approved", node_id=body.node_id, artifact_version=body.artifact_version, message="业务阶段已确认")
        _workflow_runtime._start_workflow_thread(execution_id)
        return {"ok": True, "status": "queued"}


from . import contracts as _contracts, persistence as _persistence, workflow_artifacts as _workflow_artifacts, workflow_runtime as _workflow_runtime  # noqa: E402
