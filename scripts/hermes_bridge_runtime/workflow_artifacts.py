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


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Hermes 未返回 JSON 计划")
    candidate = raw[start : end + 1]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as json_error:
        # Some Hermes routes emit strict JSON with a trailing comma. Remove
        # only commas immediately before a closing object/array delimiter.
        repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
        if repaired != candidate:
            try:
                value = json.loads(repaired)
            except json.JSONDecodeError:
                pass
            else:
                candidate = repaired
        if "value" in locals() and isinstance(value, dict):
            return value
        # Hermes occasionally emits a Python-dict-shaped object (single quotes
        # or a trailing comma). literal_eval is data-only; never use eval here.
        try:
            value = ast.literal_eval(candidate)
        except (SyntaxError, ValueError, TypeError):
            raise json_error
    if not isinstance(value, dict):
        raise ValueError("Hermes 计划必须是 JSON 对象")
    return value


def _workflow_order(plan: dict[str, Any]) -> list[str]:
    nodes = plan.get("nodes") or []
    ids = [str(node.get("id") or "") for node in nodes]
    if not ids or any(not node_id for node_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("工作流节点 ID 非法或重复")
    incoming = {node_id: 0 for node_id in ids}
    outgoing = {node_id: [] for node_id in ids}
    for edge in plan.get("edges") or []:
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source not in incoming or target not in incoming:
            raise ValueError("工作流依赖引用不存在的节点")
        outgoing[source].append(target)
        incoming[target] += 1
    queue_ids = [node_id for node_id in ids if incoming[node_id] == 0]
    ordered: list[str] = []
    while queue_ids:
        node_id = queue_ids.pop(0)
        ordered.append(node_id)
        for target in outgoing[node_id]:
            incoming[target] -= 1
            if incoming[target] == 0:
                queue_ids.append(target)
    if len(ordered) != len(ids):
        raise ValueError("工作流 DAG 存在循环依赖")
    return ordered


_CUMULATIVE_USAGE_FIELDS = (
    "input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens",
    "cache_write_tokens", "total_tokens", "estimated_cost_usd",
)


def _agent_usage_baseline(agent: Any) -> dict[str, Any]:
    """Snapshot this instance, not the last request/session's reported usage.

    Hermes initializes session_* counters on construction and retains them on
    cached reuse. turn_finalizer returns these counters, except api_calls which
    is already turn-local. Do not reset Hermes' native accounting to get a delta.
    """
    baseline = {}
    for field in _CUMULATIVE_USAGE_FIELDS:
        value = getattr(agent, "session_" + field, None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            baseline[field] = value
    return baseline


def _usage_delta(
    usage: dict[str, Any], baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Accept both Hermes' flat finalizer result and wrapped usage adapters.
    if isinstance(usage.get("usage"), dict):
        usage = usage["usage"]
    evidence = {}
    if baseline is not None and usage.get("usage_scope") != "turn":
        cumulative = {field: usage[field] for field in _CUMULATIVE_USAGE_FIELDS if field in usage}
        usage = dict(usage)
        reset_fields = []
        for field, current in cumulative.items():
            if field not in baseline:
                continue
            cast = float if field == "estimated_cost_usd" else int
            current = cast(current or 0)
            before = cast(baseline[field] or 0)
            # A decreased counter signals a new counter epoch. Never emit a
            # negative debit, nor subtract an earlier instance's usage.
            if current < before:
                reset_fields.append(field)
                usage[field] = max(0, current)
            else:
                usage[field] = current - before
        evidence = {
            "usage_scope": "turn",
            "cumulative_usage": cumulative,
            "usage_baseline": dict(baseline),
            "usage_counter_resets": reset_fields,
        }
    integer_fields = (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "total_tokens",
        "api_calls",
    )
    result: dict[str, Any] = {field: int(usage.get(field) or 0) for field in integer_fields}
    result["usage_available"] = usage.get("usage_available", any(
        field in usage
        for field in ("input_tokens", "output_tokens", "total_tokens")
    ))
    # Hermes usage_pricing.normalize_usage retains provider completion/output
    # totals; reasoning_tokens is a detail of that output, not extra generation.
    # Input/cache usage stays visible but does not consume the generation cap.
    result["budget_tokens"] = result["output_tokens"]
    result.update(
        {
            "estimated_cost_usd": float(usage.get("estimated_cost_usd") or 0),
            "model": str(usage.get("model") or ""),
            "provider": str(usage.get("provider") or ""),
            "cost_status": str(usage.get("cost_status") or "unknown"),
            "cost_source": str(usage.get("cost_source") or "none"),
        }
    )
    for field in ("usage_scope", "cumulative_usage", "usage_baseline", "usage_counter_resets"):
        if field in usage:
            result[field] = usage[field]
    result.update(evidence)
    if any(field != "estimated_cost_usd" for field in result.get("usage_counter_resets", [])):
        # An in-place token counter reset has no proven per-turn baseline.
        # Keep the evidence, but require reconciliation rather than auto-charge.
        result["usage_available"] = False
    return result


def _accumulate_usage(run: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    delta = _usage_delta(usage)
    total = run.setdefault("usage", {})
    for field in (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "total_tokens",
        "api_calls",
        "budget_tokens",
    ):
        total[field] = int(total.get(field) or 0) + int(delta[field])
    total["estimated_cost_usd"] = round(
        float(total.get("estimated_cost_usd") or 0) + delta["estimated_cost_usd"], 8
    )
    for field in ("model", "provider", "cost_status", "cost_source"):
        if delta.get(field):
            total[field] = delta[field]
    return delta


def _workflow_toolsets(node: dict[str, Any]) -> list[str]:
    """按节点最小授权工具，避免把整套 CLI Schema 重复塞进每次推理。"""
    node_type = str(node.get("node_type") or "")
    params = node.get("parameters") or {}
    if params.get("workspace_mode") == "tenant_coder":
        # Never grant Hermes' host terminal/files. These names route only to
        # the authenticated workspace and the root-owned networkless runner.
        return ["tenant_coder", "tenant_skills"]
    if node_type == "KNOWLEDGE_RETRIEVAL":
        # Tenant knowledge is fetched by Bridge through Knowledge Gateway before
        # model execution. Hermes may only supplement an explicit evidence gap
        # with the web tool; local Vault/file tools are never granted.
        return ["web"] if bool(params.get("allow_network")) else ["tenant_skills"]
    if node_type == "LLM_INFERENCE" and str(params.get("agent_id") or "") not in {
        "",
        "main_agent",
    }:
        return ["tenant_skills"]
    # AIAgent 对空列表存在跨版本 fallback 差异；给纯推理节点一个无执行副作用的
    # 最小 skill 元数据面，同时在节点 Prompt 中明确禁止工具调用。
    return ["tenant_skills"]


def _workflow_turn_token_cap(node: dict[str, Any]) -> int:
    """将 DSL 的节点总输出预算折算为 Hermes 0.19 的单回合上限。

    AIAgent 的 ``max_tokens`` 会应用到每次模型调用，而检索节点通常包含多次
    tool/model 回合；直接透传会让单节点总输出成倍突破 DSL 预算。
    """
    node_budget = max(
        256,
        min(16_384, int((node.get("parameters") or {}).get("max_tokens") or 2048)),
    )
    expected_turns = 6 if str(node.get("node_type") or "") == "KNOWLEDGE_RETRIEVAL" else 3
    return max(384, min(2048, node_budget // expected_turns))


def _workflow_tool_event_type(function_name: str) -> str:
    if function_name == "delegate_task":
        return "agent_spawn"
    if function_name in {"skill_view", "skill_load"}:
        return "skill_load"
    return "tool_start"


def _run_workflow_node_in_process(
    goal: str,
    node: dict[str, Any],
    session_id: str | None = None,
    execution_id: str | None = None,
    event_callback=None,
    sandbox: TenantHermesSandbox | None = None,
) -> tuple[str, str | None, dict[str, Any]]:
    """通过 Hermes AIAgent 原生 Session 执行节点。

    Hermes 0.19 的 ``-z`` 路径不会把 ``--resume`` 传给 one-shot runner，
    因而不能用于持久工作流。Bridge 兼容层直接使用同版本公开 AIAgent，
    同时施加节点工具、迭代和输出预算；不修改 Hermes 安装包。
    """
    from run_agent import AIAgent

    cfg = _agent_config._get_cached_config()
    model_cfg = cfg.get("model") or {}
    cfg_model = (
        model_cfg
        if isinstance(model_cfg, str)
        else model_cfg.get("default") or model_cfg.get("model") or ""
    )
    runtime = _agent_config._get_cached_runtime(cfg)
    if sandbox is None:
        raise RuntimeError("tenant_sandbox_unavailable")
    _knowledge._ensure_tenant_skill_tool_registered()
    if (node.get("parameters") or {}).get("workspace_mode") == "tenant_coder":
        _knowledge._ensure_tenant_coder_tools_registered()
    _knowledge._sandbox_tool_context.value = sandbox
    design_skill_context, design_skill_receipts = _load_workflow_design_skills(node, sandbox)
    if design_skill_context:
        goal = f"{goal}\n\n以下设计 Skill 已由可信运行时加载，必须逐项应用；不得仅复述名称：\n{design_skill_context}"
        if len(goal) > _contracts.MAX_INPUT:
            raise RuntimeError("design_skill_context_exceeds_node_input_budget")
        if event_callback:
            for receipt in design_skill_receipts:
                event_callback(
                    "skill_load",
                    tool="skill_view",
                    tool_call_id=f"design-skill:{receipt['name']}",
                    idempotency_key=f"design-skill:{receipt['name']}:{receipt['sha256']}",
                    status="done",
                    message=f"已加载设计 Skill：{receipt['name']}",
                    receipt=receipt,
                )
    session_db = _agent_config._create_sandbox_session_db(sandbox)
    from agent.runtime_cwd import set_session_cwd

    set_session_cwd(str(sandbox.root))
    from hermes_constants import (
        reset_hermes_home_override,
        set_hermes_home_override,
    )

    hermes_home_token = set_hermes_home_override(_memory._sandbox_hermes_home(sandbox))
    agent = None
    timeout_fired = threading.Event()
    timeout_timer = None
    try:
        max_tokens = _workflow_turn_token_cap(node)
        def _tool_start(tool_call_id, function_name, function_args) -> None:
            if event_callback and function_name and not str(function_name).startswith("_"):
                event_callback(
                    _workflow_tool_event_type(str(function_name)),
                    tool=str(function_name),
                    tool_call_id=str(tool_call_id or ""),
                    idempotency_key=str(tool_call_id or ""),
                    status="running",
                    message=(
                        "已委派子 Agent" if function_name == "delegate_task"
                        else f"正在调用 {function_name}"
                    ),
                )

        def _tool_complete(tool_call_id, function_name, function_args, result) -> None:
            if event_callback and function_name and not str(function_name).startswith("_"):
                event_callback(
                    (
                        "skill_load"
                        if function_name in {"skill_view", "skill_load"}
                        else "tool_complete"
                    ),
                    tool=str(function_name),
                    tool_call_id=str(tool_call_id or ""),
                    idempotency_key=str(tool_call_id or ""),
                    status="done",
                    message=f"{function_name} 调用完成",
                )

        agent = AIAgent(
            api_key=runtime.get("api_key"),
            base_url=runtime.get("base_url"),
            provider=runtime.get("provider"),
            api_mode=runtime.get("api_mode"),
            model=cfg_model,
            max_iterations=_contracts.WORKFLOW_NODE_MAX_ITERATIONS,
            max_tokens=max_tokens,
            enabled_toolsets=_workflow_toolsets(node),
            quiet_mode=True,
            platform="cli",
            session_id=session_id,
            session_db=session_db,
            credential_pool=runtime.get("credential_pool"),
            fallback_model=_agent_config._get_cached_fallback(cfg) or None,
            request_overrides=_agent_config._cache_request_overrides(
                cfg_model, str(runtime.get("provider") or "")
            ),
            reasoning_config={"effort": "minimal"},
            ephemeral_system_prompt=(
                "你是持久工作流节点执行器。严格执行当前节点，不追问、不扩展范围；"
                "工具调用以完成当前节点所需的最少次数为限；只返回可落盘成果。"
            ),
            tool_start_callback=_tool_start,
            tool_complete_callback=_tool_complete,
            **_memory._isolated_agent_context_kwargs(),
        )
        if execution_id:
            with _contracts._workflow_runs_lock:
                _contracts._workflow_agents[execution_id] = agent

        def _interrupt_on_timeout() -> None:
            timeout_fired.set()
            try:
                agent.interrupt(message="workflow-node-timeout")
            except TypeError:
                agent.interrupt()
            except Exception:
                pass

        timeout_timer = threading.Timer(
            _contracts.WORKFLOW_NODE_TIMEOUT,
            _interrupt_on_timeout,
        )
        timeout_timer.daemon = True
        timeout_timer.start()
        usage_baseline = _agent_usage_baseline(agent)
        result = agent.run_conversation(goal)
        if timeout_fired.is_set():
            raise TimeoutError(
                f"Hermes 工作流节点超过 {_contracts.WORKFLOW_NODE_TIMEOUT} 秒"
            )
        result = result if isinstance(result, dict) else {}
        reply = str(result.get("final_response") or "").strip()
        return reply, getattr(agent, "session_id", None) or session_id, _usage_delta(result, usage_baseline)
    finally:
        if timeout_timer is not None:
            timeout_timer.cancel()
        if execution_id:
            with _contracts._workflow_runs_lock:
                if _contracts._workflow_agents.get(execution_id) is agent:
                    _contracts._workflow_agents.pop(execution_id, None)
        if agent is not None:
            try:
                agent.close()
            except Exception:
                pass
        try:
            session_db.close()
        except Exception:
            pass
        _knowledge._sandbox_tool_context.value = None
        reset_hermes_home_override(hermes_home_token)


def _workflow_artifact_contract(node: dict[str, Any]) -> dict[str, str]:
    params = node.get("parameters") or {}
    declared_raw = params.get("artifact")
    declared: dict[str, Any] = declared_raw if isinstance(declared_raw, dict) else {}
    raw_type = str(declared.get("render_type") or declared.get("artifact_type") or params.get("output_format") or "markdown").strip().lower()
    aliases = {
        "md": "markdown", "markdown 文档": "markdown", "结构化 markdown": "markdown",
        "word": "word", "word 文档": "word", "word文档": "word", "docx": "word",
        "图表": "chart", "数据图表": "chart", "chart": "chart",
        "拓扑图": "topology", "topology": "topology",
        "流程图": "flowchart", "flow": "flowchart", "flowchart": "flowchart",
        "csv": "data", "json": "data",
        "presentation_outline": "presentation_outline",
        "presentation_design": "presentation_design",
        "presentation": "presentation",
        "html_design": "html_design",
        "illustration_prompt": "illustration_prompt",
        "illustration_svg": "illustration_svg",
        "html": "html", "htm": "html", "网页": "html", "网页工具": "html",
    }
    render_type = aliases.get(raw_type, raw_type if raw_type in {"markdown", "word", "chart", "topology", "flowchart", "data", "presentation_outline", "presentation_design", "presentation", "html_design", "illustration_prompt", "illustration_svg", "html"} else "markdown")
    extension, mime_type = {
        "markdown": ("md", "text/markdown"),
        "word": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "chart": ("json", "application/json"),
        "topology": ("json", "application/json"),
        "flowchart": ("json", "application/json"),
        "data": ("json", "application/json"),
        "presentation_outline": ("json", "application/json"),
        "presentation_design": ("json", "application/json"),
        "presentation": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        "html_design": ("json", "application/json"),
        "illustration_prompt": ("json", "application/json"),
        "illustration_svg": ("svg", "image/svg+xml"),
        "html": ("html", "text/html; charset=utf-8"),
    }[render_type]
    if render_type == "data" and raw_type == "csv":
        extension, mime_type = "csv", "text/csv"
    return {"render_type": render_type, "extension": extension, "mime_type": mime_type}


def _workflow_artifact_instruction(contract: dict[str, str]) -> str:
    render_type = contract["render_type"]
    if render_type == "chart":
        return '只输出合法 JSON 对象：{"labels":["维度"],"values":[1]}；values 仅使用非负数字。'
    if render_type in {"topology", "flowchart"}:
        return '只输出合法 JSON 对象：{"nodes":[{"id":"n1","label":"节点"}],"edges":[{"from":"n1","to":"n2","label":"关系"}]}。'
    if render_type == "data":
        return "只输出 CSV 表头与数据行，不要添加 Markdown 围栏。" if contract["extension"] == "csv" else "只输出合法 JSON 对象或数组；不要添加 Markdown 围栏或解释文字。"
    if render_type == "word":
        return "只输出 Word 正文纯文本，用空行分段；平台将生成真实 DOCX，不要使用 Markdown 标记。"
    if render_type == "html_design":
        return '只输出合法 JSON：{"surface":"configure|operate|explore","user_flow":["步骤"],"tokens":{"background":"#F5F5F7","surface":"#FFFFFF","text":"#1D1D1F","muted":"#6E6E73","accent":"#0071E3","radius":"12px"},"components":[{"name":"组件","states":["default","focus","error","success"]}],"responsive":"iPhone 375px first","accessibility":["WCAG 2.1 AA"]}。必须使用单一强调色、SF 系统字体、44px 触控目标、清晰焦点、深浅色和 reduced-motion；避免通用卡片阵列、无意义渐变、默认玻璃拟态与装饰性数据。'
    if render_type == "illustration_prompt":
        return "只输出合法 JSON 插图 Prompt；平台将根据真实当前段落及相邻上下文进行确定性核验。"
    if render_type == "illustration_svg":
        return '只输出一个自包含 SVG 根元素，必须包含 viewBox、title、desc；禁止脚本、外链、href、foreignObject 和嵌入图片。优先形状、留白、层级和单一强调色，不依赖小字传达语义。'
    if render_type == "html":
        return "只输出完整 HTML（从 <!doctype html> 到 </html>），不要 Markdown 围栏或解释。单文件内联 CSS/JS、不得引用 CDN/外链/网络请求。采用 iOS 优先的 Configure/Operate 组合界面：SF 系统字体、单一品牌强调色、语义化结构、44px 触控目标、WCAG AA 对比度、键盘焦点、深色/浅色/system 主题、响应式布局、prefers-reduced-motion。实现用户要求的真实交互以及默认、空、错误、成功状态；禁止通用三卡片模板、无意义渐变、默认玻璃拟态、emoji 和虚构指标。"
    if render_type == "presentation_outline":
        return '只输出合法 JSON：{"title":"标题","slides":[{"layout":"title|section|bullets|two_column|chart|table|conclusion","title":"页标题","purpose":"本页作用","key_points":["要点"],"evidence":["源文档依据"],"visual":"建议视觉"}]}；每页必须有明确作用与证据，数据不足时明确写出缺口。'
    if render_type == "presentation_design":
        return '只输出合法 JSON：{"title":"设计样稿","theme":{"colors":{"primary":"#8057E8","text":"#191521","muted":"#686275","pale":"#F1EEFA","background":"#FFFFFF","inverse":"#FFFFFF"},"fonts":{"title":"Aptos","body":"Aptos"}},"slides":[{"layout":"title|section|bullets|two_column|chart|table|conclusion","title":"代表页标题","subtitle":"可选","bullets":["真实内容"]}]}；theme 字段和值必须完整，slides 给出 3 至 5 张带真实内容、可渲染的代表页，每页仅保留所选版式需要的字段，不得使用占位符或虚构数据。'
    if render_type == "presentation":
        return '只输出合法 JSON：{"title":"标题","slides":[{"layout":"title|section|bullets|two_column|chart|table|conclusion","title":"页标题","subtitle":"可选","bullets":["要点"],"left":[],"right":[],"headers":[],"rows":[],"categories":[],"series":[{"name":"系列","values":[1]}]}]}；仅保留所选版式需要的字段。'
    return "输出可直接渲染的 Markdown 正文。"


def _normalize_presentation_reply(reply: str) -> str:
    value = _extract_json_object(reply)
    slides = value.get("slides") if isinstance(value, dict) else None
    if isinstance(slides, list):
        for slide in slides:
            if not isinstance(slide, dict):
                continue
            layout = str(slide.get("layout") or "bullets")
            if layout == "section" and slide.get("subtitle"):
                slide["layout"] = "title"
                layout = "title"
            if layout == "section" and isinstance(slide.get("key_points"), list):
                slide["layout"] = "bullets"
                layout = "bullets"
            if layout == "process" and isinstance(slide.get("steps"), list):
                slide["layout"] = "bullets"
                slide["bullets"] = slide.pop("steps")
                layout = "bullets"
            if layout == "two_column":
                for side in ("left", "right"):
                    points = slide.pop(f"{side}_points", None)
                    heading = slide.pop(f"{side}_title", None)
                    if side not in slide and isinstance(points, list):
                        slide[side] = ([str(heading)] if heading else []) + points
                    current = slide.get(side)
                    if isinstance(current, dict):
                        nested_heading = current.get("heading") or current.get("title")
                        nested_points = current.get("points") or current.get("bullets") or current.get("items") or []
                        if isinstance(nested_points, list):
                            slide[side] = ([str(nested_heading)] if nested_heading else []) + nested_points
            if layout in {"bullets", "conclusion"} and "bullets" not in slide and "key_points" in slide:
                slide["bullets"] = slide.pop("key_points")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _approved_presentation_stage(
    run: dict[str, Any], output_format: str, label: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    node = next(
        (
            item
            for item in run.get("plan", {}).get("nodes") or []
            if (item.get("parameters") or {}).get("output_format") == output_format
        ),
        None,
    )
    if not node:
        raise RuntimeError(f"presentation {label} gate is missing")
    node_id = str(node.get("id") or "")
    state = (run.get("nodes") or {}).get(node_id) or {}
    binding = (run.get("approved_gate_artifacts") or {}).get(node_id) or {}
    output = str(state.get("output") or "")
    if (node_id not in set(run.get("approved_gates") or [])
            or int(binding.get("artifact_version") or 0) != int(state.get("attempt") or 0)
            or hashlib.sha256(output.encode()).hexdigest() != binding.get("content_hash")):
        raise RuntimeError(f"approved presentation {label} is missing, stale, or tampered")
    return _extract_json_object(output), dict(binding)


def _approved_presentation_design(run: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    value, binding = _approved_presentation_stage(run, "presentation_design", "design")
    from backend.services.presentation_scenario import validate_theme
    theme = validate_theme(value.get("theme"))
    return theme, binding


def _approved_presentation_outline(run: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return _approved_presentation_stage(run, "presentation_outline", "outline")


def _assert_final_matches_approved_outline(
    final: dict[str, Any], outline: dict[str, Any]
) -> None:
    final_slides = final.get("slides")
    outline_slides = outline.get("slides")
    if not isinstance(final_slides, list) or not isinstance(outline_slides, list):
        raise RuntimeError("final presentation or approved outline has invalid slides")
    final_shape = [
        (str(item.get("layout") or ""), str(item.get("title") or "").strip())
        for item in final_slides
        if isinstance(item, dict)
    ]
    outline_shape = [
        (str(item.get("layout") or ""), str(item.get("title") or "").strip())
        for item in outline_slides
        if isinstance(item, dict)
    ]
    if final_shape != outline_shape:
        raise RuntimeError("final presentation differs from approved outline structure")


def _bind_approved_presentation_design(run: dict[str, Any], content: str) -> tuple[str, dict[str, Any]]:
    value = _extract_json_object(content)
    theme, binding = _approved_presentation_design(run)
    value["theme"] = theme
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")), binding


def _bind_approved_presentation_inputs(
    run: dict[str, Any], content: str
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    value = _extract_json_object(content)
    theme, design_binding = _approved_presentation_design(run)
    outline, outline_binding = _approved_presentation_outline(run)
    _assert_final_matches_approved_outline(value, outline)
    value["theme"] = theme
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        design_binding,
        outline_binding,
    )


def _workflow_illustration_context(run: dict[str, Any]) -> dict[str, Any]:
    source_text = str((run.get("source_document") or {}).get("text") or "")
    return select_illustration_context(source_text or str(run.get("goal") or ""), str(run.get("goal") or ""))


def _load_workflow_design_skills(
    node: dict[str, Any], sandbox: TenantHermesSandbox
) -> tuple[str, list[dict[str, str]]]:
    names = (node.get("parameters") or {}).get("design_skills") or []
    if not names:
        return "", []
    blocks: list[str] = []
    receipts: list[dict[str, str]] = []
    attachments = {
        "ui-ux-pro-max": ["references/quick-reference.md", "references/pro-rules.md"],
        "popular-web-designs": ["templates/apple.md"],
    }
    for raw_name in names:
        name = str(raw_name).strip()
        loaded = read_sandbox_skill(sandbox=sandbox, name=name)
        if not loaded:
            raise RuntimeError(f"required_design_skill_unavailable:{name}")
        pieces = [loaded]
        skill_dir = sandbox.template_skills / name
        for relative in attachments.get(name, []):
            candidate = skill_dir / relative
            if candidate.is_file() and not candidate.is_symlink():
                pieces.append(candidate.read_text(encoding="utf-8"))
        full = "\n\n".join(pieces)
        digest = hashlib.sha256(full.encode("utf-8")).hexdigest()
        budget = 16_000 if name == "claude-design" else 10_000
        compact = full if len(full) <= budget else full[: budget - 3_000] + "\n...[skill excerpt]...\n" + full[-3_000:]
        blocks.append(f"### 已加载设计 Skill：{name}\n{compact}")
        receipts.append({"name": name, "sha256": digest, "status": "loaded"})
    return "\n\n".join(blocks), receipts


def _workflow_node_prompt(run: dict[str, Any], node: dict[str, Any]) -> str:
    params = node.get("parameters") or {}
    artifact_contract = _workflow_artifact_contract(node)
    output_format = str(params.get("output_format") or "").lower()
    presentation_output = output_format.startswith("presentation")
    document_output = output_format in {"word", "docx", "word 文档", "word文档"}
    html_output = output_format in {"html", "html_design", "htm", "网页", "网页工具"}
    illustration_output = output_format in {"illustration_prompt", "illustration_svg"}
    completed = []
    current_id = str(node.get("id") or "")
    revision_comment = str((run.get("revision_feedback") or {}).get(current_id) or "").strip()
    dependency_ids = {
        str(edge.get("source") or "")
        for edge in run.get("plan", {}).get("edges") or []
        if str(edge.get("target") or "") == current_id
    }
    for candidate in run.get("plan", {}).get("nodes") or []:
        node_id = str(candidate.get("id") or "")
        if dependency_ids and node_id not in dependency_ids:
            continue
        state = (run.get("nodes") or {}).get(node_id) or {}
        if state.get("status") == "succeeded" and state.get("output"):
            upstream_limit = 16000 if html_output or illustration_output else 5000 if presentation_output else 8000 if document_output else 1800
            output = str(state["output"])
            if presentation_output or document_output or html_output or illustration_output:
                if len(output) > upstream_limit:
                    raise RuntimeError(f"上游成果 {node_id} 超过 {upstream_limit} 字符；禁止静默截断")
            completed.append(f"- {candidate.get('name') or node_id}: {output[:upstream_limit]}")
    node_type = str(node.get("node_type") or "")
    node_budget = max(
        256, int((node.get("parameters") or {}).get("max_tokens") or 2048)
    )
    output_char_limit = max(
        600,
        min(
            48000 if html_output else 24000 if illustration_output else 8000 if presentation_output or document_output else 2200,
            node_budget * 2 if html_output or illustration_output else node_budget // 2,
        ),
    )
    if params.get("workspace_mode") == "tenant_coder":
        tool_rule = (
            "可使用 tenant_read_file/tenant_write_file/tenant_patch_file/tenant_search_files/tenant_terminal。"
            "它们只操作经服务端认证的当前租户 workspace；路径必须相对，命令在无网络容器中执行。"
            "不得尝试访问共享平台、Hermes 全局目录、部署目录或其他租户。完成必要编辑/验证后仍须返回格式契约要求的完整成果。"
        )
    elif node_type == "KNOWLEDGE_RETRIEVAL":
        tool_rule = (
            "直接使用当前节点已授权的 web_search/web_extract 或文件检索工具，"
            "按最小次数完成检索；不得把工具切换标签、调用计划或‘我先检查工具’作为最终成果。"
        )
    else:
        tool_rule = "本节点禁止调用工具；只基于当前 Session 已有的上游成果完成转换、分析或格式化。"
    upstream = chr(10).join(completed) if completed else "无直接依赖或上游暂无成果"
    source = run.get("source_document") or {}
    source_text = str(source.get("text") or "")
    plan_node_ids = {
        str(item.get("id") or "") for item in run.get("plan", {}).get("nodes") or []
    }
    source_node_id = (
        "presentation_analysis" if "presentation_analysis" in plan_node_ids
        else "document_analysis" if "document_analysis" in plan_node_ids
        else "html_tool_analysis" if "html_tool_analysis" in plan_node_ids
        else "presentation_outline"
    )
    if source_text and current_id == source_node_id:
        if len(source_text) > 80_000:
            raise RuntimeError("私有源文档超过 80000 字符；文档生成工作流禁止静默截断")
        upstream += f"\n\n私有源文档（{source.get('filename', 'document')}，共 {len(source_text)} 字符）：\n{source_text}"
    if output_format == "illustration_prompt":
        upstream += "\n\n" + illustration_prompt_instruction(_workflow_illustration_context(run))
    agent_config = run.get("agent_config") or {}
    composition = agent_config.get("composition") or {}
    allowed_agents = set(composition.get("capability_agent_ids") or []) | set(
        composition.get("invoked_agent_ids") or []
    )
    requested_agent = str(params.get("agent_id") or "main_agent")
    if allowed_agents and requested_agent not in allowed_agents:
        raise RuntimeError(f"Agent {requested_agent} 不在已批准的任务能力组合中")
    task_directive = str(agent_config.get("prompt") or "")[:3000]
    delegation = composition.get("delegation") or {}
    task_boundaries = (
        f"允许能力={sorted(allowed_agents) if allowed_agents else ['平台基线']}；"
        f"知识范围={composition.get('knowledge_scope') or []}；"
        f"子 Agent 并发上限={delegation.get('max_concurrent_children', 0)}；"
        f"委派深度上限={delegation.get('max_spawn_depth', 0)}"
    )
    prompt = (
        "你是 Hermes 工作流编排引擎，正在同一个持久 Session 中推进已获用户批准的 DAG。\n"
        f"任务专用 Agent 指令：{task_directive or '使用平台基线约束'}\n"
        f"批准的运行边界：{task_boundaries}\n"
        f"工作流目标：{run.get('goal', '')}\n"
        f"最终交付：{run.get('deliverable', '')}\n"
        f"当前节点：{node.get('name') or node.get('id')} ({node.get('node_type')})\n"
        f"指定 Agent：{requested_agent}\n"
        f"设计技能：{json.dumps(params.get('design_skills') or [], ensure_ascii=False)}\n"
        f"节点要求：{params.get('instruction') or params.get('query') or ''}\n"
        f"本轮用户修改意见：{revision_comment or '无'}\n"
        f"输出格式：{artifact_contract['render_type']} / {artifact_contract['extension']}\n"
        f"格式契约：{_workflow_artifact_instruction(artifact_contract)}\n"
        f"篇幅约束：最终可落盘正文不超过 {output_char_limit} 个中文字符，优先保留事实、引用与未解决缺口。\n"
        f"知识范围：{json.dumps(params.get('knowledge_scope') or run.get('knowledge_scope') or [], ensure_ascii=False)}\n"
        f"联网权限：{'允许，但仅在证据缺口明确时使用' if run.get('allow_network') else '禁止'}\n"
        f"工具纪律：{tool_rule}\n"
        "严格遵守当前节点的 Agent、知识范围与工具授权；引用真实来源，不得虚构。"
        "只输出当前节点可落盘的完整成果，不要输出运行状态说明。\n"
        f"上游上下文：\n{upstream}"
    )
    input_limit = _contracts.MAX_DOCUMENT_WORKFLOW_INPUT if source_text and current_id == source_node_id else _contracts.MAX_INPUT
    if (presentation_output or document_output or html_output or illustration_output or input_limit > _contracts.MAX_INPUT) and len(prompt) > input_limit:
        raise RuntimeError(f"文档生成工作流输入为 {len(prompt)} 字符，超过 {input_limit} 字符上限；禁止静默截断")
    return prompt[:input_limit]


def _workflow_output_incomplete(node: dict[str, Any], reply: str) -> bool:
    """拒绝 Hermes 尚未真正执行工具时产生的中间控制文本。"""
    normalized = str(reply or "").strip().lower()
    if not normalized:
        return True
    if "<tool_switch_" in normalized or "<tool_call" in normalized:
        return True
    if str(node.get("node_type") or "") != "KNOWLEDGE_RETRIEVAL":
        return False
    planning_markers = (
        "我先确认",
        "我先检查",
        "先确认当前",
        "接下来我会",
        "使用 bash 工具",
    )
    return len(normalized) < 320 and any(marker in normalized for marker in planning_markers)


def _merge_workflow_usage(total: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """合并同一节点的受控修复调用，确保平台看到完整真实 usage。"""
    merged = dict(total)
    for key in (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "total_tokens",
        "budget_tokens",
        "api_calls",
        "estimated_cost_usd",
    ):
        merged[key] = (merged.get(key) or 0) + (delta.get(key) or 0)
    for key in ("model", "provider"):
        if delta.get(key):
            merged[key] = delta[key]
    return merged


def _normalize_presentation_contract_reply(render_type: str, reply: str) -> str:
    if render_type in {"presentation", "presentation_design"}:
        return _normalize_presentation_reply(reply)
    if render_type.startswith("presentation"):
        return json.dumps(_extract_json_object(reply), ensure_ascii=False, separators=(",", ":"))
    return reply


from . import agent_config as _agent_config, contracts as _contracts, knowledge as _knowledge, memory as _memory  # noqa: E402
