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
    assert "architecture_candidate" in resident_source
    assert "for kind in (\"skill\", \"agent\", \"capability\")" in resident_source


def test_resident_jev_shortlist_is_five_unique_cards_across_three_kinds(monkeypatch):
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
    capabilities = [{"id": "workflow.create", "kind": "capability", "use_when": ["plan a trip"]}]
    cards = capabilities + skills + agents + capabilities
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

    shortlisted_skills, shortlisted_agents, _, _, shortlisted_capabilities, _ = resident._shortlist({
        "request": "route this once",
        "skill_candidates": skills,
        "agent_candidates": agents,
        "capability_candidates": capabilities,
    })

    assert len(shortlisted_skills) + len(shortlisted_agents) + len(shortlisted_capabilities) == 5
    assert shortlisted_capabilities == capabilities


def test_agency_architect_cards_gain_governed_semantic_boundaries(monkeypatch, tmp_path):
    router = _load_router()
    catalog = tmp_path / "agents.json"
    catalog.write_text(json.dumps([{
        "slug": "security-architect",
        "name": "Security Architect",
        "description": "Security specialist.",
        "status": "active",
    }]), encoding="utf-8")
    monkeypatch.setattr(router, "_agency_data_path", lambda: catalog)

    card = router._agency_capabilities()[0]

    assert card["id"] == "agency:security-architect"
    assert any("multi-tenant isolation" in item for item in card["use_when"])
    assert any("localized code-security scan" in item for item in card["do_not_use_when"])


def test_architecture_capsule_accumulates_labels_without_copying_history():
    router = _load_router()
    secret = "SYNTHETIC_DO_NOT_COPY_4471"
    capsule = router._architecture_task_capsule(
        "这个方案的冷调用是否能优化？",
        conversation_history=[
            {"role": "user", "content": f"多租户隔离和权限边界 {secret}"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "Hermes是唯一Runtime，不要新建执行器"},
            {"role": "user", "content": "旁路POC要支持失败降级和验收"},
        ],
    )

    assert capsule["architecture_candidate"] is True
    assert capsule["routing_intent"] == "cross_component_architecture_design"
    assert capsule["dimension_count"] >= 3
    assert capsule["cross_turn"] is True
    assert {"access_control", "runtime_boundaries", "performance_budget"} <= set(
        capsule["labels"]
    )
    assert secret not in json.dumps(capsule, ensure_ascii=False)


def test_architecture_capsule_does_not_stick_to_unrelated_new_turn():
    router = _load_router()
    capsule = router._architecture_task_capsule(
        "今天晚饭吃什么？",
        conversation_history=[
            {"role": "user", "content": "设计多租户运行时、缓存和失败恢复架构"},
        ],
        prior_capsule={
            "version": "architecture-task-capsule-v1",
            "labels": ["access_control", "runtime_boundaries", "state_consistency"],
        },
    )

    assert capsule["architecture_candidate"] is False
    assert capsule["use_recent_context"] is False
    assert capsule["labels"] == []


def test_false_referent_and_single_dimension_do_not_reactivate_architecture_history():
    router = _load_router()
    prior = {
        "version": "architecture-task-capsule-v1",
        "labels": [
            "access_control", "deployment_migration", "resilience",
            "runtime_boundaries", "state_consistency",
        ],
    }
    false_referent = router._architecture_task_capsule(
        "这个天气怎么样？",
        conversation_history=[
            {"role": "user", "content": "SECRET-RAW-991 多租户架构和缓存恢复"},
        ],
        prior_capsule=prior,
    )
    narrow_task = router._architecture_task_capsule(
        "缓存怎么清？",
        conversation_history=[
            {"role": "user", "content": "旧的多租户运行时和失败恢复架构"},
        ],
        prior_capsule=prior,
    )

    assert false_referent["use_recent_context"] is False
    assert false_referent["architecture_candidate"] is False
    assert false_referent["labels"] == []
    assert narrow_task["architecture_candidate"] is False
    assert narrow_task["labels"] == ["state_consistency"]

    for request in (
        "这个问题先不谈，天气怎么样？",
        "这个任务取消。天气怎么样？",
    ):
        capsule = router._architecture_task_capsule(
            request,
            conversation_history=[
                {"role": "user", "content": "SECRET-RAW-991 旧的多租户运行时架构"},
            ],
            prior_capsule=prior,
        )
        assert capsule["architecture_candidate"] is False
        assert capsule["labels"] == []
        assert capsule["context_reset"] is True

    for request in (
        "这个问题先不谈，如何优化缓存？",
        "请忽略这个问题，缓存如何优化？",
        "这个任务取消。缓存如何优化？",
    ):
        capsule = router._architecture_task_capsule(
            request,
            conversation_history=[
                {"role": "user", "content": "SECRET-RAW-992 旧的多租户运行时架构"},
            ],
            prior_capsule=prior,
        )
        assert capsule["architecture_candidate"] is False
        assert capsule["labels"] == ["state_consistency"]
        assert capsule["context_reset"] is True

    expected_current = {
        "如何优化缓存？": ["state_consistency"],
        "缓存如何优化？": ["state_consistency"],
        "冷调用是什么？": ["performance_budget"],
        "冷调用如何优化？": ["performance_budget"],
        "Runtime调用如何优化？": ["runtime_boundaries"],
    }
    for request, labels in expected_current.items():
        capsule = router._architecture_task_capsule(
            request,
            conversation_history=[
                {"role": "user", "content": "旧的多租户运行时和失败恢复架构"},
            ],
            prior_capsule=prior,
        )
        assert capsule["architecture_candidate"] is False
        assert capsule["labels"] == labels


def test_architecture_capsule_carries_only_labels_across_long_referential_followup():
    router = _load_router()
    capsule = router._architecture_task_capsule(
        "这个问题继续修复",
        conversation_history=[
            {"role": "user", "content": f"ordinary turn {index}"}
            for index in range(12)
        ],
        prior_capsule={
            "version": "architecture-task-capsule-v1",
            "labels": ["access_control", "runtime_boundaries", "performance_budget"],
        },
    )

    assert capsule["architecture_candidate"] is True
    assert capsule["cross_turn"] is True
    assert capsule["labels"] == [
        "access_control", "performance_budget", "runtime_boundaries"
    ]


def test_resident_shortlist_reserves_authorized_architects_for_complex_task(monkeypatch):
    import numpy as np

    router = _load_router()
    resident = __import__(
        f"{router.__package__}.jev_resident", fromlist=["jev_resident"]
    )
    skills = [
        {"id": f"skill:s{i}", "kind": "skill", "use_when": [f"skill {i}"]}
        for i in range(6)
    ]
    agents = [
        {"id": "agency:generic-high-score", "kind": "agent", "use_when": ["generic"]},
        {"id": "agency:security-architect", "kind": "agent", "use_when": ["security architecture"]},
        {"id": "agency:software-architect", "kind": "agent", "use_when": ["software architecture"]},
    ]
    cards = skills + agents
    # Architects deliberately have the lowest embedding scores. The capsule may
    # reserve only already-authorized cards; it never selects them itself.
    scores = [0.99, 0.98, 0.97, 0.96, 0.95, 0.94, 0.90, 0.10, 0.09]
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
        np.asarray([[score, 1.0 - score] for score in scores]),
    )
    monkeypatch.setattr(resident, "_encode", lambda _texts: np.asarray([[1.0, 0.0]]))

    for budget in range(1, 6):
        monkeypatch.setattr(
            resident, "_integer",
            lambda name, default, budget=budget: budget if name == "shortlist_total" else default,
        )
        shortlisted_skills, shortlisted_agents, _, _, shortlisted_capabilities, _ = resident._shortlist({
            "request": "优化这套方案",
            "task_state": {"task_capsule": {
                "architecture_candidate": True,
                "labels": ["access_control", "runtime_boundaries", "performance_budget"],
            }},
            "skill_candidates": skills,
            "agent_candidates": agents,
            "capability_candidates": [],
        })

        ids = {card["id"] for card in shortlisted_agents}
        assert "agency:security-architect" in ids
        if budget >= 2:
            assert "agency:software-architect" in ids
        assert not shortlisted_capabilities
        assert len(shortlisted_skills) + len(shortlisted_agents) <= budget


def test_resident_architecture_reserve_never_invents_unauthorized_agent(monkeypatch):
    import numpy as np

    router = _load_router()
    resident = __import__(
        f"{router.__package__}.jev_resident", fromlist=["jev_resident"]
    )
    agents = [{"id": "agency:allowed-reviewer", "kind": "agent", "use_when": ["review"]}]
    monkeypatch.setattr(resident, "_READY", True)
    monkeypatch.setattr(resident, "_CARD_IDS", [agents[0]["id"]])
    monkeypatch.setattr(
        resident, "_CARD_TEXTS",
        {agents[0]["id"]: resident._card_text(agents[0])},
    )
    monkeypatch.setattr(resident, "_CARD_EMBEDDINGS", np.asarray([[1.0, 0.0]]))
    monkeypatch.setattr(resident, "_encode", lambda _texts: np.asarray([[1.0, 0.0]]))
    monkeypatch.setattr(resident, "_integer", lambda _name, default: default)

    _, shortlisted_agents, _, _, _, _ = resident._shortlist({
        "request": "设计租户隔离架构",
        "task_state": {"task_capsule": {
            "architecture_candidate": True,
            "labels": ["access_control"],
        }},
        "skill_candidates": [],
        "agent_candidates": agents,
        "capability_candidates": [],
    })

    assert [card["id"] for card in shortlisted_agents] == ["agency:allowed-reviewer"]


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

        audit_calls = 0

        def reject_commit_audit(*args, **kwargs):
            nonlocal audit_calls
            audit_calls += 1
            if audit_calls == 2:
                raise OSError("commit audit unavailable")
            return real_append(*args, **kwargs)

        monkeypatch.setattr(
            knowledge_runtime, "_append_tenant_skill_audit", reject_commit_audit
        )
        commit_denied = json.loads(bridge._tenant_skill_manage_tool({
            "action": "create", "name": "commit-denied", "content": content,
        }))
        assert commit_denied["success"] is False
        assert "commit-denied" not in {
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


def test_pcm_selection_uses_native_tool_and_requires_gateway_evidence(monkeypatch):
    from backend.services.capability_catalog import routing_capability_cards
    from backend.services.capability_projection import (
        set_runtime_routing_scope, reset_runtime_routing_scope,
        selected_capability_error, record_capability_result,
    )
    router = _load_router()
    card = routing_capability_cards({'workflow.create'})[0]
    monkeypatch.setattr(router, '_skill_capabilities', lambda: [])
    monkeypatch.setattr(router, '_agency_capabilities', lambda: [])
    decisions = []
    token = set_runtime_routing_scope({'capability_candidates': [card], 'emit_decision': decisions.append})
    def select(query, **kwargs):
        assert kwargs['capability_candidates'] == [card]
        assert kwargs['task_state']['recent_messages'][0]['content'] == '鹿儿岛七天公共交通'
        return SimpleNamespace(capability_id='workflow.create', skill_id=None,
            agent_id=None, reason='MATCHED', decision_id='pcm-test',
            catalog_version='pcm', policy_version='v1', latency_ms=1, cache_hit=False,
            as_dict=lambda: {'capability_id': 'workflow.create', 'validated': True})
    monkeypatch.setattr(router, 'select_route', select)
    try:
        plan = router._jev_routing_context('把以上做成攻略', state={},
            task_state={'recent_messages': [{'role': 'user', 'content': '鹿儿岛七天公共交通'}]},
            policy_version='v1')
        assert 'app_workflow_create' in plan and len(decisions) == 1
        assert selected_capability_error({}) == 'selected_capability_not_invoked'
        record_capability_result('notes.list', {'status': 'completed'})
        assert selected_capability_error({}) == 'selected_capability_not_invoked'
        record_capability_result('workflow.create', {'error': 'denied'})
        assert selected_capability_error({}) == 'selected_capability_failed'
        from contextvars import copy_context
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(copy_context().run, record_capability_result,
                        'workflow.create', {'status': 'awaiting_confirmation'}).result()
        assert selected_capability_error({}) is None
    finally:
        clear_runtime_capability_selection()
        reset_runtime_routing_scope(token)
