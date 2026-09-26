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


def _workflow_run_sync(execution_id: str) -> None:
    """Hermes 层推进整份 DAG；平台只消费事件，不参与节点调度。"""
    with _contracts._workflow_runs_lock:
        run = _persistence._workflow_runs.get(execution_id)
        if not run:
            return
        run["status"] = "running"
        run["error"] = None
        _persistence._workflow_event(
            run,
            "run_started",
            process_contract_digest=(run.get("plan") or {}).get("process_contract_digest"),
            resolved_manifest=run.get("resolved_manifest") or {},
            message="Hermes 工作流开始执行",
        )
    try:
        sandbox = _persistence._workflow_sandbox(run)
        agent_config = _contracts.TrustedAgentConfig.model_validate(
            run.get("agent_config") or {}
        )
        run_scope = set(str(item) for item in run.get("knowledge_scope") or [])
        agent_scope = set(agent_config.knowledge_scope)
        if not run_scope.issubset(agent_scope):
            raise RuntimeError("workflow_agent_knowledge_scope_denied")
        effective_allow_network = bool(
            run.get("allow_network") and agent_config.allow_network
        )
        plan = run["plan"]
        node_map = {str(node["id"]): node for node in plan.get("nodes") or []}
        order = _workflow_artifacts._workflow_order(plan)
        hermes_sid = run.get("hermes_session_id")
        if hermes_sid and not _persistence._session_exists(str(hermes_sid)):
            hermes_sid = None
        for position, node_id in enumerate(order):
            with _contracts._workflow_runs_lock:
                if run.get("cancel_requested"):
                    run["status"] = "cancelled"
                    _persistence._workflow_event(run, "run_cancelled", message="执行已取消")
                    return
                state = run.setdefault("nodes", {}).setdefault(node_id, {})
                if state.get("status") == "succeeded":
                    continue
                node = node_map[node_id]
                state.update({"status": "running", "attempt": int(state.get("attempt") or 0) + 1})
                _persistence._workflow_event(
                    run,
                    "node_started",
                    node_id=node_id,
                    node_attempt_id=f"{execution_id}:{node_id}:{state['attempt']}",
                    node_type=node.get("node_type"),
                    agent_id=_workflow_artifacts._workflow_agent_identity(
                        node, agent_config
                    ),
                    message=f"开始：{node.get('name') or node_id}",
                )
            node_prompt = _workflow_artifacts._workflow_node_prompt(run, node)
            binding = (node.get("parameters") or {}).get("skill_binding") or {}
            if binding:
                receipt = _contracts._verify_workflow_skill_binding(binding, sandbox)
                node_prompt = _contracts._expand_workflow_skill(node_prompt, receipt, sandbox)
                with _contracts._workflow_runs_lock:
                    _persistence._workflow_event(
                        run,
                        "skill_load",
                        node_id=node_id,
                        status="verified",
                        receipt=receipt,
                        message=f"已核验并加载 Skill：{receipt['skill_id']}",
                    )
            node_usage: dict[str, Any] = {}
            reply = ""
            gateway_completed = False
            if str(node.get("node_type") or "") == "KNOWLEDGE_RETRIEVAL":
                params = node.get("parameters") or {}
                requested_scope = list(
                    params.get("knowledge_scope") or agent_config.knowledge_scope
                )
                if not set(requested_scope).issubset(run_scope & agent_scope):
                    raise RuntimeError("workflow_node_knowledge_scope_denied")
                docs = _persistence._knowledge_gateway_search(
                    str(run.get("knowledge_capability") or ""),
                    query=str(params.get("query") or params.get("instruction") or run.get("goal") or ""),
                    category_scope=requested_scope,
                )
                node_network_allowed = bool(
                    effective_allow_network
                    and params.get("allow_network")
                    and set(agent_config.allowed_tools)
                    & {"web_search", "web_extract"}
                )
                if docs or not node_network_allowed:
                    gateway_completed = True
                    if docs:
                        rows = [
                            f"- [[{item.get('path', '')}]] **{item.get('title', '')}**："
                            f"{str(item.get('snippet') or '已授权知识条目')[:500]}"
                            for item in docs
                        ]
                        reply = "## 已授权知识证据\n\n" + "\n".join(rows)
                    else:
                        reply = "## 证据缺口\n\n当前授权知识范围内未检索到相关条目，且本节点未获联网权限。"
            def _node_event(event_type: str, **event_payload: Any) -> None:
                with _contracts._workflow_runs_lock:
                    _persistence._workflow_event(
                        run,
                        event_type,
                        node_id=node_id,
                        category=event_type,
                        source="hermes_bridge",
                        detail="",
                        **event_payload,
                    )

            for completion_attempt in range(0 if gateway_completed else 2):
                attempt_prompt = node_prompt
                if completion_attempt:
                    attempt_prompt = (
                        node_prompt
                        + "\n\n上一次响应停留在工具调用计划，没有形成成果。"
                        "这次必须立即使用已授权工具完成检索，并直接返回含来源 URL、"
                        "证据摘要和缺口标记的完整可落盘成果；禁止输出工具切换标签。"
                    )[:_contracts.MAX_INPUT]
                reply, new_sid, raw_usage = _workflow_artifacts._run_workflow_node_in_process(
                    attempt_prompt,
                    node,
                    str(hermes_sid) if hermes_sid else None,
                    execution_id,
                    event_callback=_node_event,
                    sandbox=sandbox,
                    agent_config=agent_config,
                )
                if new_sid:
                    hermes_sid = new_sid
                delta = _workflow_artifacts._accumulate_usage(run, raw_usage)
                node_usage = _workflow_artifacts._merge_workflow_usage(node_usage, delta)
                if reply.startswith("⚠️"):
                    raise RuntimeError(reply)
                if not _workflow_artifacts._workflow_output_incomplete(node, reply):
                    break
                if completion_attempt == 0:
                    with _contracts._workflow_runs_lock:
                        _persistence._workflow_event(
                            run,
                            "node_repairing",
                            node_id=node_id,
                            usage=node_usage,
                            message="Hermes 返回未完成的工具控制文本，正在受控修复",
                        )
            if _workflow_artifacts._workflow_output_incomplete(node, reply):
                raise RuntimeError("Hermes 未完成当前节点的实际工具执行")
            contract = _workflow_artifacts._workflow_artifact_contract(node)
            approved_design = None
            approved_outline = None
            render_type = str(contract["render_type"])
            if render_type == "illustration_prompt":
                context = _workflow_artifacts._workflow_illustration_context(run)
                try:
                    reply = validate_illustration_prompt(reply, context)
                except (ValueError, json.JSONDecodeError) as exc:
                    with _contracts._workflow_runs_lock:
                        _persistence._workflow_event(
                            run,
                            "node_repairing",
                            node_id=node_id,
                            usage=node_usage,
                            message=f"插图 Prompt 未通过上下文核验，正在修复：{str(exc)[:240]}",
                        )
                    repair_prompt = (
                        node_prompt
                        + f"\n\n上一次输出未通过确定性核验：{str(exc)[:240]}。"
                        "重新输出一个完整 JSON；必须逐字包含 subject、semantic_relationship、style、composition 的值于 prompt 字段。"
                    )[:_contracts.MAX_INPUT]
                    reply, new_sid, raw_usage = _workflow_artifacts._run_workflow_node_in_process(
                        repair_prompt,
                        node,
                        str(hermes_sid) if hermes_sid else None,
                        execution_id,
                        event_callback=_node_event,
                        sandbox=sandbox,
                        agent_config=agent_config,
                    )
                    if new_sid:
                        hermes_sid = new_sid
                    node_usage = _workflow_artifacts._merge_workflow_usage(
                        node_usage, _workflow_artifacts._accumulate_usage(run, raw_usage)
                    )
                    reply = validate_illustration_prompt(reply, context)
            elif render_type == "illustration_svg":
                prompt_state = (run.get("nodes") or {}).get("html_tool_illustration_prompt") or {}
                prompt_json = str(prompt_state.get("output") or "")
                if not prompt_json:
                    raise RuntimeError("verified_illustration_prompt_missing")
                reply = validate_illustration_svg(reply, prompt_json)
            elif render_type == "html":
                svg_state = (run.get("nodes") or {}).get("html_tool_illustration") or {}
                prompt_state = (run.get("nodes") or {}).get("html_tool_illustration_prompt") or {}
                prompt_json = str(prompt_state.get("output") or "")
                svg = validate_illustration_svg(str(svg_state.get("output") or ""), prompt_json)
                reply = secure_html_tool(embed_illustration(reply, svg))
            if render_type.startswith("presentation"):
                try:
                    reply = _workflow_artifacts._normalize_presentation_contract_reply(render_type, reply)
                except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                    with _contracts._workflow_runs_lock:
                        _persistence._workflow_event(
                            run,
                            "node_repairing",
                            node_id=node_id,
                            usage=node_usage,
                            message=f"Hermes 返回的演示结构无效，正在受控修复：{str(exc)[:240]}",
                        )
                    repair_prompt = (
                        node_prompt
                        + "\n\n上一次响应不是符合格式契约的有效 JSON。"
                        "这次只返回一个完整 JSON 对象，不要 Markdown 代码围栏、解释或运行状态；"
                        "字段与 layout 必须严格遵守格式契约。"
                    )[:_contracts.MAX_INPUT]
                    reply, new_sid, raw_usage = _workflow_artifacts._run_workflow_node_in_process(
                        repair_prompt,
                        node,
                        str(hermes_sid) if hermes_sid else None,
                        execution_id,
                        event_callback=_node_event,
                        sandbox=sandbox,
                        agent_config=agent_config,
                    )
                    if new_sid:
                        hermes_sid = new_sid
                    delta = _workflow_artifacts._accumulate_usage(run, raw_usage)
                    node_usage = _workflow_artifacts._merge_workflow_usage(node_usage, delta)
                    if reply.startswith("⚠️"):
                        raise RuntimeError(reply)
                    reply = _workflow_artifacts._normalize_presentation_contract_reply(render_type, reply)
            if render_type == "presentation":
                reply, approved_design, approved_outline = _workflow_artifacts._bind_approved_presentation_inputs(run, reply)
            with _contracts._workflow_runs_lock:
                run["hermes_session_id"] = hermes_sid
                state.update({"status": "succeeded", "output": reply, "usage": node_usage})
                artifact_kind = (
                    "final" if node.get("node_type") == "OUTPUT_FORMAT"
                    else "review" if node.get("node_type") == "FILTER_PASS"
                    else "source" if node.get("node_type") == "KNOWLEDGE_RETRIEVAL"
                    else "draft"
                )
                artifact_contract = contract
                approval_gate = str((node.get("parameters") or {}).get("approval_gate") or "")
                _persistence._workflow_event(
                    run,
                    "node_succeeded",
                    node_id=node_id,
                    progress=int(((position + 1) / max(1, len(order))) * 100),
                    usage=node_usage,
                    route={
                        "model": node_usage.get("model"),
                        "provider": node_usage.get("provider"),
                        "reason": "Hermes 多模型路由按当前 Profile、任务能力与回退策略选择",
                    },
                    artifact={
                        "kind": artifact_kind,
                        "title": str(node.get("name") or node_id),
                        "content": reply,
                        "source_kind": "hermes_output",
                        **artifact_contract,
                        "approval_gate": approval_gate or None,
                        "artifact_version": state["attempt"],
                        "approved_design": approved_design,
                        "approved_outline": approved_outline,
                    },
                    message=f"完成：{node.get('name') or node_id}",
                )
                if approval_gate and node_id not in set(run.get("approved_gates") or []):
                    run["status"] = "awaiting_approval"
                    _persistence._workflow_event(run, "run_awaiting_approval", node_id=node_id, approval_gate=approval_gate, artifact_version=state["attempt"], message=f"等待确认：{node.get('name') or node_id}")
                    return
                if int(run["usage"].get("budget_tokens") or 0) > int(run.get("max_tokens") or 0):
                    raise RuntimeError(
                        "Hermes 工作流 Token 预算已耗尽"
                        f"（预算口径 {run['usage'].get('budget_tokens', 0)} / {run.get('max_tokens', 0)}）"
                    )
        with _contracts._workflow_runs_lock:
            run["status"] = "awaiting_review"
            _persistence._workflow_event(
                run,
                "run_completed",
                progress=100,
                usage=run.get("usage") or {},
                message="Hermes 执行完成，等待成果复核",
            )
    except Exception as exc:
        with _contracts._workflow_runs_lock:
            run["status"] = "failed"
            run["error"] = str(exc)[:2000]
            running_node = next(
                (node_id for node_id, state in (run.get("nodes") or {}).items() if state.get("status") == "running"),
                None,
            )
            if running_node:
                run["nodes"][running_node]["status"] = "failed"
            _persistence._workflow_event(
                run,
                "run_failed",
                node_id=running_node,
                error=run["error"],
                message="Hermes 工作流执行失败",
            )
    finally:
        with _contracts._workflow_runs_lock:
            _contracts._workflow_threads.pop(execution_id, None)
            _persistence._save_workflow_runs()


def _start_workflow_thread(execution_id: str) -> None:
    with _contracts._workflow_runs_lock:
        existing = _contracts._workflow_threads.get(execution_id)
        if existing and existing.is_alive():
            return
        thread = threading.Thread(
            target=_workflow_run_sync,
            args=(execution_id,),
            daemon=True,
            name=f"workflow-{execution_id[:16]}",
        )
        _contracts._workflow_threads[execution_id] = thread
        thread.start()


def _workflow_plan_prompt(body: _contracts.WorkflowPlanRequest) -> str:
    return (
        "你是 Hermes 工作流规划器。将需求编译为通用、可编辑、无环的 WorkflowDSLPlan。\n"
        "只输出一个 JSON 对象，不要 Markdown 代码围栏或解释。\n"
        "根字段必须为 plan_id/name/version/nodes/edges。每个节点必须包含 "
        "id/node_type/name/parameters；node_type 只能是 KNOWLEDGE_RETRIEVAL、"
        "LLM_INFERENCE、PROMPT_TRANSFORM、FILTER_PASS、AGGREGATION、OUTPUT_FORMAT。\n"
        "parameters 必须包含 agent_id、max_tokens、knowledge_scope、allow_network，并按需包含 "
        "query/instruction/output_format/requires_review。单节点 max_tokens 必须在 1..128000 内；"
        "最后必须有 FILTER_PASS 与 OUTPUT_FORMAT。\n"
        f"workflow_id={body.workflow_id}\n标题={body.title}\n目标={body.description}\n"
        f"交付物={body.deliverable}\n知识范围={json.dumps(body.knowledge_scope, ensure_ascii=False)}\n"
        f"可用 Agent={json.dumps(body.allowed_agents, ensure_ascii=False)}\n"
        f"联网权限={body.allow_network}\n总 Token 上限={body.max_tokens}\n"
        f"修改意见={body.revision_note or '无'}"
    )


def _execute_planning_run(run_id: str) -> None:
    try:
        with _contracts._planning_runs_lock:
            run = _persistence._planning_runs.get(run_id)
            if not run or run.get("status") == "completed":
                return
            run["status"] = "running"
            run["error"] = ""
            _persistence._planning_event(
                run,
                "planner",
                "Hermes 规划会话已启动",
                status="running",
                tool="hermes_planner",
                detail="正在生成可编辑工作流 DAG",
            )
            request_data = dict(run["request"])
            _persistence._save_planning_runs()
        body = _contracts._contracts.WorkflowPlanningStartRequest(**request_data)
        reply, hermes_sid, usage = _persistence._run_hermes_with_usage(
            _workflow_plan_prompt(body)[:_contracts.MAX_INPUT], None
        )
        plan = _workflow_artifacts._extract_json_object(reply)
        plugin_steps: list[dict[str, Any]] = []
        if hermes_sid:
            try:
                rows = _session_runtime._readback_delta(hermes_sid, 0)
                plugin_steps = [
                    step.model_dump()
                    for step in extract_steps(rows)
                    if step.type in {"tool_call", "skill_load", "agent_spawn"}
                ]
            except Exception as exc:
                print(f"[bridge] 规划步骤回读失败·降级里程碑: {exc}")
        with _contracts._planning_runs_lock:
            run = _persistence._planning_runs[run_id]
            for step in plugin_steps:
                _persistence._planning_event(
                    run,
                    step["type"],
                    step["title"],
                    tool=step["title"].split(":", 1)[-1].strip(),
                    detail=step.get("detail", ""),
                )
            _persistence._planning_event(
                run,
                "planner",
                "Hermes 已返回工作流 DAG",
                tool="workflow_dag",
                detail=f"{len(plan.get('nodes') or [])} 个节点",
            )
            run["plan"] = plan
            run["usage"] = _workflow_artifacts._usage_delta(usage)
            run["hermes_session_id"] = hermes_sid
            run["status"] = "completed"
            run["updated_at"] = time.time()
            _persistence._save_planning_runs()
    except Exception as exc:
        with _contracts._planning_runs_lock:
            run = _persistence._planning_runs.get(run_id)
            if run:
                run["status"] = "failed"
                run["error"] = str(exc)[:500]
                _persistence._planning_event(
                    run,
                    "planner",
                    "Hermes 规划失败",
                    status="failed",
                    detail=str(exc)[:300],
                )
                _persistence._save_planning_runs()
    finally:
        with _contracts._planning_runs_lock:
            _contracts._planning_threads.pop(run_id, None)


def _start_planning_thread(run_id: str) -> None:
    with _contracts._planning_runs_lock:
        current = _contracts._planning_threads.get(run_id)
        if current and current.is_alive():
            return
        thread = threading.Thread(
            target=_execute_planning_run,
            args=(run_id,),
            daemon=True,
            name=f"workflow-plan-{run_id[-8:]}",
        )
        _contracts._planning_threads[run_id] = thread
        thread.start()


async def start_workflow_plan(
    body: _contracts.WorkflowPlanningStartRequest,
    x_hermes_internal_token: str | None = Header(None),
):
    _persistence._require_internal(x_hermes_internal_token)
    run_id = f"wfplan_{body.planning_job_id}"
    with _contracts._planning_runs_lock:
        current = _persistence._planning_runs.get(run_id)
        if current and current.get("idempotency_key") != body.idempotency_key:
            raise HTTPException(status_code=409, detail="planning idempotency conflict")
        if not current:
            _persistence._planning_runs[run_id] = {
                "run_id": run_id,
                "planning_job_id": body.planning_job_id,
                "idempotency_key": body.idempotency_key,
                "request": body.model_dump(),
                "status": "queued",
                "events": [],
                "next_seq": 1,
                "plan": None,
                "error": "",
                "created_at": time.time(),
                "updated_at": time.time(),
            }
            _persistence._save_planning_runs()
    _start_planning_thread(run_id)
    return {"run_id": run_id, "status": _persistence._planning_runs[run_id]["status"]}


async def workflow_plan_status(
    run_id: str,
    after: int = Query(0, ge=0),
    x_hermes_internal_token: str | None = Header(None),
):
    _persistence._require_internal(x_hermes_internal_token)
    with _contracts._planning_runs_lock:
        run = _persistence._planning_runs.get(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="planning run not found")
        return {
            "run_id": run_id,
            "status": run.get("status"),
            "events": [event for event in run.get("events", []) if int(event["id"]) > after],
            "plan": run.get("plan") if run.get("status") == "completed" else None,
            "usage": run.get("usage") or {},
            "error": run.get("error") or "",
        }


async def workflow_plan(
    body: _contracts.WorkflowPlanRequest,
    x_hermes_internal_token: str | None = Header(None),
):
    """Backward-compatible synchronous planning endpoint."""
    _persistence._require_internal(x_hermes_internal_token)
    reply, _, usage = await asyncio.to_thread(
        _persistence._run_hermes_with_usage,
        _workflow_plan_prompt(body)[:_contracts.MAX_INPUT],
        None,
    )
    try:
        plan = _workflow_artifacts._extract_json_object(reply)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "plan": plan,
        "usage": _workflow_artifacts._usage_delta(usage),
        "route": {
            "model": usage.get("model"),
            "provider": usage.get("provider"),
            "reason": "Hermes 多模型路由根据规划任务与当前 Profile 自动选择",
        },
    }


def _execute_agent_evaluation(run_id: str) -> None:
    try:
        with _contracts._evaluation_runs_lock:
            run = _persistence._evaluation_runs.get(run_id)
            if not run or run.get("status") == "completed":
                return
            run["status"] = "running"
            _persistence._evaluation_event(
                run, "evaluation_started", "正式评估已启动",
                status="running", category="evaluation",
            )
            request = dict(run["request"])
        agent_config = request.get("agent_config") or {}
        suite = request.get("suite") or []
        prompt = (
            "你是独立 Agent 评估器。根据 Agent 配置与测试套件完成审计。"
            "只输出 JSON 对象，字段为 score(0-100)、results；results 每项包含 "
            "id/name/status(passed|warning|failed)/score(0-100)/detail。不得虚构工具执行。\n"
            f"Agent 配置={json.dumps(agent_config, ensure_ascii=False)}\n"
            f"测试套件={json.dumps(suite, ensure_ascii=False)}"
        )[:_contracts.MAX_INPUT]
        reply, hermes_sid, raw_usage = _persistence._run_hermes_with_usage(prompt, None)
        payload = _workflow_artifacts._extract_json_object(reply)
        plugin_steps: list[dict[str, Any]] = []
        if hermes_sid:
            try:
                plugin_steps = [
                    step.model_dump() for step in extract_steps(_session_runtime._readback_delta(hermes_sid, 0))
                    if step.type in {"tool_call", "skill_load", "agent_spawn"}
                ]
            except Exception:
                plugin_steps = []
        with _contracts._evaluation_runs_lock:
            run = _persistence._evaluation_runs[run_id]
            for step in plugin_steps:
                _persistence._evaluation_event(
                    run, step["type"], step["title"],
                    category=step["type"], tool=step["title"].split(":", 1)[-1].strip(),
                    detail=step.get("detail", ""),
                )
            run["results"] = payload.get("results") or []
            run["score"] = max(0, min(100, float(payload.get("score") or 0)))
            run["usage"] = _workflow_artifacts._usage_delta(raw_usage)
            run["hermes_session_id"] = hermes_sid
            run["status"] = "completed"
            _persistence._evaluation_event(run, "evaluation_completed", "Agent 正式评估完成")
    except Exception as exc:
        with _contracts._evaluation_runs_lock:
            run = _persistence._evaluation_runs.get(run_id)
            if run:
                run["status"] = "failed"
                run["error"] = str(exc)[:500]
                _persistence._evaluation_event(
                    run, "evaluation_failed", "Agent 正式评估失败",
                    status="failed", detail=str(exc)[:300],
                )
    finally:
        with _contracts._evaluation_runs_lock:
            _contracts._evaluation_threads.pop(run_id, None)


def _start_evaluation_thread(run_id: str) -> None:
    with _contracts._evaluation_runs_lock:
        current = _contracts._evaluation_threads.get(run_id)
        if current and current.is_alive():
            return
        thread = threading.Thread(
            target=_execute_agent_evaluation, args=(run_id,), daemon=True,
            name=f"agent-eval-{run_id[-8:]}",
        )
        _contracts._evaluation_threads[run_id] = thread
        thread.start()


async def start_agent_evaluation(
    body: _contracts.AgentEvaluationRequest,
    x_hermes_internal_token: str | None = Header(None),
):
    _persistence._require_internal(x_hermes_internal_token)
    _persistence._validated_knowledge_claims(
        body.knowledge_capability,
        subject_id=body.run_id,
        policy_version=body.knowledge_policy_version,
    )
    with _contracts._evaluation_runs_lock:
        current = _persistence._evaluation_runs.get(body.run_id)
        if current and current.get("idempotency_key") != body.idempotency_key:
            raise HTTPException(status_code=409, detail="evaluation idempotency conflict")
        if not current:
            _persistence._evaluation_runs[body.run_id] = {
                "run_id": body.run_id,
                "idempotency_key": body.idempotency_key,
                "request": body.model_dump(),
                "status": "queued", "events": [], "next_seq": 1,
                "results": [], "score": 0, "usage": {}, "error": "",
                "created_at": time.time(), "updated_at": time.time(),
            }
            _persistence._save_evaluation_runs()
    _start_evaluation_thread(body.run_id)
    return {"run_id": body.run_id, "status": _persistence._evaluation_runs[body.run_id]["status"]}


async def get_agent_evaluation(
    run_id: str,
    after: int = Query(0, ge=0),
    x_hermes_internal_token: str | None = Header(None),
):
    _persistence._require_internal(x_hermes_internal_token)
    with _contracts._evaluation_runs_lock:
        run = _persistence._evaluation_runs.get(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="evaluation run not found")
        return {
            "run_id": run_id, "status": run.get("status"),
            "events": [item for item in run.get("events") or [] if int(item["seq"]) > after],
            "results": run.get("results") or [], "score": run.get("score") or 0,
            "usage": run.get("usage") or {}, "error": run.get("error") or "",
        }


async def start_workflow_run(
    body: _contracts.WorkflowRunRequest,
    x_hermes_internal_token: str | None = Header(None),
):
    """幂等启动或恢复 Hermes 工作流 Run。"""
    _persistence._require_internal(x_hermes_internal_token)
    claims = _persistence._validated_knowledge_claims(
        body.knowledge_capability,
        subject_id=body.execution_id,
        policy_version=body.knowledge_policy_version,
    )
    allowed = set(str(item) for item in (claims or {}).get("scopes") or [])
    if not set(body.knowledge_scope).issubset(allowed):
        raise HTTPException(status_code=403, detail="knowledge_scope_denied")
    if str((claims or {}).get("tenant_key") or "") != body.tenant_id:
        raise HTTPException(status_code=403, detail="sandbox_identity_denied")
    sandbox = _persistence._tenant_sandbox_from_claims(
        subject_id=body.execution_id,
        knowledge_claims=claims,
        client_claims=None,
    )
    if body.plan.get("process_contract_id"):
        from backend.services.process_contract_registry import dependency_lock_digest

        if body.process_contract_digest != body.plan.get("process_contract_digest"):
            raise HTTPException(status_code=409, detail="process contract digest mismatch")
        if body.activation_revision != body.plan.get("activation_revision"):
            raise HTTPException(status_code=409, detail="activation revision mismatch")
        if body.dependency_lock_digest != dependency_lock_digest(body.plan):
            raise HTTPException(status_code=409, detail="dependency lock digest mismatch")
    _workflow_artifacts._workflow_order(body.plan)
    with _contracts._workflow_runs_lock:
        current = _persistence._workflow_runs.get(body.execution_id)
        if current:
            if current.get("idempotency_key") != body.idempotency_key:
                raise HTTPException(status_code=409, detail="execution idempotency conflict")
            if body.command_id and current.get("command_id") != body.command_id:
                raise HTTPException(status_code=409, detail="command idempotency conflict")
            if current.get("status") in {"interrupted", "queued", "running"}:
                current["cancel_requested"] = False
                _start_workflow_thread(body.execution_id)
            return {
                "execution_id": body.execution_id,
                "status": current.get("status"),
                "hermes_session_id": current.get("hermes_session_id"),
            }
        skill_receipts = []
        try:
            for node in body.plan.get("nodes") or []:
                binding = (node.get("parameters") or {}).get("skill_binding") or {}
                if binding:
                    skill_receipts.append(_contracts._verify_workflow_skill_binding(binding, sandbox))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        run = body.model_dump(mode="json")
        run["command_id"] = body.command_id or f"command:{body.execution_id}"
        run["execution_request_id"] = (
            body.execution_request_id or f"request:{body.execution_id}"
        )
        run["resolved_manifest"] = {
            "process_contract_digest": body.process_contract_digest,
            "dependency_lock_digest": body.dependency_lock_digest,
            "activation_revision": body.activation_revision,
            "skill_receipts": skill_receipts,
        }
        run.update(
            {
                "status": "queued",
                "error": None,
                "events": [],
                "next_seq": 1,
                "nodes": {
                    str(node["id"]): {"status": "pending", "attempt": 0}
                    for node in body.plan.get("nodes") or []
                },
                "usage": {},
                "cancel_requested": False,
                "hermes_session_id": None,
                "approved_gates": [],
                "approved_gate_artifacts": {},
            }
        )
        _persistence._workflow_runs[body.execution_id] = run
        _persistence._workflow_event(run, "run_queued", message="Hermes 工作流已入队")
        _start_workflow_thread(body.execution_id)
    return {"execution_id": body.execution_id, "status": "queued"}


async def get_workflow_run(
    execution_id: str,
    after_seq: int = Query(0, ge=0),
    x_hermes_internal_token: str | None = Header(None),
):
    _persistence._require_internal(x_hermes_internal_token)
    with _contracts._workflow_runs_lock:
        run = _persistence._workflow_runs.get(execution_id)
        if not run:
            raise HTTPException(status_code=404, detail="workflow run not found")
        return {
            "execution_id": execution_id,
            "status": run.get("status"),
            "error": run.get("error"),
            "hermes_session_id": run.get("hermes_session_id"),
            "usage": run.get("usage") or {},
            "nodes": run.get("nodes") or {},
            "events": [
                event for event in run.get("events") or []
                if int(event.get("seq") or 0) > after_seq
            ],
        }


async def cancel_workflow_run(
    execution_id: str,
    x_hermes_internal_token: str | None = Header(None),
):
    _persistence._require_internal(x_hermes_internal_token)
    with _contracts._workflow_runs_lock:
        run = _persistence._workflow_runs.get(execution_id)
        if not run:
            raise HTTPException(status_code=404, detail="workflow run not found")
        run["cancel_requested"] = True
        active_agent = _contracts._workflow_agents.get(execution_id)
        if active_agent is not None:
            try:
                active_agent.interrupt(message="workflow-cancelled")
            except TypeError:
                active_agent.interrupt()
            except Exception:
                pass
        _persistence._workflow_event(run, "cancel_requested", message="已请求 Hermes 取消执行")
        return {"ok": True, "status": run.get("status")}


async def retry_workflow_run(
    execution_id: str,
    body: _contracts.WorkflowRetryRequest,
    x_hermes_internal_token: str | None = Header(None),
):
    _persistence._require_internal(x_hermes_internal_token)
    with _contracts._workflow_runs_lock:
        run = _persistence._workflow_runs.get(execution_id)
        if not run:
            raise HTTPException(status_code=404, detail="workflow run not found")
        order = _workflow_artifacts._workflow_order(run["plan"])
        target = body.from_node_id
        if target is None:
            target = next(
                (node_id for node_id in order if (run.get("nodes") or {}).get(node_id, {}).get("status") == "failed"),
                None,
            )
        if target not in order:
            raise HTTPException(status_code=409, detail="no retryable node")
        start = order.index(target)
        for node_id in order[start:]:
            run["nodes"][node_id] = {"status": "pending", "attempt": run["nodes"].get(node_id, {}).get("attempt", 0)}
        if body.revision_comment:
            run.setdefault("revision_feedback", {})[target] = body.revision_comment.strip()
        run["approved_gates"] = [node_id for node_id in (run.get("approved_gates") or []) if node_id not in set(order[start:])]
        run["approved_gate_artifacts"] = {node_id: value for node_id, value in (run.get("approved_gate_artifacts") or {}).items() if node_id not in set(order[start:])}
        run["status"] = "queued"
        run["error"] = None
        run["cancel_requested"] = False
        _persistence._workflow_event(
            run,
            "retry_queued",
            node_id=target,
            message="已按用户反馈重新生成" if body.revision_comment else "失败节点已重新入队",
        )
        _start_workflow_thread(execution_id)
        return {"ok": True, "status": "queued", "from_node_id": target}


from . import contracts as _contracts, persistence as _persistence, session_runtime as _session_runtime, workflow_artifacts as _workflow_artifacts  # noqa: E402
