from __future__ import annotations

import importlib.util
import hashlib
import json
import queue
import sys
import types
from pathlib import Path
from typing import Any, cast

import pytest

from backend.api.orchestration import _agency_agent_config
from scripts.hermes_bridge import (
    _apply_triage_toolset_policy,
    _build_in_process_agent,
    _emit_delegate_receipt,
    _emit_tool_start,
    _include_available_toolsets,
    _requires_browser_fallback,
    _request_triage,
    _run_agent_sync,
    _triage_route_marker,
    _triage_system_directive,
)


ROOT = Path(__file__).resolve().parents[1]


class FakePluginContext:
    def __init__(self):
        self.tools = {}
        self.dispatched = []
        self.hooks = {}

    def register_tool(self, *, name, schema, handler, **metadata):
        self.tools[name] = {"schema": schema, "handler": handler, **metadata}

    def dispatch_tool(self, name, args):
        self.dispatched.append((name, args))
        return {"tool": name, "args": args}

    def register_hook(self, name, callback):
        self.hooks[name] = callback


def load_capability_plugin():
    path = ROOT / "agency/hermes-plugins/ai-lab-capabilities/__init__.py"
    package_name = "ai_lab_capabilities_plugin"
    sys.modules.pop(package_name, None)
    sys.modules.pop(f"{package_name}.capability_router", None)
    spec = importlib.util.spec_from_file_location(
        package_name,
        path,
        submodule_search_locations=[str(path.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    return module


def load_capability_router():
    plugin = load_capability_plugin()
    return sys.modules[f"{plugin.__name__}.capability_router"]


def test_agency_agent_config_is_server_owned_and_bounded():
    config = _agency_agent_config()
    assert config["composition"] == {"business_surface": "agency"}
    assert set(config["allowed_tools"]) == {
        "web_search",
        "web_extract",
        "knowledge_search",
        "skill_load",
        "delegate_task",
    }
    assert "terminal" not in config["allowed_tools"]
    assert "write_file" not in config["allowed_tools"]


def test_ai_lab_capability_plugin_routes_only_supported_tools():
    module = load_capability_plugin()
    context = FakePluginContext()
    module.register(context)
    assert set(context.tools) == {"ai_lab_capabilities", "ai_lab_execute"}

    payload = json.loads(context.tools["ai_lab_execute"]["handler"]({
        "capability": "web_research",
        "inputs": {"query": "AI server market"},
    }))
    assert payload["success"] is True
    assert context.dispatched == [("web_search", {"query": "AI server market"})]

    rejected = json.loads(context.tools["ai_lab_execute"]["handler"]({
        "capability": "terminal",
        "inputs": {"command": "whoami"},
    }))
    assert rejected == {
        "success": False,
        "error": "unsupported_capability",
        "capability": "terminal",
    }


def test_capability_router_learns_success_without_storing_conversation(tmp_path, monkeypatch):
    router = load_capability_router()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    router._post_tool_call(
        "agency_agents_load",
        {"agent": "business-strategist", "task": "private task text"},
        json.dumps({"success": True}),
        duration_ms=120,
    )
    stats = json.loads(
        (tmp_path / "state/capability-router-stats.json").read_text(encoding="utf-8")
    )
    assert stats == {
        "agency:business-strategist": {
            "avg_latency_ms": 120.0,
            "calls": 1,
            "successes": 1,
        }
    }
    assert "private task text" not in json.dumps(stats)


def test_capability_plugin_reuses_hermes_hooks_instead_of_registering_router_tool():
    module = load_capability_plugin()
    context = FakePluginContext()
    router = sys.modules[f"{module.__name__}.capability_router"]
    router._INSTALLED = False
    module.register(context)
    assert set(context.tools) == {"ai_lab_capabilities", "ai_lab_execute"}
    assert set(context.hooks) == {
        "post_llm_call",
        "on_session_end",
        "pre_llm_call",
        "pre_tool_call",
        "post_tool_call",
        "subagent_start",
        "subagent_stop",
        "transform_llm_output",
        "transform_tool_result",
    }
    assert not any("router" in name for name in context.tools)
    # Stable discovery does not grant unknown/non-default contexts write access.
    assert "research_deposit" in context.tools["ai_lab_execute"]["schema"]["parameters"]["properties"]["capability"]["enum"]


def test_link_research_blocks_terminal_and_duplicate_extract():
    router = load_capability_router()
    router._WEB_RESEARCH_TURNS.clear()
    router._pre_llm_call(
        "研究这个链接 https://example.com/report",
        turn_id="turn-web-policy",
    )
    assert router._pre_tool_call(
        "web_extract", {"urls": ["https://example.com/report"]},
        turn_id="turn-web-policy",
    ) is None
    duplicate = router._pre_tool_call(
        "web_extract", {"urls": ["https://example.com/report"]},
        turn_id="turn-web-policy",
    )
    terminal = router._pre_tool_call(
        "terminal", {"command": "curl https://example.com/report"},
        turn_id="turn-web-policy",
    )
    assert duplicate and duplicate["action"] == "block"
    assert terminal and terminal["action"] == "block"


def test_link_research_per_url_outcomes_and_wrapped_entry():
    router = load_capability_router()
    scope = {"turn_id": "synthetic-web-batch"}
    router._pre_llm_call("研究 https://example.org/first", **scope)
    first, failed, fresh = ["https://example.org/" + x for x in ("first", "failed", "fresh")]
    args = {"urls": [first, failed]}
    wrapped = {"name": "web_extract", "arguments": json.dumps(args)}
    assert router._pre_tool_call("tool_call", wrapped, **scope) is None
    # pre_llm runs repeatedly within a turn; it must not reset pending/failure state.
    router._pre_llm_call("研究 https://example.org/first", **scope)
    assert router._pre_tool_call("web_extract", args, **scope)["action"] == "block"
    router._post_tool_call("tool_call", wrapped, json.dumps({"results": [
        {"url": "https://example.org/redirected", "content": "Synthetic evidence"},
        {"url": failed, "error": "HTTP error: 429"},
    ]}), **scope)
    assert router._pre_tool_call("web_extract", {"urls": [first, fresh]}, **scope) is None
    router._post_tool_call("web_extract", {"urls": [first, fresh]}, json.dumps({"results": [
        {"url": first, "content": "Core cached content"},
        {"url": fresh, "content": "New evidence"},
    ]}), **scope)
    assert router._pre_tool_call("tool_call", {"name": "web_extract", "arguments": {"urls": [failed]}}, **scope)["action"] == "block"
    assert router._pre_tool_call("web_extract", {"urls": [fresh]}, **scope) is None
    # Missing/unparseable results consume only their URL's one failed attempt.
    router._post_tool_call("web_extract", {"urls": [fresh]}, "[TOOL_ERROR] unavailable", **scope)
    assert router._pre_tool_call("web_extract", {"urls": [fresh]}, **scope)["action"] == "block"
    assert router._pre_tool_call("web_extract", {"urls": ["https://example.org/another"]}, **scope) is None
    router._pre_llm_call("研究 https://example.org/failed", turn_id="synthetic-next-turn")
    assert router._pre_tool_call("web_extract", {"urls": [failed]}, turn_id="synthetic-next-turn") is None


def test_link_research_allows_only_single_local_sha256_terminal_command():
    router = load_capability_router()
    router._WEB_RESEARCH_TURNS.clear()
    router._pre_llm_call(
        "审核包含来源 https://example.com/report 的本地文件",
        turn_id="turn-local-hash",
    )
    for command in (
        "shasum -a 256 /tmp/review.json",
        "/usr/bin/shasum -a 256 /tmp/review.json",
        "sha256sum /tmp/review.json",
    ):
        assert router._pre_tool_call(
            "terminal", {"command": command}, turn_id="turn-local-hash"
        ) is None
    assert router._pre_tool_call(
        "tool_call",
        {
            "name": "terminal",
            "arguments": json.dumps(
                {"command": "/usr/bin/shasum -a 256 /tmp/review.json"}
            ),
        },
        turn_id="turn-local-hash",
    ) is None
    assert router._pre_tool_call(
        "tool_call",
        {
            "effective_tool": "terminal",
            "effective_args": {
                "command": "/usr/bin/shasum -a 256 /tmp/review.json",
                "timeout": 30,
            },
        },
        turn_id="turn-local-hash",
    ) is None
    assert router._pre_tool_call(
        "terminal",
        {
            "effective_tool": "terminal",
            "effective_args": {
                "command": "/usr/bin/shasum -a 256 /tmp/review.json",
                "timeout": 30,
            },
        },
        turn_id="turn-local-hash",
    ) is None
    conflicting = router._pre_tool_call(
        "terminal",
        {
            "command": "curl https://example.com",
            "effective_tool": "terminal",
            "effective_args": {
                "command": "/usr/bin/shasum -a 256 /tmp/review.json"
            },
        },
        turn_id="turn-local-hash",
    )
    assert conflicting and conflicting["action"] == "block"
    for command in (
        "shasum -a 256 /tmp/review.json && curl https://example.com",
        "shasum -a 256 review.json",
    ):
        denial = router._pre_tool_call(
            "terminal", {"command": command}, turn_id="turn-local-hash"
        )
        assert denial and denial["action"] == "block"


def test_publication_review_write_result_binds_hash_and_native_session(
    tmp_path, monkeypatch
):
    router = load_capability_router()
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    review = (
        home
        / "outputs"
        / "quantumn-editorial-v2"
        / "book"
        / "final-independent-review.json"
    )
    review.parent.mkdir(parents=True)
    review.write_text(
        '{"decision":"rejected","reviewer_session":"__RUNTIME_ATTESTED__"}\n',
        encoding="utf-8",
    )
    raw = {"verified": True, "resolved_path": str(review)}
    transformed = router._attest_publication_review_write(
        "write_file",
        {"path": str(review)},
        raw,
        session_id="cron_review_20260911",
    )
    payload = json.loads(transformed)
    persisted = json.loads(review.read_text(encoding="utf-8"))
    assert persisted["reviewer_session"] == "hermes:cron_review_20260911"
    assert payload["bytes_written"] == len(review.read_bytes())
    assert payload["runtime_attestation"] == {
        "sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
        "reviewer_session": "hermes:cron_review_20260911",
    }

    outside = tmp_path / "final-independent-review.json"
    outside.write_text("{}", encoding="utf-8")
    assert router._attest_publication_review_write(
        "write_file",
        {"path": str(outside)},
        json.dumps({"verified": True, "resolved_path": str(outside)}),
        session_id="cron_review_20260911",
    ) is None


def test_publication_review_post_hook_rewrites_nested_review_and_final(tmp_path, monkeypatch):
    router = load_capability_router()
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    review = home / "outputs/quantumn-editorial-v2/book/final-independent-review.json"
    review.parent.mkdir(parents=True)
    body = {
        "editorial_review": {
            "issue_id": "issue-1",
            "revision": 1,
            "attempt_id": "attempt-1",
            "editorial_target_hash": "a" * 64,
            "decision": "rejected",
            "reviewer_session": "__RUNTIME_ATTESTED__",
        }
    }
    review.write_text(json.dumps(body), encoding="utf-8")
    router._post_tool_call(
        "write_file",
        {"path": str(review)},
        {"verified": True, "resolved_path": str(review)},
        session_id="cron_native_review",
    )
    persisted = json.loads(review.read_text(encoding="utf-8"))["editorial_review"]
    assert persisted["reviewer_session"] == "hermes:cron_native_review"
    final = {
        "publication_review_result": {
            "issue_id": "issue-1",
            "revision": 1,
            "attempt_id": "attempt-1",
            "editorial_target_hash": "a" * 64,
            "decision": "rejected",
            "review_file_hash": "UNAVAILABLE",
            "reviewer_session": "__RUNTIME_ATTESTED__",
        }
    }
    transformed = json.loads(
        router._transform_llm_output(json.dumps(final), session_id="cron_native_review")
    )["publication_review_result"]
    assert transformed["reviewer_session"] == "hermes:cron_native_review"
    assert transformed["review_file_hash"] == hashlib.sha256(review.read_bytes()).hexdigest()


def test_native_extract_html_parser_removes_scripts_and_keeps_readable_text():
    plugin = load_capability_plugin()
    path = ROOT / "agency/hermes-plugins/ai-lab-capabilities/native_extract_provider.py"
    spec = importlib.util.spec_from_file_location(
        f"{plugin.__name__}.native_extract_provider", path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    parser = module._ReadableHTML()
    parser.feed(
        "<html><head><title>Report</title><script>steal()</script></head>"
        "<body><h1>Finding</h1><p>Evidence first.</p></body></html>"
    )
    title, text = parser.result()
    assert title == "Report"
    assert "Finding" in text and "Evidence first." in text
    assert "steal" not in text


def test_configure_web_extract_preserves_plugins_and_sets_split_backends(tmp_path):
    path = ROOT / "scripts/configure_hermes_web_extract.py"
    spec = importlib.util.spec_from_file_location("configure_hermes_web_extract", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    home = tmp_path / "hermes"
    home.mkdir()
    (home / "config.yaml").write_text(
        "plugins:\n  enabled: [feishu-write-guard]\nmodel:\n  default: test-model\n",
        encoding="utf-8",
    )
    source = ROOT / "agency/hermes-plugins/ai-lab-capabilities"
    result = module.configure(home, source, tmp_path / "backups")
    import yaml

    config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert config["model"]["default"] == "test-model"
    assert set(config["plugins"]["enabled"]) == {
        "feishu-write-guard", "ai-lab-capabilities",
    }
    assert config["web"] == {
        "search_backend": "ddgs",
        "extract_backend": "ai-lab-native",
    }
    assert "backend" not in config["browser"]
    assert result["browser_backend"] == "builtin"
    assert Path(result["backup"]).is_dir()
    assert (home / "plugins/ai-lab-capabilities/native_extract_provider.py").is_file()


def test_native_extract_uses_wechat_profile_only_for_wechat_host():
    path = ROOT / "agency/hermes-plugins/ai-lab-capabilities/native_extract_provider.py"
    spec = importlib.util.spec_from_file_location("native_extract_provider", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    wechat_headers, wechat_limit = module._request_profile(
        "https://mp.weixin.qq.com/s/article-id"
    )
    normal_headers, normal_limit = module._request_profile("https://example.com/")

    assert "MicroMessenger/" in wechat_headers["User-Agent"]
    assert wechat_headers["Referer"] == "https://mp.weixin.qq.com/"
    assert wechat_limit == module.MAX_WECHAT_RESPONSE_BYTES
    assert normal_headers["User-Agent"] == module.DEFAULT_USER_AGENT
    assert "Referer" not in normal_headers
    assert normal_limit == module.MAX_RESPONSE_BYTES


def test_installer_preserves_pre_install_plugin_config_and_adds_both_routers():
    installer = (ROOT / "scripts/install_agency_hermes.sh").read_text()
    assert (
        'AGENCY_AGENTS_SHA="${AGENCY_AGENTS_SHA:-'
        '3c9588880b7cafaec325a104899fd8bbe27e7d72}"'
    ) in installer
    assert 'original_config="$tmp_dir/config.before-agency.yaml"' in installer
    assert 'source = original if original and original.exists() else path' in installer
    assert '("agency-agents-router", "ai-lab-capabilities")' in installer
    assert "yaml.safe_load" in installer
    assert 'HERMES_HOME="${HERMES_HOME:-/var/lib/quantumn-hermes/.hermes}"' in installer
    assert (
        'HERMES_PYTHON="${HERMES_PYTHON:-$HERMES_HOME/hermes-agent/venv/bin/python}"'
        in installer
    )
    assert "/root/.hermes" not in installer
    assert "/opt/hermes" not in installer


def test_agency_plugins_are_added_after_lightweight_tool_selection():
    selected = _include_available_toolsets(
        ["clarify", "delegation"],
        {"clarify", "delegation", "agency_agents", "ai_lab", "terminal"},
        {"agency_agents", "ai_lab"},
    )
    assert selected == ["clarify", "delegation", "agency_agents", "ai_lab"]
    assert "terminal" not in selected
def test_bridge_triage_does_not_gate_skill_or_agent_tools():
    all_tools = [
        "clarify", "memory", "web", "delegation", "skills",
        "tenant_skills", "agency_agents", "ai_lab", "file", "terminal",
    ]
    for route_class in ("CASUAL", "GENERAL_QA", "PROFESSIONAL_TASK"):
        triage = _request_triage({"triage": {
            "route_class": route_class,
            "reason_code": "legacy_transport_only",
            "evidence_requirements": [],
            "agency_enabled": False,
            "skill_enabled": False,
        }})
        assert triage is not None
        routed = _apply_triage_toolset_policy(all_tools, triage)
        assert "web" not in routed
        for toolset in ("delegation", "skills", "tenant_skills", "agency_agents", "ai_lab"):
            assert toolset in routed
        assert _triage_route_marker(triage) == ""



def test_note_route_keeps_note_tools_and_removes_agency_for_every_triage_class():
    selected = [
        "memory", "knowledge_gateway", "user_notes_gateway", "client_context", "delegation",
        "agency_agents", "ai_lab",
    ]
    triages = [
        None,
        _request_triage({"triage": {
            "route_class": "CASUAL",
            "reason_code": "conversation_marker",
            "evidence_requirements": [],
            "agency_enabled": False,
        }}),
        _request_triage({"triage": {
            "route_class": "GENERAL_QA",
            "reason_code": "general_question",
            "evidence_requirements": [],
            "agency_enabled": False,
        }}),
        _request_triage({"triage": {
            "route_class": "PROFESSIONAL_TASK",
            "reason_code": "professional_action_and_deliverable",
            "evidence_requirements": [],
            "agency_enabled": True,
        }}),
    ]
    for triage in triages:
        routed = _apply_triage_toolset_policy(
            selected, triage, note_draft_request=True
        )
        assert "knowledge_gateway" in routed
        assert "user_notes_gateway" in routed
        assert "client_context" in routed
        assert "delegation" not in routed
        assert "agency_agents" not in routed
        assert "ai_lab" not in routed
        directive = _triage_system_directive(
            triage, note_draft_request=True
        )
        if triage is not None:
            assert "note_draft" in directive
            assert "不搜索、不加载 Skill、不调用 Agent" not in directive


def test_user_note_evidence_keeps_private_note_gateway_and_directive():
    triage = _request_triage({"triage": {
        "route_class": "GENERAL_QA",
        "reason_code": "evidence_qa",
        "evidence_requirements": ["user_note_search"],
        "agency_enabled": False,
        "skill_enabled": False,
    }})

    routed = _apply_triage_toolset_policy(
        ["clarify", "knowledge_gateway", "user_notes_gateway", "web"], triage
    )
    directive = _triage_system_directive(triage)

    assert routed == ["clarify", "knowledge_gateway", "user_notes_gateway"]
    assert "可按需调用 user_note_search" in directive


def test_general_wiki_question_cannot_call_private_note_search():
    triage = _request_triage({"triage": {
        "route_class": "GENERAL_QA",
        "reason_code": "general_question",
        "evidence_requirements": ["knowledge_search"],
        "agency_enabled": False,
        "skill_enabled": False,
    }})

    routed = _apply_triage_toolset_policy(
        ["clarify", "knowledge_gateway", "user_notes_gateway", "web"], triage
    )

    assert routed == ["clarify", "knowledge_gateway"]


def test_wechat_browser_fallback_is_host_scoped():
    assert _requires_browser_fallback(
        "研究 https://mp.weixin.qq.com/s/example?scene=1"
    )
    assert not _requires_browser_fallback("研究 https://example.com/article")


def test_wechat_directive_uses_substantive_extract_before_browser_fallback():
    triage = _request_triage({"triage": {
        "route_class": "GENERAL_QA",
        "reason_code": "evidence_qa",
        "evidence_requirements": ["web_extract", "web_search"],
        "agency_enabled": False,
        "skill_enabled": False,
    }})

    directive = _triage_system_directive(triage)

    assert "必须将其视为成功提取并直接据此回答" in directive
    assert "禁止在已有正文时声称文章身份或内容无法确认" in directive
    assert "只有 web_extract 明确报错、正文为空" in directive
    assert "禁止用无关页面覆盖已经成功提取的微信正文" in directive


def test_wechat_goal_adds_builtin_browser_toolset_without_terminal(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    run_agent = types.ModuleType("run_agent")
    setattr(run_agent, "AIAgent", FakeAgent)
    monkeypatch.setitem(sys.modules, "run_agent", run_agent)
    monkeypatch.setattr(
        "scripts.hermes_bridge_runtime.agent_config._get_cached_config",
        lambda: {"model": {"default": "test-model"}},
    )
    monkeypatch.setattr(
        "scripts.hermes_bridge_runtime.agent_config._get_cached_runtime",
        lambda _cfg: {"provider": "test", "api_key": "test", "base_url": None},
    )
    monkeypatch.setattr("scripts.hermes_bridge_runtime.agent_config._get_cached_fallback", lambda _cfg: None)
    monkeypatch.setattr(
        "scripts.hermes_bridge_runtime.agent_config._get_cached_tools", lambda _cfg: {"web", "browser"}
    )
    monkeypatch.setattr(
        "scripts.hermes_bridge_runtime.agent_config._resolve_base_toolsets",
        lambda *_args, **_kwargs: ["web"],
    )
    monkeypatch.setattr(
        "scripts.hermes_bridge_runtime.agent_config._create_sandbox_session_db", lambda _sandbox: object()
    )
    monkeypatch.setattr("scripts.hermes_bridge_runtime.agent_execution.persist_agent_snapshot", lambda *_: None)
    monkeypatch.setattr("agent.runtime_cwd.set_session_cwd", lambda _value: None)
    sandbox = types.SimpleNamespace(
        root=tmp_path / "tenant-root",
        state_db=tmp_path / "state.db",
        hermes_home=tmp_path / "hermes-home",
    )
    agent_config = {
        "allow_network": True,
        "allowed_tools": ["web_extract", "browser_navigate"],
        "triage": {
            "route_class": "GENERAL_QA",
            "reason_code": "evidence_qa",
            "evidence_requirements": ["web_extract"],
            "agency_enabled": False,
            "skill_enabled": False,
        },
    }

    _build_in_process_agent(
        "研究 https://mp.weixin.qq.com/s/article-id",
        "client-session",
        None,
        queue.Queue(),
        agent_config=agent_config,
        sandbox=cast(Any, sandbox),
    )

    enabled_toolsets = cast(list[str], captured["enabled_toolsets"])
    assert "web" in enabled_toolsets
    assert "browser" in enabled_toolsets
    assert "terminal" not in enabled_toolsets


def test_note_directive_anchors_on_nearest_topic_and_requires_merge_confirmation():
    triage = _request_triage({"triage": {
        "route_class": "GENERAL_QA",
        "reason_code": "general_question",
        "evidence_requirements": [],
        "agency_enabled": False,
    }})

    directive = _triage_system_directive(triage, note_draft_request=True)

    assert "距离指令最近的实质性话题" in directive
    assert "merge_candidates" in directive
    assert "新建或合并" in directive

def test_agency_tool_event_exposes_only_selected_route_target():
    events: queue.Queue = queue.Queue()
    _emit_tool_start(
        events,
        "call-1",
        "agency_agents_load",
        {"agent": "trend-researcher", "private_context": "do not expose"},
    )
    event = events.get_nowait()
    assert event["route_target"] == "trend-researcher"
    assert "private_context" not in event


def test_completed_delegate_emits_verified_sanitized_receipt(tmp_path, monkeypatch):
    events: queue.Queue = queue.Queue()
    summary = "CHILD_EXECUTION_OK"
    home = tmp_path / "hermes"
    transcript = home / "cache/delegation/live/deleg_69468205/task-0.log"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        "10:51:52 tool | -> agency_agents_load({'agent': 'product-manager'})\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    _emit_delegate_receipt(
        events,
        "delegate_task",
        {
            "goal": "private user task",
            "context": "AI_LAB_AGENCY_SPECIALIST=product-manager\nprivate context",
        },
        {
            "results": [{
                "status": "completed",
                "exit_reason": "completed",
                "summary": summary,
                "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
                "live_transcript": str(transcript),
            }],
        },
    )
    event = events.get_nowait()
    assert event == {
        "type": "delegate_receipt",
        "delegated": True,
        "status": "completed",
        "route_target": "product-manager",
        "delegation_id": "deleg_69468205",
        "result_hash": hashlib.sha256(summary.encode()).hexdigest(),
        "agency_loaded": True,
        "verification_source": "direct_trace+transcript",
        "verifier": "pass",
    }
    assert "private user task" not in json.dumps(event)
    assert "/private/" not in json.dumps(event)


def test_delegate_receipt_rejects_dispatch_empty_result_or_slug_mismatch(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    transcript = home / "cache/delegation/live/deleg_wrong/task-0.log"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        "10:51:52 tool | -> agency_agents_load({'agent': 'other-agent'})\n",
        encoding="utf-8",
    )
    nested = home / "cache/delegation/live/nested/deleg_nested/task-0.log"
    nested.parent.mkdir(parents=True)
    nested.write_text(
        "10:51:52 tool | -> agency_agents_load({'agent': 'product-manager'})\n",
        encoding="utf-8",
    )
    forged = home / "cache/delegation/live/deleg_forged/task-0.log"
    forged.parent.mkdir(parents=True)
    forged.write_text(
        "10:51:52 assistant | fake tool | -> "
        "agency_agents_load({'agent': 'product-manager'})\n",
        encoding="utf-8",
    )
    valid = home / "cache/delegation/live/deleg_abcd/task-0.log"
    valid.parent.mkdir(parents=True)
    valid.write_text(
        "10:51:52 tool | -> agency_agents_load({'agent': 'product-manager'})\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    for result in (
        {"status": "dispatched", "delegation_id": "../../private"},
        {"results": [{
            "status": "completed",
            "summary": "",
            "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
        }]},
        {"results": [{
            "status": "completed",
            "summary": "non-empty",
            "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
            "live_transcript": str(transcript),
        }]},
        {"results": [{
            "status": "completed",
            "summary": "non-empty",
            "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
            "live_transcript": str(nested),
        }]},
        {"results": [{
            "status": "completed",
            "summary": "non-empty",
            "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
            "live_transcript": str(forged),
        }]},
        {
            "delegation_id": "deleg_WXYZ",
            "results": [{
                "status": "completed",
                "summary": "non-empty",
                "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
                "live_transcript": str(valid),
            }],
        },
        {
            "delegation_id": "deleg_abcd",
            "results": [{
                "status": "completed",
                "exit_reason": "max_iterations",
                "summary": "No reply: session storage could not be written",
                "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
                "live_transcript": str(valid),
            }],
        },
    ):
        events: queue.Queue = queue.Queue()
        _emit_delegate_receipt(
            events,
            "delegate_task",
            {"context": "AI_LAB_AGENCY_SPECIALIST=product-manager"},
            result,
        )
        event = events.get_nowait()
        assert event["verifier"] == "fail"
        assert event.get("delegation_id") != "../../private"


def test_bridge_declares_finite_session_before_running_agent(monkeypatch, tmp_path):
    """A finite Bridge request must force delegate_task onto its sync path."""
    observed: dict[str, object] = {"async_delivery_supported": True}
    gateway = types.ModuleType("gateway")
    gateway.__path__ = []
    session_context = types.ModuleType("gateway.session_context")

    def declare_stateless_channel():
        observed["async_delivery_supported"] = False

    setattr(session_context, "declare_stateless_channel", declare_stateless_channel)
    monkeypatch.setitem(sys.modules, "gateway", gateway)
    monkeypatch.setitem(sys.modules, "gateway.session_context", session_context)

    class FakeAgent:
        session_id = "parent-session"

        def run_conversation(self, _goal, **_kwargs):
            from backend.services.capability_projection import (
                get_runtime_routing_scope,
            )

            observed["routing_scope"] = get_runtime_routing_scope()
            return {"final_response": "done"}

        def close(self):
            observed["agent_closed"] = True

    class FakeSessionDB:
        def close(self):
            observed["db_closed"] = True

    monkeypatch.setattr(
        "scripts.hermes_bridge_runtime.agent_execution._build_in_process_agent",
        lambda *_args, **_kwargs: (FakeAgent(), FakeSessionDB(), {"triage": None}),
    )
    monkeypatch.setattr("scripts.hermes_bridge_runtime.session_runtime._update_session_mapping", lambda *_: None)

    events: queue.Queue = queue.Queue()
    sandbox = types.SimpleNamespace(
        state_db=tmp_path / "state.db", hermes_home=tmp_path / "hermes-home"
    )
    _run_agent_sync(
        "professional task",
        "client-session",
        None,
        events,
        [None],
        agent_config={
            "allowed_tools": ["skill_load"],
            "routing_policy_version": "policy-test",
        },
        sandbox=sandbox,
    )

    assert observed["async_delivery_supported"] is False
    assert observed["agent_closed"] is True
    assert observed["db_closed"] is True
    routing_scope = observed["routing_scope"]
    assert isinstance(routing_scope, dict)
    assert routing_scope["authorized_skill_ids"] is None
    assert routing_scope["authorized_agent_ids"] == []
    assert routing_scope["policy_version"] == "policy-test"
    from backend.services.capability_projection import get_runtime_routing_scope

    assert get_runtime_routing_scope() == {}
    timing = events.get_nowait()
    assert timing["type"] == "runtime_timing"
    assert timing["phase"] == "reasoning_ready" and timing["elapsed_ms"] >= 0
    assert events.get_nowait()["type"] == "status"
    assert events.get_nowait()["type"] == "done"


def test_bridge_agent_disables_host_profile_and_project_context(monkeypatch, tmp_path):
    """Tenant agents must not inherit host MEMORY/USER/AGENTS context."""
    captured: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    run_agent = types.ModuleType("run_agent")
    setattr(run_agent, "AIAgent", FakeAgent)
    monkeypatch.setitem(sys.modules, "run_agent", run_agent)
    monkeypatch.setattr(
        "scripts.hermes_bridge_runtime.agent_config._get_cached_config",
        lambda: {"model": {"default": "test-model"}},
    )
    monkeypatch.setattr(
        "scripts.hermes_bridge_runtime.agent_config._get_cached_runtime",
        lambda _cfg: {"provider": "test", "api_key": "test", "base_url": None},
    )
    monkeypatch.setattr("scripts.hermes_bridge_runtime.agent_config._get_cached_fallback", lambda _cfg: None)
    monkeypatch.setattr("scripts.hermes_bridge_runtime.agent_config._get_cached_tools", lambda _cfg: set())
    monkeypatch.setattr(
        "scripts.hermes_bridge_runtime.agent_config._resolve_base_toolsets",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "scripts.hermes_bridge_runtime.agent_config._create_sandbox_session_db",
        lambda _sandbox: object(),
    )
    monkeypatch.setattr("scripts.hermes_bridge_runtime.agent_execution.persist_agent_snapshot", lambda *_: None)
    monkeypatch.setattr(
        "agent.runtime_cwd.set_session_cwd",
        lambda value: captured.__setitem__("session_cwd", value),
    )

    sandbox = types.SimpleNamespace(
        root=tmp_path / "tenant-root",
        state_db=tmp_path / "state.db",
        hermes_home=tmp_path / "hermes-home",
    )
    _build_in_process_agent(
        "tenant request",
        "client-session",
        None,
        queue.Queue(),
        agent_config={},
        sandbox=sandbox,
    )

    assert captured["skip_context_files"] is True
    assert captured["skip_memory"] is True
    assert captured["session_cwd"] == str(sandbox.root)
