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


_chat_run_store: DurableChatRunStore | None = None


_POLICY_SCOPED_SESSION_KEY_RE = re.compile(
    r"^(t[0-9a-f]{12}-u[0-9a-f]{12})-p[0-9a-z]{1,24}-(.+)$"
)


def _stable_session_key(user_id: str) -> str:
    """Normalize legacy policy-scoped keys to stable tenant/user identities."""
    match = _POLICY_SCOPED_SESSION_KEY_RE.match(str(user_id or ""))
    if not match:
        return str(user_id or "")
    return f"{match.group(1)}-{match.group(2)}"


def _append_session_messages(
    session_db: Any, session_id: str, messages: list[dict[str, str]]
) -> int:
    """Import recovery history across supported Hermes SessionDB versions."""
    append_batch = getattr(session_db, "append_messages_batch", None)
    if callable(append_batch):
        result = append_batch(session_id, messages)
        return result if isinstance(result, int) else len(messages)
    appended = 0
    for message in messages:
        session_db.append_message(
            session_id,
            role=message["role"],
            content=message["content"],
        )
        appended += 1
    return appended


def _resolve_hermes_session(user_id: str) -> str | None:
    """Resolve a user's session in the same state.db where it was created."""
    hermes_sid = _persistence._user_session_map.get(user_id)
    state_db = _persistence._user_state_db_map.get(user_id)
    if not hermes_sid:
        # One-time compatibility migration for sessions created before policy
        # version was removed from identity. Never guess by JSON/dict order when
        # historical policy versions point at different Hermes sessions.
        aliases: dict[tuple[str, str], str] = {}
        for key, candidate_sid in _persistence._user_session_map.items():
            if _stable_session_key(key) != user_id or not candidate_sid:
                continue
            candidate_db = _persistence._user_state_db_map.get(key)
            if _persistence._session_exists(candidate_sid, candidate_db):
                aliases[(candidate_sid, str(candidate_db or ""))] = key
        if len(aliases) > 1:
            raise RuntimeError("ambiguous_legacy_session_mapping")
        if aliases:
            (hermes_sid, encoded_db), _legacy_key = next(iter(aliases.items()))
            state_db = encoded_db or None
            _persistence._user_session_map[user_id] = hermes_sid
            if state_db:
                _persistence._user_state_db_map[user_id] = state_db
            _persistence._save_mapping()
            _persistence._save_state_db_mapping()
    if hermes_sid and not _persistence._session_exists(hermes_sid, state_db):
        print(f"[bridge] user {user_id} session {hermes_sid} 已失效·清除映射·新建")
        _persistence._user_session_map.pop(user_id, None)
        _persistence._user_state_db_map.pop(user_id, None)
        _persistence._save_mapping()
        _persistence._save_state_db_mapping()
        hermes_sid = None
    return hermes_sid


def _update_session_mapping(
    user_id: str, hermes_sid: str, state_db: str | Path | None = None
) -> None:
    """Persist user -> Hermes session and its physical state.db binding."""
    _persistence._user_session_map[user_id] = hermes_sid
    _persistence._save_mapping()
    if state_db is not None:
        _persistence._user_state_db_map[user_id] = str(state_db)
        _persistence._save_state_db_mapping()
    print(f"[bridge] 会话映射: user={user_id} -> session={hermes_sid}")


def _get_baseline_id(
    session_id: str | None, state_db: str | None = None
) -> int:
    """Snapshot the max message ID from the session's owning state.db."""
    db_path = state_db or _contracts.STATE_DB
    if not session_id or not os.path.exists(db_path):
        return 0
    try:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                "SELECT COALESCE(MAX(id), 0) FROM messages WHERE session_id=?",
                (session_id,),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except Exception as e:
        print(f"[bridge] 水位线快照失败·按 0 处理: {e}")
        return 0


def _readback_delta(
    session_id: str | None, baseline_id: int, state_db: str | None = None
) -> list[dict]:
    """Read this turn's rows from the session's owning state.db."""
    db_path = state_db or _contracts.STATE_DB
    if not session_id or not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, session_id, role, content, reasoning_content, tool_name, tool_calls "
            "FROM messages WHERE session_id=? AND id>? ORDER BY id ASC",
            (session_id, baseline_id),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _build_status_phrase(last_row) -> str:
    """latest_step 双驱动之一：tool_start 短语。

    最新一条为 tool 消息 → 「正在执行: <tool_name>」微信式进度短语。
    """
    role = (last_row["role"] or "").strip()
    if role == "tool":
        name = (last_row["tool_name"] or "").strip()
        return f"正在执行: {name}" if name else "正在执行工具"
    return ""


def _thought_summary(rows) -> str:
    """latest_step 双驱动之二：从最近 thought（assistant.reasoning_content）取摘要。

    截断 60 字符 + 省略号，避免长思考文本撑爆进度行。
    """
    for row in reversed(rows):
        if (row["role"] or "").strip() != "assistant":
            continue
        rc = (row["reasoning_content"] or "").strip()
        if rc:
            return rc[:60] + ("…" if len(rc) > 60 else "")
    return ""


def _latest_step_text(rows) -> str:
    """latest_step 双驱动合成：tool_start 短语优先，无则 thought 摘要，再兜底文案。"""
    last = rows[-1]
    role = (last["role"] or "").strip()
    phrase = _build_status_phrase(last)
    if phrase:
        return phrase
    if role == "assistant":
        summary = _thought_summary(rows)
        if summary:
            return f"思考中: {summary}"
        if (last["content"] or "").strip():
            return "已生成回答"
        return "思考中"
    if role == "user":
        return "正在初始化…"
    return "处理中"


def _pending_clarify(user_id: str) -> dict | None:
    """从 clarify_gateway._entries 取未 resolve 的 pending entry（response is None）。

    只返回当前 user 的 entry（session_key 匹配）；已 resolve/已消费（wait_for_response
    超时清理）的 entry 自然被过滤。载荷对齐前端 ClarifyBlock：question/choices/
    multi_select/clarify_id。
    """
    cg = None
    try:
        cg = _contracts._get_clarify_gateway()
        entries = getattr(cg, "_entries", None)
        lock = getattr(cg, "_lock", None)
        if entries is None:
            return None
        if lock is not None:
            with lock:
                items = list(entries.values())
        else:
            items = list(entries.values())
        # 诊断日志：多步 Clarify 卡丢失定位（微信模式 status 轮询读 pending entry）
        if items:
            debug_entries = [
                f"{getattr(e, 'session_key', '?')[:20]}/resp={getattr(e, 'response', '§') is not None}"
                for e in items
            ]
            print(f"[bridge] _pending_clarify entries={len(items)} user={user_id[:20]} list={debug_entries}")
        for entry in items:
            if getattr(entry, "session_key", None) == user_id and getattr(entry, "response", "§") is None:
                run = _receipts._stream_run_get(user_id)
                issued = float((run or {}).get("clarify_issued") or time.monotonic())
                return {
                    "clarify_id": entry.clarify_id,
                    "request_id": (run or {}).get("request_id"),
                    "question": entry.question,
                    "choices": list(entry.choices) if entry.choices else [],
                    # 兼容服务器 Hermes v0.19.0（_ClarifyEntry 无 multi_select 字段，仅 awaiting_text）
                    "multi_select": bool(getattr(entry, "multi_select", False)),
                    "expires_in_seconds": max(
                        0, int(_contracts.CLARIFY_TIMEOUT_SECONDS - (time.monotonic() - issued))
                    ),
                }
    except Exception as e:
        print(f"[bridge] pending clarify 查询失败·忽略: {e}")
    return None


def _knowledge_action_authorized(
    client_capabilities: list[str] | set[str] | tuple[str, ...],
    *,
    knowledge_claims: dict | None,
    client_context_claims: dict | None,
) -> bool:
    """Treat the client feature bit as transport negotiation, never authority."""
    return bool(
        "knowledge_action_v1" in set(client_capabilities)
        and (
            client_context_claims is not None
            or (
                knowledge_claims is not None
                and "user_notes" in set(knowledge_claims.get("sources") or [])
            )
        )
    )


def _interrupt_and_discard(user_id: str, run_id: str | None) -> None:
    """超时回收：interrupt agent + discard run（watchdog 与 status 命中 timeout 共用路径）。"""
    state = _receipts._stream_run_get(user_id)
    if state:
        agent = state.get("agent_holder", [None])[0]
        if agent is not None:
            try:
                agent.interrupt()
            except Exception:
                pass
    _receipts._stream_run_discard(user_id, run_id)


def _query_status(
    hermes_sid: str | None, user_id: str | None = None, offset: int = 0
) -> dict:
    """只读查询 state.db 会话状态，返回四元组快照（方案 v5）。

    返回字段：
    - status     : completed / running / timeout / not_found（兼容旧客户端）
    - phase      : boot / reasoning / tool / clarify / completed / timeout / not_found
    - latest_step: tool_start 短语（build_status_phrase）+ thought 摘要双驱动
    - reasoning  : 思维链步骤；offset>0 时仅返回消息 id>offset 的新条（增量轮询）
    - clarify    : 未 resolve 的 pending clarify entry（无则 null）
    - last_message_id: 当前最大消息 id（前端据此推进 offset）
    - answer     : completed 时完整回答
    - consumed   : 消费水位线标记（consume=1 推进）

    timeout 判定（单一时钟源，对齐 watchdog）：
    - run 存在   → run.start_ts 超 STREAM_MAX_DURATION_SECONDS → timeout，
                   命中同时 interrupt+discard（复用 watchdog 路径）
    - run 不存在 → 会话 ended 无答案 / 最后消息超同一运行时上限无更新 → timeout
                  （bridge 重启后旧 run 进程消亡，无双 run，按 state.db 判定）
    显式移除历史「>300s 无更新」stale 判定。
    """
    wm_key = user_id or hermes_sid or ""
    run = _receipts._stream_run_get(user_id or "")
    state_db = str(
        (run or {}).get("state_db")
        or _persistence._user_state_db_map.get(user_id or "")
        or _contracts.STATE_DB
    )
    empty = {
        "status": "not_found",
        "phase": "not_found",
        "answer": "",
        "reasoning": [],
        "latest_step": "",
        "clarify": None,
        "last_message_id": 0,
    }

    def _running_fallback() -> dict:
        # 微信模式提交后立即轮询（2s）vs agent 构建 10s+：映射未写期间
        # 必须认 _stream_runs（进程内流式 run 已注册）→ running 兜底，绝不误报 not_found
        if _contracts._is_in_flight(user_id) or _receipts._stream_run_get(user_id) is not None:
            return {"status": "running", "answer": "", "reasoning": [], "latest_step": "处理中"}
        return empty

    if not hermes_sid:
        return _running_fallback()
    if not os.path.exists(state_db):
        return _running_fallback()
    try:
        conn = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True)
    except Exception as e:
        print(f"[bridge] state.db 只读连接失败: {e}")
        return _running_fallback()
    try:
        conn.row_factory = sqlite3.Row
        srow = conn.execute(
            "SELECT ended_at, archived FROM sessions WHERE id=? LIMIT 1",
            (hermes_sid,),
        ).fetchone()
        if srow is None or srow["archived"]:
            return _running_fallback()

        rows = conn.execute(
            "SELECT id, role, content, reasoning_content, tool_name, tool_calls, timestamp "
            "FROM messages WHERE session_id=? AND active=1 ORDER BY id ASC",
            (hermes_sid,),
        ).fetchall()
        if not rows:
            return {
                "status": "running",
                "phase": "boot",
                "answer": "",
                "reasoning": [],
                "latest_step": "正在初始化…",
                "clarify": None,
                "last_message_id": 0,
            }

        last = rows[-1]
        role = (last["role"] or "").strip()
        content = (last["content"] or "").strip()
        ts = last["timestamp"] or 0
        max_msg_id = max(int(r["id"]) for r in rows)
        latest_step = _latest_step_text(rows)

        # pending clarify 优先（agent 阻塞等用户点选时最后一条可能是引导语，
        # 必须先于 completed 判定，避免误判完成）
        clarify = _pending_clarify(user_id or "")

        # run 存在性判定（单一时钟源）：start_ts 超 720s → timeout + interrupt+discard
        if run is not None:
            start_ts = run.get("start_ts") or 0
            if time.monotonic() - start_ts > _contracts.STREAM_MAX_DURATION_SECONDS:
                print(
                    f"[bridge] status 命中 timeout: user={user_id} run 超 "
                    f"{_contracts.STREAM_MAX_DURATION_SECONDS}s·interrupt+discard"
                )
                _interrupt_and_discard(user_id or "", run.get("run_id"))
                return {
                    "status": "timeout",
                    "phase": "timeout",
                    "answer": "",
                    "reasoning": [],
                    "latest_step": latest_step,
                    "clarify": None,
                    "last_message_id": max_msg_id,
                }

        # completed：最后一条 assistant 且内容非空（且无 pending clarify 阻塞）
        if role == "assistant" and content and clarify is None:
            steps = [s.model_dump() for s in extract_steps([dict(r) for r in rows])]
            if run is not None:
                # A detached SSE has no live generator left to consume the done
                # frame and clear its slot. The durable assistant row is the
                # terminal truth, so release the run atomically here.
                _receipts._stream_run_discard(user_id or "", run.get("run_id"))
            return {
                "status": "completed",
                "phase": "completed",
                "answer": content,
                "reasoning": steps,
                "latest_step": "",
                "clarify": None,
                "last_message_id": max_msg_id,
                "consumed": last["id"] <= _persistence._get_watermark(wm_key),
            }

        # 有 pending clarify → 卡在澄清等待（优先级高于 running 细分）
        if clarify is not None:
            return {
                "status": "running",
                "phase": "clarify",
                "answer": "",
                "reasoning": [],
                "latest_step": latest_step,
                "clarify": clarify,
                "last_message_id": max_msg_id,
            }

        # run 不存在（重启/被杀/异常结束）且非 completed：
        # 会话已 ended 无答案，或最后消息超 720s 无新消息 → timeout
        # （run 存在且未超预算时由 agent 线程保障，不适用此判定）
        if run is None:
            session_ended = srow["ended_at"] is not None
            no_progress = (time.time() - ts) > _contracts.STREAM_MAX_DURATION_SECONDS
            if session_ended or no_progress:
                return {
                    "status": "timeout",
                    "phase": "timeout",
                    "answer": "",
                    "reasoning": [],
                    "latest_step": latest_step,
                    "clarify": None,
                    "last_message_id": max_msg_id,
                }

        # running 细分（boot/reasoning/tool）：reasoning 支持 offset 增量
        delta_rows = [dict(r) for r in rows if int(r["id"]) > offset]
        steps = [s.model_dump() for s in extract_steps(delta_rows)] if delta_rows else []
        if role == "tool":
            phase = "tool"
        elif role == "assistant":
            phase = "reasoning"
        else:
            phase = "boot"
        return {
            "status": "running",
            "phase": phase,
            "answer": "",
            "reasoning": steps,
            "latest_step": latest_step,
            "clarify": None,
            "last_message_id": max_msg_id,
        }
    finally:
        conn.close()


def _mark_consumed(user_id: str, hermes_sid: str | None) -> None:
    """将当前会话最新消息 id 推进到消费水位线（断点 0ms 回读后标记已消费）。"""
    if not hermes_sid:
        return
    try:
        _persistence._set_watermark(
            user_id,
            _get_baseline_id(hermes_sid, _persistence._user_state_db_map.get(user_id)),
        )
    except Exception as e:
        print(f"[bridge] 标记消费失败·忽略: {e}")


def _durable_status(
    session_id: str, tenant_id: str, user_id: str, offset: int = 0
) -> dict | None:
    """Project the owner's latest durable Run onto the legacy status contract."""
    if _chat_run_store is None:
        raise HTTPException(status_code=503, detail="durable_run_store_unavailable")
    owner_hash = _chat_run_store.tenant_user_hash(tenant_id, user_id)
    run, events, clarify_row = _chat_run_store.status_snapshot(
        tenant_user_hash=owner_hash, session_id=session_id
    )
    if run is None:
        return None
    run_id = str(run["run_id"])
    exact_status = str(run["status"])
    execution_available = _contracts._durable_worker_is_live()
    status = (
        "running"
        if exact_status in {"queued", "running", "stalled"}
        else exact_status
    )
    if exact_status in {"failed", "cancelled"}:
        # Legacy clients understand timeout as the terminal interrupted state.
        # Preserve the exact durable state separately in run_status/phase.
        status = "timeout"
    phase = exact_status
    latest_step = ""
    reasoning = []
    reasoning_by_call_id = {}
    for event in events:
        event_type = str(event.get("type") or "")
        if event_type == "status":
            phase = str(event.get("phase") or phase)
            latest_step = str(event.get("detail") or latest_step)
        elif event_type == "tool_start":
            phase = "tool"
            latest_step = str(event.get("label") or event.get("tool") or "正在执行工具")
            if exact_status in {"completed", "failed", "cancelled"} or int(
                event.get("event_sequence") or 0
            ) > max(0, offset):
                call_id = str(event.get("id") or "")
                reasoning.append(
                    {
                        "type": "tool_call",
                        "title": latest_step,
                        "detail": "",
                        "status": "running",
                    }
                )
                if call_id:
                    reasoning_by_call_id[call_id] = len(reasoning) - 1
        elif event_type == "tool_complete":
            phase = "tool"
            latest_step = f"工具执行完成: {event.get('tool') or ''}".rstrip()
            if exact_status in {"completed", "failed", "cancelled"} or int(
                event.get("event_sequence") or 0
            ) > max(0, offset):
                call_id = str(event.get("id") or "")
                if call_id and call_id in reasoning_by_call_id:
                    reasoning[reasoning_by_call_id[call_id]]["status"] = "completed"
                else:
                    reasoning.append(
                        {
                            "type": "tool_call",
                            "title": latest_step,
                            "detail": "",
                            "status": "completed",
                        }
                    )
    clarify = None
    if clarify_row is not None:
        phase = "clarify"
        clarify = {
            "clarify_id": clarify_row["clarify_id"],
            "request_id": clarify_row["request_id"],
            "question": clarify_row["question"],
            "choices": clarify_row["choices"],
            "multi_select": bool(clarify_row["multi_select"]),
            "expires_in_seconds": clarify_row["expires_in_seconds"],
        }
    if exact_status in {"completed", "failed", "cancelled"}:
        phase = exact_status
        latest_step = ""
        clarify = None
    elif not execution_available:
        status = "unavailable"
        phase = "maintenance"
        latest_step = _contracts._WORKER_MAINTENANCE["message"]
        clarify = None
    cursor = int(run["event_sequence"])
    return {
        "status": status,
        "run_status": exact_status,
        "phase": phase,
        "answer": str(
            run["final_answer"]
            if exact_status == "completed"
            else run["partial_answer"]
        ),
        "reasoning": reasoning,
        "latest_step": latest_step,
        "clarify": clarify,
        "last_message_id": cursor,
        "event_sequence": cursor,
        "run_id": run_id,
        "consumed": float(run.get("consumed_at") or 0) > 0,
        **({
            "execution_available": False,
            "execution_error": dict(_contracts._WORKER_MAINTENANCE),
        } if exact_status in {"queued", "running", "stalled"} and not execution_available else {}),
    }


def _clean_ansi(text: str) -> str:
    """清洗 ANSI 转义序列（hermes serve PTY 输出包含颜色/光标控制码）。"""
    return _contracts.ANSI_ESCAPE_RE.sub('', text)


async def _stream_from_ws_pty(goal: str, session_id: str | None = None):
    """通过 WebSocket 连接 hermes serve /api/pty 端点·实现真实流式。

    协议：
    1. 建立 WS 连接（ws://127.0.0.1:9119/api/pty）
    2. 握手携带 Authorization: Bearer <HERMES_SERVE_TOKEN>
    3. 发送 {"type":"input","data":"<goal>\\n"} 作为用户输入
    4. 持续接收 PTY 输出（含 ANSI 转义）
    5. 清洗 ANSI → 提取 token 流 → 以 SSE data: {type:chunk,content:...} 转发

    失败时抛出异常·由调用方降级到 /v1/chat 非流式。
    """
    import websockets  # 懒加载：WS PTY 默认禁用，无 websockets 依赖也不阻塞启动

    if len(goal) > _contracts.MAX_INPUT:
        goal = goal[:_contracts.MAX_INPUT]

    # 构造 WS 握手 headers
    # ⚠️ 2026-08-10 修复: serve PTY 认证用 ?token= query 参数（非 Authorization 头）·
    #    实测 ws://127.0.0.1:9119/api/pty?token=<TOKEN> 握手成功（否则 403）
    ws_headers = {}

    ws_url = _contracts.HERMES_WS_URL
    if _contracts.HERMES_SERVE_TOKEN:
        sep = "&" if "?" in ws_url else "?"
        ws_url = f"{ws_url}{sep}token={_contracts.HERMES_SERVE_TOKEN}"

    print(f"[bridge] WS PTY 连接: {_contracts.HERMES_WS_URL} (query token)")

    async with websockets.connect(
        ws_url,
        additional_headers=ws_headers,
        open_timeout=10,
        close_timeout=5,
    ) as ws:
        print("[bridge] WS PTY 已连接·发送 goal")

        # 发送用户输入（PTY 协议：原始文本·非 JSON·实测 web_server.py writer loop）
        # ⚠️ 2026-08-10 修复: 之前发 {"type":"input","data":...} JSON 被当纯文本写入 PTY
        await ws.send(goal + "\n")

        # 持续接收 PTY 输出并转发为 SSE
        full_reply = ""
        # ⚠️ 2026-08-10 临时: WS PTY 挂起未通·加 8s 首帧超时·无输出即降级（流式做好后移除）
        try:
            first_frame = await asyncio.wait_for(ws.recv(), timeout=8)
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            print("[bridge] WS PTY 8s 无输出·降级")
            raise TimeoutError("WS PTY 无输出超时") from None

        async def _frame_gen(first):
            yield first
            async for m in ws:
                yield m

        try:
            async for raw_msg in _frame_gen(first_frame):
                # 解析 WS 消息
                try:
                    msg = json.loads(raw_msg)
                    msg_type = msg.get("type", "")
                    text = msg.get("data", "") or msg.get("content", "") or ""
                except (json.JSONDecodeError, AttributeError):
                    # 非 JSON 消息视为纯文本
                    text = str(raw_msg)
                    msg_type = "output"

                # 清洗 ANSI 转义序列
                cleaned = _clean_ansi(text)

                # 跳过空内容
                if not cleaned.strip() and not cleaned:
                    continue

                full_reply += cleaned

                # 以 SSE 格式转发给前端
                sse_payload = json.dumps({
                    "type": "chunk",
                    "content": cleaned,
                }, ensure_ascii=False)
                yield f"data: {sse_payload}\n\n"

                # 检测结束信号
                if msg_type == "done" or msg_type == "exit":
                    break

        except websockets.exceptions.ConnectionClosed:
            print("[bridge] WS PTY 连接关闭·流结束")

        # 发送结束标记
        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"
        print(f"[bridge] WS PTY 流结束·总长度: {len(full_reply)}")


async def _fallback_sse(reply: str):
    """将非流式 reply 包装为标准 SSE 流（与前端契约一致）。

    产出：
      data: {"type": "chunk", "content": "<reply>"}\n\n
      data: {"type": "done", "content": ""}\n\n
    """
    payload = json.dumps({"type": "chunk", "content": reply}, ensure_ascii=False)
    yield f"data: {payload}\n\n"
    done_payload = json.dumps({"type": "done", "content": ""}, ensure_ascii=False)
    yield f"data: {done_payload}\n\n"


async def _stream_from_serve(goal: str, session_id: str | None = None):
    """对接 hermes serve SSE 流式端点·逐 chunk 转发。

    返回异步生成器·产出 SSE 格式字符串（data: {...}\n\n）。
    失败时抛出异常·由调用方降级处理。
    """
    if len(goal) > _contracts.MAX_INPUT:
        goal = goal[:_contracts.MAX_INPUT]

    # 构造 hermes serve 请求
    headers = {"Content-Type": "application/json"}
    if _contracts.HERMES_SERVE_TOKEN:
        headers["Authorization"] = f"Bearer {_contracts.HERMES_SERVE_TOKEN}"

    payload = {
        "message": goal,
        "stream": True,
    }
    if session_id:
        payload["session_id"] = session_id

    # 连接 hermes serve（SSE 流式）
    async with httpx.AsyncClient(timeout=_contracts.SERVE_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{_contracts.HERMES_SERVE_URL}/api/chat",
            json=payload,
            headers=headers,
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(f"hermes serve 返回 {response.status_code}")

            # 逐行读取 SSE 流
            async for line in response.aiter_lines():
                if not line:
                    continue
                # SSE 格式：data: {...}
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        # 转发给前端（保持 SSE 格式）
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    except json.JSONDecodeError:
                        # 非 JSON 行·原样转发
                        yield f"data: {data_str}\n\n"


async def _startup():
    global _chat_run_store
    _chat_run_store = DurableChatRunStore(_contracts.HERMES_CHAT_RUN_DB)
    stalled = _chat_run_store.recover_after_restart()
    if stalled:
        print(f"[bridge] durable chat runs: {stalled} orphaned run(s) marked stalled")
    _persistence._load_mapping()
    _persistence._load_state_db_mapping()
    _persistence._load_watermarks()
    _persistence._load_workflow_runs()
    _persistence._load_planning_runs()
    for planning_run_id, planning_run in list(_persistence._planning_runs.items()):
        if planning_run.get("status") in {"queued", "running"}:
            _workflow_runtime._start_planning_thread(planning_run_id)
    _persistence._load_evaluation_runs()
    for evaluation_run_id, evaluation_run in list(_persistence._evaluation_runs.items()):
        if evaluation_run.get("status") in {"queued", "running"}:
            _workflow_runtime._start_evaluation_thread(evaluation_run_id)
    print(f"[bridge] v5 启动·已加载 {len(_persistence._user_session_map)} 条 user→session 映射")
    if not _contracts.HERMES_SERVE_TOKEN:
        print("[bridge] ⚠️ 警告: HERMES_SERVE_TOKEN 未设置·serve 认证可能失败")
    # 保活机制 v6（M-3）：独立守护线程，扫描 detached runs 超时 interrupt+discard
    watchdog = threading.Thread(
        target=_receipts._watchdog_loop,
        daemon=True,
        name="bridge-watchdog",
    )
    watchdog.start()
    print(
        f"[bridge] watchdog 已启动: 间隔 {_contracts.WATCHDOG_INTERVAL_SECONDS}s"
        f"·detached 超时 {_contracts.STREAM_MAX_DURATION_SECONDS}s"
    )


def _block_safe_event(event: dict[str, Any]) -> dict[str, Any] | None:
    event_type = event.get("type")
    if event_type == "delta":
        return None
    if event_type == "done":
        return {key: value for key, value in event.items() if key != "answer"} | {
            "answer_projection": "blocks_v1"
        }
    return event


def _durable_replay_sse(run_id: str, owner_hash: str, *, blocks_v1: bool = False):
    """Replay a duplicate request without starting another Hermes execution."""
    if _chat_run_store is None:
        return
    snapshot = _chat_run_store.get(run_id, tenant_user_hash=owner_hash)
    for event in _chat_run_store.events_after(run_id, 0, tenant_user_hash=owner_hash):
        if blocks_v1:
            event = _block_safe_event(event)
            if event is None:
                continue
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    if blocks_v1:
        page = _chat_run_store.block_page(run_id, tenant_user_hash=owner_hash)
        if any(str(block.get("content") or "").strip() for block in page["blocks"]):
            yield f"data: {json.dumps({'type': 'answer_page', **page}, ensure_ascii=False)}\n\n"
    if snapshot["status"] in {"queued", "running", "stalled"} and not _contracts._durable_worker_is_live():
        yield f"data: {json.dumps({'type': 'error', **_contracts._WORKER_MAINTENANCE, 'run_id': run_id, 'event_sequence': snapshot['event_sequence']}, ensure_ascii=False)}\n\n"
    elif snapshot["status"] in {"queued", "running"}:
        yield f"data: {json.dumps({'type': 'status', 'phase': snapshot['status'], 'detail': '相同任务已在执行', 'run_id': run_id, 'event_sequence': snapshot['event_sequence']}, ensure_ascii=False)}\n\n"
    elif snapshot["status"] == "stalled":
        yield f"data: {json.dumps({'type': 'error', 'code': 'stalled', 'message': '任务在 Worker 重启后等待有界恢复', 'run_id': run_id, 'event_sequence': snapshot['event_sequence']}, ensure_ascii=False)}\n\n"


async def _durable_subscribe_sse(
    run_id: str, owner_hash: str, after: int = 0, *, blocks_v1: bool = False
):
    """Replay and follow a persisted Run; disconnecting never owns its lifecycle."""
    cursor = max(0, int(after))
    yielded_any = False
    last_page_signature = None
    while True:
        if _chat_run_store is None:
            yield f"data: {json.dumps({'type': 'error', 'code': 'run_store_unavailable', 'message': '持久任务存储不可用'}, ensure_ascii=False)}\n\n"
            return
        try:
            events = _chat_run_store.events_after(run_id, cursor, tenant_user_hash=owner_hash)
            snapshot = _chat_run_store.get(run_id, tenant_user_hash=owner_hash)
        except (KeyError, PermissionError):
            yield f"data: {json.dumps({'type': 'error', 'code': 'run_not_found', 'message': '任务不存在'}, ensure_ascii=False)}\n\n"
            return
        for event in events:
            yielded_any = True
            cursor = max(cursor, int(event.get('event_sequence') or 0))
            if blocks_v1:
                event = _block_safe_event(event)
                if event is None:
                    continue
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("type") == "done":
                _chat_run_store.mark_consumed(
                    run_id, tenant_user_hash=owner_hash
                )
        if blocks_v1:
            # answer_page is a bounded replacement snapshot (not an append).
            # Compare content/metadata, not the time-dependent signed cursor.
            page = _chat_run_store.block_page(run_id, tenant_user_hash=owner_hash)
            signature = json.dumps({key: value for key, value in page.items()
                                    if key != "next_cursor"}, sort_keys=True)
            meaningful = any(str(block.get("content") or "").strip() for block in page["blocks"])
            terminal_reset = (last_page_signature is not None
                              and page["status"] in {"completed", "failed", "cancelled"})
            if (meaningful or terminal_reset) and signature != last_page_signature:
                last_page_signature = signature
                yield f"data: {json.dumps({'type': 'answer_page', **page}, ensure_ascii=False)}\n\n"
        status = str(snapshot.get("status") or "")
        if status in {"completed", "failed", "cancelled"}:
            # A worker can commit done between events_after() and get(). Drain
            # that event before closing, including for legacy delta subscribers.
            if cursor < int(snapshot.get("event_sequence") or 0):
                continue
            return
        if not _contracts._durable_worker_is_live():
            yield f"data: {json.dumps({'type': 'error', **_contracts._WORKER_MAINTENANCE, 'run_id': run_id, 'event_sequence': cursor}, ensure_ascii=False)}\n\n"
            return
        if not yielded_any:
            yielded_any = True
            yield f"data: {json.dumps({'type': 'status', 'phase': status or 'queued', 'detail': '任务已进入服务端持久队列', 'run_id': run_id, 'event_sequence': cursor}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.15)


async def durable_chat_run(
    run_id: str,
    after: int = Query(0, ge=0),
    x_knowledge_capability: str | None = Header(None),
    x_hermes_internal_token: str | None = Header(None),
    x_tenant_id: str | None = Header(None),
    x_user_id: str | None = Header(None),
    answer_blocks_v1: bool = False,
):
    """Return an owner-authorized snapshot plus replay events after sequence N."""
    if _chat_run_store is None:
        raise HTTPException(status_code=503, detail="durable_run_store_unavailable")
    try:
        if x_hermes_internal_token:
            _persistence._require_internal_strict(x_hermes_internal_token)
            tenant_id = str(x_tenant_id or "")
            user_id = str(x_user_id or "")
            if not tenant_id or not user_id:
                raise HTTPException(status_code=403, detail="owner_context_required")
        else:
            if not x_knowledge_capability:
                raise HTTPException(status_code=401, detail="knowledge_capability_required")
            claims = verify_capability(x_knowledge_capability)
            tenant_id = str(claims.get("tenant_key") or "")
            user_id = str(claims.get("user_id") or "")
            if not tenant_id or not user_id:
                raise HTTPException(status_code=403, detail="knowledge_scope_denied")
        owner_hash = _chat_run_store.tenant_user_hash(tenant_id, user_id)
        snapshot = _chat_run_store.get(run_id, tenant_user_hash=owner_hash)
        events = _chat_run_store.events_after(run_id, after, tenant_user_hash=owner_hash)
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc
    except KnowledgeScopeDenied as exc:
        raise HTTPException(status_code=403, detail="knowledge_scope_denied") from exc
    if answer_blocks_v1:
        snapshot = {key: value for key, value in snapshot.items() if key not in {"partial_answer", "final_answer", "block_buffer"}}
        events = [safe for event in events if (safe := _block_safe_event(event)) is not None]
        snapshot["answer_projection"] = _chat_run_store.block_page(
            run_id, tenant_user_hash=owner_hash
        )
    response = {"run": snapshot, "events": events, "dropped_event_count": 0}
    if snapshot["status"] in {"queued", "running", "stalled"} and not _contracts._durable_worker_is_live():
        response["execution"] = {"available": False, "error": dict(_contracts._WORKER_MAINTENANCE)}
    return response


async def durable_chat_blocks(
    run_id: str,
    cursor: str | None = Query(None),
    max_blocks: int = Query(10, ge=1, le=20),
    max_bytes: int = Query(65_536, ge=32_768, le=131_072),
    x_hermes_internal_token: str | None = Header(None),
    x_tenant_id: str | None = Header(None),
    x_user_id: str | None = Header(None),
):
    if _chat_run_store is None:
        raise HTTPException(status_code=503, detail="durable_run_store_unavailable")
    _persistence._require_internal_strict(x_hermes_internal_token)
    tenant_id, user_id = str(x_tenant_id or ""), str(x_user_id or "")
    if not tenant_id or not user_id:
        raise HTTPException(status_code=403, detail="owner_context_required")
    try:
        page = _chat_run_store.block_page(
            run_id,
            tenant_user_hash=_chat_run_store.tenant_user_hash(tenant_id, user_id),
            cursor=cursor, max_blocks=max_blocks, max_bytes=max_bytes,
        )
        if page["status"] in {"queued", "running", "stalled"} and not _contracts._durable_worker_is_live():
            page["execution_available"] = False
            page["execution_error"] = dict(_contracts._WORKER_MAINTENANCE)
        return page
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def chat_stream(
    body: _contracts.GoalRequest,
    x_hermes_internal_token: str | None = Header(None),
):
    """SSE 流式对话入口（Bridge v7 核心端点）。

    优先级：进程内 agent runner（真实逐 token·v7 主路径）→ WS PTY（默认禁用）→ CLI -z 非流式降级。
    全部以 SSE data: {type:...} 格式推送给前端。
    在途标记 _in_flight_users 首秒登记、finally 移除，供 /v1/chat/status 瞬时 running 兜底。
    """
    _persistence._require_internal_strict(x_hermes_internal_token)
    user_id = body.session_id or "anonymous"
    knowledge_claims = _persistence._validated_knowledge_claims(
        body.knowledge_capability,
        subject_id=user_id,
        policy_version=body.knowledge_policy_version,
    )
    client_context_claims = _persistence._validated_client_context_claims(
        body.client_context_capability,
        body.client_session_context,
        subject_id=user_id,
        request_id=body.request_id,
        policy_version=body.knowledge_policy_version,
    )
    qws_context_claims = _persistence._validated_qws_business_context_claims(
        body.qws_context_capability,
        body.qws_business_context,
        subject_id=user_id,
        request_id=body.request_id,
        policy_version=body.knowledge_policy_version,
    )
    sandbox = _persistence._tenant_sandbox_from_claims(
        subject_id=user_id,
        knowledge_claims=knowledge_claims,
        client_claims=client_context_claims or qws_context_claims,
    )
    goal = _contracts._expand_requested_skill(body.goal, body.skill_id, sandbox)

    # v7 主路径：进程内 AIAgent 真实流式（IN_PROCESS_STREAM_ENABLED 默认 true）
    if _contracts.IN_PROCESS_STREAM_ENABLED:
        if _contracts.DURABLE_CHAT_WORKER_ENABLED:
            _contracts._require_durable_worker()
            assert _chat_run_store is not None
            request_id = body.request_id or uuid.uuid4().hex
            identity_claims = knowledge_claims or client_context_claims or qws_context_claims or {}
            tenant_id = str(identity_claims.get("tenant_key") or "public")
            owner_user_id = str(identity_claims.get("user_id") or user_id)
            owner_hash = _chat_run_store.tenant_user_hash(tenant_id, owner_user_id)
            if body.regenerate:
                _chat_run_store.cancel_active_session(owner_hash, user_id, code="superseded_by_regenerate")
            durable_run, _ = _chat_run_store.create_or_get(
                tenant_user_hash=owner_hash,
                tenant_id=tenant_id,
                user_id=owner_user_id,
                user_key=user_id,
                session_id=user_id,
                request_id=request_id,
                execution_payload={
                    "goal": goal,
                    "agent_config": body.agent_config,
                    "knowledge_claims": knowledge_claims,
                    "client_session_context": body.client_session_context,
                    "client_context_claims": client_context_claims,
                    "qws_business_context": body.qws_business_context,
                    "qws_context_claims": qws_context_claims,
                    "knowledge_action_enabled": _knowledge_action_authorized(
                        body.client_capabilities,
                        knowledge_claims=knowledge_claims,
                        client_context_claims=client_context_claims,
                    ),
                    "answer_blocks_v1": "answer_blocks_v1" in set(body.client_capabilities),
                },
            )
            run_id = str(durable_run["run_id"])
            return StreamingResponse(
                _durable_subscribe_sse(
                    run_id, owner_hash,
                    blocks_v1="answer_blocks_v1" in set(body.client_capabilities),
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Session-ID": user_id,
                    "X-Run-ID": run_id,
                },
            )
        # 并发防护（G-6）：同 session 已有活跃 run（attached 或 detached 后台保活中）
        # → 返回 running 状态事件流，绝不启动第二个 agent
        # 例外：regenerate=true（重新生成）→ 作废旧 run 后全新执行，不被防护拦截
        existing = _receipts._stream_run_get(user_id)
        if existing is not None and not body.regenerate:
            print(f"[bridge] 并发防护: user={user_id} 已有活跃 run·拒绝新 agent")
            return StreamingResponse(
                agent_execution._busy_sse(user_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Session-ID": user_id,
                },
            )
        if existing is not None and body.regenerate:
            # 重新生成：interrupt 旧 agent 线程（若可寻址）+ 作废注册，启动全新尝试
            print(f"[bridge] 重新生成: user={user_id} 作废旧 run 后全新执行")
            try:
                old_agent = (existing.get("agent_holder") or [None])[0]
                if old_agent is not None:
                    old_agent.interrupt(message="superseded-by-regenerate")
            except Exception:
                pass
            if existing.get("queue") is not None:
                _receipts._qput(existing["queue"], {"type": "cancelled", "code": "superseded_by_regenerate"})
            _receipts._stream_run_discard(user_id, existing.get("run_id"))
        request_id = body.request_id or uuid.uuid4().hex
        run_id = uuid.uuid4().hex
        if _chat_run_store is not None:
            identity_claims = knowledge_claims or client_context_claims or qws_context_claims or {}
            tenant_id = str(identity_claims.get("tenant_key") or "public")
            owner_user_id = str(identity_claims.get("user_id") or user_id)
            owner_hash = _chat_run_store.tenant_user_hash(tenant_id, owner_user_id)
            durable_run, created = _chat_run_store.create_or_get(
                tenant_user_hash=owner_hash,
                session_id=user_id,
                request_id=request_id,
                run_id=run_id,
                execution_payload={
                    "answer_blocks_v1": "answer_blocks_v1" in set(body.client_capabilities)
                },
            )
            run_id = str(durable_run["run_id"])
            if not created:
                return StreamingResponse(
                    _durable_replay_sse(
                        run_id, owner_hash,
                        blocks_v1="answer_blocks_v1" in set(body.client_capabilities),
                    ),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                        "X-Run-ID": run_id,
                    },
                )
        if not _receipts._stream_run_reserve(
            user_id,
            run_id,
            request_id,
            sandbox.state_db if sandbox is not None else _contracts.STATE_DB,
        ):
            return StreamingResponse(
                agent_execution._busy_sse(user_id),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        try:
            print(f"[bridge] v7 进程内流式: user={user_id}")
            return StreamingResponse(
                agent_execution._sse_from_in_process(
                    user_id,
                    goal,
                    request_id=body.request_id,
                    reserved_run_id=run_id,
                    allow_local_files=False,
                    agent_config=body.agent_config,
                    knowledge_capability=body.knowledge_capability,
                    knowledge_claims=knowledge_claims,
                    client_session_context=body.client_session_context,
                    client_context_claims=client_context_claims,
                    qws_business_context=body.qws_business_context,
                    sandbox=sandbox,
                    knowledge_action_enabled=_knowledge_action_authorized(
                        body.client_capabilities,
                        knowledge_claims=knowledge_claims,
                        client_context_claims=client_context_claims,
                    ),
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Session-ID": user_id,
                    "X-Run-ID": run_id,
                },
            )
        except Exception as stream_err:
            _receipts._stream_run_discard(user_id, run_id)
            print(f"[bridge] v7 进程内流式失败·降级: {stream_err}")

    if knowledge_claims or client_context_claims or qws_context_claims:
        raise HTTPException(
            status_code=503, detail="tenant_sandbox_requires_in_process_runtime"
        )

    # Only the legacy CLI/WS fallback relies on this process-local status hint.
    # Durable and in-process paths have their own authoritative run state.
    _contracts._mark_in_flight(user_id)
    try:
        hermes_sid = _agent_config._hermes_session_for_request(user_id, body.client_session_context)

        # 首次对话：先通过 CLI 新建会话·捕获 session_id
        if not hermes_sid:
            print("[bridge] 首次对话·先通过 CLI 新建会话")
            reply, new_sid = await asyncio.to_thread(_persistence._run_hermes, goal, None)
            if new_sid:
                _update_session_mapping(user_id, new_sid)
                hermes_sid = new_sid
            else:
                # CLI 新建失败·包装为 SSE 流（与前端契约一致·杜绝裸 JSON 导致前端空回复）
                print("[bridge] CLI 新建失败·降级 SSE 包装返回")
                return StreamingResponse(
                    _fallback_sse(reply),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                        "X-Session-ID": user_id,
                    },
                )

        # 尝试 WS PTY 流式（v6 主路径·默认禁用——serve PTY 只回显不执行 Hermes·流式做好后设 WS_PTY_ENABLED=true 启用）
        if os.environ.get("WS_PTY_ENABLED", "false") == "true":
            try:
                print(f"[bridge] WS PTY 流式: user={user_id} session={hermes_sid}")
                return StreamingResponse(
                    _stream_from_ws_pty(goal, hermes_sid),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",  # nginx 禁用缓冲
                    },
                )
            except Exception as ws_err:
                print(f"[bridge] WS PTY 失败·降级到 SSE: {ws_err}")

        # 二级降级：SSE 流式（v5 路径·serve 无 /api/chat 端点恒 405·2026-08-10 禁用直接走 CLI）
        # try:
        #     print(f"[bridge] SSE 流式降级: user={user_id} session={hermes_sid}")
        #     return StreamingResponse(
        #         _stream_from_serve(body.goal, hermes_sid),
        #         media_type="text/event-stream",
        #         headers={
        #             "Cache-Control": "no-cache",
        #             "Connection": "keep-alive",
        #             "X-Accel-Buffering": "no",
        #         },
        #     )
        # except Exception as sse_err:
        #     print(f"[bridge] SSE 流式失败·降级到非流式: {sse_err}")

        # 最终降级：CLI -z 非流式（SSE 包装·契约统一）·包装为 SSE 流（与前端契约一致·杜绝裸 JSON 导致前端空回复）
        reply, _ = await asyncio.to_thread(_persistence._run_hermes, goal, hermes_sid)
        print("[bridge] 最终降级 CLI·包装 SSE 返回")
        return StreamingResponse(
            _fallback_sse(reply),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Session-ID": user_id,
            },
        )
    except _persistence.HermesInvocationError:
        raise HTTPException(
            status_code=502, detail=_persistence.HermesInvocationError.category
        ) from None
    finally:
        _contracts._clear_in_flight(user_id)


async def chat_prewarm(
    body: _contracts.GoalRequest,
    x_hermes_internal_token: str | None = Header(None),
):
    """Queue one session-scoped Agent build in the durable Hermes worker."""
    _persistence._require_internal_strict(x_hermes_internal_token)
    if not _contracts.DURABLE_CHAT_WORKER_ENABLED:
        raise HTTPException(status_code=503, detail="durable_run_store_unavailable")
    _contracts._require_durable_worker()
    assert _chat_run_store is not None
    user_id = body.session_id or ""
    if not user_id:
        raise HTTPException(status_code=422, detail="session_id_required")
    claims = _persistence._validated_knowledge_claims(
        body.knowledge_capability,
        subject_id=user_id,
        policy_version=body.knowledge_policy_version,
    )
    if not claims:
        raise HTTPException(status_code=403, detail="knowledge_scope_denied")
    tenant_id = str(claims.get("tenant_key") or "public")
    owner_user_id = str(claims.get("user_id") or user_id)
    owner_hash = _chat_run_store.tenant_user_hash(tenant_id, owner_user_id)
    request_id = f"prewarm-{_contracts._BRIDGE_PREWARM_EPOCH}-{hashlib.sha256(user_id.encode()).hexdigest()[:24]}"
    run, _ = _chat_run_store.create_or_get(
        tenant_user_hash=owner_hash,
        tenant_id=tenant_id,
        user_id=owner_user_id,
        user_key=user_id,
        session_id=user_id,
        request_id=request_id,
        execution_payload={
            "run_type": "chat_prewarm",
            "agent_config": body.agent_config,
            "knowledge_claims": claims,
            "knowledge_action_enabled": _knowledge_action_authorized(
                body.client_capabilities,
                knowledge_claims=claims,
                client_context_claims=None,
            ),
        },
    )
    return {"run_id": run["run_id"], "status": run["status"]}


from . import (  # noqa: E402
    agent_config as _agent_config, agent_execution, contracts as _contracts, persistence as _persistence, receipts as _receipts,
    workflow_runtime as _workflow_runtime,
)
