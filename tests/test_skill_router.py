from backend.services import skill_router


def test_skill_router_contains_metadata_helpers_only():
    assert not hasattr(skill_router, "rank_skill_candidates")
    assert not hasattr(skill_router, "candidate_prompt")
    assert not hasattr(skill_router, "load_routing_overrides")
    assert not hasattr(skill_router, "apply_routing_overrides")


def test_normalize_skill_record_preserves_compact_pcm_metadata():
    record = skill_router.normalize_skill_record({
        "name": "market-research",
        "description": "Use when market research is requested.",
        "skill_path": "research/market",
        "skill_level": "professional",
        "trigger_phrases": ["market research"],
        "negative_phrases": ["do not use for coding"],
    })
    assert record["name"] == "market-research"
    assert record["skill_path"] == "research/market"
    assert record["skill_level"] == "professional"


def test_build_skill_tree_is_inventory_not_semantic_ranking():
    tree = skill_router.build_skill_tree([
        {"name": "a", "skill_path": "research/market"},
        {"name": "b", "skill_path": "software/debugging"},
    ])
    assert tree["count"] == 2
    assert [node["name"] for node in tree["children"]] == ["research", "software"]
