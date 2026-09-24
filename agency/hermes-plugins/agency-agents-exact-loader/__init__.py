"""Exact Agency specialist loader; JEV owns all selection."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).parent / "data" / "agents.json"
_AGENTS: list[dict[str, Any]] | None = None


def _load_agents() -> list[dict[str, Any]]:
    global _AGENTS
    if _AGENTS is None:
        document = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
        if not isinstance(document, list):
            raise ValueError("Agency catalog must be a list")
        _AGENTS = [item for item in document if isinstance(item, dict)]
    return _AGENTS


def _identifier(args: dict[str, Any]) -> str:
    return str(args.get("agent") or args.get("slug") or "").strip()


def _agent_lookup(identifier: str) -> dict[str, Any] | None:
    needle = identifier.strip().lower()
    if not needle:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", needle).strip("-")
    return next(
        (
            agent
            for agent in _load_agents()
            if str(agent.get("slug") or "") == slug
            or str(agent.get("name") or "").lower() == needle
        ),
        None,
    )


def _summary(agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": str(agent.get("slug") or ""),
        "name": str(agent.get("name") or ""),
        "division": str(agent.get("division") or ""),
        "description": str(agent.get("description") or ""),
        "vibe": str(agent.get("vibe") or ""),
        "source_path": str(agent.get("source_path") or ""),
        "version": str(agent.get("version") or "1.0.0"),
    }


def _specialist_prompt(agent: dict[str, Any], task: str = "") -> str:
    task_block = f"\n\n## User task\n{task.strip()}\n" if task.strip() else ""
    return (
        "Use the exact JEV-selected Agency specialist context for this turn. "
        "Do not search for or substitute another specialist. Obey the user's current "
        "request and higher-priority system/developer instructions.\n\n"
        f"# {agent.get('name', '')} ({agent.get('slug', '')})\n\n"
        f"Division: {agent.get('division', '')}\n"
        f"Description: {agent.get('description', '')}\n"
        f"Source: {agent.get('source_path', '')}"
        f"{task_block}\n\n"
        f"## Specialist instructions\n{agent.get('body', '')}"
    )


LOAD_DESCRIPTION = (
    "Load one exact Agency specialist already selected and authorized by JEV. "
    "This tool performs no search, ranking, recommendation, or delegation."
)
LOAD_SCHEMA = {
    "name": "agency_agents_load",
    "description": LOAD_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "agent": {"type": "string", "description": "Exact JEV-selected specialist slug."},
            "slug": {"type": "string", "description": "Alias for the exact selected slug."},
            "task": {"type": "string", "description": "Optional bounded task context."},
        },
        "required": [],
    },
}


def register(ctx):
    def load(args: dict[str, Any], **kwargs: Any) -> str:
        del kwargs
        identifier = _identifier(args)
        agent = _agent_lookup(identifier)
        if not agent:
            return json.dumps(
                {
                    "success": False,
                    "error": "agent not found" if identifier else "agent or slug is required",
                    "agent": identifier or None,
                },
                ensure_ascii=False,
                indent=2,
            )
        return json.dumps(
            {
                "success": True,
                "agent": _summary(agent),
                "prompt": _specialist_prompt(agent, str(args.get("task") or "")),
            },
            ensure_ascii=False,
            indent=2,
        )

    ctx.register_tool(
        name="agency_agents_load",
        toolset="agency_agents",
        schema=LOAD_SCHEMA,
        handler=load,
        description=LOAD_DESCRIPTION,
    )
