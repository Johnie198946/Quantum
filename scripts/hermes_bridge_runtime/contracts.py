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


def _routed_skill_catalog(sandbox: TenantHermesSandbox) -> list[dict[str, Any]]:
    """Return PCM metadata projection without ranking or selection."""
    # list_sandbox_skills is already the tenant-authorized runtime projection.
    # Do not enrich it with legacy alias/trigger/bonus routing overrides.
    return list_sandbox_skills(sandbox)


HERMES_BIN = os.environ.get(
    "HERMES_BIN", "/var/lib/quantumn-hermes/.local/bin/hermes"
)


HERMES_CWD = os.environ.get("HERMES_CWD", "/opt/ai-lab-platform")


HERMES_SERVE_URL = os.environ.get("HERMES_SERVE_URL", "http://127.0.0.1:9119")


HERMES_WS_URL = os.environ.get("HERMES_WS_URL", "ws://127.0.0.1:9119/api/pty")


HERMES_SERVE_TOKEN = os.environ.get("HERMES_SERVE_TOKEN", "")


STATE_DB = os.environ.get(
    "HERMES_STATE_DB",
    str(Path.home() / ".hermes" / "state.db")
)


MAPPING_FILE = Path(
    os.environ.get(
        "HERMES_MAPPING_FILE",
        "/opt/ai-lab-platform/data/session_mappings.json",
    )
)


STATE_DB_MAPPING_FILE = Path(
    os.environ.get(
        "HERMES_STATE_DB_MAPPING_FILE",
        "/opt/ai-lab-platform/data/session_state_dbs.json",
    )
)


WATERMARK_FILE = Path(
    os.environ.get(
        "HERMES_WATERMARK_FILE",
        "/opt/ai-lab-platform/data/delivered_watermarks.json",
    )
)


MAX_INPUT = 12000


MAX_DOCUMENT_WORKFLOW_INPUT = 96_000


ALLOWED_CHAT_SKILLS = {"solution-consultant-persona"}


DEFAULT_TIMEOUT = 300


SERVE_TIMEOUT = 300


WORKFLOW_NODE_TIMEOUT = max(
    DEFAULT_TIMEOUT,
    int(os.environ.get("HERMES_WORKFLOW_NODE_TIMEOUT", "900")),
)


WORKFLOW_NODE_MAX_ITERATIONS = max(
    2,
    min(12, int(os.environ.get("HERMES_WORKFLOW_NODE_MAX_ITERATIONS", "6"))),
)


IN_PROCESS_STREAM_ENABLED = os.environ.get("HERMES_IN_PROCESS_STREAM", "false") == "true"


STREAM_KEEPALIVE_SECONDS = float(os.environ.get("HERMES_STREAM_KEEPALIVE", "30"))


STREAM_MAX_DURATION_SECONDS = int(os.environ.get("HERMES_STREAM_MAX_DURATION", "3600"))


WATCHDOG_INTERVAL_SECONDS = float(os.environ.get("HERMES_WATCHDOG_INTERVAL", "10"))


CLARIFY_TIMEOUT_SECONDS = int(os.environ.get("HERMES_CLARIFY_TIMEOUT", "180"))


DRILL_ME_MIN_ROUNDS = max(2, int(os.environ.get("HERMES_DRILL_ME_MIN_ROUNDS", "3")))


DRILL_ME_MAX_ROUNDS = max(
    DRILL_ME_MIN_ROUNDS,
    int(os.environ.get("HERMES_DRILL_ME_MAX_ROUNDS", "5")),
)


STREAM_QUEUE_CAPACITY = 0


HERMES_CHAT_RUN_DB = Path(
    os.environ.get(
        "HERMES_CHAT_RUN_DB",
        "/opt/ai-lab-platform/data/hermes_chat_runs.sqlite3",
    )
)


DURABLE_CHAT_WORKER_ENABLED = os.environ.get("HERMES_DURABLE_CHAT_WORKER", "false") == "true"


DURABLE_WORKER_HEARTBEAT_MAX_AGE = max(
    1.0, float(os.environ.get("HERMES_CHAT_WORKER_HEARTBEAT_MAX_AGE", "5"))
)


_BRIDGE_PREWARM_EPOCH = uuid.uuid4().hex[:12]


_WORKER_MAINTENANCE = {
    "code": "execution_worker_unavailable",
    "message": "Durable chat execution is temporarily unavailable for maintenance.",
    "recoverable": True,
}


def _durable_worker_is_live() -> bool:
    try:
        return bool(
            _session_runtime._chat_run_store is not None
            and _session_runtime._chat_run_store.worker_is_live(
                max_age_seconds=DURABLE_WORKER_HEARTBEAT_MAX_AGE
            )
        )
    except (OSError, sqlite3.Error):
        return False


def _require_durable_worker() -> None:
    if not _durable_worker_is_live():
        raise HTTPException(
            status_code=503,
            detail=_WORKER_MAINTENANCE,
            headers={"Retry-After": str(int(DURABLE_WORKER_HEARTBEAT_MAX_AGE))},
        )


WORKFLOW_RUNS_FILE = Path(
    os.environ.get(
        "HERMES_WORKFLOW_RUNS_FILE",
        "/opt/ai-lab-platform/data/hermes_workflow_runs.json",
    )
)


WORKFLOW_PLANNING_RUNS_FILE = Path(
    os.environ.get(
        "HERMES_WORKFLOW_PLANNING_RUNS_FILE",
        "/opt/ai-lab-platform/data/hermes_workflow_planning_runs.json",
    )
)


AGENT_EVALUATION_RUNS_FILE = Path(
    os.environ.get(
        "HERMES_AGENT_EVALUATION_RUNS_FILE",
        "/opt/ai-lab-platform/data/hermes_agent_evaluation_runs.json",
    )
)


HERMES_BRIDGE_INTERNAL_TOKEN = os.environ.get("HERMES_BRIDGE_INTERNAL_TOKEN", "")


KNOWLEDGE_GATEWAY_URL = os.environ.get(
    "KNOWLEDGE_GATEWAY_URL", "http://127.0.0.1:8000/api/internal/knowledge/search"
)


_workflow_runs_lock = threading.RLock()


_workflow_threads: dict[str, threading.Thread] = {}


_workflow_agents: dict[str, Any] = {}


_planning_runs_lock = threading.RLock()


_planning_threads: dict[str, threading.Thread] = {}


_evaluation_runs_lock = threading.RLock()


_evaluation_threads: dict[str, threading.Thread] = {}


_stream_runs: dict[str, dict] = {}


_stream_runs_guard = threading.Lock()


_clarify_gateway = None


_resolved_clarifies: dict[str, dict[str, Any]] = {}


_resolved_clarifies_guard = threading.Lock()


CLARIFY_REPLAY_TTL_SECONDS = max(
    CLARIFY_TIMEOUT_SECONDS + 60,
    int(os.environ.get("HERMES_CLARIFY_REPLAY_TTL", "600")),
)


def _clarify_response_fingerprint(response: str) -> str:
    return hashlib.sha256(response.encode("utf-8")).hexdigest()


def _remember_resolved_clarify(clarify_id: str, response: str, session_id: str) -> None:
    now = time.monotonic()
    with _resolved_clarifies_guard:
        expired = [
            cid for cid, value in _resolved_clarifies.items()
            if now - float(value.get("resolved_at") or 0) > CLARIFY_REPLAY_TTL_SECONDS
        ]
        for cid in expired:
            _resolved_clarifies.pop(cid, None)
        _resolved_clarifies[clarify_id] = {
            "fingerprint": _clarify_response_fingerprint(response),
            "session_id": session_id,
            "resolved_at": now,
        }


def _resolved_clarify_state(clarify_id: str, response: str, session_id: str) -> str | None:
    now = time.monotonic()
    with _resolved_clarifies_guard:
        value = _resolved_clarifies.get(clarify_id)
        if value is None:
            return None
        if now - float(value.get("resolved_at") or 0) > CLARIFY_REPLAY_TTL_SECONDS:
            _resolved_clarifies.pop(clarify_id, None)
            return None
        if value.get("session_id") != session_id:
            return "stale"
        if value.get("fingerprint") == _clarify_response_fingerprint(response):
            return "replayed"
        return "stale"


def _get_clarify_gateway():
    """返回 clarify_gateway 模块（懒加载 + 缓存）。"""
    global _clarify_gateway
    if _clarify_gateway is None:
        from tools import clarify_gateway
        _clarify_gateway = clarify_gateway
    return _clarify_gateway


ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


MAX_CONCURRENT_REQUESTS = max(int(os.environ.get("HERMES_MAX_CONCURRENCY", "2")), 1)


MAX_QUEUED_REQUESTS = max(int(os.environ.get("HERMES_MAX_QUEUE", "8")), 0)


QUEUE_TIMEOUT_SECONDS = max(float(os.environ.get("HERMES_QUEUE_TIMEOUT_SECONDS", "30")), 0.1)


_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


_queued_requests = 0


_clarification_rate_lock = threading.Lock()


_clarification_last_run: dict[str, float] = {}


CLARIFICATION_MIN_INTERVAL_SECONDS = 2.0


_mapping_lock = threading.Lock()


_watermark_lock = threading.Lock()


_user_locks: dict[str, asyncio.Lock] = {}


_user_lock_timestamps: dict[str, float] = {}


USER_LOCK_CAPACITY = 512


USER_LOCK_TTL_SECONDS = 30 * 60


ANONYMOUS_LOCK_KEY = "_anonymous"


_in_flight_users: dict[str, float] = {}


IN_FLIGHT_STALE_SECONDS = 300


@asynccontextmanager
async def _admit_request():
    """Bound concurrency and queue depth; callers can retry a saturated shard."""
    global _queued_requests
    queued = _semaphore.locked()
    if queued:
        if _queued_requests >= MAX_QUEUED_REQUESTS:
            raise HTTPException(
                status_code=503,
                detail="runtime_capacity_exceeded",
                headers={"Retry-After": "2"},
            )
        _queued_requests += 1
    try:
        try:
            await asyncio.wait_for(_semaphore.acquire(), timeout=QUEUE_TIMEOUT_SECONDS)
        except TimeoutError as error:
            raise HTTPException(
                status_code=503,
                detail="runtime_queue_timeout",
                headers={"Retry-After": "2"},
            ) from error
        try:
            yield
        finally:
            _semaphore.release()
    finally:
        if queued:
            _queued_requests -= 1


def _mark_in_flight(user_id: str) -> None:
    """登记 user 在途任务开始时间戳（进程内瞬时状态，finally 移除）。"""
    _in_flight_users[user_id] = time.time()


def _clear_in_flight(user_id: str) -> None:
    """移除 user 在途标记（任务结束/异常 finally 块调用）。"""
    _in_flight_users.pop(user_id, None)


def _is_in_flight(user_id: str | None) -> bool:
    """判定 user 是否有在途任务且未超时（首秒 running 兜底依据）。"""
    if not user_id:
        return False
    ts = _in_flight_users.get(user_id)
    if ts is None:
        return False
    return (time.time() - ts) <= IN_FLIGHT_STALE_SECONDS


def _get_user_lock(user_id: str) -> asyncio.Lock:
    """按 user_id 取细粒度锁；anonymous 统一固定 `_anonymous` key。

    LRU 512 上限 + 30 分钟空闲 TTL 惰性清理，杜绝锁对象无限堆积内存泄漏。
    """
    lock_key = user_id if user_id and user_id != "anonymous" else ANONYMOUS_LOCK_KEY
    now = time.monotonic()

    # 空闲 TTL 惰性清理
    stale = [
        k for k, ts in _user_lock_timestamps.items()
        if now - ts > USER_LOCK_TTL_SECONDS
    ]
    for k in stale:
        _user_locks.pop(k, None)
        _user_lock_timestamps.pop(k, None)

    lock = _user_locks.get(lock_key)
    if lock is None:
        # LRU 淘汰最久未使用
        if len(_user_locks) >= USER_LOCK_CAPACITY:
            oldest = min(_user_lock_timestamps.items(), key=lambda kv: kv[1])[0]
            _user_locks.pop(oldest, None)
            _user_lock_timestamps.pop(oldest, None)
        lock = asyncio.Lock()
        _user_locks[lock_key] = lock
    _user_lock_timestamps[lock_key] = now
    return lock


class AgentDelegationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_concurrent_children: int = Field(..., ge=0, le=3)
    max_spawn_depth: int = Field(..., ge=0, le=1)


class AgentTriageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(..., min_length=1, max_length=40)
    route_class: Literal["CASUAL", "GENERAL_QA", "PROFESSIONAL_TASK"]
    confidence: float = Field(..., ge=0, le=1)
    reason_code: str = Field(..., min_length=1, max_length=100)
    evidence_requirements: list[str] = Field(default_factory=list, max_length=8)
    agency_enabled: bool = False
    skill_enabled: bool = False

    @field_validator("evidence_requirements")
    @classmethod
    def _bounded_evidence_requirements(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 100 for value in values):
            raise ValueError("invalid evidence requirement")
        return values


class AgentCompositionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_surface: Literal["agency"] | None = None


class TrustedAgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(None, min_length=1, max_length=100)
    base_agent_id: str | None = Field(None, min_length=1, max_length=100)
    name: str | None = Field(None, max_length=200)
    prompt: str | None = Field(None, max_length=12000)
    allowed_tools: list[str] = Field(default_factory=list, max_length=32)
    capability_agent_ids: list[str] = Field(default_factory=list, max_length=16)
    knowledge_scope: list[str] = Field(default_factory=list, max_length=32)
    allow_network: bool | None = None
    delegation: AgentDelegationConfig | None = None
    triage: AgentTriageConfig | None = None
    composition: AgentCompositionConfig | None = None
    knowledge_stage_only: bool | None = None
    inference_policy: dict[str, Any] | None = None
    runtime_placement: dict[str, Any] | None = None

    @field_validator("allowed_tools", "capability_agent_ids", "knowledge_scope")
    @classmethod
    def _bounded_string_list(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 200 for value in values):
            raise ValueError("invalid agent configuration list")
        return values

    @field_validator("allowed_tools")
    @classmethod
    def _server_authorized_tools(cls, values: list[str]) -> list[str]:
        if any(value not in SAFE_GLOBAL_TOOLS for value in values):
            raise ValueError("unsupported agent tool")
        return values


class GoalRequest(BaseModel):
    # V2 权限只能来自平台签发的 KnowledgeCapability。旧客户端继续发送
    # pure/standard/kb 时必须显式失败，不能静默忽略后造成“看似隔离”的假象。
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., max_length=262_144)
    request_id: str | None = Field(None, min_length=8, max_length=100)
    session_id: str | None = None  # 前端传入的 user_id（用于映射 Hermes 原生 session）
    client_session_id: str | None = Field(None, min_length=1, max_length=100)
    skill_id: str | None = Field(None, max_length=80)
    # 重新生成语义（2026-08-17 修复）：true 时作废旧 run（interrupt 旧 agent + discard 注册）
    # 再启动全新尝试——对齐 ChatGPT「重新生成」= 上次回答作废重跑，而非被并发防护拒绝
    regenerate: bool = Field(False, description="重新生成：作废旧 run 后全新执行")
    knowledge_capability: str | None = None
    knowledge_policy_version: str | None = None
    # Raw user question, separate from the augmented goal.  This is the only
    # text used for the request-scoped Wiki lookup.
    knowledge_query: str | None = Field(None, max_length=200)
    agent_config: dict[str, Any] = Field(default_factory=dict)
    client_session_context: dict[str, Any] | None = None
    client_context_capability: str | None = None
    qws_business_context: dict[str, Any] | None = None
    qws_context_capability: str | None = None
    client_capabilities: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _long_goal_requires_selected_book(self):
        if len(self.goal) > MAX_INPUT:
            if not self.knowledge_capability or not verify_capability(self.knowledge_capability).get("book_scope"):
                raise ValueError("long chat context requires signed selected book")
        return self

    @field_validator("agent_config")
    @classmethod
    def _trusted_agent_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        return TrustedAgentConfig.model_validate(value).model_dump(exclude_none=True)


class WorkflowPlanRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    workflow_id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=160)
    description: str = Field(..., min_length=3, max_length=12000)
    deliverable: str = Field(..., min_length=1, max_length=300)
    knowledge_scope: list[str] = Field(default_factory=list)
    allowed_agents: list[str] = Field(default_factory=list)
    allow_network: bool = True
    max_tokens: int = Field(999999, ge=1000, le=999999)
    revision_note: str = Field("", max_length=2000)


class WorkflowPlanningStartRequest(WorkflowPlanRequest):
    planning_job_id: str = Field(..., min_length=8, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=160)


class WorkflowRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1, max_length=64)
    execution_id: str = Field(..., min_length=1, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=160)
    command_id: str | None = Field(None, min_length=8, max_length=160)
    execution_request_id: str | None = Field(None, min_length=8, max_length=160)
    process_contract_digest: str | None = Field(None, min_length=64, max_length=64)
    dependency_lock_digest: str | None = Field(None, min_length=64, max_length=64)
    activation_revision: int | None = Field(None, ge=1)
    goal: str = Field(..., min_length=1, max_length=12000)
    deliverable: str = Field(..., min_length=1, max_length=300)
    plan: dict[str, Any]
    allow_network: bool = True
    knowledge_scope: list[str] = Field(default_factory=list)
    max_tokens: int = Field(999999, ge=1000, le=999999)
    knowledge_capability: str = Field(..., min_length=20)
    knowledge_policy_version: str = Field(..., min_length=8, max_length=80)
    agent_config: dict[str, Any] = Field(default_factory=dict)
    source_document: dict[str, Any] | None = None

    @field_validator("agent_config")
    @classmethod
    def _trusted_agent_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        return TrustedAgentConfig.model_validate(value).model_dump(exclude_none=True)

    @field_validator("source_document")
    @classmethod
    def _trusted_source_document(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        allowed = {"source_id", "source_revision", "content_hash", "filename", "content_type", "text"}
        if set(value) - allowed or not re.fullmatch(r"doc_[a-f0-9]{32}", str(value.get("source_id") or "")) or not re.fullmatch(r"[a-f0-9]{64}", str(value.get("content_hash") or "")):
            raise ValueError("invalid private source document")
        text = str(value.get("text") or "")
        if not text or len(text) > 80_000:
            raise ValueError("private source document text exceeds 80000 characters; truncation is forbidden")
        return {key: value[key] for key in allowed if key in value}


class ClarificationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=4000)


class ClarificationBridgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1, max_length=64)
    workflow_id: str = Field(..., min_length=1, max_length=64)
    goal: str = Field(..., min_length=3, max_length=12000)
    transcript: list[ClarificationTurn] = Field(default_factory=list, max_length=12)


class ClarificationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["question", "READY"]
    question: str | None = Field(None, max_length=500)
    dimension: str | None = Field(None, max_length=80)


class WorkflowRetryRequest(BaseModel):
    from_node_id: str | None = Field(None, max_length=80)
    revision_comment: str | None = Field(None, max_length=2000)


class WorkflowGateApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1, max_length=80)
    artifact_version: int = Field(..., ge=1)
    artifact_id: str = Field(..., pattern=r"^wfa_[a-f0-9]{32}$")
    expected_hash: str = Field(..., pattern=r"^[a-f0-9]{64}$")


class AgentEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., min_length=8, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=160)
    agent_config: dict[str, Any]
    suite: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_capability: str = Field(..., min_length=20)
    knowledge_policy_version: str = Field(..., min_length=8, max_length=80)

    @field_validator("agent_config")
    @classmethod
    def _trusted_agent_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        return TrustedAgentConfig.model_validate(value).model_dump(exclude_none=True)


def _expand_requested_skill(
    goal: str,
    skill_id: str | None,
    sandbox: TenantHermesSandbox,
) -> str:
    """Load an explicit Skill only from the authenticated tenant sandbox."""
    if not skill_id:
        return goal
    if skill_id not in ALLOWED_CHAT_SKILLS:
        raise HTTPException(status_code=400, detail=f"unsupported skill: {skill_id}")
    instructions = read_sandbox_skill(sandbox, skill_id)
    if not instructions:
        raise HTTPException(status_code=503, detail=f"skill not installed: {skill_id}")
    return (
        "【已从当前租户 Hermes 沙箱加载 Skill；只遵循以下副本】\n"
        + instructions
        + "\n\n【用户请求】\n"
        + goal
    )


from . import session_runtime as _session_runtime  # noqa: E402


def _verify_workflow_skill_binding(
    binding: dict[str, Any], sandbox: TenantHermesSandbox
) -> dict[str, str]:
    """Verify frozen Skill bytes from the authenticated tenant sandbox."""
    skill_id = str(binding.get("skill_id") or "")
    expected = str(binding.get("sha256") or "")
    if not skill_id or len(expected) != 64:
        raise ValueError("invalid workflow Skill binding")
    command_key = f"/{skill_id.replace('_', '-')}"
    skill_text = read_sandbox_skill(sandbox, skill_id, max_chars=1_000_000)
    if not skill_text:
        raise ValueError(f"workflow Skill not installed: {skill_id}")
    actual = hashlib.sha256(skill_text.encode("utf-8")).hexdigest()
    if actual != expected:
        raise ValueError(f"workflow Skill hash mismatch: {skill_id}")
    return {"skill_id": skill_id, "sha256": actual, "command_key": command_key}


def _expand_workflow_skill(
    goal: str, receipt: dict[str, str], sandbox: TenantHermesSandbox
) -> str:
    skill_id = receipt["skill_id"]
    instructions = read_sandbox_skill(sandbox, skill_id, max_chars=80_000)
    if not instructions:
        raise ValueError(f"workflow Skill not installed: {skill_id}")
    return (
        "【当前租户 Hermes 沙箱 Skill（已校验摘要）】\n"
        + instructions
        + "\n\n【工作流节点任务】\n"
        + goal
    )


def _run_bridge_coroutine(coro, *, timeout: float):
    """Run DB-backed bridge work on the process-owned asyncio loop."""
    loop = _bridge_async_loop
    if loop is None or loop.is_closed():
        return asyncio.run(coro)
    if loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            raise
    lock = _bridge_async_loop_lock
    if lock is None:
        return loop.run_until_complete(coro)
    with lock:
        return loop.run_until_complete(coro)


_bridge_async_loop: asyncio.AbstractEventLoop | None = None
_bridge_async_loop_lock: Any = None
CAPABILITY_DISPATCH_TIMEOUT_SECONDS = 30
