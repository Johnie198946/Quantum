"""Existing Workflow contracts for explicitly requested PPTX and DOCX outputs."""

from __future__ import annotations

import re
from typing import Any

SCENARIO_ID = "presentation-generation"
LEGACY_SCENARIO_ID = "document-to-presentation"
DOCUMENT_SCENARIO_ID = "document-generation"
SCENARIO_VERSION = "3.0.0"
DEFAULT_THEME = {
    "colors": {
        "primary": "#8057E8",
        "text": "#191521",
        "muted": "#686275",
        "pale": "#F1EEFA",
        "background": "#FFFFFF",
        "inverse": "#FFFFFF",
    },
    "fonts": {"title": "Aptos", "body": "Aptos"},
}


def validate_theme(raw: Any) -> dict[str, dict[str, str]]:
    if not isinstance(raw, dict) or set(raw) != {"colors", "fonts"}:
        raise ValueError("theme contains unsupported or missing fields")
    colors, fonts = raw.get("colors"), raw.get("fonts")
    if not isinstance(colors, dict) or set(colors) != set(DEFAULT_THEME["colors"]):
        raise ValueError("theme colors are incomplete or unsupported")
    if not isinstance(fonts, dict) or set(fonts) != set(DEFAULT_THEME["fonts"]):
        raise ValueError("theme fonts are incomplete or unsupported")
    if any(
        not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color)
        for color in colors.values()
    ):
        raise ValueError("theme colors must use #RRGGBB")
    if any(
        not isinstance(font, str)
        or not font.strip()
        or len(font) > 80
        or any(ord(character) < 32 for character in font)
        for font in fonts.values()
    ):
        raise ValueError("theme font names are invalid")
    return {
        "colors": {key: color.upper() for key, color in colors.items()},
        "fonts": {key: font.strip() for key, font in fonts.items()},
    }


def is_presentation_workflow(workflow) -> bool:
    return (workflow.requirements_snapshot or {}).get("scenario_id") in {
        SCENARIO_ID,
        LEGACY_SCENARIO_ID,
    }


def is_document_workflow(workflow) -> bool:
    return (workflow.requirements_snapshot or {}).get("scenario_id") == DOCUMENT_SCENARIO_ID


def build_presentation_plan(
    workflow, *, plan_id: str, knowledge_scope: list[str]
) -> dict[str, Any] | None:
    if not is_presentation_workflow(workflow):
        return None
    snapshot = workflow.requirements_snapshot or {}
    configured_review_gates = snapshot.get("presentation_review_gates") or []
    if (
        not isinstance(configured_review_gates, list)
        or any(gate not in {"outline", "design"} for gate in configured_review_gates)
    ):
        raise ValueError("presentation_review_gates contains unsupported values")
    review_gates = set(configured_review_gates)
    source = snapshot.get("source_document") or {}
    text_material = str(snapshot.get("text_material") or "").strip()
    should_research = not source and not text_material
    source_hint = (
        "源文档"
        if source
        else "用户提供的文字材料"
        if text_material
        else "用户指令与检索到的可靠资料"
    )
    common = {
        "scenario_id": SCENARIO_ID,
        "scenario_version": SCENARIO_VERSION,
        "knowledge_scope": knowledge_scope,
        "allow_network": True,
    }
    nodes = [
        {
            "id": "presentation_analysis",
            "node_type": "LLM_INFERENCE",
            "name": "分析文档与提炼证据",
            "parameters": {
                **common,
                "agent_id": "main_agent",
                "output_format": "markdown",
                "instruction": f"基于{source_hint}形成演示简报：受众目标、核心结论、关键事实、可用数据、内容缺口与不得推断项。每项事实必须保留事实清单中的 claim_id；不得凭空补造事实。",
                "max_tokens": 5000,
            },
        },
        {
            "id": "presentation_outline",
            "node_type": "LLM_INFERENCE",
            "name": "生成演示文稿大纲",
            "parameters": {
                **common,
                "agent_id": "main_agent",
                "output_format": "presentation_outline",
                **({"approval_gate": "outline"} if "outline" in review_gates else {}),
                "instruction": "基于分析和已确认需求设计逐页故事线。每页写明标题、页面作用、核心要点、source_claim_ids 与建议视觉；标题直接说明主题或有证据支持的结论，不得补造事实。",
                "max_tokens": 8000,
            },
        },
        {
            "id": "presentation_design",
            "node_type": "LLM_INFERENCE",
            "name": "生成代表页设计样稿",
            "parameters": {
                **common,
                "agent_id": "main_agent",
                "output_format": "presentation_design",
                **({"approval_gate": "design"} if "design" in review_gates else {}),
                "instruction": "仅基于已批准大纲生成 3 至 5 张带真实内容的代表页，覆盖封面、关键正文以及适用的数据或结论页；同时给出完整配色与字体。保留 source_claim_ids，不得使用空占位符或虚构数据。",
                "max_tokens": 7000,
            },
        },
        {
            "id": "presentation_deck",
            "node_type": "OUTPUT_FORMAT",
            "name": "生成可编辑演示文稿",
            "parameters": {
                **common,
                "agent_id": "main_agent",
                "output_format": "presentation",
                "instruction": "严格按已批准的大纲逐页填入内容，并沿用已批准代表页的设计系统。优先删减内容而不是缩小字号；标题直接、文字自然，图表只使用可核验的数据。",
                "max_tokens": 16000,
            },
        },
    ]
    if should_research:
        nodes.insert(0, {
            "id": "presentation_research",
            "node_type": "KNOWLEDGE_RETRIEVAL",
            "name": "检索主题资料与证据",
            "parameters": {
                **common,
                "agent_id": "knowledge",
                "query": workflow.description,
                "max_tokens": 5000,
            },
        })
    edges = [
        {"source": "presentation_analysis", "target": "presentation_outline"},
        {"source": "presentation_analysis", "target": "presentation_design"},
        {"source": "presentation_outline", "target": "presentation_design"},
        {"source": "presentation_outline", "target": "presentation_deck"},
        {"source": "presentation_design", "target": "presentation_deck"},
    ]
    if should_research:
        edges.insert(0, {"source": "presentation_research", "target": "presentation_analysis"})
    return {
        "plan_id": plan_id,
        "name": workflow.title,
        "version": SCENARIO_VERSION,
        "scenario_id": SCENARIO_ID,
        "source_document": source,
        "nodes": nodes,
        "edges": edges,
    }


def build_document_plan(
    workflow, *, plan_id: str, knowledge_scope: list[str]
) -> dict[str, Any] | None:
    if not is_document_workflow(workflow):
        return None
    source = (workflow.requirements_snapshot or {}).get("source_document") or {}
    profile = (workflow.requirements_snapshot or {}).get("document_profile") or {}
    document_kind = str(profile.get("kind") or "word")
    citation_style = str(profile.get("citation_style") or "none")
    required_structure = str(
        profile.get("required_structure") or "清晰的标题层级与正文"
    )
    common = {
        "scenario_id": DOCUMENT_SCENARIO_ID,
        "scenario_version": SCENARIO_VERSION,
        "knowledge_scope": knowledge_scope,
        "allow_network": profile.get("evidence_policy") != "user_material_only",
        "document_kind": document_kind,
        "citation_style": citation_style,
    }
    nodes = [
        {
            "id": "document_analysis",
            "node_type": "LLM_INFERENCE",
            "name": "分析目标与素材",
            "parameters": {
                **common,
                "agent_id": "main_agent",
                "output_format": "markdown",
                "instruction": f"基于用户指令、可选源文件和可靠资料，明确文档目的、读者、核心观点、证据、结构约束与内容缺口，不得虚构。文档类型：{document_kind}；必要结构：{required_structure}；引文格式：{citation_style}。",
                "max_tokens": 5000,
            },
        },
        {
            "id": "document_outline",
            "node_type": "LLM_INFERENCE",
            "name": "生成 Word 文档大纲",
            "parameters": {
                **common,
                "agent_id": "main_agent",
                "output_format": "markdown",
                "approval_gate": "outline",
                "instruction": f"基于分析和已确认需求生成可审阅的分级大纲，逐节说明目的、要点和证据依据；必须覆盖：{required_structure}。",
                "max_tokens": 7000,
            },
        },
        {
            "id": "document_draft",
            "node_type": "LLM_INFERENCE",
            "name": "生成 Word 文档全文",
            "parameters": {
                **common,
                "agent_id": "main_agent",
                "output_format": "word",
                "approval_gate": "content",
                "instruction": f"严格按已批准大纲写成完整、可直接使用的正文；结构清晰、事实可核验、语言符合用户指定风格；引文和参考文献统一采用 {citation_style}，未知来源必须标记待核验而非编造。",
                "max_tokens": 16000,
            },
        },
        {
            "id": "document_file",
            "node_type": "OUTPUT_FORMAT",
            "name": "输出可编辑 Word 文档",
            "parameters": {
                **common,
                "agent_id": "main_agent",
                "output_format": "word",
                "instruction": "严格保留已批准全文的结构、事实和表达，输出最终可编辑 Word 文档。",
                "max_tokens": 16000,
            },
        },
    ]
    edges = [
        {"source": "document_analysis", "target": "document_outline"},
        {"source": "document_outline", "target": "document_draft"},
        {"source": "document_draft", "target": "document_file"},
    ]
    if not source:
        nodes.insert(0, {
            "id": "document_research",
            "node_type": "KNOWLEDGE_RETRIEVAL",
            "name": "检索主题资料与证据",
            "parameters": {
                **common,
                "agent_id": "knowledge",
                "query": workflow.description,
                "max_tokens": 5000,
            },
        })
        edges.insert(0, {"source": "document_research", "target": "document_analysis"})
    return {
        "plan_id": plan_id,
        "name": workflow.title,
        "version": SCENARIO_VERSION,
        "scenario_id": DOCUMENT_SCENARIO_ID,
        "source_document": source,
        "nodes": nodes,
        "edges": edges,
    }
