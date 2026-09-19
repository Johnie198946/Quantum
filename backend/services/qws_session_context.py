"""Pure Quantum Workspace card/session context mapping.

Routes and persistence stay in ``backend.api.quantum_workspace``.  This module is
the single source for bounded context normalization, deltas, and task mapping.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from backend.models.workspace import WorkspaceProject

CARD_CONTEXT_MAX_BYTES = 512 * 1024
QWS_BUSINESS_CONTEXT_MAX_BYTES = 24 * 1024


def normalize_card_context(
    raw: dict[str, Any] | None,
    *,
    project: WorkspaceProject,
    task: dict[str, Any],
) -> dict[str, Any]:
    context = raw or {
        "schema_version": 1,
        "project": {
            "id": project.id,
            "name": project.name,
            "business_goal": project.goal,
        },
        "task": {
            "qws_task_id": task["id"],
            "title": task["title"],
            "descriptions": [
                {"source": "qws_summary", "content": task.get("summary") or ""}
            ],
            "status": task.get("status"),
            "assignee": task.get("assignee_role"),
            "deliverables": task.get("deliverables") or [],
        },
    }
    try:
        normalized = json.loads(json.dumps(context, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail="card_context must be JSON serializable"
        ) from exc
    if not isinstance(normalized, dict):
        raise HTTPException(status_code=422, detail="card_context must be an object")
    project_context = normalized.get("project")
    task_context = normalized.get("task")
    if not isinstance(project_context, dict) or not isinstance(task_context, dict):
        raise HTTPException(
            status_code=422, detail="card_context project/task objects are required"
        )
    if str(project_context.get("id") or "") != project.id:
        raise HTTPException(status_code=409, detail="card context project binding changed")
    if str(task_context.get("qws_task_id") or "") != task["id"]:
        raise HTTPException(status_code=409, detail="card context task binding changed")
    encoded = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if len(encoded.encode("utf-8")) > CARD_CONTEXT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="card_context exceeds 512 KiB")
    return normalized


def context_changes(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            child_path = f"{path}.{key}" if path else key
            if key not in before:
                changes.append(
                    {"path": child_path, "change": "added", "after": after[key]}
                )
            elif key not in after:
                changes.append(
                    {"path": child_path, "change": "removed", "before": before[key]}
                )
            else:
                changes.extend(context_changes(before[key], after[key], child_path))
        return changes
    if (
        isinstance(before, list)
        and isinstance(after, list)
        and all(
            isinstance(item, dict) and item.get("id") is not None
            for item in before + after
        )
    ):
        before_by_id = {str(item["id"]): item for item in before}
        after_by_id = {str(item["id"]): item for item in after}
        changes = []
        for item_id in sorted(set(before_by_id) | set(after_by_id)):
            child_path = f"{path}[id={item_id}]"
            if item_id not in before_by_id:
                changes.append(
                    {
                        "path": child_path,
                        "change": "added",
                        "after": after_by_id[item_id],
                    }
                )
            elif item_id not in after_by_id:
                changes.append(
                    {
                        "path": child_path,
                        "change": "removed",
                        "before": before_by_id[item_id],
                    }
                )
            else:
                changes.extend(
                    context_changes(
                        before_by_id[item_id], after_by_id[item_id], child_path
                    )
                )
        return changes
    return [
        {"path": path or "$", "change": "updated", "before": before, "after": after}
    ]


def compact_qws_business_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Bound per-turn mutable business data; full sections stay server-readable."""
    compact = deepcopy(snapshot)
    compact["project_planning_history"] = []
    compact["project_documents"] = [
        {
            key: item.get(key)
            for key in ("id", "title", "status", "canonical", "source_refs")
        }
        for item in compact.get("project_documents") or []
        if isinstance(item, dict)
    ]
    compact["session_directory"] = [
        {
            key: item.get(key)
            for key in (
                "session_id",
                "task_id",
                "identifier",
                "title",
                "responsibility",
                "status",
                "is_current",
            )
        }
        for item in compact.get("session_directory") or []
        if isinstance(item, dict)
    ]
    task_value = compact.get("task")
    task: dict[str, Any] = task_value if isinstance(task_value, dict) else {}
    if isinstance(task.get("comments"), list):
        task["comments"] = task["comments"][-10:]
    if isinstance(task.get("attachments"), list):
        task["attachments"] = [
            {
                key: item.get(key)
                for key in ("id", "filename", "content_type", "kind")
            }
            for item in task["attachments"][-12:]
            if isinstance(item, dict)
        ]
    encoded = json.dumps(
        compact, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if len(encoded.encode("utf-8")) > QWS_BUSINESS_CONTEXT_MAX_BYTES:
        compact["session_directory"] = compact.get("session_directory", [])[:40]
        compact["project_execution_log"] = (
            compact.get("project_execution_log") or []
        )[-20:]
        if isinstance(task.get("descriptions"), list):
            task["descriptions"] = [
                {**item, "content": str(item.get("content") or "")[:3000]}
                for item in task["descriptions"]
                if isinstance(item, dict)
            ]
    encoded = json.dumps(
        compact, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if len(encoded.encode("utf-8")) > QWS_BUSINESS_CONTEXT_MAX_BYTES:
        task_value = compact.get("task")
        task = task_value if isinstance(task_value, dict) else {}
        relation_value = task.get("relation_projection")
        relation: dict[str, Any] = (
            relation_value if isinstance(relation_value, dict) else {}
        )
        compact = {
            "schema_version": compact.get("schema_version"),
            "intent_capsule": compact.get("intent_capsule"),
            "intent_migration_required": compact.get(
                "intent_migration_required", False
            ),
            "project_overview": compact.get("project_overview"),
            "task": {
                key: (
                    {
                        **relation,
                        "canonical_entries": (relation.get("canonical_entries") or [])[:40],
                        "taskboard_entries": (relation.get("taskboard_entries") or [])[:40],
                    }
                    if key == "relation_projection"
                    and isinstance(relation_value, dict)
                    else task.get(key)
                )
                for key in (
                    "qws_task_id",
                    "dashi_task_id",
                    "title",
                    "status",
                    "priority",
                    "assignee",
                    "labels",
                    "due_date",
                    "qws",
                    "relation_projection",
                )
            },
            "project_documents": compact.get("project_documents", [])[:20],
            "session_directory": compact.get("session_directory", [])[:20],
            "context_delta": compact.get("context_delta", [])[-40:],
        }
    encoded = json.dumps(
        compact, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if len(encoded.encode("utf-8")) > QWS_BUSINESS_CONTEXT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="qws_business_context_exceeds_24k")
    return compact


def task_from_card_context(
    context: dict[str, Any] | None, *, expected_task_id: str
) -> dict[str, Any] | None:
    card = (context or {}).get("task")
    if not isinstance(card, dict):
        return None
    if str(card.get("dashi_task_id") or "") != expected_task_id:
        return None
    if str(card.get("qws_task_id") or "") != expected_task_id:
        return None
    qws_value = card.get("qws")
    qws: dict[str, Any] = qws_value if isinstance(qws_value, dict) else {}
    descriptions_value = card.get("descriptions")
    descriptions: list[Any] = (
        descriptions_value if isinstance(descriptions_value, list) else []
    )
    summary = next(
        (
            str(item.get("content") or "")
            for item in descriptions
            if isinstance(item, dict) and item.get("content")
        ),
        "",
    )
    assignee_value = card.get("assignee")
    assignee: dict[str, Any] = (
        assignee_value if isinstance(assignee_value, dict) else {}
    )
    return {
        "id": expected_task_id,
        "canonical_task_id": str(qws.get("canonical_task_id") or "") or None,
        "title": str(card.get("title") or "Taskboard card"),
        "summary": summary,
        "status": str(card.get("status") or "UNSPECIFIED"),
        "assignee_role": assignee.get("name"),
        "deliverables": qws.get("deliverables") or [],
        "stage_id": qws.get("stage_id") or "taskboard-card",
        "workflow_id": qws.get("workflow_id"),
        "binding_kind": (
            "project_planning"
            if qws.get("binding_kind") == "project_planning"
            else "taskboard_card"
        ),
    }
