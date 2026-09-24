from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "agency" / "hermes-plugins" / "ai-lab-capabilities"


def _load_router():
    package = "jev_no_legacy_router_plugin"
    for name in list(sys.modules):
        if name == package or name.startswith(package + "."):
            sys.modules.pop(name, None)
    pkg = type(sys)(package)
    pkg.__path__ = [str(PLUGIN_DIR)]
    sys.modules[package] = pkg
    spec = importlib.util.spec_from_file_location(
        f"{package}.capability_router", PLUGIN_DIR / "capability_router.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_capability_router_has_no_keyword_or_alias_selector():
    router = _load_router()
    for name in (
        "recommend", "_selected_skill", "_selected_agency", "_routing_overrides",
        "_govern_skill", "_score_capability", "_extend_tool_search",
    ):
        assert not hasattr(router, name)


def test_provider_unavailable_means_direct_hermes_execution(monkeypatch):
    router = _load_router()
    monkeypatch.delenv("JEV_SELECTOR_URL", raising=False)
    state: dict[str, Any] = {"tenant_id": "local", "principal": "local_owner"}
    context = router._jev_routing_context(
        "定位本地源码问题",
        state=state,
        authorized_skill_ids=None,
        authorized_agent_ids=None,
    )
    assert context == ""
    decision = state["route_decision"]
    assert isinstance(decision, dict)
    assert decision["reason_code"] == "PROVIDER_UNAVAILABLE"
    assert state["requested_skill"] is None
    assert state["requested_agent"] is None
