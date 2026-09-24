from __future__ import annotations

from backend.services import skill_router


def test_server_skill_catalog_has_no_intent_bonus_or_ranker() -> None:
    assert not hasattr(skill_router, "_intent_skill_bonus")
    assert not hasattr(skill_router, "_score")
    assert not hasattr(skill_router, "rank_skill_candidates")


def test_bridge_skill_projection_ignores_server_policy_prefix() -> None:
    from scripts import hermes_bridge

    raw = "请研究这个架构链接并核实关键事实。"
    augmented = "纪律：产品、客户、业务知识只能按授权检索。\n【用户问题】" + raw
    assert hermes_bridge._routing_user_goal(augmented) == raw


def test_bridge_has_no_skill_semantic_selector() -> None:
    from scripts import hermes_bridge

    assert not hasattr(hermes_bridge, "rank_skill_candidates")
    assert not hasattr(hermes_bridge, "candidate_prompt")
    assert not hasattr(hermes_bridge, "apply_routing_overrides")
