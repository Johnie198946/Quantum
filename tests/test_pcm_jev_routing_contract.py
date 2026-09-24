from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import sys
import types
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "agency/hermes-plugins/ai-lab-capabilities"


def _load_router():
    package = "pcm_jev_contract_test_plugin"
    for name in list(sys.modules):
        if name == package or name.startswith(package + "."):
            sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(
        package,
        PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[package] = module
    spec.loader.exec_module(module)
    return sys.modules[f"{package}.capability_router"]


def _card(identifier: str, kind: str) -> dict:
    name = identifier.split(":", 1)[1]
    return {
        "id": identifier,
        "kind": kind,
        "name": name,
        "description": f"Use {name} for its bounded task.",
        "version": "1.0.0",
        "use_when": [f"Use {name} for its bounded task."],
        "do_not_use_when": [],
        "requires": {"permissions": [], "tools": [], "platforms": []},
        "risk": "read",
        "status": "active",
    }


def _decision(skill_id: str | None, agent_id: str | None):
    return types.SimpleNamespace(
        decision_id="route-guard",
        skill_id=skill_id,
        agent_id=agent_id,
        catalog_version="sha256:test",
        policy_version="policy-test",
        as_dict=lambda: {
            "decision_id": "route-guard", "skill_id": skill_id, "agent_id": agent_id,
            "skill_confidence": 0.9 if skill_id else 0.0,
            "agent_confidence": 0.9 if agent_id else 0.0,
            "reason_code": "MATCHED" if skill_id or agent_id else "NO_MATCH",
            "policy_version": "policy-test", "catalog_version": "sha256:test",
            "latency_ms": 1.0, "validated": True,
        },
    )


def test_pcm_routing_contract_is_parseable_and_declares_single_runtime():
    contract = yaml.safe_load(
        (ROOT / "config/pcm-routing-contract.yaml").read_text(encoding="utf-8")
    )
    assert contract["runtime"] == "hermes"
    assert contract["execution"] == {
        "runtime": "hermes",
        "skill_adapter": "native-skill-view",
        "agent_adapter": "native-delegate-task",
        "agent_catalog": "agency_catalog_only",
        "named_profile_binding": "forbidden",
        "recursive_agent_selection": "forbidden",
        "tool_authorization": "qcp",
        "subagent_scope": "parent_subset",
    }
    assert contract["selector"]["limits"] == {"skills": 1, "agents": 1}
    assert contract["selector"]["residency"] == "hermes_gateway_process"
    assert contract["selector"]["cold_start_on_request"] == "forbidden"
    assert contract["selector"]["config_key"] == "plugins.entries.ai-lab-capabilities.settings.jev"
    assert contract["selector"]["candidate_projection"] == {
        "source": "pcm_authorized_cards",
        "shortlist": "resident_multilingual_embedding_top_k",
        "semantic_decision": "resident_hermes_auxiliary_client",
        "low_affinity_behavior": "hermes_direct",
    }
    assert contract["resident_model"]["runtime_owner"] == "hermes_gateway_process"
    assert contract["resident_model"]["deployment_activation"] == (
        "enabled_remote_semantic_default"
    )
    shortlist = contract["resident_model"]["shortlist"]
    assert shortlist["provisioner"] == "scripts/provision_jev_resident.py"
    assert shortlist["artifacts"] == {
        "arm64": {
            "path": "onnx/model_qint8_arm64.onnx",
            "sha256": "783fea82d71a58179b830a4dbd2d58447e640609e98eedf9ffa12622d375a672",
        },
        "x86_64": {
            "path": "onnx/model_quint8_avx2.onnx",
            "sha256": "98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f",
        },
    }
    assert contract["resident_model"]["decision"]["provider"] == "hermes_auxiliary_client"
    assert contract["resident_model"]["decision"]["config_key"] == "auxiliary.jev_selection"
    assert contract["resident_model"]["decision"] == {
        "purpose": "selection_only",
        "provider": "hermes_auxiliary_client",
        "model_provider": "openai-codex",
        "model": "gpt-6-luna",
        "api_mode": "codex_responses",
        "residency": "cached_client_in_gateway_process_remote_semantic_provider",
        "config_key": "auxiliary.jev_selection",
        "network_access": "required_on_cache_miss",
        "structured_output": "required",
        "request_timeout_seconds": 12.0,
        "warmup_timeout_seconds": 20.0,
    }
    assert contract["release_acceptance"]["decision"] == "accepted_accuracy_over_latency"
    assert contract["release_acceptance"]["policy"] == {
        "accuracy_gate": "passed_on_bounded_acceptance_set",
        "latency_gate": "explicitly_waived_by_owner",
        "timeout_or_invalid_output": "hermes_direct",
        "legacy_agency_selector": "forbidden",
        "jev_semantic_selector": "sole",
    }
    provisioner = (ROOT / "scripts/provision_jev_resident.py").read_text(encoding="utf-8")
    installer = (ROOT / "scripts/install_agency_hermes.sh").read_text(encoding="utf-8")
    assert "verify_dependencies()" in provisioner
    assert '"pip"' not in provisioner
    assert 'JEV_RESIDENT_ENABLE:-1' in installer
    assert "agency-agents-exact-loader/__init__.py" in installer
    exact_loader = (
        ROOT / "agency/hermes-plugins/agency-agents-exact-loader/__init__.py"
    ).read_text(encoding="utf-8")
    exact_manifest = yaml.safe_load(
        (ROOT / "agency/hermes-plugins/agency-agents-exact-loader/plugin.yaml")
        .read_text(encoding="utf-8")
    )
    assert exact_manifest["provides_tools"] == ["agency_agents_load"]
    assert "agency_agents_search" not in exact_loader
    assert "agency_agents_inspect" not in exact_loader
    assert "agency_agents_delegate" not in exact_loader
    assert "def _score" not in exact_loader
    assert set(contract["candidate_card_schema"]["required"]) == {
        "id", "kind", "version", "use_when", "do_not_use_when",
        "requires", "risk", "status",
    }


def test_named_profiles_and_inactive_agents_are_not_delegate_candidates(
    tmp_path, monkeypatch
):
    router = _load_router()
    catalog = tmp_path / "agents.json"
    catalog.write_text(json.dumps([
        {"slug": "reviewer", "status": "active", "version": "1.2.0"},
        {"slug": "supervision", "status": "disabled", "version": "1.0.0"},
    ]), encoding="utf-8")
    monkeypatch.setattr(router, "_agency_data_path", lambda: catalog)
    ids = {item["id"] for item in router._agency_capabilities()}
    assert ids == {"agency:reviewer"}


def test_runtime_main_chain_has_no_legacy_skill_or_agent_ranker_call():
    router_source = (PLUGIN_DIR / "capability_router.py").read_text(encoding="utf-8")
    bridge_source = (ROOT / "scripts/hermes_bridge.py").read_text(encoding="utf-8")
    router_tree = ast.parse(router_source)
    bridge_tree = ast.parse(bridge_source)

    functions = {
        node.name: node
        for node in router_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    jev_calls = {
        node.func.id
        for node in ast.walk(functions["_jev_routing_context"])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    install_calls = {
        node.func.id
        for node in ast.walk(functions["install"])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    bridge_calls = {
        node.func.id
        for node in ast.walk(bridge_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "select_route" in jev_calls
    assert not {"recommend", "_selected_skill", "_selected_agency"} & jev_calls
    assert "_extend_tool_search" not in install_calls
    assert "rank_skill_candidates" not in bridge_calls
    assert "candidate_prompt" not in bridge_calls

    skill_router = ast.parse((ROOT / "backend/services/skill_router.py").read_text())
    defined = {
        node.name for node in skill_router.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert not {
        "rank_skill_candidates", "candidate_prompt",
        "load_routing_overrides", "apply_routing_overrides",
    } & defined


def test_validated_jev_plan_uses_exact_native_skill_and_agent(monkeypatch):
    router = _load_router()
    skill = _card("skill:research", "skill")
    agent = _card("agency:reviewer", "agency_agent")
    captured = {}

    monkeypatch.setattr(router, "_skill_capabilities", lambda: [skill])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: [agent])

    def select(request_text, **kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(
            decision_id="route-test",
            skill_id="skill:research",
            agent_id="agency:reviewer",
            catalog_version="sha256:test",
            policy_version="policy-test",
            as_dict=lambda: {
                "decision_id": "route-test",
                "skill_id": "skill:research",
                "agent_id": "agency:reviewer",
                "skill_confidence": 0.9,
                "agent_confidence": 0.9,
                "reason_code": "MATCHED",
                "policy_version": "policy-test",
                "catalog_version": "sha256:test",
                "latency_ms": 1.0,
                "validated": True,
            },
        )

    monkeypatch.setattr(router, "select_route", select)
    state: dict[str, Any] = {"tenant_id": "tenant-a", "principal": "user-a"}
    context = router._jev_routing_context(
        "研究并复核",
        state,
        policy_version="policy-test",
        authorized_skill_ids=["skill:research"],
        authorized_agent_ids=["agency:reviewer"],
    )

    plan = json.loads(context.split("Plan: ", 1)[1])
    assert plan[0] == {
        "phase": "skill",
        "invoke": {"tool": "skill_view", "arguments": {"name": "research"}},
    }
    assert plan[1]["phase"] == "agent"
    assert plan[1]["invoke"]["tool"] == "delegate_task"
    assert state["decision_id"] == "route-test"
    assert captured["skill_candidates"] == [skill]
    assert captured["agent_candidates"] == [agent]


def test_selected_plan_cannot_bypass_existing_execution_guards(monkeypatch):
    router = _load_router()
    monkeypatch.setattr(
        router, "_skill_capabilities", lambda: [_card("skill:alpha", "skill")]
    )
    monkeypatch.setattr(
        router, "_agency_capabilities", lambda: [_card("agency:beta", "agency_agent")]
    )
    monkeypatch.setattr(router, "select_route", lambda *args, **kwargs: _decision(
        "skill:alpha", "agency:beta"
    ))
    state: dict[str, Any] = {"tenant_id": "tenant-a", "principal": "local_owner"}
    router._jev_routing_context(
        "task", state,
        authorized_skill_ids=["skill:alpha"],
        authorized_agent_ids=["agency:beta"],
    )
    router._LOCAL_TURN_STATES["guarded"] = state

    exact = state["expected_delegate_args"]
    assert router._pre_tool_call(
        "delegate_task", exact, session_id="guarded"
    )["action"] == "block"
    state["loaded_skill"] = "alpha"
    assert router._pre_tool_call(
        "delegate_task", {"tasks": [{"goal": "tampered"}]}, session_id="guarded"
    )["action"] == "block"
    assert router._pre_tool_call(
        "delegate_task", exact, session_id="guarded"
    ) is None


def test_child_inherits_scope_and_never_reselects(monkeypatch):
    router = _load_router()
    router._LOCAL_TURN_STATES["parent"] = {
        "principal": "approved_user",
        "tenant_id": "tenant-a",
        "policy_version": "policy-7",
        "catalog_version": "catalog-9",
        "decision_id": "decision-11",
    }
    router._subagent_start("parent", "child")
    child = router._LOCAL_TURN_STATES["child"]
    assert child == {
        "principal": "approved_user",
        "tenant_id": "tenant-a",
        "policy_version": "policy-7",
        "catalog_version": "catalog-9",
        "decision_id": "decision-11",
        "requested_skill": None,
        "requested_agent": None,
        "requested_agent_version": None,
        "skill_selected": False,
        "agent_selected": False,
        "is_child": True,
        "parent_session_id": "parent",
    }

    def forbidden(*args, **kwargs):
        raise AssertionError("child must not invoke JEV")

    monkeypatch.setattr(router, "select_route", forbidden)
    assert router._pre_llm_call("new child prompt", session_id="child") is None


def test_authorization_projection_is_applied_before_jev(monkeypatch):
    router = _load_router()
    monkeypatch.setattr(
        router,
        "_skill_capabilities",
        lambda: [_card("skill:a", "skill"), _card("skill:b", "skill")],
    )
    monkeypatch.setattr(
        router,
        "_agency_capabilities",
        lambda: [_card("agency:a", "agency_agent"), _card("agency:b", "agency_agent")],
    )
    observed = {}

    def select(_request_text, **kwargs):
        observed.update(kwargs)
        return types.SimpleNamespace(
            decision_id="route-none",
            skill_id=None,
            agent_id=None,
            catalog_version="sha256:test",
            policy_version="policy-test",
            as_dict=lambda: {
                "decision_id": "route-none", "skill_id": None, "agent_id": None,
                "skill_confidence": 0.0, "agent_confidence": 0.0,
                "reason_code": "NO_MATCH", "policy_version": "policy-test",
                "catalog_version": "sha256:test", "latency_ms": 1.0,
                "validated": True,
            },
        )

    monkeypatch.setattr(router, "select_route", select)
    state: dict[str, Any] = {"tenant_id": "tenant-a", "principal": "user-a"}
    assert router._jev_routing_context(
        "direct",
        state,
        authorized_skill_ids=["skill:a"],
        authorized_agent_ids=["agency:b"],
    ) == ""
    assert [item["id"] for item in observed["skill_candidates"]] == ["skill:a"]
    assert [item["id"] for item in observed["agent_candidates"]] == ["agency:b"]
    decision = state["route_decision"]
    assert isinstance(decision, dict)
    assert decision["reason_code"] == "NO_MATCH"


def test_bridge_request_scope_removes_agents_before_jev(monkeypatch):
    router = _load_router()
    from backend.services.capability_projection import (
        reset_runtime_routing_scope,
        set_runtime_routing_scope,
    )

    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(
        router,
        "_agency_capabilities",
        lambda: [_card("agency:a", "agency_agent")],
    )
    observed = {}

    def select(_request_text, **kwargs):
        observed.update(kwargs)
        return types.SimpleNamespace(
            decision_id="route-scoped",
            skill_id=None,
            agent_id=None,
            catalog_version="sha256:scoped",
            policy_version="tenant-policy-3",
            as_dict=lambda: {
                "decision_id": "route-scoped", "skill_id": None, "agent_id": None,
                "skill_confidence": 0.0, "agent_confidence": 0.0,
                "reason_code": "NO_MATCH", "policy_version": "tenant-policy-3",
                "catalog_version": "sha256:scoped", "latency_ms": 0.0,
                "validated": True, "cache_hit": False,
            },
        )

    monkeypatch.setattr(router, "select_route", select)
    token = set_runtime_routing_scope({
        "tenant_scope": "tenant:ta:user:ua",
        "policy_version": "tenant-policy-3",
        "authorized_agent_ids": [],
    })
    try:
        router._pre_llm_call(
            "ordinary request",
            session_id="bridge-scoped",
            platform="cli",
            sender_id="tenant-user",
        )
    finally:
        reset_runtime_routing_scope(token)
    assert observed["agent_candidates"] == []
    assert observed["policy_version"] == "tenant-policy-3"
    assert observed["tenant_scope"] == "tenant:ta:user:ua"
