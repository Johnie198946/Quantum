"""Knowledge retrieval remains authorized and optional, never a semantic gate."""
from __future__ import annotations

import json

import pytest

from backend.services.chat_triage import classify_request
from scripts import hermes_bridge as bridge


@pytest.mark.parametrize("question", [
    "康旅适合哪种智能分析方法？", "这个项目应该采用什么知识维护方法？",
    "How does this approach apply to our project?", "只查我的笔记，项目有什么约束？",
    "你好", "只回答OK", "",
])
def test_triage_never_removes_authorized_skill_agent_or_knowledge_tools(question):
    triage = classify_request(question).as_dict()
    selected = [
        "knowledge_gateway", "agency_agents", "delegation", "terminal", "file",
        "skills", "tenant_skills",
    ]
    assert bridge._apply_triage_toolset_policy(selected, triage) == selected
    assert bridge._apply_triage_toolset_policy([], triage) == []


@pytest.mark.parametrize("question", [
    "把这句话翻译成英文：今天心情很好",
    "翻译成英文：研究最新政策并设计架构报告",
    "Translate into Chinese: research latest prices and deploy the implementation",
])
def test_translation_adds_no_mandatory_knowledge_instruction(question):
    directive = bridge._triage_system_directive(classify_request(question).as_dict())
    assert "必须调用 knowledge_search" not in directive
    assert "回答前置条件" not in directive


def test_authorized_gateway_does_not_enable_public_web_without_evidence():
    triage = classify_request("仅内部材料，这个项目有什么约束？").as_dict()
    assert bridge._apply_triage_toolset_policy(
        ["knowledge_gateway", "web"], triage
    ) == ["knowledge_gateway"]


def test_platform_search_reads_authorized_body_and_preserves_evidence_metadata(monkeypatch):
    monkeypatch.setattr(bridge.persistence, "_knowledge_gateway_search", lambda *args, **kwargs: [{
        "path": "wiki/example.md", "title": "Example", "snippet": "定位片段",
        "markdown": "# Example\n\n完整正文", "content_status": "complete",
        "category": "knowledge/methodology/public", "freshness": "current",
        "knowledge_id": "kn-example", "version": "v3", "citation": "knowledge:wiki/example.md",
        "source_kind": "approved_summary", "conditions": ["仅适用于测试"],
        "effective_at": "2026-09-01",
    }])
    bridge._knowledge_tool_context.value = {
        "capability": "signed", "sources": ["tenant_knowledge"],
        "scopes": ["knowledge/methodology/public"],
    }
    try:
        result = json.loads(bridge._knowledge_search_tool({"query": "Example"}))
    finally:
        bridge._knowledge_tool_context.value = None
    assert result["success"] is True
    assert result["docs"][0]["markdown"].endswith("完整正文")
    assert result["docs"][0]["version"] == "v3"
    assert result["docs"][0]["conditions"] == ["仅适用于测试"]
