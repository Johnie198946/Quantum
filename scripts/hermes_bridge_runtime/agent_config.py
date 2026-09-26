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
from . import contracts as _contracts


_CACHED_CFG = None


_CACHED_CFG_LOCK = threading.Lock()


_CACHED_TOOLS = None


_CACHED_RUNTIME = None


_CACHED_FALLBACK = None


_AGENT_CACHE_MAX_SIZE = max(0, int(os.environ.get("HERMES_CHAT_AGENT_CACHE_SIZE", "32")))


_AGENT_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()


_AGENT_CACHE_LOCK = threading.Lock()


def _close_agent_resources(agent: Any, session_db: Any) -> None:
    try:
        if agent is not None:
            agent.close()
    except Exception:
        pass
    try:
        if session_db is not None:
            session_db.close()
    except Exception:
        pass


def _agent_cache_signature(
    *, model: str, runtime: dict[str, Any], toolsets: list[str], prompt: str,
    fallback: Any, request_overrides: dict[str, Any] | None, service_tier: str,
    sandbox: "TenantHermesSandbox",
) -> str:
    payload = {
        "model": model,
        "provider": runtime.get("provider"),
        "base_url": runtime.get("base_url"),
        "api_mode": runtime.get("api_mode"),
        "toolsets": toolsets,
        "prompt": prompt,
        "fallback": fallback,
        "request_overrides": request_overrides,
        "service_tier": service_tier,
        "sandbox_root": str(sandbox.root),
        "state_db": str(sandbox.state_db),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def _take_cached_agent(
    cache_key: str, signature: str, hermes_sid: str | None,
) -> tuple[Any, Any, str] | None:
    stale: tuple[Any, Any] | None = None
    with _AGENT_CACHE_LOCK:
        entry = _AGENT_CACHE.get(cache_key)
        if entry is None or entry["in_use"]:
            return None
        agent = entry["agent"]
        session_db = entry["session_db"]
        cached_sid = str(getattr(agent, "session_id", "") or "")
        if entry["signature"] != signature or cached_sid != str(hermes_sid or ""):
            _AGENT_CACHE.pop(cache_key, None)
            stale = (agent, session_db)
        else:
            try:
                current_count = session_db.message_count(cached_sid)
            except Exception:
                current_count = None
            if current_count != entry["message_count"]:
                _AGENT_CACHE.pop(cache_key, None)
                stale = (agent, session_db)
            else:
                entry["in_use"] = True
                _AGENT_CACHE.move_to_end(cache_key)
                try:
                    from agent.session_activity import ActivityProvenance

                    agent._last_activity_ts = time.time()
                    agent._last_activity_desc = "starting new turn (cached)"
                    agent._last_activity_provenance = ActivityProvenance.UNKNOWN
                except Exception:
                    pass
                agent._api_call_count = 0
                if hasattr(agent, "_last_flushed_db_idx"):
                    agent._last_flushed_db_idx = 0
                return agent, session_db, str(entry.get("cache_origin") or "prior_turn")
    if stale is not None:
        _close_agent_resources(*stale)
    return None


def _finish_cached_agent(
    cache_key: str, signature: str, agent: Any, session_db: Any, *, keep: bool,
    cache_origin: str = "prior_turn",
) -> bool:
    if not keep or _AGENT_CACHE_MAX_SIZE == 0:
        with _AGENT_CACHE_LOCK:
            entry = _AGENT_CACHE.get(cache_key)
            if entry is not None and entry["agent"] is agent:
                _AGENT_CACHE.pop(cache_key, None)
        _close_agent_resources(agent, session_db)
        return False

    try:
        message_count = session_db.message_count(str(getattr(agent, "session_id", "") or ""))
    except Exception:
        _close_agent_resources(agent, session_db)
        return False

    evicted: list[tuple[Any, Any]] = []
    retained = False
    with _AGENT_CACHE_LOCK:
        current = _AGENT_CACHE.get(cache_key)
        if current is None or current["agent"] is agent or not current["in_use"]:
            if current is not None and current["agent"] is not agent:
                evicted.append((current["agent"], current["session_db"]))
            _AGENT_CACHE[cache_key] = {
                "agent": agent,
                "session_db": session_db,
                "signature": signature,
                "message_count": message_count,
                "in_use": False,
                "cache_origin": cache_origin,
            }
            _AGENT_CACHE.move_to_end(cache_key)
            retained = True
            while len(_AGENT_CACHE) > _AGENT_CACHE_MAX_SIZE:
                victim_key = next(
                    (key for key, value in _AGENT_CACHE.items() if not value["in_use"]),
                    None,
                )
                if victim_key is None:
                    break
                victim = _AGENT_CACHE.pop(victim_key)
                evicted.append((victim["agent"], victim["session_db"]))
    if not retained:
        evicted.append((agent, session_db))
    for victim in evicted:
        _close_agent_resources(*victim)
    return retained


def _prewarm_session_agent(
    user_id: str,
    agent_config: dict[str, Any],
    sandbox: "TenantHermesSandbox",
    *,
    knowledge_action_enabled: bool = False,
    qcp_enabled: bool = False,
) -> tuple[str, bool]:
    """Build the ordinary fast-lane agent without spending a model turn."""
    hermes_sid = _session_runtime._resolve_hermes_session(user_id)
    if not hermes_sid:
        session_db = _create_sandbox_session_db(sandbox)
        try:
            hermes_sid = f"prewarm_{uuid.uuid4().hex}"
            session_db.create_session(hermes_sid, source="cli")
        finally:
            session_db.close()
        _session_runtime._update_session_mapping(user_id, hermes_sid, sandbox.state_db)

    from hermes_constants import (
        reset_hermes_home_override,
        set_hermes_home_override,
    )

    hermes_home_token = set_hermes_home_override(_memory._sandbox_hermes_home(sandbox))
    agent = session_db = None
    try:
        agent, session_db, route = _agent_execution._build_in_process_agent(
            "解释一个常见概念",
            user_id,
            hermes_sid,
            queue.Queue(),
            agent_config=agent_config,
            client_context_enabled=False,
            knowledge_action_enabled=knowledge_action_enabled,
            qcp_enabled=qcp_enabled,
            sandbox=sandbox,
        )
        source = str(route.get("agent_cache_source") or "cold_build")
        retained = _finish_cached_agent(
            str(route["agent_cache_key"]),
            str(route["agent_cache_signature"]),
            agent,
            session_db,
            keep=True,
            cache_origin="prewarm" if source == "cold_build" else source,
        )
        agent = session_db = None
        return hermes_sid, retained
    finally:
        _knowledge._sandbox_tool_context.value = None
        _knowledge._skill_route_context.value = None
        _close_agent_resources(agent, session_db)
        reset_hermes_home_override(hermes_home_token)


def _get_cached_config() -> dict:
    """常驻 Config 单例：首次加载后内存复用（0ms 读盘）。"""
    global _CACHED_CFG
    if _CACHED_CFG is None:
        with _CACHED_CFG_LOCK:
            if _CACHED_CFG is None:
                from hermes_cli.config import load_config
                _CACHED_CFG = load_config()
    return _CACHED_CFG


def _get_cached_runtime(cfg: dict) -> dict:
    """常驻 Runtime Provider 单例（0ms 解析）。"""
    global _CACHED_RUNTIME
    if _CACHED_RUNTIME is None:
        with _CACHED_CFG_LOCK:
            if _CACHED_RUNTIME is None:
                from hermes_cli.runtime_provider import resolve_runtime_provider
                model_cfg = cfg.get("model") or {}
                m = model_cfg if isinstance(model_cfg, str) else (model_cfg.get("default") or model_cfg.get("model") or "")
                _CACHED_RUNTIME = resolve_runtime_provider(requested=None, target_model=m or None)
    return _CACHED_RUNTIME


def _get_cached_tools(cfg: dict) -> list:
    """常驻 Tools 元数据单例（0ms 反射扫描）。"""
    global _CACHED_TOOLS
    if _CACHED_TOOLS is None:
        with _CACHED_CFG_LOCK:
            if _CACHED_TOOLS is None:
                from hermes_cli.tools_config import _get_platform_tools
                _CACHED_TOOLS = sorted(_get_platform_tools(cfg, "cli"))
    return _CACHED_TOOLS


def _get_cached_fallback(cfg: dict):
    """常驻 Fallback 链单例。"""
    global _CACHED_FALLBACK
    if _CACHED_FALLBACK is None:
        with _CACHED_CFG_LOCK:
            if _CACHED_FALLBACK is None:
                from hermes_cli.fallback_config import get_fallback_chain
                _CACHED_FALLBACK = get_fallback_chain(cfg)
    return _CACHED_FALLBACK


def _resolve_base_toolsets(cfg: dict, *, allow_local_files: bool) -> list[str]:
    """Build a stable base from explicit local authority, never goal keywords."""
    platform_tools = set(_get_cached_tools(cfg))
    # Keep the prompt surface small and byte-stable. Request-level authorization
    # adds network, tenant, knowledge, and Agency toolsets below.
    # Delegation is part of the normal Hermes reasoning loop, not only a coding
    # task.  Omitting it here made ``delegate_task`` impossible even when the
    # server-owned agent capability explicitly allowed it.
    core_tools = {"clarify"}
    if allow_local_files:
        core_tools.update({"file", "terminal"})
    return sorted(list(core_tools & platform_tools))


def _include_available_toolsets(
    selected: list[str],
    platform_tools: set[str],
    requested: set[str],
) -> list[str]:
    """Add explicitly requested plugin toolsets after lightweight selection."""
    result = list(selected)
    for toolset in sorted(requested & platform_tools):
        if toolset not in result:
            result.append(toolset)
    return result


def _request_triage(agent_config: dict[str, Any]) -> dict[str, Any] | None:
    triage = agent_config.get("triage")
    if not isinstance(triage, dict):
        return None
    route_class = str(triage.get("route_class") or "")
    if route_class not in {CASUAL, GENERAL_QA, PROFESSIONAL_TASK}:
        return None
    evidence = triage.get("evidence_requirements") or []
    if not isinstance(evidence, (list, tuple)):
        evidence = []
    try:
        confidence = float(triage.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "route_class": route_class,
        "confidence": confidence,
        "reason_code": str(triage.get("reason_code") or "unspecified")[:80],
        "evidence_requirements": [str(item) for item in evidence][:8],
        "agency_enabled": bool(triage.get("agency_enabled")),
        "skill_enabled": bool(triage.get("skill_enabled")),
    }


def _request_inference_policy(agent_config: dict[str, Any]) -> dict[str, Any] | None:
    policy = agent_config.get("inference_policy")
    if policy is None:
        return None
    if not isinstance(policy, dict) or policy.get("policy_version") != "inference-v1":
        raise RuntimeError("invalid_inference_policy")
    tier = str(policy.get("tier") or "")
    ceilings = {"fast": 1_200, "balanced": 4_000, "reasoning": 12_000}
    if tier not in ceilings:
        raise RuntimeError("invalid_inference_tier")
    try:
        max_output = int(policy.get("max_output_tokens") or 0)
    except (TypeError, ValueError) as error:
        raise RuntimeError("invalid_inference_budget") from error
    if not 1 <= max_output <= ceilings[tier]:
        raise RuntimeError("invalid_inference_budget")
    allow_subagents = bool(policy.get("allow_subagents")) and tier == "reasoning"
    return {
        "tier": tier,
        "policy_version": "inference-v1",
        "max_output_tokens": max_output,
        "allow_subagents": allow_subagents,
    }


def _request_runtime_placement(agent_config: dict[str, Any]) -> dict[str, Any] | None:
    placement = agent_config.get("runtime_placement")
    if placement is None:
        return None
    if not isinstance(placement, dict):
        raise RuntimeError("invalid_runtime_placement")
    shard_id = str(placement.get("shard_id") or "")
    local_shard = os.environ.get("QUANTUM_RUNTIME_SHARD_ID", "shard-1").strip()
    try:
        generation = int(placement.get("generation") or 0)
    except (TypeError, ValueError) as error:
        raise RuntimeError("invalid_runtime_generation") from error
    if shard_id != local_shard:
        raise RuntimeError("runtime_shard_mismatch")
    if generation < 1:
        raise RuntimeError("invalid_runtime_generation")
    return {"shard_id": shard_id, "generation": generation}


def _triage_route_marker(triage: dict[str, Any] | None) -> str:
    """Legacy compatibility: triage no longer controls Skill/Agent routing."""
    del triage
    return ""


def _triage_system_directive(
    triage: dict[str, Any] | None,
) -> str:
    if triage is None:
        return ""
    evidence = set(triage.get("evidence_requirements") or [])
    lines = ["\n服务端证据需求（不参与 Skill/Agent 选择，也不授予权限）："]

    if "web_extract" in evidence:
        lines.append(
            "用户指定了 URL：回答前必须先调用 web_extract 读取原文。若返回结果已包含可识别的"
            "文章标题、作者/发布者和连续正文，必须将其视为成功提取并直接据此回答；页面尾部的"
            "微信扫码、点赞、分享等 UI 杂项不构成提取失败，禁止在已有正文时声称文章身份或内容"
            "无法确认。"
        )
    if "web_search" in evidence:
        lines.append("该请求需要公开证据：必须调用 web_search；涉及 URL 时在 extract 后扩展。")
    if "knowledge_search" in evidence:
        lines.append("可按需使用已授权的知识检索工具补充内部证据；不得把检索作为回答前置条件。")
    if "user_note_search" in evidence:
        lines.append(
            "用户可能在查询自己的笔记：可按需调用 user_note_search；未检索时直接基于"
            "现有上下文回答，不得伪造命中。"
        )
    if "web_extract" in evidence:
        lines.append(
            "若 URL 是微信文章，只有 web_extract 明确报错、正文为空，或结果主体仅为“环境异常/"
            "访问过于频繁/完成验证”等拦截文案且没有连续文章正文时，才改用 browser_navigate 后"
            "读取页面快照；仍失败再用 web_search 补证。公开搜索结果若与目标文章标题、发布者不"
            "一致，必须丢弃，禁止用无关页面覆盖已经成功提取的微信正文。"
        )
    return "\n".join(lines)


def _knowledge_tools_eligible(triage: dict[str, Any] | None) -> bool:
    """Knowledge need is Hermes-owned, independent of expert task complexity.

    This only retains already-authorized Gateway tools; it grants neither
    document access nor a mandatory search for translation or casual turns.
    """
    return triage is None or (
        triage.get("route_class") != CASUAL
        and triage.get("reason_code") not in {"direct_response", "empty_or_ambiguous"}
    )


def _knowledge_public_fallback_allowed(goal: str, agent_config: dict, triage: dict | None) -> bool:
    """Retain an existing web grant for Wiki gaps, never create network authority."""
    if not agent_config.get("allow_network") or "web_search" not in set(agent_config.get("allowed_tools") or []):
        return False
    if not _knowledge_tools_eligible(triage):
        return False
    if "user_note_search" in set((triage or {}).get("evidence_requirements") or []):
        return False
    return not re.search(
        r"离线|不要联网|禁止联网|不联网|仅内部|只[看用查].{0,8}(?:笔记|内部|知识库)|"
        r"offline|no (?:web|network|internet)|do not (?:browse|search)|only.{0,20}(?:notes|internal)",
        _receipts._routing_user_goal(goal), re.I,
    )


def _apply_triage_toolset_policy(
    selected: list[str],
    triage: dict[str, Any] | None,
    *,
    public_knowledge_fallback: bool = False,
) -> list[str]:
    """Apply evidence-source boundaries without filtering Skill/Agent tools."""
    evidence = set((triage or {}).get("evidence_requirements") or [])
    denied: set[str] = set()
    if not evidence & {"web_search", "web_extract"} and not public_knowledge_fallback:
        denied.add("web")
    if "user_note_search" not in evidence:
        denied.add("user_notes_gateway")
    return [item for item in selected if item not in denied]


def _hermes_session_for_request(
    user_id: str, client_session_context: dict[str, Any] | None
) -> str | None:
    """Always resolve the mapped Hermes session for this logical conversation.

    Signed client context is auxiliary migration/recovery or local-note data. It
    must never replace Hermes SessionDB or force an otherwise resumable turn into
    a fresh session.
    """
    return _session_runtime._resolve_hermes_session(user_id)


def _prewarm_bridge_agent() -> threading.Thread:
    """Start prewarm and return its thread so durable workers may gate queue claims."""
    def _warmup_worker():
        try:
            t0 = time.monotonic()
            cfg = _get_cached_config()
            _get_cached_runtime(cfg)
            _get_cached_tools(cfg)
            _get_cached_fallback(cfg)
            _contracts._get_clarify_gateway()
            _get_shared_session_db()  # 预热 160MB state.db 的 SessionDB 冷建（6.6s 挪到启动期）
            from run_agent import AIAgent
            runtime = _get_cached_runtime(cfg)
            model_cfg = cfg.get("model") or {}
            model = (
                model_cfg if isinstance(model_cfg, str)
                else model_cfg.get("default") or model_cfg.get("model") or ""
            )
            # 预热极简 AIAgent 实例以触发底层 httpx/openai/pydantic 模块编译与单例常驻
            warm_agent = AIAgent(
                api_key=runtime.get("api_key"),
                base_url=runtime.get("base_url"),
                provider=runtime.get("provider"),
                api_mode=runtime.get("api_mode"),
                model=model,
                quiet_mode=True,
                platform="cli",
                ephemeral_system_prompt="warmup",
                **_memory._isolated_agent_context_kwargs(),
            )
            warm_agent.close()
            print(f"[bridge] 实例池预热完成 · 耗时 {(time.monotonic() - t0)*1000:.1f}ms")
        except Exception as e:
            print(f"[bridge] 实例预热失败·忽略: {e}")

    thread = threading.Thread(target=_warmup_worker, daemon=True, name="bridge-prewarm")
    thread.start()
    return thread


def _create_thread_local_session_db():
    """线程局部 SessionDB（避免 SQLite 跨线程冲突）：轻量创建 <0.2ms。"""
    from hermes_cli.oneshot import _create_session_db_for_oneshot
    return _create_session_db_for_oneshot()


def _create_sandbox_session_db(sandbox: TenantHermesSandbox):
    """Open one request-local connection to the current tenant/user database."""
    try:
        from hermes_state import SessionDB

        return SessionDB(db_path=sandbox.state_db)
    except Exception as exc:
        raise RuntimeError("tenant_session_db_unavailable") from exc


_SHARED_SESSION_DB = None


_SHARED_SESSION_DB_LOCK = threading.Lock()


def _get_shared_session_db():
    """常驻 SessionDB 单例：首次懒加载（预热线程提前完成），后续 0ms 复用。"""
    global _SHARED_SESSION_DB
    if _SHARED_SESSION_DB is None:
        with _SHARED_SESSION_DB_LOCK:
            if _SHARED_SESSION_DB is None:
                _SHARED_SESSION_DB = _create_thread_local_session_db()
    return _SHARED_SESSION_DB


def _supports_reasoning_effort(model: str) -> bool:
    """自适应检测：目标模型/Provider 是否支持 reasoning_effort 参数（支柱二兼容层）。

    复用 Hermes 原生 capability 检查；检测失败时保守返回 False（不传该参数），
    由 CLARIFY_GATE_PROMPT 的 prompt 级限词约束兜底，绝不触发 400。
    """
    if not model:
        return False
    try:
        from hermes_cli.models import github_model_reasoning_efforts
        return bool(github_model_reasoning_efforts(model))
    except Exception:
        return False


def _cache_request_overrides(
    model: str,
    provider: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按实际路由过滤缓存字段，避免兼容接口收到不支持的 OpenAI 参数。

    DeepSeek 使用自身的隐式前缀缓存统计，不接受 OpenAI Responses 的
    ``prompt_cache_retention``。Bridge 不主动启用扩展保留；支持该能力的专用
    路由应由 Hermes provider adapter 自行协商。
    """
    cleaned = dict(overrides or {})
    normalized = f"{provider}/{model}".lower()
    if "deepseek" in normalized:
        # DeepSeek rejects these keys even when their JSON value is null.  The
        # OpenAI-compatible client serializes an explicit ``None`` as a present
        # field, so the only safe representation is complete absence.
        cleaned.pop("prompt_cache_retention", None)
        cleaned.pop("prompt_cache_options", None)
        extra = cleaned.get("extra_body")
        if isinstance(extra, dict):
            extra = dict(extra)
            extra.pop("prompt_cache_retention", None)
            extra.pop("prompt_cache_options", None)
            if extra:
                cleaned["extra_body"] = extra
            else:
                cleaned.pop("extra_body", None)
    return cleaned


KB_RETRIEVAL_DISCIPLINE = (
    "【租户知识隔离纪律·必须严格遵守】\n"
    "1. 仅当回答需要平台内部事实、产品、客户、业务或租户知识时，调用 knowledge_search；"
    "润色、翻译、闲聊、纯创作和无需内部证据的问题不要调用。\n"
    "2. knowledge_search 是唯一允许的租户知识入口；禁止使用 file、bash、search_files、"
    "read_file 或任何本机路径读取知识 Vault。\n"
    "3. 调用 knowledge_search 时默认只传 query，不传 category_scope，让签名 capability 提供"
    "当前租户全部已授权分类；只有已知完整的 knowledge/.../public 或 "
    "knowledge/.../entitlement/... 路径时才可传 category_scope，禁止猜测 green、yellow、"
    "公司名或短分类。先理解实体与主题、形成取知要求；明确主题时在 query 之外传 "
    "entities/topics（例如 entities=[超聚变,华为], topics=[IPD]），后端只做字面匹配，"
    "不替你推断同义词。query 保留用户原始问题；entities/topics 只表达用户所需实体与主题，"
    "不得把用户未请求的 PDT/TR 等词自行加入强制覆盖条件。按任务选取返回 wikilinks，再用 paths 追读；链接和 Matrix "
    "只定位，不自动成为证据。matched 也不代表证据充分，须核对任务所需事实。\n"
    "4. 若 knowledge_search 零命中、证据不足、权限不可用或 Gateway 暂时不可用，且当前 Agent 已获"
    "联网权限，必须继续调用 web_search；需要核实正文时再调用 web_extract。公开网络结果"
    "必须标注为“公开网络资料”并引用 URL，不得伪装成租户知识，也不得借联网推测或重构"
    "red/yellow 受限内容。若未获联网权限，才明确说明证据缺口。\n"
    "5. 租户知识结果必须保留 [[path]] 引用；公开网络结果必须保留 URL，不得伪造来源。\n"
    "6. 默认实体/概念问答只调用 knowledge_search，不机械追加 user_note_search；仅问题明确"
    "涉及我的笔记/历史私有记录，或已识别来源缺口指向笔记时，才补查 user_note_search。"
    "若 Gateway 已覆盖同范围 notes，不重复检索；不得为了减少回合忽略真实证据缺口。"
)


GENERAL_KNOWLEDGE_SPEED_DISCIPLINE = (
    "\n一般知识问答默认先做一轮并行公开检索；只有能明确写出尚未覆盖的关键事实时才做第二轮精查。"
    "证据完整后立即作答，正文默认不超过600个汉字，先结论、后关键差异与来源；"
    "用户明确要求深入、报告、方案、清单或长文时不适用该长度约束。"
)


CLARIFY_GATE_PROMPT = """【AI Lab 全局交互与对话规范】
1. 根据用户指令提供直接、准确、结构清晰的结果。
2. Skill/Agent 语义选择只接受 capability_router 注入并验证的同一次 JEV 决策。
3. 仅在当前请求确有关键歧义或已验证 Skill 明确要求时调用 clarify；选项回答属于当前问题的状态，不是新的独立指令。
4. 写操作只能使用当前回合 QCP 已授权并实际提供的工具；工具成功回执前不得声称完成。"""


def _steer_drill_me_response(response: str, round_number: int, enabled: bool) -> str:
    """把选项作为工具答案送回 Agent，并在收敛不足时注入下一轮 Steering 指令。"""
    if not enabled or round_number >= _contracts.DRILL_ME_MIN_ROUNDS:
        return response
    next_round = round_number + 1
    return (
        f"{response}\n\n"
        f"[Harness steering: 这是 Drill-me 第 {round_number} 轮的结构化答案，"
        "不是一条新的用户指令。请把它合并进原始需求状态；当前尚未达到收敛门槛，"
        f"不得输出方案或解释该选项。现在必须调用 clarify 发出第 {next_round} 轮问题，"
        "询问一个尚未确认且不重复的关键维度。]"
    )


from . import agent_execution, knowledge as _knowledge, memory as _memory, receipts as _receipts, session_runtime as _session_runtime  # noqa: E402

from . import session_runtime as _session_runtime

from . import memory as _memory

from . import agent_execution as _agent_execution

from . import knowledge as _knowledge
