"""Context selection and fail-closed validation for HTML illustrations."""

from __future__ import annotations

import hashlib
from html import escape
import json
import re
from typing import Any
from xml.etree import ElementTree

_MAX_SVG_BYTES = 160_000
_REQUIRED_PROMPT_FIELDS = {
    "subject",
    "semantic_relationship",
    "must_include",
    "must_avoid",
    "style",
    "composition",
    "accessibility_alt",
    "prompt",
}


def _paragraphs(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"\n\s*\n+", text) if item.strip()]


def select_illustration_context(source_text: str, goal: str) -> dict[str, Any]:
    """Select a focus paragraph plus its immediate neighbours deterministically."""
    paragraphs = _paragraphs(source_text) or [str(goal or "").strip()]
    if not paragraphs or not paragraphs[0]:
        raise ValueError("illustration_context_unavailable")
    goal_terms = {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", goal)
    }

    def score(item: tuple[int, str]) -> tuple[int, int, int]:
        index, paragraph = item
        folded = paragraph.casefold()
        overlap = sum(1 for token in goal_terms if token in folded)
        return overlap, min(len(paragraph), 1200), -index

    index, focus = max(enumerate(paragraphs), key=score)
    before = paragraphs[index - 1] if index else ""
    after = paragraphs[index + 1] if index + 1 < len(paragraphs) else ""
    joined = "\n\n".join(item for item in (before, focus, after) if item)
    return {
        "paragraph_index": index,
        "context_before": before[:4000],
        "focus_paragraph": focus[:8000],
        "context_after": after[:4000],
        "context_digest": hashlib.sha256(joined.encode("utf-8")).hexdigest(),
    }


def illustration_prompt_instruction(context: dict[str, Any]) -> str:
    return (
        "只输出合法 JSON。插图必须依据以下当前段落及相邻上下文设计，不能按章节标题套模板。\n"
        f"上文：{context.get('context_before') or '无'}\n"
        f"当前段落：{context['focus_paragraph']}\n"
        f"下文：{context.get('context_after') or '无'}\n"
        f"上下文摘要：{context['context_digest']}\n"
        "字段必须为 subject、semantic_relationship、must_include、must_avoid、style、"
        "composition、accessibility_alt、prompt。must_include/must_avoid 为字符串数组；"
        "prompt 必须明确主体、语义关系、必含元素、禁止元素、风格、构图、可读性，且不得包含图片中的小字。"
    )


def validate_illustration_prompt(raw: str, context: dict[str, Any]) -> str:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(raw).strip(), flags=re.I)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("illustration_prompt_invalid_json") from exc
    if not isinstance(value, dict) or not _REQUIRED_PROMPT_FIELDS.issubset(value):
        raise ValueError("illustration_prompt_fields_missing")
    for field in _REQUIRED_PROMPT_FIELDS - {"must_include", "must_avoid"}:
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise ValueError(f"illustration_prompt_invalid_{field}")
    for field in ("must_include", "must_avoid"):
        items = value.get(field)
        if not isinstance(items, list) or not items or any(
            not isinstance(item, str) or not item.strip() for item in items
        ):
            raise ValueError(f"illustration_prompt_invalid_{field}")
        value[field] = [item.strip()[:160] for item in items[:12]]
    prompt = value["prompt"]
    required_phrases = [value["subject"], value["semantic_relationship"], value["style"], value["composition"]]
    if any(phrase.strip() not in prompt for phrase in required_phrases):
        raise ValueError("illustration_prompt_not_traceable")
    if len(prompt) > 6000:
        raise ValueError("illustration_prompt_too_long")
    value.update({
        "context_digest": context["context_digest"],
        "paragraph_index": context["paragraph_index"],
        "context_before": context.get("context_before", ""),
        "focus_paragraph": context["focus_paragraph"],
        "context_after": context.get("context_after", ""),
        "verified": True,
    })
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def validate_illustration_svg(raw: str, prompt_json: str) -> str:
    svg = re.sub(r"^```(?:svg|xml)?\s*|\s*```$", "", str(raw).strip(), flags=re.I)
    if len(svg.encode("utf-8")) > _MAX_SVG_BYTES:
        raise ValueError("illustration_svg_too_large")
    if re.search(r"<(?:script|foreignObject)\b|\b(?:href|src)\s*=", svg, re.I):
        raise ValueError("illustration_svg_external_or_executable_content")
    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError as exc:
        raise ValueError("illustration_svg_invalid") from exc
    if root.tag.split("}")[-1] != "svg" or not root.attrib.get("viewBox"):
        raise ValueError("illustration_svg_viewbox_required")
    children = {child.tag.split("}")[-1] for child in root}
    if not {"title", "desc"}.issubset(children):
        raise ValueError("illustration_svg_accessibility_required")
    prompt = json.loads(prompt_json)
    digest = hashlib.sha256(prompt_json.encode("utf-8")).hexdigest()
    root.set("data-quantum-illustration", digest)
    root.set("role", "img")
    root.set("aria-label", str(prompt["accessibility_alt"])[:500])
    return ElementTree.tostring(root, encoding="unicode")


def embed_illustration(html: str, svg: str) -> str:
    digest = re.search(r'data-quantum-illustration="([0-9a-f]{64})"', svg)
    if not digest:
        raise ValueError("illustration_svg_receipt_missing")
    figure = (
        f'<figure class="quantum-illustration" data-prompt-sha256="{digest.group(1)}">'
        f"{svg}<figcaption class=\"sr-only\">章节语义插图</figcaption></figure>"
    )
    marker = "<!-- QUANTUM_ILLUSTRATION -->"
    if marker not in html:
        raise ValueError("html_illustration_marker_required")
    return html.replace(marker, figure, 1)
