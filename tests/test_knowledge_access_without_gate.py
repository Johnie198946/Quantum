"""Knowledge retrieval is optional and must never gate an answer."""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import hermes_bridge as bridge


@pytest.fixture
def router(monkeypatch):
    path = (
        Path(__file__).resolve().parents[1]
        / "agency/hermes-plugins/ai-lab-capabilities/capability_router.py"
    )
    spec = importlib.util.spec_from_file_location("open_knowledge_router", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_skill_capabilities", lambda: [{
        "id": "skill:vault-knowledge-retrieval",
        "name": "vault-knowledge-retrieval",
        "kind": "skill",
        "negative_phrases": [],
    }])
    return module


def test_local_general_qa_only_recommends_knowledge(router):
    ctx = Mock()
    result = router._pre_llm_with_runtime_skill(
        ctx,
        "内部政策是什么？",
        session_id="open-knowledge",
        platform="cli",
        sender_id="owner",
    )

    assert "Hermes ordinary knowledge recommendation" in result["context"]
    assert "defer_streaming" not in result
    ctx.dispatch_tool.assert_not_called()
    state = router._LOCAL_TURN_STATES["open-knowledge"]
    assert state["requested_skill"] is None
    assert state["requested_agent"] is None
    assert state["route_decision"]["reason_code"] in {
        "PROVIDER_UNAVAILABLE", "INVALID_OUTPUT"
    }
    assert "knowledge_gate" not in state
    assert router._pre_tool_call(
        "web_search", {"query": "policy"}, session_id="open-knowledge"
    ) is None
    assert router._transform_llm_output(
        "direct answer", session_id="open-knowledge"
    ) == "direct answer"


def test_legacy_gate_state_cannot_rewrite_or_block_answer(router):
    router._LOCAL_TURN_STATES["legacy"] = {
        "principal": "local_owner",
        "route_class": "GENERAL_QA",
        "knowledge_gate": True,
        "requested_skill": "vault-knowledge-retrieval",
        "loaded_skill": None,
        "vault_lookup_complete": False,
    }

    assert router._pre_tool_call(
        "web_search", {"query": "public evidence"}, session_id="legacy"
    ) is None
    assert router._transform_llm_output("unchanged", session_id="legacy") == "unchanged"


def test_bridge_has_no_knowledge_gate_in_answer_execution_path():
    run_source = inspect.getsource(bridge._run_agent_sync)
    emit_source = inspect.getsource(bridge._emit_tool_complete)

    assert "_perform_knowledge_preread" not in run_source
    assert "_KnowledgeBarrierQueue" not in run_source
    assert "_finalize_knowledge_gate" not in run_source
    assert "knowledge_receipt" not in run_source
    assert "_record_knowledge_gate_tool_result" not in emit_source
