"""Synthetic regression: optional failed pre-read must not block public QA."""
import json

import pytest

from scripts import hermes_bridge as bridge


@pytest.mark.parametrize("error", ["knowledge_gateway_unavailable", "knowledge_gateway_timeout"])
def test_public_question_recovers_after_failed_optional_preread(monkeypatch, error):
    goal = "Explain the abilities of a fictional character."
    config = {
        "allowed_tools": ["knowledge_search", "web_search"],
        "triage": {
            "route_class": "GENERAL_QA", "reason_code": "general_question",
            "confidence": 0.78, "evidence_requirements": [],
            "agency_enabled": False, "skill_enabled": False,
        },
    }
    requirement = bridge._knowledge_gate_requirement(
        goal, config, "synthetic-capability", {"sources": ["tenant_knowledge"]}
    )
    assert requirement == "optional"
    monkeypatch.setattr(bridge, "_knowledge_search_tool", lambda *a, **k: json.dumps({
        "success": False, "error": error, "retrieval_status": "error", "docs": [],
    }))
    _, state = bridge._perform_knowledge_preread(goal, requirement=requirement)
    bridge._knowledge_gate_context.value = state
    try:
        for tool, args in [("web_search", None), ("tool_call", {"name": "web_search"})]:
            bridge._record_knowledge_gate_tool_result(
                tool, {"data": {"web": [{"url": "https://example.com/public-source"}]}}, args
            )
    finally:
        bridge._knowledge_gate_context.value = None
    answer, receipt = bridge._finalize_knowledge_gate(
        "Public answer https://example.com/public-source", "synthetic-capability", state
    )
    assert answer.startswith("Public answer")
    assert receipt["schema_version"] == "knowledge_gate_receipt.v2"
    assert receipt["decision"] == "allowed_public_only"
    assert receipt["required_internal_knowledge"] is False
    assert receipt["attempted_internal_search"] is True
    assert receipt["consumed_internal_knowledge"] is False
    assert receipt["web_fallback"] is True
    assert receipt["semantic"] == "public_evidence_only"


@pytest.mark.parametrize("status", ["denied", "unknown_status"])
def test_optional_unknown_or_denied_state_never_fails_open(status):
    answer, receipt = bridge._finalize_knowledge_gate(
        "Public answer https://example.com/public-source", "synthetic-capability", {
            "status": status, "requirement": "optional", "docs": [],
            "web_succeeded": True, "web_urls": {"https://example.com/public-source"},
        },
    )
    assert "门禁未通过" in answer
    assert receipt["decision"].startswith("blocked_")


@pytest.mark.parametrize("status", ["denied", "unknown_status"])
def test_runtime_observer_does_not_reclassify_rejection_as_no_match(status):
    state = {"status": "no_match", "requirement": "optional", "docs": []}
    bridge._observe_internal_search_result(state, {
        "success": True, "retrieval_status": status, "docs": [],
    })
    bridge._observe_internal_search_result(state, {
        "success": True, "retrieval_status": "no_match", "docs": [],
    })
    answer, receipt = bridge._finalize_knowledge_gate("Public answer", "cap", state)
    assert "门禁未通过" in answer
    assert receipt["decision"].startswith("blocked_")
