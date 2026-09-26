#!/usr/bin/env python3
"""HTTP composition root and live compatibility facade for Hermes runtime."""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from typing import Any

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

import uvicorn
from fastapi import FastAPI

from scripts.hermes_bridge_runtime import (
    agent_config,
    agent_execution,
    contracts,
    endpoints,
    knowledge,
    memory,
    persistence,
    receipts,
    session_runtime,
    workflow_artifacts,
    workflow_runtime,
)

_RUNTIME_MODULES = (
    agent_config,
    agent_execution,
    contracts,
    endpoints,
    knowledge,
    memory,
    persistence,
    receipts,
    session_runtime,
    workflow_artifacts,
    workflow_runtime,
)


def _runtime_owner(name: str) -> types.ModuleType | None:
    """Resolve the owning runtime module for a legacy Bridge export."""
    for module in _RUNTIME_MODULES:
        if name in vars(module):
            return module
    return None


def __getattr__(name: str) -> Any:
    """Return live runtime state instead of a detached import-time copy."""
    owner = _runtime_owner(name)
    if owner is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(owner, name)


def __dir__() -> list[str]:
    exported = set(globals())
    for module in _RUNTIME_MODULES:
        exported.update(name for name in vars(module) if not name.startswith("__"))
    return sorted(exported)


class _BridgeFacade(types.ModuleType):
    """Forward legacy monkeypatch/rebinding writes to the runtime owner."""

    def __setattr__(self, name: str, value: Any) -> None:
        if name in self.__dict__ or name.startswith("__"):
            super().__setattr__(name, value)
            return
        owner = _runtime_owner(name)
        if owner is None:
            super().__setattr__(name, value)
            return
        setattr(owner, name, value)

    def __delattr__(self, name: str) -> None:
        if name in self.__dict__ or name.startswith("__"):
            super().__delattr__(name)
            return
        owner = _runtime_owner(name)
        if owner is None:
            super().__delattr__(name)
            return
        delattr(owner, name)


app = FastAPI(title="Hermes Bridge v6.0")


def _register_routes() -> None:
    app.on_event("startup")(session_runtime._startup)
    app.add_api_route("/v1/chat/runs/{run_id}", session_runtime.durable_chat_run, methods=["GET"])
    app.add_api_route("/v1/chat/runs/{run_id}/blocks", session_runtime.durable_chat_blocks, methods=["GET"])
    app.add_api_route("/v1/chat/stream", session_runtime.chat_stream, methods=["POST"])
    app.add_api_route("/v1/chat/prewarm", session_runtime.chat_prewarm, methods=["POST"], status_code=202)
    app.add_api_route("/v1/chat/clarify", endpoints.clarify_resolve, methods=["POST"])
    app.add_api_route("/v1/chat/stream/cancel", endpoints.stream_cancel, methods=["POST"])
    app.add_api_route("/v1/workflows/clarify", endpoints.clarify_workflow, methods=["POST"])
    app.add_api_route("/v1/chat", endpoints.chat, methods=["POST"])
    app.add_api_route("/v1/chat/status/{user_id}", endpoints.chat_status, methods=["GET"])
    app.add_api_route("/v1/workflows/plans", workflow_runtime.start_workflow_plan, methods=["POST"], status_code=202)
    app.add_api_route("/v1/workflows/plans/{run_id}/status", workflow_runtime.workflow_plan_status, methods=["GET"])
    app.add_api_route("/v1/workflows/plan", workflow_runtime.workflow_plan, methods=["POST"])
    app.add_api_route("/v1/agent-evaluations", workflow_runtime.start_agent_evaluation, methods=["POST"], status_code=202)
    app.add_api_route("/v1/agent-evaluations/{run_id}", workflow_runtime.get_agent_evaluation, methods=["GET"])
    app.add_api_route("/v1/workflow-runs", workflow_runtime.start_workflow_run, methods=["POST"])
    app.add_api_route("/v1/workflow-runs/{execution_id}", workflow_runtime.get_workflow_run, methods=["GET"])
    app.add_api_route("/v1/workflow-runs/{execution_id}/cancel", workflow_runtime.cancel_workflow_run, methods=["POST"])
    app.add_api_route("/v1/workflow-runs/{execution_id}/retry", workflow_runtime.retry_workflow_run, methods=["POST"])
    app.add_api_route("/v1/memory", memory.list_native_memory, methods=["GET"])
    app.add_api_route("/v1/memory", memory.add_native_memory, methods=["POST"])
    app.add_api_route("/v1/memory/{memory_id}", memory.replace_native_memory, methods=["PUT"])
    app.add_api_route("/v1/memory/{memory_id}", memory.delete_native_memory, methods=["DELETE"])
    app.add_api_route("/v1/workflow-runs/{execution_id}/approve-gate", memory.approve_workflow_gate, methods=["POST"])
    app.add_api_route("/v1/skills", knowledge.list_skills, methods=["GET"])
    app.add_api_route("/v1/skills/{name}", knowledge.delete_skill, methods=["DELETE"])
    app.add_api_route("/v1/owner-sessions/resolve", session_runtime.owner_session_resolve, methods=["POST"])
    app.add_api_route("/v1/owner-sessions/resume", session_runtime.owner_session_resume, methods=["POST"])
    app.add_api_route("/v1/owner-sessions/delete", session_runtime.owner_session_delete, methods=["POST"])
    app.add_api_route("/v1/skills", knowledge.create_skill, methods=["POST"])
    app.add_api_route("/v1/skills/{name}", knowledge.update_skill, methods=["PUT"])
    from scripts.hermes_bridge_runtime import note_illustrations
    app.add_api_route("/v1/note-illustrations", note_illustrations.start, methods=["POST"])
    app.add_api_route("/v1/note-illustrations/by-note/{note_id}", note_illustrations.latest, methods=["GET"])
    app.add_api_route("/v1/note-illustrations/{run_id}", note_illustrations.status, methods=["GET"])
    app.add_api_route("/v1/note-illustrations/{run_id}/cancel", note_illustrations.cancel, methods=["POST"])
    app.add_api_route("/v1/note-illustrations/{run_id}/assets/{index}", note_illustrations.asset, methods=["GET"])
    app.add_api_route("/health", endpoints.health, methods=["GET"])


_register_routes()
sys.modules[__name__].__class__ = _BridgeFacade

if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise RuntimeError("hermes_bridge.py does not accept command-line bind overrides")
    bind_address = endpoints._private_bridge_bind_address()
    agent_config._prewarm_bridge_agent()
    uvicorn.run(app, host=bind_address, port=9118)
