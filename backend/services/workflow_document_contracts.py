"""Pure document workflow prompt and structural contract helpers.

This module is the single source of truth for document output constraints used by
Hermes workflow execution.  It deliberately has no FastAPI, database, or Hermes
runtime dependencies so the behavior can be golden-tested independently.
"""

from __future__ import annotations

import re
from typing import Any


def apply_explicit_document_replacements(reply: str, revision_comment: str) -> str:
    """Apply auditable exact ``将 A 改为 B`` revisions or fail closed."""
    text = str(reply or "")
    replacements: list[tuple[str, str]] = []
    for clause in re.split(r"[；;\n]+", str(revision_comment or "")):
        marker = clause.find("将")
        if marker < 0 or "改为" not in clause[marker + 1 :]:
            continue
        source, target = clause[marker + 1 :].split("改为", 1)
        source = source.strip().removeprefix("原来的").strip(" \t\r\n“”\"'。")
        target = target.strip(" \t\r\n“”\"'。")
        if source and target and source != target:
            replacements.append((source, target))
    for source, target in replacements:
        if source in text:
            text = text.replace(source, target)
        elif target not in text:
            raise RuntimeError(
                f"修订失败：成果中既没有待替换值 {source!r}，也没有目标值 {target!r}"
            )
    return text


def document_source_constraints(run: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return literal verified DOI identifiers and fail-closed source markers."""
    source_text = str(((run.get("source_material") or {}).get("text")) or "")
    verified_dois = list(
        dict.fromkeys(
            match.rstrip(".,;:)]}")
            for match in re.findall(
                r"(?<![A-Za-z0-9])10\.\d{4,9}/[A-Za-z0-9._;()/:+\-]+",
                source_text,
                flags=re.IGNORECASE,
            )
        )
    )
    exclusion_lines = [
        line
        for line in source_text.splitlines()
        if re.search(r"fail[- ]closed|unverified|未核实|未验证", line, flags=re.IGNORECASE)
    ]
    exclusion_text = "\n".join(exclusion_lines)
    forbidden: list[str] = []
    for url in re.findall(r"https?://[^\s]+", exclusion_text):
        clean_url = url.rstrip(".,;)]}")
        forbidden.append(clean_url)
        without_scheme = re.sub(r"^https?://", "", clean_url, flags=re.IGNORECASE)
        forbidden.append(without_scheme)
        if "/" in without_scheme:
            host, path = without_scheme.split("/", 1)
            forbidden.extend((host, path.rstrip("/")))
    return verified_dois, list(dict.fromkeys(marker for marker in forbidden if marker))


def document_required_source_labels(run: dict[str, Any]) -> list[str]:
    """Return explicit S-number citation labels that must survive rendering."""
    source_text = str(((run.get("source_material") or {}).get("text")) or "")
    return list(dict.fromkeys(re.findall(r"\[S\d+\]", source_text, flags=re.IGNORECASE)))


def document_source_constraint_issues(run: dict[str, Any], reply: str) -> list[str]:
    verified_dois, forbidden = document_source_constraints(run)
    source_text = str((run.get("source_material") or {}).get("text") or "")
    section_match = re.search(
        r"must contain,? in this order:\s*([^.]+)",
        source_text,
        flags=re.IGNORECASE,
    )
    required_sections: list[str] = []
    if section_match:
        raw_sections = re.sub(
            r"\s+and\s+", ",", section_match.group(1), flags=re.IGNORECASE
        )
        required_sections = [
            part.strip(" .") for part in raw_sections.split(",") if part.strip(" .")
        ]
    text = str(reply or "")
    issues = [f"缺少已核验 DOI：{doi}" for doi in verified_dois if doi not in text]
    required_labels = document_required_source_labels(run)
    issues.extend(
        f"缺少指定来源标签：{label}" for label in required_labels if label not in text
    )
    issues.extend(
        f"包含 fail-closed 来源标记：{marker}" for marker in forbidden if marker in text
    )
    lowered = text.lower()
    issues.extend(
        f"缺少必需章节：{section}"
        for section in required_sections
        if section.lower() not in lowered
    )
    return issues


def document_source_constraint_instruction(run: dict[str, Any]) -> str:
    verified_dois, forbidden = document_source_constraints(run)
    lines = [
        "重写完整正文并严格执行来源字面量门禁：",
        "每个已核验 DOI 必须在正文引用和 References 的对应记录中原样保留："
        + "、".join(verified_dois),
    ]
    if forbidden:
        lines.append(
            "以下 fail-closed 来源及其域名、路径不得出现在正文或 References，"
            "也不要用‘已排除’之类句子再次提及它们：" + "、".join(forbidden)
        )
    required_labels = document_required_source_labels(run)
    if required_labels:
        lines.append(
            "来源标签必须逐字保留并在正文引用及对应参考文献中使用，不得改成纯数字脚注："
            + "、".join(required_labels)
        )
    source_text = str((run.get("source_material") or {}).get("text") or "")
    section_match = re.search(
        r"must contain,? in this order:\s*([^.]+)", source_text, flags=re.IGNORECASE
    )
    if section_match:
        lines.append("以下章节标题必须原样出现且顺序不变：" + section_match.group(1).strip())
    lines.append("不得声称已提供的 DOI 缺失或待核验；不得新增其他来源。")
    return "\n".join(lines)


def workflow_minimum_document_pages(run: dict[str, Any]) -> int:
    values = [
        str(run.get("goal") or ""),
        str(run.get("deliverable") or ""),
        str(((run.get("source_material") or {}).get("text")) or ""),
    ]
    values.extend(
        str(state.get("output") or "")
        for state in (run.get("nodes") or {}).values()
        if isinstance(state, dict)
    )
    source = "\n".join(values)
    chinese = {"二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6}
    pages = [
        int(token) if token.isdigit() else chinese.get(token, 1)
        for token in re.findall(
            r"(?:至少|不少于|不低于)\s*([二两三四五六]|\d+)\s*页", source
        )
    ]
    english = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
    pages.extend(
        int(token) if token.isdigit() else english.get(token.lower(), 1)
        for token in re.findall(
            r"(?:at\s+least|no\s+fewer\s+than|minimum(?:\s+of)?)\s+"
            r"(two|three|four|five|six|\d+)\s+(?:(?:full|rendered)\s+)?pages?",
            source,
            flags=re.IGNORECASE,
        )
    )
    pages.extend(
        int((node.get("parameters") or {}).get("minimum_pages") or 1)
        for node in ((run.get("plan") or {}).get("nodes") or [])
        if isinstance(node, dict)
    )
    return max(pages, default=1)


def ensure_document_page_breaks(reply: str, minimum_pages: int) -> str:
    text = str(reply or "")
    current_pages = text.count("\f") + 1
    if minimum_pages <= current_pages:
        return text
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    if len(paragraphs) < minimum_pages:
        raise RuntimeError(
            f"文档只有 {len(paragraphs)} 个段落，无法生成 {minimum_pages} 个非空页面"
        )
    base, extra = divmod(len(paragraphs), minimum_pages)
    chunks: list[str] = []
    cursor = 0
    for index in range(minimum_pages):
        size = base + (1 if index < extra else 0)
        chunks.append("\n\n".join(paragraphs[cursor : cursor + size]))
        cursor += size
    return "\f".join(chunks)


def workflow_output_incomplete(node: dict[str, Any], reply: str) -> bool:
    """Reject intermediate control text emitted before actual tool execution."""
    normalized = str(reply or "").strip().lower()
    if not normalized:
        return True
    if "<tool_switch_" in normalized or "<tool_call" in normalized:
        return True
    if str(node.get("node_type") or "") != "KNOWLEDGE_RETRIEVAL":
        return False
    planning_markers = (
        "我先确认",
        "我先检查",
        "先确认当前",
        "接下来我会",
        "使用 bash 工具",
    )
    return len(normalized) < 320 and any(
        marker in normalized for marker in planning_markers
    )
