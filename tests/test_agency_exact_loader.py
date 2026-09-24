from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOADER_PATH = (
    ROOT / "agency/hermes-plugins/agency-agents-exact-loader/__init__.py"
)


class Context:
    def __init__(self):
        self.tools = {}

    def register_tool(self, *, name, schema, handler, **metadata):
        self.tools[name] = {"schema": schema, "handler": handler, **metadata}


def _module():
    spec = importlib.util.spec_from_file_location("agency_exact_loader_test", LOADER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_loader_registers_only_exact_load_and_never_ranks(tmp_path):
    module = _module()
    catalog = tmp_path / "agents.json"
    catalog.write_text(
        json.dumps(
            [
                {
                    "slug": "code-reviewer",
                    "name": "Code Reviewer",
                    "division": "engineering",
                    "description": "Review code.",
                    "source_path": "engineering/code-reviewer.md",
                    "body": "Review correctness and safety.",
                    "version": "1.2.3",
                },
                {
                    "slug": "mobile-app-builder",
                    "name": "Mobile App Builder",
                    "division": "engineering",
                    "description": "Build mobile apps.",
                    "source_path": "engineering/mobile-app-builder.md",
                    "body": "Build the requested app.",
                },
            ]
        ),
        encoding="utf-8",
    )
    setattr(module, "_DATA_PATH", catalog)
    setattr(module, "_AGENTS", None)
    context = Context()
    module.register(context)

    assert set(context.tools) == {"agency_agents_load"}
    handler = context.tools["agency_agents_load"]["handler"]
    loaded = json.loads(handler({"agent": "code-reviewer", "task": "Inspect diff"}))
    assert loaded["success"] is True
    assert loaded["agent"]["slug"] == "code-reviewer"
    assert loaded["agent"]["version"] == "1.2.3"
    assert "Inspect diff" in loaded["prompt"]
    assert "Do not search for or substitute another specialist" in loaded["prompt"]

    missing = json.loads(handler({"agent": "review code"}))
    assert missing == {
        "success": False,
        "error": "agent not found",
        "agent": "review code",
    }
