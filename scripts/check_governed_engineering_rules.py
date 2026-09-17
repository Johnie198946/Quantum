#!/usr/bin/env python3
"""Fail when Gateway engineering rules drift from their governed source."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = "docs/product-specs/capability-gateway.md"
FILES = {
    "spec": ROOT / SPEC_PATH,
    "agents": ROOT / "AGENTS.md",
    "manual": ROOT / "docs" / "product-capability-manual.md",
    "architecture": ROOT / "docs" / "wiki-hermes-chat-architecture.md",
}


def violations() -> list[str]:
    text = {name: path.read_text(encoding="utf-8") for name, path in FILES.items()}
    errors: list[str] = []

    if text["manual"].count(text["spec"].strip()) != 1:
        errors.append("generated PCM must contain the governed Gateway specification exactly once")

    required_agent_markers = (
        "## 7. Gateway/Bridge 统一工程规则",
        SPEC_PATH,
        "单一真相源与优先级",
        "开发前",
        "对接时",
        "联调时",
        "Debug 时",
        "类型化 receipt",
        "禁止仅凭用户文案",
    )
    for marker in required_agent_markers:
        if marker not in text["agents"]:
            errors.append(f"AGENTS.md missing governed marker: {marker}")

    required_spec_markers = (
        "### 10. 开发、接入、联调与 Debug 执行合同",
        "#### 10.1 开发与变更设计",
        "#### 10.2 对接与联调",
        "#### 10.3 Debug 与事故定位",
        "#### 10.4 完成证据",
        "required_internal_knowledge",
        "attempted_internal_search",
        "consumed_internal_knowledge",
    )
    for marker in required_spec_markers:
        if marker not in text["spec"]:
            errors.append(f"Gateway specification missing governed marker: {marker}")

    if SPEC_PATH not in text["architecture"] or "不得覆盖或放宽" not in text["architecture"]:
        errors.append("Hermes Chat architecture must defer to the governed Gateway specification")

    generated_notice = "Generated view. Do not edit manually."
    if generated_notice not in text["manual"]:
        errors.append("generated PCM is missing its no-manual-edit notice")
    return errors


def main() -> int:
    errors = violations()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Gateway engineering rules: synchronized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
