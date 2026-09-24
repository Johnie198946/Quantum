"""Server-owned Skill metadata normalization and tree construction.

Only compact routing metadata is handled here. Full Skill instructions remain
inside the authenticated Hermes sandbox and are loaded after model selection.
"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any, Iterable

VALID_LEVELS = {"simple", "professional"}

_SPACE_RE = re.compile(r"\s+")
_PROFESSIONAL_RE = re.compile(
    r"(?:深入|专业|完整|系统|多源|核验|审计|生产|上线|架构|基准|报告|方案|"
    r"合规|风险|指标|端到端|竞品|行业研究|professional|production|benchmark|audit)",
    re.IGNORECASE,
)
_TRIGGER_SCENE_RE = re.compile(
    r"(?:当用户|用户要求|用户需要|适用于|仅用于|不能用于|不要用于|use when|"
    r"when the user|only for|do not use|must not use)",
    re.IGNORECASE,
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")

def _clean(value: Any, *, limit: int = 300) -> str:
    text = _CONTROL_RE.sub(" ", str(value or ""))
    return _SPACE_RE.sub(" ", text).strip()[:limit]


def _as_list(value: Any, *, limit: int = 24) -> list[str]:
    if isinstance(value, str):
        raw = re.split(r"[,，;；|\n]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = []
    items = [_clean(item, limit=120) for item in raw]
    return list(dict.fromkeys(item for item in items if item))[:limit]


def normalize_skill_path(value: Any, *, name: str = "") -> str:
    parts = [
        re.sub(r"[^a-z0-9_-]+", "-", part.casefold()).strip("-")
        for part in re.split(r"[/\\>]+", str(value or ""))
    ]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        leaf = re.sub(r"[^a-z0-9_-]+", "-", name.casefold()).strip("-") or "skill"
        parts = [*(parts or ["uncategorized"]), leaf]
    return "/".join(parts[:6])


def legacy_skill_path(category: str, name: str, description: str = "") -> str:
    """Give legacy one-folder catalogs a useful second-level tree bucket."""
    top = re.sub(r"[^a-z0-9_-]+", "-", str(category or "uncategorized").casefold()).strip("-")
    top = top or "uncategorized"
    haystack = f"{name} {description}".casefold()
    rules = (
        ("ios", r"ios|swiftui|xcode|iphone"),
        ("frontend", r"frontend|web-design|ui-|ux-|html|css|motion|animation"),
        ("article", r"article|link|url|wechat|blog|content-research"),
        ("market", r"market|industry|competitive|competitor|business-model|product-review"),
        ("verification", r"verify|verification|audit|review|acceptance|evaluation|benchmark|test"),
        ("debugging", r"debug|troubleshoot|incident|failure|fix-"),
        ("deployment", r"deploy|release|server|migration|git|github"),
        ("agents", r"agent|hermes|codex|opencode|orchestration"),
        ("documents", r"docx|document|pdf|powerpoint|pptx|xlsx|spreadsheet|deck"),
        ("knowledge", r"knowledge|wiki|obsidian|note|vault|ingest"),
        ("media", r"image|video|audio|gif|transcription|ocr"),
        ("visualization", r"diagram|chart|canvas|infographic|excalidraw"),
        ("automation", r"cron|workflow|automation|pipeline"),
    )
    subcategory = next((label for label, pattern in rules if re.search(pattern, haystack)), "general")
    return f"{top}/{subcategory}"


def legacy_skill_level(name: str, description: str = "") -> str:
    haystack = f"{name} {description}".casefold()
    professional = re.search(
        r"market-research|competitive-intelligence|architecture|governance|incident|"
        r"benchmark|evaluation|audit|research-paper|multi-source|production|compliance|"
        r"executive|professional|enterprise|end-to-end",
        haystack,
    )
    return "professional" if professional else "simple"


def normalize_skill_record(item: dict[str, Any]) -> dict[str, Any]:
    name = _clean(item.get("name"), limit=80)
    path = normalize_skill_path(
        item.get("skill_path") or item.get("taxonomy") or item.get("path"),
        name=name,
    )
    level = _clean(item.get("skill_level") or item.get("level"), limit=20).casefold()
    if level not in VALID_LEVELS:
        level = "professional" if _PROFESSIONAL_RE.search(
            " ".join((name, _clean(item.get("description")), path))
        ) else "simple"
    triggers = _as_list(
        item.get("trigger_phrases") or item.get("triggers") or item.get("positive_examples")
    )
    negatives = _as_list(
        item.get("negative_phrases") or item.get("exclusions") or item.get("negative_examples")
    )
    return {
        **item,
        "name": name,
        "description": _clean(item.get("description"), limit=300),
        "skill_path": path,
        "skill_level": level,
        "trigger_phrases": triggers,
        "negative_phrases": negatives,
    }


def legacy_routing_hints(text: str, metadata: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Extract compatibility hints without making legacy metadata compliant."""
    description = _clean(metadata.get("description"), limit=300)
    triggers = [description] if description else []
    negatives: list[str] = []
    in_positive_section = False
    in_negative_section = False
    for raw_line in str(text or "").splitlines()[:240]:
        line = _clean(raw_line.lstrip("#*- "), limit=240)
        if not line:
            continue
        lowered = line.casefold()
        if re.search(r"^(?:when to use|何时使用|适用场景|触发场景)", lowered):
            in_positive_section, in_negative_section = True, False
            continue
        if re.search(r"^(?:do not use|when not to use|不适用|禁止使用|不能用于)", lowered):
            in_positive_section, in_negative_section = False, True
            continue
        if raw_line.lstrip().startswith("#"):
            in_positive_section = False
            in_negative_section = False
        negative_line = bool(re.search(
            r"(?:do not use|don't use|not for|不能用于|不要用于|不适用于)",
            lowered,
        ))
        positive_line = bool(re.search(
            r"(?:use when|when (?:the )?user|用户.{0,30}(?:要求|需要|发送)|适用于)",
            lowered,
        ))
        if negative_line or in_negative_section:
            negatives.append(line)
        elif positive_line or in_positive_section:
            triggers.append(line)
    nested = metadata.get("metadata")
    if isinstance(nested, dict):
        hermes = nested.get("hermes")
        if isinstance(hermes, dict):
            triggers.extend(_as_list(hermes.get("tags"), limit=16))
    return _as_list(triggers, limit=16), _as_list(negatives, limit=12)



def build_skill_tree(skills: Iterable[dict[str, Any]]) -> dict[str, Any]:
    root: dict[str, Any] = {"name": "root", "count": 0, "skills": [], "children": {}}
    for raw in skills:
        skill = normalize_skill_record(dict(raw))
        if not skill["name"]:
            continue
        root["count"] += 1
        node = root
        for part in skill["skill_path"].split("/"):
            children = node["children"]
            node = children.setdefault(
                part, {"name": part, "count": 0, "skills": [], "children": {}}
            )
            node["count"] += 1
        node["skills"].append(skill["name"])

    def freeze(node: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": node["name"],
            "count": node["count"],
            "skills": sorted(node["skills"]),
            "children": [freeze(node["children"][key]) for key in sorted(node["children"])],
        }

    return freeze(root)


def routing_quality_issues(raw: dict[str, Any]) -> list[str]:
    description = _clean(raw.get("description"), limit=1000)
    name = _clean(raw.get("name"), limit=80)
    path_value = raw.get("skill_path") or raw.get("taxonomy") or raw.get("path")
    raw_path_parts = [part for part in re.split(r"[/\\>]+", str(path_value or "")) if part]
    level = _clean(raw.get("skill_level") or raw.get("level"), limit=20).casefold()
    triggers = _as_list(
        raw.get("trigger_phrases") or raw.get("triggers") or raw.get("positive_examples")
    )
    negatives = _as_list(
        raw.get("negative_phrases") or raw.get("exclusions") or raw.get("negative_examples")
    )
    issues: list[str] = []
    if not name:
        issues.append("missing_name")
    if not _TRIGGER_SCENE_RE.search(description):
        issues.append("description_missing_trigger_scene")
    if len(raw_path_parts) < 2:
        issues.append("skill_path_too_shallow")
    if level not in VALID_LEVELS:
        issues.append("invalid_skill_level")
    if not triggers:
        issues.append("missing_trigger_phrases")
    if not negatives:
        issues.append("missing_negative_phrases")
    return issues
