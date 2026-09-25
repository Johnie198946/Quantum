#!/usr/bin/env python3
"""HTTP composition root for the managed Hermes runtime."""
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HERMES_SOURCE_ROOT = Path(
    os.environ.get("HERMES_AGENT_ROOT")
    or Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes") / "hermes-agent"
).resolve()
if _HERMES_SOURCE_ROOT.is_dir():
    try:
        sys.path.remove(str(_HERMES_SOURCE_ROOT))
    except ValueError:
        pass
    sys.path.insert(0, str(_HERMES_SOURCE_ROOT))
if str(_REPO_ROOT) not in sys.path:
    sys.path.append(str(_REPO_ROOT))

import httpx
import sqlite3
import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
import uvicorn
from scripts.chat_run_store import DurableChatRunStore
from backend.services.tenant_hermes_sandbox import persist_agent_snapshot
from backend.services.knowledge_policy import verify_capability

from scripts.hermes_bridge_runtime import (
    agent_config, agent_execution, contracts, endpoints, knowledge,
    memory, persistence, receipts, session_runtime, workflow_artifacts, workflow_runtime,
)

from scripts.hermes_bridge_runtime.agent_config import (
    CLARIFY_GATE_PROMPT, GENERAL_KNOWLEDGE_SPEED_DISCIPLINE,
    KB_RETRIEVAL_DISCIPLINE, _AGENT_CACHE,
    _AGENT_CACHE_LOCK, _AGENT_CACHE_MAX_SIZE,
    _CACHED_CFG, _CACHED_CFG_LOCK,
    _CACHED_FALLBACK, _CACHED_RUNTIME,
    _CACHED_TOOLS, _DRILL_ME_ACTION_RE,
    _DRILL_ME_ARTIFACT_RE, _SHARED_SESSION_DB,
    _SHARED_SESSION_DB_LOCK, _agent_cache_signature,
    _apply_triage_toolset_policy, _cache_request_overrides,
    _close_agent_resources, _create_sandbox_session_db,
    _create_thread_local_session_db, _finish_cached_agent,
    _get_cached_config, _get_cached_fallback,
    _get_cached_runtime, _get_cached_tools,
    _get_shared_session_db, _hermes_session_for_request,
    _include_available_toolsets, _is_drill_me_goal,
    _knowledge_public_fallback_allowed, _knowledge_tools_eligible,
    _prewarm_bridge_agent, _prewarm_session_agent,
    _request_inference_policy, _request_runtime_placement,
    _request_triage, _resolve_base_toolsets,
    _steer_drill_me_response, _supports_reasoning_effort,
    _take_cached_agent, _triage_route_marker,
    _triage_system_directive,
)

from scripts.hermes_bridge_runtime.agent_execution import (
    CancelRequest, ClarifyResolveRequest,
    _build_in_process_agent, _busy_sse,
    _run_agent_sync, _sse_from_in_process,
)

from scripts.hermes_bridge_runtime.contracts import (
    AGENT_EVALUATION_RUNS_FILE, ALLOWED_CHAT_SKILLS,
    ANONYMOUS_LOCK_KEY, ANSI_ESCAPE_RE,
    AgentCompositionConfig, AgentDelegationConfig,
    AgentEvaluationRequest, AgentTriageConfig,
    CLARIFICATION_MIN_INTERVAL_SECONDS, CLARIFY_REPLAY_TTL_SECONDS,
    CLARIFY_TIMEOUT_SECONDS, ClarificationBridgeRequest,
    ClarificationDecision, ClarificationTurn,
    DEFAULT_TIMEOUT, DRILL_ME_MAX_ROUNDS,
    DRILL_ME_MIN_ROUNDS, DURABLE_CHAT_WORKER_ENABLED,
    DURABLE_WORKER_HEARTBEAT_MAX_AGE, GoalRequest,
    HERMES_BIN, HERMES_BRIDGE_INTERNAL_TOKEN,
    HERMES_CHAT_RUN_DB, HERMES_CWD,
    HERMES_SERVE_TOKEN, HERMES_SERVE_URL,
    HERMES_WS_URL, IN_FLIGHT_STALE_SECONDS,
    IN_PROCESS_STREAM_ENABLED, KNOWLEDGE_GATEWAY_URL,
    MAPPING_FILE, MAX_CONCURRENT_REQUESTS,
    MAX_DOCUMENT_WORKFLOW_INPUT, MAX_INPUT,
    MAX_QUEUED_REQUESTS, QUEUE_TIMEOUT_SECONDS,
    SERVE_TIMEOUT, STATE_DB,
    STATE_DB_MAPPING_FILE, STREAM_KEEPALIVE_SECONDS,
    STREAM_MAX_DURATION_SECONDS, STREAM_QUEUE_CAPACITY,
    TrustedAgentConfig, USER_LOCK_CAPACITY,
    USER_LOCK_TTL_SECONDS, WATCHDOG_INTERVAL_SECONDS,
    WATERMARK_FILE, WORKFLOW_NODE_MAX_ITERATIONS,
    WORKFLOW_NODE_TIMEOUT, WORKFLOW_PLANNING_RUNS_FILE,
    WORKFLOW_RUNS_FILE, WorkflowGateApprovalRequest,
    WorkflowPlanRequest, WorkflowPlanningStartRequest,
    WorkflowRetryRequest, WorkflowRunRequest,
    _BRIDGE_PREWARM_EPOCH, _WORKER_MAINTENANCE,
    _admit_request, _clarification_last_run,
    _clarification_rate_lock, _clarify_gateway,
    _clarify_response_fingerprint, _clear_in_flight,
    _durable_worker_is_live, _evaluation_runs_lock,
    _evaluation_threads, _expand_requested_skill,
    _expand_workflow_skill, _get_clarify_gateway,
    _get_user_lock, _in_flight_users,
    _is_in_flight, _mapping_lock,
    _mark_in_flight, _planning_runs_lock,
    _planning_threads, _queued_requests,
    _remember_resolved_clarify, _require_durable_worker,
    _resolved_clarifies, _resolved_clarifies_guard,
    _resolved_clarify_state, _routed_skill_catalog,
    _semaphore, _stream_runs,
    _stream_runs_guard, _user_lock_timestamps,
    _user_locks, _verify_workflow_skill_binding,
    _watermark_lock, _workflow_agents,
    _workflow_runs_lock, _workflow_threads,
)

from scripts.hermes_bridge_runtime.endpoints import (
    _legacy_nonstream_chat, _private_bridge_bind_address,
    _reserve_clarification_slot, _run_clarification_in_process,
    chat, chat_status,
    clarify_resolve, clarify_workflow,
    health, stream_cancel,
)

from scripts.hermes_bridge_runtime.knowledge import (
    _FULL_KNOWLEDGE_CATEGORY_RE, _KNOWLEDGE_MERGE_DIRECTIVE,
    _KNOWLEDGE_MUTATION_KINDS, _KNOWLEDGE_NAV_DESTINATIONS,
    _NOTE_DRAFT_REQUEST_RE, _PropagatedRequestContext,
    _REVISION_REQUEST_RE, _SKILL_CREATE_REQUEST_RE,
    _client_context_tool_context, _client_context_tool_registration_lock,
    _client_context_tools_registered, _ensure_client_context_tools_registered,
    _ensure_knowledge_gateway_tool_registered, _ensure_knowledge_workspace_tools_registered,
    _ensure_tenant_coder_tools_registered, _ensure_tenant_skill_tool_registered,
    _explicit_knowledge_category_scope, _fallback_note_title,
    _inline_user_note_matches, _is_note_draft_request,
    _is_revision_request, _knowledge_action_propose_tool,
    _knowledge_fallback_payload, _knowledge_search_tool,
    _knowledge_tool_context, _knowledge_tool_registered,
    _knowledge_tool_registration_lock, _knowledge_ui_navigate_tool,
    _knowledge_workspace_read_tool, _knowledge_workspace_tool_registration_lock,
    _knowledge_workspace_tools_registered, _note_draft_tool,
    _requires_browser_fallback, _sandbox_tool_context,
    _sandbox_tool_registered, _sandbox_tool_registration_lock,
    _session_context_read_tool, _skill_route_context,
    _tenant_coder_dispatch, _tenant_coder_tool_registration_lock,
    _tenant_coder_tools_registered, _tenant_skill_manage_tool,
    _tenant_skill_read_tool, _user_note_search_tool,
    _workspace_notes, delete_skill,
    list_skills,
)

from scripts.hermes_bridge_runtime.memory import (
    MemoryReplaceRequest, MemoryWriteRequest,
    _isolated_agent_context_kwargs, _memory_id,
    _memory_sandbox, _memory_write_error,
    _mutate_sandbox_memory, _sandbox_hermes_home,
    _sandbox_memory_payload, _with_sandbox_memory,
    add_native_memory, approve_workflow_gate,
    delete_native_memory, list_native_memory,
    replace_native_memory,
)

from scripts.hermes_bridge_runtime.persistence import (
    HermesCallResult, HermesInvocationError,
    _HERMES_PROVIDER_FAILURE_RE, _delivered_watermark,
    _evaluation_event, _evaluation_runs,
    _extract_session_from_usage, _extract_usage,
    _get_watermark, _knowledge_gateway_search,
    _load_evaluation_runs, _load_mapping,
    _load_planning_runs, _load_state_db_mapping,
    _load_watermarks, _load_workflow_runs,
    _planning_event, _planning_runs,
    _recent_conversation_context, _require_internal,
    _require_internal_strict, _run_hermes,
    _run_hermes_with_usage, _save_evaluation_runs,
    _save_mapping, _save_planning_runs,
    _save_state_db_mapping, _save_watermarks,
    _save_workflow_runs, _session_exists,
    _set_watermark, _tenant_sandbox_from_claims,
    _user_session_map, _user_state_db_map,
    _validated_client_context_claims, _validated_knowledge_claims,
    _validated_qws_business_context_claims, _with_qws_business_context,
    _workflow_event, _workflow_runs,
    _workflow_sandbox,
)

from scripts.hermes_bridge_runtime.receipts import (
    DurableEventQueue, _AGENCY_RESULT_LINE_RE,
    _AGENCY_SPECIALIST_MARKER_RE, _AGENCY_TOOL_LINE_RE,
    _DELEGATE_STATUSES, _DELEGATION_ID_FULL_RE,
    _EXPLICIT_MEMORY_RE, _delegation_transcript_details,
    _emit_delegate_receipt, _emit_tool_complete,
    _emit_tool_start, _explicit_memory_content,
    _expose_eager_request_tools, _legacy_client_context_enabled,
    _memory_tool_succeeded, _qput,
    _routing_user_goal, _save_explicit_user_memory,
    _stream_run_discard, _stream_run_get,
    _stream_run_register, _stream_run_reserve,
    _tenant_base_toolsets, _tenantize_created_skill,
    _verified_delegation_transcript, _watchdog_loop,
    _watchdog_loop_step, _watchdog_scan_once,
)

from scripts.hermes_bridge_runtime.session_runtime import (
    _POLICY_SCOPED_SESSION_KEY_RE, _append_session_messages,
    _block_safe_event, _build_status_phrase,
    _chat_run_store, _clean_ansi,
    _durable_replay_sse, _durable_status,
    _durable_subscribe_sse, _fallback_sse,
    _get_baseline_id, _interrupt_and_discard,
    _latest_step_text, _mark_consumed,
    _pending_clarify, _query_status,
    _readback_delta, _resolve_hermes_session,
    _stable_session_key, _startup,
    _stream_from_serve, _stream_from_ws_pty,
    _thought_summary, _update_session_mapping,
    chat_prewarm, chat_stream,
    durable_chat_blocks, durable_chat_run,
)

from scripts.hermes_bridge_runtime.workflow_artifacts import (
    _CUMULATIVE_USAGE_FIELDS, _accumulate_usage,
    _agent_usage_baseline, _approved_presentation_design,
    _approved_presentation_outline, _approved_presentation_stage,
    _assert_final_matches_approved_outline, _bind_approved_presentation_design,
    _bind_approved_presentation_inputs, _extract_json_object,
    _load_workflow_design_skills, _merge_workflow_usage,
    _normalize_presentation_contract_reply, _normalize_presentation_reply,
    _run_workflow_node_in_process, _usage_delta,
    _workflow_artifact_contract, _workflow_artifact_instruction,
    _workflow_illustration_context, _workflow_node_prompt,
    _workflow_order, _workflow_output_incomplete,
    _workflow_tool_event_type, _workflow_toolsets,
    _workflow_turn_token_cap,
)

from scripts.hermes_bridge_runtime.workflow_runtime import (
    _execute_agent_evaluation, _execute_planning_run,
    _start_evaluation_thread, _start_planning_thread,
    _start_workflow_thread, _workflow_plan_prompt,
    _workflow_run_sync, cancel_workflow_run,
    get_agent_evaluation, get_workflow_run,
    retry_workflow_run, start_agent_evaluation,
    start_workflow_plan, start_workflow_run,
    workflow_plan, workflow_plan_status,
)

app = FastAPI(title="Hermes Bridge v6.0")

def _register_routes() -> None:
    app.add_event_handler("startup", _startup)
    app.add_api_route('/v1/chat/runs/{run_id}', durable_chat_run, methods=['GET'])
    app.add_api_route('/v1/chat/runs/{run_id}/blocks', durable_chat_blocks, methods=['GET'])
    app.add_api_route('/v1/chat/stream', chat_stream, methods=['POST'])
    app.add_api_route('/v1/chat/prewarm', chat_prewarm, methods=['POST'], status_code=202)
    app.add_api_route('/v1/chat/clarify', clarify_resolve, methods=['POST'])
    app.add_api_route('/v1/chat/stream/cancel', stream_cancel, methods=['POST'])
    app.add_api_route('/v1/workflows/clarify', clarify_workflow, methods=['POST'])
    app.add_api_route('/v1/chat', chat, methods=['POST'])
    app.add_api_route('/v1/chat/status/{user_id}', chat_status, methods=['GET'])
    app.add_api_route('/v1/workflows/plans', start_workflow_plan, methods=['POST'], status_code=202)
    app.add_api_route('/v1/workflows/plans/{run_id}/status', workflow_plan_status, methods=['GET'])
    app.add_api_route('/v1/workflows/plan', workflow_plan, methods=['POST'])
    app.add_api_route('/v1/agent-evaluations', start_agent_evaluation, methods=['POST'], status_code=202)
    app.add_api_route('/v1/agent-evaluations/{run_id}', get_agent_evaluation, methods=['GET'])
    app.add_api_route('/v1/workflow-runs', start_workflow_run, methods=['POST'])
    app.add_api_route('/v1/workflow-runs/{execution_id}', get_workflow_run, methods=['GET'])
    app.add_api_route('/v1/workflow-runs/{execution_id}/cancel', cancel_workflow_run, methods=['POST'])
    app.add_api_route('/v1/workflow-runs/{execution_id}/retry', retry_workflow_run, methods=['POST'])
    app.add_api_route('/v1/memory', list_native_memory, methods=['GET'])
    app.add_api_route('/v1/memory', add_native_memory, methods=['POST'])
    app.add_api_route('/v1/memory/{memory_id}', replace_native_memory, methods=['PUT'])
    app.add_api_route('/v1/memory/{memory_id}', delete_native_memory, methods=['DELETE'])
    app.add_api_route('/v1/workflow-runs/{execution_id}/approve-gate', approve_workflow_gate, methods=['POST'])
    app.add_api_route('/v1/skills', list_skills, methods=['GET'])
    app.add_api_route('/v1/skills/{name}', delete_skill, methods=['DELETE'])
    app.add_api_route('/health', health, methods=['GET'])


_register_routes()

if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise RuntimeError("hermes_bridge.py does not accept command-line bind overrides")
    bind_address = _private_bridge_bind_address()
    _prewarm_bridge_agent()
    uvicorn.run(app, host=bind_address, port=9118)
