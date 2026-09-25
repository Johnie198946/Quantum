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


class DurableEventQueue(queue.Queue):
    """Commit 150ms text chunks before transport; control events flush immediately."""

    def __init__(self, run_id: str):
        super().__init__(maxsize=_contracts.STREAM_QUEUE_CAPACITY)
        self.run_id = run_id
        self._delta_lock = threading.Lock()
        self._delta_buffer = ""
        self._last_delta_flush = time.monotonic()

    def _commit_and_enqueue(self, item: dict) -> None:
        if _session_runtime._chat_run_store is not None:
            item = _session_runtime._chat_run_store.append_event(self.run_id, item)
        self.put_nowait(item)

    def flush_delta(self) -> None:
        with self._delta_lock:
            content = self._delta_buffer
            self._delta_buffer = ""
            self._last_delta_flush = time.monotonic()
        if content:
            self._commit_and_enqueue({"type": "delta", "content": content})

    def accept(self, item: dict) -> bool:
        if item.get("type") == "delta":
            with self._delta_lock:
                self._delta_buffer += str(item.get("content") or "")
                due = time.monotonic() - self._last_delta_flush >= 0.15
            if due:
                self.flush_delta()
            return True
        self.flush_delta()
        self._commit_and_enqueue(item)
        return True


def _qput(stream_q: queue.Queue, item: dict) -> bool:
    """Persist stable text chunks and every control event; never drop accepted events."""
    # ``importlib.reload`` and rolling worker upgrades can leave a sink derived
    # from the previous class object. Accept the durable protocol by capability,
    # not only by class identity, so terminal events are never silently dropped.
    accept = getattr(stream_q, "accept", None)
    if callable(accept):
        try:
            return accept(item) is not False
        except KeyError:
            # Unit/direct compatibility path without a pre-created durable Run.
            stream_q.put_nowait(item)
            return True
        except RuntimeError:
            # A losing worker may finish after explicit cancellation/regeneration.
            return False
    stream_q.put_nowait(item)
    return True


def _stream_run_register(user_id: str, state: dict) -> None:
    with _contracts._stream_runs_guard:
        _contracts._stream_runs[user_id] = state


def _stream_run_reserve(
    user_id: str,
    run_id: str,
    request_id: str | None,
    state_db: str | Path | None = None,
) -> bool:
    """Atomically claim one logical session before constructing its SSE body."""
    with _contracts._stream_runs_guard:
        if user_id in _contracts._stream_runs:
            return False
        _contracts._stream_runs[user_id] = {
            "reserved": True,
            "attached": True,
            "start_ts": time.monotonic(),
            "run_id": run_id,
            "request_id": request_id,
            "state_db": str(state_db) if state_db is not None else _contracts.STATE_DB,
        }
        return True


def _stream_run_get(user_id: str) -> dict | None:
    with _contracts._stream_runs_guard:
        return _contracts._stream_runs.get(user_id)


def _stream_run_discard(user_id: str, run_id: str | None = None) -> None:
    """移除在途 run 状态；传入 run_id 时校验匹配，防止误删新启动的 run（M-6 并发防护）。"""
    with _contracts._stream_runs_guard:
        state = _contracts._stream_runs.get(user_id)
        if state is None:
            return
        if run_id is not None and state.get("run_id") != run_id:
            return
        _contracts._stream_runs.pop(user_id, None)


def _watchdog_scan_once(now: float | None = None) -> list[tuple[str, str | None]]:
    """Return Runs past the server execution deadline, independent of SSE state.

    Connection loss never shortens a Run. Attached and detached executions share
    the same governance deadline; only that deadline or explicit user cancel may
    interrupt the worker.
    """
    now = now if now is not None else time.monotonic()
    victims: list[tuple[str, str | None]] = []
    with _contracts._stream_runs_guard:
        for uid, state in _contracts._stream_runs.items():
            start_ts = state.get("start_ts") or 0
            if now - start_ts > _contracts.STREAM_MAX_DURATION_SECONDS:
                victims.append((uid, state.get("run_id")))
    return victims


def _watchdog_loop_step() -> None:
    """watchdog 单轮执行：扫描 → 逐个 interrupt + discard（可单测驱动，G-10）。

    interrupt+discard 复用 _interrupt_and_discard（status 命中 timeout 同路径）。
    """
    for uid, run_id in _watchdog_scan_once():
        print(
            f"[bridge] watchdog: run 超 {_contracts.STREAM_MAX_DURATION_SECONDS}s"
            f"·interrupt+discard user={uid}"
        )
        _session_runtime._interrupt_and_discard(uid, run_id)


def _watchdog_loop() -> None:
    """独立守护线程：周期扫描 detached runs，超时 interrupt + discard（第 1 处中断入口）。"""
    while True:
        time.sleep(_contracts.WATCHDOG_INTERVAL_SECONDS)
        _watchdog_loop_step()


def _emit_tool_start(stream_q: queue.Queue, tool_call_id, function_name, function_args) -> None:
    """工具启动事件（模块级可测）：过滤内部工具 + 载荷治理（仅 preview/label）。

    代码块唤起（对齐官方 gateway fenced code block 语义）：代码型工具
    （terminal/write_file/patch/execute_code）附 code 字段（截断预览），
    前端渲染为代码块卡片；非代码工具 code=None。
    """
    if not tool_call_id or (function_name or "").startswith("_"):
        return
    label = function_name
    try:
        from agent.display import build_tool_preview
        preview = build_tool_preview(function_name, function_args)
        if preview:
            label = preview
    except Exception:
        pass

    code: str | None = None
    try:
        args = function_args or {}
        if function_name == "terminal":
            code = str(args.get("command") or "").rstrip()
        elif function_name in ("write_file", "patch"):
            content = args.get("content") or args.get("new_string") or ""
            content_s = str(content)
            code = content_s[:400] + ("\n…（预览截断）" if len(content_s) > 400 else "")
        elif function_name == "execute_code":
            content_s = str(args.get("code") or "")
            code = content_s[:400] + ("\n…（预览截断）" if len(content_s) > 400 else "")
    except Exception:
        code = None
    if code is not None and not code.strip():
        code = None

    route_target: str | None = None
    if function_name in {"agency_agents_load", "agency_agents_delegate"}:
        args = function_args or {}
        route_target = str(args.get("agent") or args.get("slug") or "").strip()[:100] or None

    _qput(stream_q, {
        "type": "tool_start",
        "id": tool_call_id,
        "tool": function_name,
        "label": label,
        "code": code,
        "route_target": route_target,
    })


def _tenantize_created_skill(
    function_args, sandbox: TenantHermesSandbox | None
) -> None:
    """Copy a newly-created Skill into the authenticated tenant overlay."""
    try:
        args = function_args or {}
        if args.get("action") != "create" or not args.get("name"):
            return
        if sandbox is None:
            return
        name = str(args["name"]).strip()
        if not name:
            return
        home = Path(os.environ.get("HERMES_HOME", str(Path.home())))
        skills_root = home / "skills" if home.name == ".hermes" else home / ".hermes" / "skills"
        # 新技能目录可能在分类子目录（<category>/<name>）或顶层（<name>）
        candidates = list(skills_root.glob(f"*/{name}")) + list(skills_root.glob(name))
        for src in candidates:
            if src.is_dir() and (src / "SKILL.md").exists() and "tenants" not in src.parts:
                dst = sandbox.custom_skills / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    shutil.copytree(str(src), str(dst), symlinks=False)
                print(
                    f"[bridge] 技能租户化副本: {name} → "
                    f"tenant={sandbox.tenant_namespace}"
                )
                return
    except Exception as e:
        print(f"[bridge] 技能租户化失败: {e}")


def _emit_tool_complete(stream_q: queue.Queue, tool_call_id, function_name, function_args=None, result=None) -> None:
    """工具完成事件（模块级可测）：不发 raw result（对齐 api_server 契约·防内部信息泄露）。"""
    if not tool_call_id or (function_name or "").startswith("_"):
        return
    _qput(stream_q, {
        "type": "tool_complete",
        "id": tool_call_id,
        "tool": function_name,
    })


_AGENCY_SPECIALIST_MARKER_RE = re.compile(
    r"(?:^|\n)AI_LAB_AGENCY_SPECIALIST=([a-z0-9][a-z0-9_-]{0,99})(?:\n|$)",
    re.IGNORECASE,
)


_DELEGATION_ID_FULL_RE = re.compile(r"deleg_[a-zA-Z0-9]{4,64}")


_AGENCY_TOOL_LINE_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2}\s+tool\s+\|\s+->\s+agency_agents_load\(\{"
    r"[^}\n]*['\"]agent['\"]\s*:\s*"
    r"['\"]([a-z0-9][a-z0-9_-]{0,99})['\"]",
    re.IGNORECASE | re.MULTILINE,
)


_AGENCY_RESULT_LINE_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2}\s+result\s+\|\s+agency_agents_load\s+ok\b"
    r"[^\n]*['\"]success['\"]\s*:\s*true"
    r"[^\n]*['\"]slug['\"]\s*:\s*"
    r"['\"]([a-z0-9][a-z0-9_-]{0,99})['\"]",
    re.IGNORECASE | re.MULTILINE,
)


_DELEGATE_STATUSES = frozenset(
    {"completed", "failed", "error", "timeout", "cancelled", "dispatched", "unknown"}
)


def _delegation_transcript_details(
    value: Any,
) -> tuple[str | None, str | None, str | None]:
    """Return bounded (delegation_id, called_slug, successful_slug) evidence."""
    raw = str(value or "").strip()
    if not raw:
        return None, None, None
    home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    root = home / "cache/delegation/live"
    try:
        resolved_root = root.resolve(strict=True)
        path = Path(raw).resolve(strict=True)
        if path.parent.parent != resolved_root or path.name != "task-0.log":
            return None, None, None
        if path.stat().st_size > 1_000_000:
            return None, None, None
    except (OSError, RuntimeError):
        return None, None, None
    delegation_id = path.parent.name
    if _DELEGATION_ID_FULL_RE.fullmatch(delegation_id) is None:
        return None, None, None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None, None
    called_slugs = set(_AGENCY_TOOL_LINE_RE.findall(text))
    successful_slugs = set(_AGENCY_RESULT_LINE_RE.findall(text))
    called_slug = next(iter(called_slugs)) if len(called_slugs) == 1 else None
    effective_slugs = called_slugs & successful_slugs
    successful_slug = next(iter(effective_slugs)) if len(effective_slugs) == 1 else None
    return delegation_id, called_slug, successful_slug


def _verified_delegation_transcript(value: Any) -> tuple[str | None, str | None]:
    """Return only successful effective-load evidence for deferred tool _receipts."""
    delegation_id, _called_slug, successful_slug = _delegation_transcript_details(value)
    return delegation_id, successful_slug


def _emit_delegate_receipt(
    stream_q: queue.Queue,
    function_name: str,
    function_args=None,
    result=None,
) -> None:
    """Emit a sanitized receipt derived from Hermes' terminal child result.

    A dispatch acknowledgement is deliberately not a successful receipt.  No
    goal, child summary, transcript path, or tenant context leaves the bridge.
    """
    if function_name != "delegate_task":
        return
    payload = result
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    args = function_args if isinstance(function_args, dict) else {}
    context = str(args.get("context") or "")
    marker = _AGENCY_SPECIALIST_MARKER_RE.search(context)
    route_target = marker.group(1) if marker else None

    results = payload.get("results")
    child = results[0] if isinstance(results, list) and results else {}
    if not isinstance(child, dict):
        child = {}
    raw_status = str(child.get("status") or payload.get("status") or "unknown")
    summary = str(child.get("summary") or "").strip()
    exit_reason = str(child.get("exit_reason") or "").strip()
    summary_is_failure = summary.lower().startswith(("no reply:", "(empty)"))
    terminal_success = bool(
        raw_status == "completed"
        and exit_reason == "completed"
        and summary
        and not summary_is_failure
    )
    if raw_status == "completed" and not terminal_success:
        # Hermes intentionally labels a non-empty max-iteration response as
        # ``completed``. Agent OS has a stricter contract: only a genuinely
        # completed child with a usable summary may cross the verification
        # gate. This also rejects the SessionDB failure sentinel observed in
        # real concurrent Bridge runs.
        status = "failed"
    else:
        status = raw_status if raw_status in _DELEGATE_STATUSES else "unknown"
    trace = child.get("tool_trace") if isinstance(child.get("tool_trace"), list) else []
    trace_reports_load = any(
        isinstance(item, dict)
        and item.get("tool") == "agency_agents_load"
        and item.get("status") == "ok"
        for item in trace
    )
    payload_id = str(payload.get("delegation_id") or "").strip()
    delegation_id = (
        payload_id if _DELEGATION_ID_FULL_RE.fullmatch(payload_id) is not None else None
    )
    transcript_value = child.get("live_transcript")
    transcript_id, called_slug, successful_slug = _delegation_transcript_details(
        transcript_value
    )
    if not trace_reports_load:
        verified_id, verified_slug = _verified_delegation_transcript(transcript_value)
        transcript_id = verified_id or transcript_id
        successful_slug = verified_slug or successful_slug
    loaded_slug = called_slug if trace_reports_load else successful_slug
    ids_match = not payload_id or payload_id == transcript_id
    if transcript_id is not None:
        delegation_id = transcript_id if ids_match else None
    verification_source = (
        "direct_trace+transcript"
        if trace_reports_load and called_slug
        else "deferred_trace+transcript" if successful_slug else None
    )
    agency_loaded = bool(
        verification_source and route_target and loaded_slug == route_target
    )
    delegated = bool(delegation_id or child)
    verified = bool(
        transcript_id
        and ids_match
        and delegated
        and terminal_success
        and agency_loaded
    )

    _qput(stream_q, {
        "type": "delegate_receipt",
        "delegated": delegated,
        "status": status,
        "route_target": route_target,
        "delegation_id": delegation_id,
        "result_hash": hashlib.sha256(summary.encode()).hexdigest() if verified else None,
        "agency_loaded": agency_loaded,
        "verification_source": verification_source,
        "verifier": "pass" if verified else "fail",
    })


def _tenant_base_toolsets(allowed_tools: set[str]) -> set[str]:
    """Return only tenant-authorized stateful toolsets."""
    requested = {"clarify"}
    requested.update({"memory", "session_search"} & allowed_tools)
    if "tenant_skill_manage" in allowed_tools:
        requested.add("tenant_skills")
    return requested


def _routing_user_goal(goal: str) -> str:
    marker = "【用户问题】"
    if marker in (goal or ""):
        return goal.split(marker, 1)[1].strip()
    return (goal or "").strip()


_EXPLICIT_MEMORY_RE = re.compile(
    r"^\s*(?:以后\s*)?(?:(?:请你?|麻烦你|帮我|你要)\s*)?"
    r"(?:记住|remember(?:\s+that)?)\s*[：:,，\s]*(.+?)\s*[。.!！]?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _explicit_memory_content(goal: str) -> str | None:
    """Return only content behind an explicit remember command."""
    match = _EXPLICIT_MEMORY_RE.fullmatch(_routing_user_goal(goal))
    content = match.group(1).strip() if match else ""
    return content or None


def _save_explicit_user_memory(
    sandbox: TenantHermesSandbox, content: str
) -> tuple[str, bool]:
    """Persist one explicit user memory through the native guarded writer."""
    current = _memory._sandbox_memory_payload(sandbox)
    existing = next(
        (
            item for item in current["items"]
            if item["target"] == "user" and item["content"] == content
        ),
        None,
    )
    if existing is not None:
        return str(existing["id"]), False
    updated = _memory._mutate_sandbox_memory(
        sandbox, action="add", target="user", content=content
    )
    saved = next(
        item for item in updated["items"]
        if item["target"] == "user" and item["content"] == content
    )
    return str(saved["id"]), True


def _memory_tool_succeeded(result: Any) -> bool:
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            return False
    return isinstance(result, dict) and result.get("success") is True


def _legacy_client_context_enabled(
    client_context_enabled: bool, knowledge_action_enabled: bool
) -> bool:
    return client_context_enabled and not knowledge_action_enabled


def _expose_eager_request_tools(agent: Any, toolsets: list[str]) -> None:
    """Expose the small authorized write surface without discovery round trips."""
    from model_tools import get_tool_definitions

    agent.tools = get_tool_definitions(
        enabled_toolsets=toolsets,
        quiet_mode=True,
        skip_tool_search_assembly=True,
    )
    agent.valid_tool_names = {
        item["function"]["name"] for item in agent.tools
    }


from . import contracts as _contracts, memory as _memory, session_runtime as _session_runtime  # noqa: E402
