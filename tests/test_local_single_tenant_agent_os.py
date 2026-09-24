from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = (
    ROOT
    / "agency"
    / "hermes-plugins"
    / "ai-lab-capabilities"
    / "__init__.py"
)


class LocalPluginContext:
    profile_name = "default"

    def __init__(self):
        self.tools = {}
        self.hooks = {}
        self.dispatched = []

    def register_tool(self, *, name, schema, handler, **metadata):
        self.tools[name] = {"schema": schema, "handler": handler, **metadata}

    def register_hook(self, name, callback):
        self.hooks[name] = callback

    def dispatch_tool(self, name, args, **kwargs):
        self.dispatched.append((name, args, kwargs))
        if name == "skill_view":
            return json.dumps({
                "success": True,
                "name": args["name"],
                "content": "# Verified skill\nUse evidence and preserve the original URL.",
                "readiness_status": "available",
            })
        if name == "delegate_task":
            return json.dumps({
                "status": "dispatched",
                "mode": "background",
                "delegation_id": "deleg-runtime-test",
                "count": 1,
            })
        return json.dumps({"success": False, "error": "unexpected_tool"})


def load_router():
    package_name = "local_single_tenant_agent_os_plugin"
    sys.modules.pop(package_name, None)
    sys.modules.pop(f"{package_name}.capability_router", None)
    spec = importlib.util.spec_from_file_location(
        package_name,
        PLUGIN_PATH,
        submodule_search_locations=[str(PLUGIN_PATH.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    return module, sys.modules[f"{package_name}.capability_router"]


def agency(router):
    return [{
        "id": "agency:trend-researcher",
        "kind": "agency_agent",
        "name": "Trend Researcher",
        "description": "Research market trends with evidence.",
        "domain": "research",
        "invoke_tool": "agency_agents_load",
        "invoke_args": {"agent": "trend-researcher"},
        "depth": 0.82,
        "cost": 0.10,
    }]


def skill(router):
    del router
    return {
        "id": "skill:business-model-research",
        "kind": "skill",
        "name": "business-model-research",
        "description": "Use when researching a business model.",
        "domain": "research",
        "invoke_tool": "skill_view",
        "invoke_args": {"name": "business-model-research"},
        "version": "1.0.0",
        "use_when": ["research a business model"],
        "do_not_use_when": [],
        "requires": {"permissions": [], "tools": [], "platforms": []},
        "risk": "read",
        "status": "active",
    }


def _test_select(request_text, **kwargs):
    """Simulate a validated JEV response without restoring a production heuristic."""
    skills = list(kwargs.get("skill_candidates") or [])
    agents = list(kwargs.get("agent_candidates") or [])
    explicit_agent = "必须委派" in request_text
    skill_id = str(skills[0]["id"]) if skills else None
    agent_id = str(agents[0]["id"]) if agents and explicit_agent else None
    return types.SimpleNamespace(
        decision_id="route-test",
        skill_id=skill_id,
        agent_id=agent_id,
        catalog_version="sha256:test",
        policy_version=str(kwargs.get("policy_version") or "policy-test"),
        as_dict=lambda: {
            "decision_id": "route-test", "skill_id": skill_id,
            "agent_id": agent_id, "skill_confidence": 0.9 if skill_id else 0.0,
            "agent_confidence": 0.9 if agent_id else 0.0,
            "reason_code": "MATCHED" if skill_id or agent_id else "NO_MATCH",
            "policy_version": str(kwargs.get("policy_version") or "policy-test"),
            "catalog_version": "sha256:test", "latency_ms": 1.0,
            "validated": True,
        },
    )


def stub_jev(router, monkeypatch):
    monkeypatch.setattr(router, "select_route", _test_select)


def test_default_profile_registers_local_agent_os_lifecycle():
    plugin, router = load_router()
    router._INSTALLED = False
    context = LocalPluginContext()
    plugin.register(context)
    assert set(context.hooks) == {
        "post_llm_call",
        "on_session_end",
        "pre_gateway_dispatch",
        "pre_llm_call",
        "pre_tool_call",
        "post_tool_call",
        "subagent_start",
        "subagent_stop",
        "transform_llm_output",
        "transform_tool_result",
    }
    # Stable schema is independent from runtime authorization and write-enable.
    assert "research_deposit" in context.tools["ai_lab_execute"]["schema"]["parameters"]["properties"]["capability"]["enum"]


def test_cloud_runtime_keeps_jev_skill_and_child_verification_hooks(monkeypatch):
    plugin, router = load_router()
    stub_jev(router, monkeypatch)
    router._INSTALLED = False
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setenv("AI_LAB_AGENT_OS_MODE", "cloud_multi_tenant")
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [skill(router)])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: [])
    context = LocalPluginContext()
    plugin.register(context)

    assert "pre_gateway_dispatch" not in context.hooks
    assert {"subagent_start", "subagent_stop", "transform_llm_output"} <= set(
        context.hooks
    )
    result = context.hooks["pre_llm_call"](
        "请使用技能研究市场",
        session_id="cloud-runtime-skill",
        turn_id="cloud-runtime-turn",
        platform="cli",
        sender_id="tenant-user",
        authorized_skill_ids=["skill:business-model-research"],
        authorized_agent_ids=[],
    )
    assert result is not None
    assert context.dispatched[0][0:2] == (
        "skill_view",
        {"name": "business-model-research"},
    )
    assert router._LOCAL_TURN_STATES["cloud-runtime-skill"]["loaded_skill"] == (
        "business-model-research"
    )


def test_runtime_reads_selected_skill_and_preserves_original_url_before_model(monkeypatch):
    plugin, router = load_router()
    stub_jev(router, monkeypatch)
    router._INSTALLED = False
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [skill(router)])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: agency(router))
    context = LocalPluginContext()
    plugin.register(context)
    original = "请必须委派子代理研究这篇文章并核验来源：https://example.com/report?a=1&b=2"

    result = context.hooks["pre_llm_call"](
        original,
        session_id="runtime-skill-parent",
        turn_id="runtime-skill-turn",
        platform="feishu",
        sender_id="owner-open-id",
    )

    assert result is not None
    assert context.dispatched[0][0:2] == (
        "skill_view",
        {"name": "business-model-research"},
    )
    state = router._LOCAL_TURN_STATES["runtime-skill-parent"]
    assert state["loaded_skill"] == "business-model-research"
    assert state["skill_result_hash"] == hashlib.sha256(
        "# Verified skill\nUse evidence and preserve the original URL.".encode()
    ).hexdigest()
    assert "RUNTIME_VERIFIED_SKILL_RESULT" in result["context"]
    assert len(context.dispatched) == 1
    assert state["delegation_dispatched"] is False
    raw_plan = result["context"].split("Plan: ", 1)[1]
    plan, _ = json.JSONDecoder().raw_decode(raw_plan)
    delegate_args = plan[1]["invoke"]["arguments"]
    assert delegate_args == state["expected_delegate_args"]
    assert delegate_args["tasks"][0]["goal"] == original
    blocked_other = router._pre_tool_call(
        "web_extract",
        {"urls": ["https://example.com/report"]},
        session_id="runtime-skill-parent",
    )
    assert blocked_other and "DELEGATION_REQUIRED" in blocked_other["message"]
    assert json.dumps(
        delegate_args, ensure_ascii=False, separators=(",", ":")
    ) in blocked_other["message"]
    assert router._pre_tool_call(
        "delegate_task", delegate_args, session_id="runtime-skill-parent"
    ) is None
    router._post_tool_call(
        "delegate_task",
        delegate_args,
        json.dumps({
            "status": "dispatched",
            "delegation_id": "deleg-runtime-test",
            "count": 1,
        }),
        session_id="runtime-skill-parent",
    )
    assert state["delegation_dispatched"] is True
    assert state["dispatch_delegation_id"] == "deleg-runtime-test"
    duplicate = router._pre_tool_call(
        "delegate_task", delegate_args, session_id="runtime-skill-parent"
    )
    assert duplicate and "already dispatched" in duplicate["message"]
    started = router._transform_llm_output(
        "我自行研究得到的未经 child 验证结果",
        session_id="runtime-skill-parent",
    )
    assert started.startswith("已启动专业研究")


def test_runtime_skill_failure_degrades_without_blocking_main(monkeypatch):
    plugin, router = load_router()
    stub_jev(router, monkeypatch)
    router._INSTALLED = False
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [skill(router)])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: agency(router))
    context = LocalPluginContext()
    context.dispatch_tool = lambda *_args, **_kwargs: json.dumps({
        "success": False,
        "error": "skill unavailable",
    })
    plugin.register(context)
    context.hooks["pre_llm_call"](
        "请使用技能研究 https://example.com/report",
        session_id="runtime-skill-failure",
        turn_id="runtime-skill-failure-turn",
        platform="feishu",
        sender_id="owner-open-id",
    )

    fallback = context.hooks["transform_llm_output"](
        "主 Agent 已直接完成任务。",
        session_id="runtime-skill-failure",
    )
    assert fallback == "主 Agent 已直接完成任务。"
    assert router._LOCAL_TURN_STATES["runtime-skill-failure"][
        "skill_failure_code"
    ] == "SKILL_RESULT_FAILED"


def test_runtime_skill_context_stays_below_hook_spill_limit(monkeypatch):
    plugin, router = load_router()
    stub_jev(router, monkeypatch)
    router._INSTALLED = False
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [skill(router)])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: agency(router))
    context = LocalPluginContext()
    context.dispatch_tool = lambda name, args, **_kwargs: json.dumps({
        "success": True,
        "name": args["name"],
        "content": "A" * 12000,
    })
    plugin.register(context)
    result = context.hooks["pre_llm_call"](
        "请使用技能研究 https://example.com/report",
        session_id="runtime-skill-spill",
        turn_id="runtime-skill-spill-turn",
        platform="feishu",
        sender_id="owner-open-id",
    )
    assert result is not None
    assert len(result["context"]) < 10000
    assert '"content_truncated":true' in result["context"]


def test_local_professional_turn_requires_native_skill_then_delegation(monkeypatch):
    _, router = load_router()
    stub_jev(router, monkeypatch)
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [skill(router)])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: agency(router))

    result = router._pre_llm_call(
        "请必须委派子代理系统调研企业 AI 市场并给出有证据的专业报告",
        session_id="local-parent",
        turn_id="local-turn",
        platform="desktop",
        sender_id="local-owner",
    )

    assert result is not None
    context = result["context"]
    assert "JEV_SELECTOR_PLAN" in context
    assert context.index('"tool":"skill_view"') < context.index('"tool":"delegate_task"')
    state = router._LOCAL_TURN_STATES["local-parent"]
    assert state["skill_selected"] is True
    assert state["requested_skill"] == "business-model-research"
    assert state["agent_selected"] is True
    assert state["requested_agent"] == "trend-researcher"
    assert state["expected_delegate_args"]["tasks"][0]["goal"] == (
        "请必须委派子代理系统调研企业 AI 市场并给出有证据的专业报告"
    )


def test_ordinary_professional_work_uses_optional_agency_and_never_blocks_tools(monkeypatch):
    _, router = load_router()
    stub_jev(router, monkeypatch)
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [skill(router)])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: agency(router))

    router._pre_llm_call(
        "请深入研究并整理以下土耳其旅行笔记，写入本地知识库并更新索引。",
        session_id="optional-ingestion",
        turn_id="optional-ingestion-turn",
        platform="desktop",
        sender_id="local-owner",
    )
    state = router._LOCAL_TURN_STATES["optional-ingestion"]
    assert state["route_decision"]["agent_id"] is None
    assert state["agent_selected"] is False
    assert router._pre_tool_call(
        "write_file",
        {"path": "/tmp/turkey.md", "content": "verified note"},
        session_id="optional-ingestion",
    ) is None
    state["skill_failure_code"] = "SKILL_RESULT_FAILED"
    assert router._transform_llm_output(
        "已真实写入并读回核验。", session_id="optional-ingestion"
    ) == "已真实写入并读回核验。"


def test_optional_delegate_failure_is_diagnostic_not_task_failure(monkeypatch):
    _, router = load_router()
    stub_jev(router, monkeypatch)
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: agency(router))
    router._pre_llm_call(
        "请必须委派子代理深入研究行业格局并核验来源",
        session_id="optional-research",
        turn_id="optional-research-turn",
        platform="desktop",
        sender_id="local-owner",
    )
    state = router._LOCAL_TURN_STATES["optional-research"]
    assert state["agent_selected"] is True
    router._post_tool_call(
        "delegate_task",
        state["expected_delegate_args"],
        json.dumps({"error": "temporary child failure"}),
        session_id="optional-research",
    )
    assert state["failure_code"] == "DELEGATE_RESULT_FAILED"
    assert "未通过本地 Agent OS 执行验证" in router._transform_llm_output(
        "主 Agent 使用真实网页证据完成研究。", session_id="optional-research"
    )


def test_wechat_verification_fallback_allows_real_browser_for_approved_user(monkeypatch):
    _, router = load_router()
    stub_jev(router, monkeypatch)
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: [])
    router._pre_llm_call(
        "看看这个微信链接 https://mp.weixin.qq.com/s/article-id",
        session_id="wechat-browser",
        turn_id="wechat-browser-turn",
        platform="feishu",
        sender_id="approved-user",
    )
    assert router._pre_tool_call(
        "browser_exec",
        {"code": "print(page_info())"},
        session_id="wechat-browser",
        turn_id="wechat-browser-turn",
    ) is None
    assert router._pre_tool_call(
        "web_extract",
        {"urls": ["https://mp.weixin.qq.com/s/article-id"]},
        session_id="wechat-browser",
        turn_id="wechat-browser-turn",
    ) is None
    repeated = router._pre_tool_call(
        "web_extract",
        {"urls": ["https://mp.weixin.qq.com/s/article-id"]},
        session_id="wechat-browser",
        turn_id="wechat-browser-turn",
    )
    assert repeated and "browser_exec" in repeated["message"]


def test_local_principal_scope_is_inherited_by_native_child(monkeypatch):
    _, router = load_router()
    stub_jev(router, monkeypatch)
    router._LOCAL_TURN_STATES.clear()
    router._GATEWAY_IDENTITIES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: [])
    source = types.SimpleNamespace(
        platform=types.SimpleNamespace(value="slack"),
        user_id="member-1",
        chat_id="group-1",
        chat_type="group",
    )
    event = types.SimpleNamespace(source=source, text="请专业调研行业趋势")
    assert router._pre_gateway_dispatch(event=event) is None
    router._pre_llm_call(
        event.text,
        session_id="parent-group",
        turn_id="turn-group",
        platform="slack",
        sender_id="member-1",
    )
    assert router._LOCAL_TURN_STATES["parent-group"]["principal"] == "group_member"
    assert router._pre_tool_call(
        "web_search", {"query": "AI market"}, session_id="parent-group"
    ) is None
    denied = router._pre_tool_call(
        "terminal", {"command": "whoami"}, session_id="parent-group"
    )
    assert denied and denied["action"] == "block"

    router._subagent_start(
        parent_session_id="parent-group",
        child_session_id="child-group",
    )
    assert router._pre_llm_call(
        "执行委派的专业研究任务",
        session_id="child-group",
        platform="subagent",
    ) is None
    assert router._LOCAL_TURN_STATES["child-group"]["is_child"] is True
    child_denied = router._pre_tool_call(
        "write_file", {"path": "/tmp/nope"}, session_id="child-group"
    )
    assert child_denied and child_denied["action"] == "block"
    recursive = router._pre_tool_call(
        "delegate_task", {"tasks": [{"goal": "escape"}]}, session_id="child-group"
    )
    assert recursive and "CHILD_REDELEGATION_FORBIDDEN" in recursive["message"]


def test_child_scope_allows_only_inherited_skill_and_agent(monkeypatch):
    _, router = load_router()
    monkeypatch.setattr(
        router,
        "_agency_capabilities",
        lambda: [{"id": "agency:trend-researcher", "version": "2.3.0"}],
    )
    router._LOCAL_TURN_STATES.clear()
    router._LOCAL_TURN_STATES["parent-bounded"] = {
        "principal": "local_owner",
        "tenant_id": "tenant-a",
        "policy_version": "policy-a",
        "catalog_version": "catalog-a",
        "route_decision": {"decision_id": "decision-a"},
        "requested_skill": "business-model-research",
        "requested_agent": "trend-researcher",
        "requested_agent_version": "2.3.0",
    }
    router._subagent_start(
        parent_session_id="parent-bounded",
        child_session_id="child-bounded",
    )
    assert router._pre_tool_call(
        "skill_view", {"name": "business-model-research"}, session_id="child-bounded"
    ) is None
    wrong_skill = router._pre_tool_call(
        "skill_view", {"name": "other-skill"}, session_id="child-bounded"
    )
    assert wrong_skill and "CHILD_SKILL_SCOPE_VIOLATION" in wrong_skill["message"]
    assert router._pre_tool_call(
        "agency_agents_load",
        {"agent": "trend-researcher", "task": "bounded"},
        session_id="child-bounded",
    ) is None
    wrong_agent = router._pre_tool_call(
        "agency_agents_load",
        {"agent": "other-agent", "task": "escape"},
        session_id="child-bounded",
    )
    assert wrong_agent and "CHILD_AGENT_SCOPE_VIOLATION" in wrong_agent["message"]
    router._LOCAL_TURN_STATES["child-bounded"]["requested_agent_version"] = "2.2.0"
    stale_agent = router._pre_tool_call(
        "agency_agents_load",
        {"agent": "trend-researcher", "task": "bounded"},
        session_id="child-bounded",
    )
    assert stale_agent and "CHILD_AGENT_VERSION_STALE" in stale_agent["message"]
    child = router._LOCAL_TURN_STATES["child-bounded"]
    assert child["tenant_id"] == "tenant-a"
    assert child["policy_version"] == "policy-a"
    assert child["catalog_version"] == "catalog-a"


def test_router_uses_request_local_hermes_home(tmp_path, monkeypatch):
    _, router = load_router()
    monkeypatch.setitem(
        sys.modules,
        "hermes_constants",
        types.SimpleNamespace(get_hermes_home=lambda: tmp_path),
    )
    assert router._hermes_home() == tmp_path


def test_direct_feishu_surface_is_local_owner_without_per_user_downgrade(monkeypatch):
    _, router = load_router()
    stub_jev(router, monkeypatch)
    router._LOCAL_TURN_STATES.clear()
    router._GATEWAY_IDENTITIES.clear()
    monkeypatch.delenv("FEISHU_CODE_WRITE_OWNER_IDS", raising=False)
    monkeypatch.delenv("AI_LAB_LOCAL_OWNER_IDS", raising=False)
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: [])
    router._pre_llm_call(
        "写入本地知识库",
        session_id="feishu-direct-owner",
        turn_id="feishu-direct-owner-turn",
        platform="feishu",
        sender_id="authenticated-feishu-user",
    )
    state = router._LOCAL_TURN_STATES["feishu-direct-owner"]
    assert state["principal"] == "local_owner"
    assert router._pre_tool_call(
        "write_file",
        {"path": "/tmp/direct-owner-note.md", "content": "ok"},
        session_id="feishu-direct-owner",
    ) is None


def test_cloud_multi_tenant_feishu_keeps_scoped_identity(monkeypatch):
    _, router = load_router()
    stub_jev(router, monkeypatch)
    router._LOCAL_TURN_STATES.clear()
    router._GATEWAY_IDENTITIES.clear()
    monkeypatch.setenv("AI_LAB_AGENT_OS_MODE", "cloud_multi_tenant")
    monkeypatch.delenv("FEISHU_CODE_WRITE_OWNER_IDS", raising=False)
    monkeypatch.delenv("AI_LAB_LOCAL_OWNER_IDS", raising=False)
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: [])
    router._pre_llm_call(
        "写入知识库",
        session_id="cloud-feishu-user",
        turn_id="cloud-feishu-user-turn",
        platform="feishu",
        sender_id="tenant-user",
    )
    state = router._LOCAL_TURN_STATES["cloud-feishu-user"]
    assert state["principal"] == "approved_user"
    denied = router._pre_tool_call(
        "write_file",
        {"path": "/tmp/cloud-user-note.md", "content": "no"},
        session_id="cloud-feishu-user",
    )
    assert denied and denied["action"] == "block"


def test_feishu_configured_owner_gets_full_local_owner_capabilities(monkeypatch):
    _, router = load_router()
    stub_jev(router, monkeypatch)
    router._LOCAL_TURN_STATES.clear()
    router._GATEWAY_IDENTITIES.clear()
    monkeypatch.setenv("FEISHU_CODE_WRITE_OWNER_IDS", "ou_owner")
    monkeypatch.delenv("AI_LAB_LOCAL_OWNER_IDS", raising=False)
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: [])

    source = types.SimpleNamespace(
        platform=types.SimpleNamespace(value="feishu"),
        user_id="ou_owner",
        chat_id="owner-dm",
        chat_type="dm",
    )
    event = types.SimpleNamespace(source=source, text="写入本地知识库")
    router._pre_gateway_dispatch(event=event)
    injected = router._pre_llm_call(
        event.text,
        session_id="owner-admin-session",
        turn_id="owner-admin-turn",
        platform="feishu",
        sender_id="ou_owner",
    )
    state = router._LOCAL_TURN_STATES["owner-admin-session"]
    assert state["principal"] == "local_owner"
    assert not injected or "read-only vault access" not in str(injected.get("context") or "")
    for tool_name, args in (
        ("terminal", {"command": "pwd"}),
        ("write_file", {"path": "/tmp/owner-note.md", "content": "ok"}),
        ("patch", {"path": "/tmp/owner-note.md"}),
        ("browser_exec", {"code": "print(page_info())"}),
    ):
        assert router._pre_tool_call(
            tool_name, args, session_id="owner-admin-session"
        ) is None


def test_missing_sender_internal_turn_inherits_verified_local_owner(monkeypatch):
    _, router = load_router()
    stub_jev(router, monkeypatch)
    router._LOCAL_TURN_STATES.clear()
    router._GATEWAY_IDENTITIES.clear()
    monkeypatch.setenv("FEISHU_CODE_WRITE_OWNER_IDS", "ou_owner")
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: [])

    first = router._pre_llm_call(
        "什么是本地知识库",
        session_id="owner-continuation",
        turn_id="owner-continuation-1",
        platform="feishu",
        sender_id="ou_owner",
    )
    assert not first or "knowledge recommendation" in first.get("context", "")
    second = router._pre_llm_call(
        "继续读取",
        session_id="owner-continuation",
        turn_id="owner-continuation-2",
        platform="feishu",
        sender_id="",
    )
    assert router._LOCAL_TURN_STATES["owner-continuation"]["principal"] == "local_owner"
    assert not second or "knowledge recommendation" in second.get("context", "")


def test_non_owner_feishu_user_cannot_read_local_vault(monkeypatch, tmp_path):
    _, router = load_router()
    router._LOCAL_TURN_STATES.clear()
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    monkeypatch.setenv("FEISHU_CODE_WRITE_OWNER_IDS", "ou_owner")
    router._LOCAL_TURN_STATES["non-owner"] = {
        "principal": "approved_user",
    }
    denied = router._pre_tool_call(
        "read_file", {"path": str(vault / "note.md")}, session_id="non-owner"
    )
    assert denied and denied["action"] == "block"


def test_local_in_memory_receipt_is_diagnostic_only(monkeypatch):
    _, router = load_router()
    stub_jev(router, monkeypatch)
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: agency(router))
    router._pre_llm_call(
        "请必须委派子代理系统调研市场趋势并核验多源证据",
        session_id="receipt-parent",
        turn_id="receipt-turn",
        platform="desktop",
        sender_id="owner",
    )

    blocked = router._transform_llm_output(
        response_text="看起来已经完成。",
        session_id="receipt-parent",
    )
    assert "未通过本地 Agent OS 执行验证" in blocked

    summary = "独立研究结论：企业采用率增长的主要约束是数据治理与集成成本。"
    router._subagent_stop(
        parent_session_id="receipt-parent",
        child_session_id="receipt-child",
        child_status="completed",
        child_summary=summary,
        tool_call_history=[{
            "tool_name": "agency_agents_load",
            "tool_input": {"targets": {"agent": "trend-researcher"}},
            "status": "ok",
        }],
    )
    state = router._LOCAL_TURN_STATES["receipt-parent"]
    assert state["receipt"]["verifier"] == "pass"
    assert state["receipt"]["result_hash"] == hashlib.sha256(summary.encode()).hexdigest()

    adopted = router._transform_llm_output(
        response_text="一段没有消费 child 结论的空泛回答。",
        session_id="receipt-parent",
    )
    assert "未通过本地 Agent OS 执行验证" in adopted


def test_untrusted_sender_cannot_use_wrapped_or_direct_privileged_tools(monkeypatch):
    _, router = load_router()
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: [])
    router._pre_llm_call(
        "请检查系统",
        session_id="untrusted",
        turn_id="untrusted-turn",
        platform="slack",
        sender_id="",
    )
    assert router._LOCAL_TURN_STATES["untrusted"]["principal"] == "untrusted_sender"
    direct = router._pre_tool_call(
        "terminal", {"command": "whoami"}, session_id="untrusted"
    )
    wrapped = router._pre_tool_call(
        "tool_call",
        {"name": "write_file", "arguments": {"path": "/tmp/nope"}},
        session_id="untrusted",
    )
    assert direct and direct["action"] == "block"
    assert wrapped and wrapped["action"] == "block"


def test_canonical_receipt_is_rebuilt_from_hermes_state_db(tmp_path, monkeypatch):
    _, router = load_router()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    connection = sqlite3.connect(tmp_path / "state.db")
    connection.executescript(
        """
        CREATE TABLE async_delegations (
            delegation_id TEXT, parent_session_id TEXT, state TEXT,
            dispatched_at REAL, completed_at REAL, task_json TEXT, result_json TEXT
        );
        CREATE TABLE sessions (
            id TEXT, parent_session_id TEXT, source TEXT, started_at REAL
        );
        CREATE TABLE messages (
            id INTEGER, session_id TEXT, tool_name TEXT, content TEXT
        );
        """
    )
    summary = "child verified result"
    requested = "trend-researcher"
    connection.execute(
        "INSERT INTO async_delegations VALUES (?,?,?,?,?,?,?)",
        (
            "deleg-real",
            "parent-real",
            "completed",
            10.0,
            20.0,
            json.dumps({"context": None}),
            json.dumps({
                "results": [{
                    "status": "completed",
                    "summary": summary,
                    "result_hash": hashlib.sha256(summary.encode()).hexdigest(),
                    "child_session_id": "child-real",
                    "tool_trace": [{
                        "tool": "tool_call",
                        "status": "ok",
                        "input_summary": {"targets": {}},
                    }],
                }]
            }),
        ),
    )
    connection.execute(
        "INSERT INTO sessions VALUES (?,?,?,?)",
        # Real Desktop delegations currently persist the child surface as
        # desktop; parent binding and delegation window are the stable facts.
        ("child-real", "parent-real", "desktop", 11.0),
    )
    connection.execute(
        "INSERT INTO messages VALUES (?,?,?,?)",
        (
            1,
            "child-real",
            "agency_agents_load",
            json.dumps({"success": True, "agent": {"slug": requested}}),
        ),
    )
    connection.commit()
    connection.close()

    receipt = router._canonical_local_receipt("parent-real", requested)
    assert receipt is not None
    assert receipt["verifier"] == "pass"
    assert receipt["delegation_id"] == "deleg-real"
    assert receipt["child_session_id"] == "child-real"
    assert receipt["loaded_agent"] == requested
    assert receipt["result_hash"] == hashlib.sha256(summary.encode()).hexdigest()
