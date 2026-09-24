from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any


REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "agency/hermes-plugins/ai-lab-capabilities"


def _router():
    package = "agency_abstention_jev_plugin"
    for name in list(sys.modules):
        if name == package or name.startswith(package + "."):
            sys.modules.pop(name, None)
    pkg = type(sys)(package)
    pkg.__path__ = [str(PLUGIN)]
    sys.modules[package] = pkg
    spec = importlib.util.spec_from_file_location(
        f"{package}.capability_router", PLUGIN / "capability_router.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parallel_keyword_abstention_router_is_removed():
    router = _router()
    for name in (
        "recommend", "_candidate_context", "_score_capability",
        "_selected_agency", "_direct_capability",
    ):
        assert not hasattr(router, name)


def test_provider_unavailable_abstains_without_fallback_ranking(monkeypatch):
    router = _router()
    monkeypatch.delenv("JEV_SELECTOR_URL", raising=False)
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: [{
        "id": "agency:ui-designer",
        "kind": "agency_agent",
        "name": "UI Designer",
        "description": "UI and visual design",
    }])
    state: dict[str, Any] = {"tenant_id": "local", "principal": "local_owner"}
    context = router._jev_routing_context(
        "审计 Agent OS 控制面",
        state,
        authorized_skill_ids=[],
        authorized_agent_ids=["agency:ui-designer"],
    )
    assert context == ""
    assert state["requested_agent"] is None
    decision = state["route_decision"]
    assert isinstance(decision, dict)
    assert decision["reason_code"] == "PROVIDER_UNAVAILABLE"
