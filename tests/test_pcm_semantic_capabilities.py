from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

from backend.services.capability_projection import (
    bind_runtime_capability_selection,
    clear_runtime_capability_selection,
)
from backend.services.skill_router import routing_quality_issues
from backend.services.tenant_hermes_sandbox import (
    ensure_tenant_sandbox,
    list_sandbox_skills,
)
from scripts import hermes_bridge as bridge


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "backend" / "skill_packs"
PLUGIN = (
    ROOT / "agency" / "hermes-plugins" / "ai-lab-capabilities" / "__init__.py"
)
FORMAL_SKILLS = {
    "requirements-clarification",
    "personal-knowledge-action",
    "skill-authoring",
}


def _metadata(name: str) -> dict:
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---", 2)[1])


def _load_router():
    package = "pcm_semantic_capabilities_plugin"
    sys.modules.pop(package, None)
    sys.modules.pop(f"{package}.capability_router", None)
    spec = importlib.util.spec_from_file_location(
        package,
        PLUGIN,
        submodule_search_locations=[str(PLUGIN.parent)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[package] = module
    spec.loader.exec_module(module)
    return sys.modules[f"{package}.capability_router"]


def test_formal_pcm_skills_have_governed_positive_negative_and_attack_cases():
    for name in FORMAL_SKILLS:
        metadata = _metadata(name)
        assert routing_quality_issues(metadata) == []
        assert len(metadata["trigger_phrases"]) >= 3
        assert len(metadata["negative_phrases"]) >= 3
        assert any("ignore" in item.casefold() for item in metadata["negative_phrases"])
        assert metadata["skill_level"] == "professional"


def test_formal_skill_cards_preserve_governed_boundaries_and_candidate_budget(monkeypatch):
    router = _load_router()
    runtime_skills = []
    for name in FORMAL_SKILLS:
        runtime_skills.append(_metadata(name))
    skills_tool = __import__("tools.skills_tool", fromlist=["_find_all_skills"])
    monkeypatch.setattr(skills_tool, "_find_all_skills", lambda: runtime_skills)

    cards = router._skill_capabilities()
    assert len(cards) == 3
    for card in cards:
        assert len(card["use_when"]) >= 3
        assert any("ignore" in item.casefold() for item in card["do_not_use_when"])
    resident_source = (
        ROOT / "agency/hermes-plugins/ai-lab-capabilities/jev_resident.py"
    ).read_text(encoding="utf-8")
    assert '"shortlist_total"' in resident_source
    assert "selected = scored[:top_k]" in resident_source


def test_resident_jev_shortlist_is_five_cards_total_across_both_kinds(monkeypatch):
    import numpy as np

    router = _load_router()
    resident = __import__(
        f"{router.__package__}.jev_resident", fromlist=["jev_resident"]
    )
    skills = [
        {"id": f"skill:s{i}", "kind": "skill", "description": f"skill {i}"}
        for i in range(6)
    ]
    agents = [
        {"id": f"agency:a{i}", "kind": "agent", "description": f"agent {i}"}
        for i in range(6)
    ]
    cards = skills + agents
    monkeypatch.setattr(resident, "_READY", True)
    monkeypatch.setattr(resident, "_CARD_IDS", [card["id"] for card in cards])
    monkeypatch.setattr(
        resident,
        "_CARD_TEXTS",
        {card["id"]: resident._card_text(card) for card in cards},
    )
    monkeypatch.setattr(
        resident,
        "_CARD_EMBEDDINGS",
        np.asarray([[1.0 - i * 0.02, i * 0.02] for i in range(len(cards))]),
    )
    monkeypatch.setattr(resident, "_encode", lambda _texts: np.asarray([[1.0, 0.0]]))
    monkeypatch.setattr(resident, "_integer", lambda _name, default: default)

    shortlisted_skills, shortlisted_agents, _, _ = resident._shortlist({
        "request": "route this once",
        "skill_candidates": skills,
        "agent_candidates": agents,
    })

    assert len(shortlisted_skills) + len(shortlisted_agents) == 5


def test_prefixed_qcp_skill_scope_reaches_the_single_jev_decision(monkeypatch):
    router = _load_router()
    card = {
        "id": "skill:personal-knowledge-action",
        "kind": "skill",
        "name": "personal-knowledge-action",
        "description": "personal notes",
        "version": "1.0.0",
        "use_when": ["save my note"],
        "do_not_use_when": ["public facts"],
        "requires": {},
        "risk": "write",
        "status": "active",
        "domain": "knowledge/personal-actions",
        "invoke_tool": "skill_view",
        "invoke_args": {"name": "personal-knowledge-action"},
    }
    observed: dict[str, object] = {}
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [card])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: [])

    def fake_select(_query, **kwargs):
        observed["skill_candidates"] = kwargs["skill_candidates"]
        return SimpleNamespace(
            skill_id=card["id"], agent_id=None, reason="MATCHED",
            decision_id="d-one", catalog_version="c-one",
            policy_version="p-one", latency_ms=1.0, cache_hit=False,
            as_dict=lambda: {
                "skill_id": card["id"], "agent_id": None, "reason": "MATCHED",
            },
        )

    monkeypatch.setattr(router, "select_route", fake_select)
    state = {"tenant_id": "t", "principal": "u"}
    text = router._jev_routing_context(
        "save my note",
        state,
        authorized_skill_ids=["skill:personal-knowledge-action"],
        authorized_agent_ids=[],
    )

    assert observed["skill_candidates"] == [card]
    assert state["requested_skill"] == "personal-knowledge-action"
    assert "personal-knowledge-action" in text


def test_formal_pcm_skills_are_projected_into_each_isolated_runtime(tmp_path: Path):
    tenant_a = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="user-a", root=tmp_path / "sandboxes"
    )
    tenant_b = ensure_tenant_sandbox(
        tenant_key="tenant-b", user_id="user-b", root=tmp_path / "sandboxes"
    )
    names_a = {item["name"] for item in list_sandbox_skills(tenant_a)}
    names_b = {item["name"] for item in list_sandbox_skills(tenant_b)}

    assert FORMAL_SKILLS <= names_a
    assert FORMAL_SKILLS <= names_b
    assert tenant_a.hermes_home != tenant_b.hermes_home


def test_requirements_clarification_protocol_enforces_rounds_and_recovery_boundary():
    from scripts.hermes_bridge_runtime.agent_execution import (
        _requirements_clarification_protocol_complete,
    )
    from scripts.hermes_bridge_runtime.contracts import DRILL_ME_MIN_ROUNDS

    selection = {
        "validated": True,
        "skill_id": "requirements-clarification",
    }
    assert not _requirements_clarification_protocol_complete(selection, {})
    assert not _requirements_clarification_protocol_complete(
        selection,
        {"clarify_attempts": 1, "clarify_rounds": 1},
    )
    assert _requirements_clarification_protocol_complete(
        selection,
        {
            "clarify_attempts": DRILL_ME_MIN_ROUNDS,
            "clarify_rounds": DRILL_ME_MIN_ROUNDS,
        },
    )
    assert not _requirements_clarification_protocol_complete(
        selection,
        {
            "clarify_attempts": 1,
            "clarify_rounds": 0,
            "clarify_expired": True,
        },
    )


def test_sensitive_execution_protocols_require_exact_same_turn_jev_skill():
    router = _load_router()
    router._LOCAL_TURN_STATES["none"] = {
        "principal": "local_owner",
        "requested_skill": None,
    }
    router._LOCAL_TURN_STATES["knowledge"] = {
        "principal": "local_owner",
        "requested_skill": "personal-knowledge-action",
    }
    router._LOCAL_TURN_STATES["authoring"] = {
        "principal": "local_owner",
        "requested_skill": "skill-authoring",
    }

    for tool in ("knowledge_workspace_read", "knowledge_action_propose", "note_draft"):
        denial = router._pre_tool_call(tool, {}, session_id="none")
        assert denial and "PCM_EXECUTION_PROTOCOL_MISMATCH" in denial["message"]
        assert router._pre_tool_call(tool, {}, session_id="knowledge") is None
    denial = router._pre_tool_call("tenant_skill_manage", {}, session_id="none")
    assert denial and "PCM_EXECUTION_PROTOCOL_MISMATCH" in denial["message"]
    assert router._pre_tool_call("tenant_skill_manage", {}, session_id="authoring") is None


def test_non_delegating_skill_agent_combination_is_rejected_by_jev_validation():
    router = _load_router()
    selector = sys.modules[f"{router.__package__}.jev_selector"]
    decision = selector._validate_output(
        {
            "skill_id": "skill:personal-knowledge-action",
            "agent_id": "agency:researcher",
            "skill_confidence": 0.9,
            "agent_confidence": 0.9,
            "reason_code": "MATCHED",
        },
        skill_ids={"skill:personal-knowledge-action"},
        agent_ids={"agency:researcher"},
        threshold=0.55,
        policy_version="p",
        catalog_version_value="c",
        latency_ms=1.0,
        decision_id="d",
        forbid_agent_with_skills={"skill:personal-knowledge-action"},
    )

    assert decision.skill_id is None
    assert decision.agent_id is None
    assert decision.reason_code == "INVALID_OUTPUT"


def test_skill_authoring_is_tenant_isolated_audited_and_requires_selection(
    tmp_path: Path, monkeypatch,
):
    sandbox = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="user-a", root=tmp_path / "sandboxes"
    )
    bridge._sandbox_tool_context.value = sandbox
    content = """---
name: test-helper
description: Use when the user asks for a bounded test helper. Do not use for deployment.
skill_path: testing/helpers
skill_level: professional
trigger_phrases:
  - create a bounded test helper
negative_phrases:
  - deploy to production
---
Return a deterministic checklist.
"""
    try:
        clear_runtime_capability_selection()
        denied = json.loads(bridge._tenant_skill_manage_tool({
            "action": "create", "name": "test-helper", "content": content,
        }))
        assert denied["error"] == "skill_authoring_not_selected"

        bind_runtime_capability_selection(
            skill_id="skill-authoring",
            agent_id=None,
            decision_id="authoring-test",
            catalog_version="test",
            policy_version="test",
        )
        from scripts.hermes_bridge_runtime import knowledge as knowledge_runtime

        real_append = knowledge_runtime._append_tenant_skill_audit

        def reject_audit(*_args, **_kwargs):
            raise OSError("audit unavailable")

        monkeypatch.setattr(
            knowledge_runtime, "_append_tenant_skill_audit", reject_audit
        )
        audit_denied = json.loads(bridge._tenant_skill_manage_tool({
            "action": "create", "name": "audit-denied", "content": content,
        }))
        assert audit_denied["success"] is False
        assert "audit-denied" not in {
            item["name"] for item in list_sandbox_skills(sandbox)
        }
        monkeypatch.setattr(
            knowledge_runtime, "_append_tenant_skill_audit", real_append
        )

        created = json.loads(bridge._tenant_skill_manage_tool({
            "action": "create", "name": "test-helper", "content": content,
        }))
        assert created["success"] is True
        assert created["scope"] == "tenant_private"
        assert len(created["sha256"]) == 64
        records = [
            json.loads(line)
            for line in (
                sandbox.hermes_home / "audit" / "tenant-skill-actions.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        assert records[-1]["name"] == "test-helper"
        assert records[-1]["phase"] == "committed"
        assert records[-1]["decision_id"] == "authoring-test"
        assert records[-1]["policy_version"] == "test"
        assert records[-1]["sha256"] == created["sha256"]
        assert "content" not in records[-1]
    finally:
        clear_runtime_capability_selection()
        bridge._sandbox_tool_context.value = None


def test_bridge_has_no_legacy_natural_language_capability_classifiers():
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "backend" / "api" / "chat.py",
            ROOT / "scripts" / "hermes_bridge_runtime" / "knowledge.py",
            ROOT / "scripts" / "hermes_bridge_runtime" / "agent_execution.py",
        )
    )
    for legacy_name in (
        "_NOTE_DRAFT_REQUEST_RE",
        "_SKILL_CREATE_REQUEST_RE",
        "_DRILL_ME_ACTION_RE",
        "_DRILL_ME_ARTIFACT_RE",
        "_is_note_draft_request",
        "_is_drill_me_goal",
        "_skill_management_decision",
    ):
        assert legacy_name not in production
