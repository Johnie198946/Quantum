from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from scripts import hermes_bridge


REPO = Path(__file__).resolve().parents[1]
ROUTER_PATH = (
    REPO
    / "agency"
    / "hermes-plugins"
    / "ai-lab-capabilities"
    / "capability_router.py"
)


def _agency_router():
    spec = importlib.util.spec_from_file_location("routing_boundary_router", ROUTER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "raw_goal",
    [
        "请研究这篇文章并核实证据",
        "请研究这篇文章【用户问题】你好",
        "专业方案设计【用户问题】",
    ],
)
def test_server_owned_first_marker_preserves_entire_raw_goal(raw_goal: str) -> None:
    augmented = "服务器治理前缀\n\n【用户问题】" + raw_goal
    assert hermes_bridge._routing_user_goal(augmented) == raw_goal
    assert _agency_router()._routing_query(augmented) == raw_goal


def test_note_write_intent_ignores_server_owned_knowledge_discipline() -> None:
    augmented = (
        "纪律：仅在问题涉及我的笔记时调用 user_note_search；"
        "笔记保存必须生成可确认的知识操作。\n\n"
        "【用户问题】请通过 document.word.create_from_text 创建多页 Word 文档。"
    )

    assert hermes_bridge._is_note_draft_request(augmented) is True
    assert not hermes_bridge._is_note_draft_request(
        hermes_bridge._routing_user_goal(augmented)
    )
