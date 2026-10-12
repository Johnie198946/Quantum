"""The saved travel template uses the existing private note store and travel rules."""
from __future__ import annotations

import copy
import json
from datetime import datetime

from backend.services.travel_plan import validate_travel_document, revise_travel_document, update_travel_client_state

TEMPLATE = {"id": "quantum.travel.revision68", "version": 1, "render_type": "travel_space"}
LINK_FIELDS = ("workflow_id", "workflow_execution_id", "workflow_artifact_id", "workflow_artifact_hash", "note_template")


def parse_notebook(markdown: str) -> dict | None:
    text = str(markdown or "").strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def serialize_notebook(document: dict) -> str:
    title = str((document.get("client_state") or {}).get("noteTitle") or document.get("title") or document["destination"] + "旅行手记")[:200]
    return "---\ntitle: " + json.dumps(title, ensure_ascii=False) + "\ntags: [旅行]\nlayout: travel\ntemplate: quantum.travel.revision68\n---\n\n```json\n" + json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n```\n"


def record_progress(previous: dict, action_id: str, progress: str, *, now: datetime, happened_at: datetime | None = None) -> dict:
    if progress not in {"delayed", "in_progress", "completed", "cancelled", "skipped"}:
        raise ValueError("实际进度无效")
    updated = copy.deepcopy(previous)
    action = next((a for a in updated.get("actions", []) if a["id"] == action_id), None)
    if action is None:
        raise ValueError("行程事项不存在")
    status = action.get("status", "planned")
    if status in {"completed", "cancelled", "skipped"}:
        raise ValueError("已发生事项不可通过进度更新覆盖")
    actual = happened_at or now
    if actual.utcoffset() is None or actual > now:
        raise ValueError("实际发生时间必须含时区且不能位于未来")
    if status == "in_progress" and progress == "in_progress":
        raise ValueError("已经开始的事项不能覆盖原开始时间")
    if progress == "delayed" and (status not in {"planned", "delayed"} or action.get("actual_start")):
        raise ValueError("已实际开始的事项不能改成尚未出发")
    action["status"] = progress
    if progress == "in_progress":
        action["actual_start"] = actual.isoformat()
    elif progress != "delayed":
        action["actual_end"] = actual.isoformat()
    return validate_travel_document(updated)


def update_notebook(previous: dict, data: dict, *, now: datetime) -> dict:
    personal, proposed, progress = data.get("client_state"), data.get("proposed"), data.get("progress")
    if sum(value is not None for value in (personal, proposed, progress)) != 1:
        raise ValueError("一次只保存个人记录、计划调整或实际进度")
    if personal is not None:
        if data.get("action_id") or data.get("confirmed_bookings"):
            raise ValueError("个人记录不能修改预订或实际进度")
        # Chat can update a selection without deleting unrelated private writing.
        # Arrays and explicit scalar values replace; omitted object fields survive.
        update_travel_client_state(previous, personal)  # validate bounds before recursion
        def merge(old, patch):
            result = copy.deepcopy(old) if isinstance(old, dict) else {}
            for key, value in patch.items():
                result[key] = merge(result.get(key), value) if isinstance(value, dict) else copy.deepcopy(value)
            return result
        updated = update_travel_client_state(previous, merge(previous.get("client_state"), personal))
    elif proposed is not None:
        if data.get("action_id"):
            raise ValueError("计划调整不能同时记录实际进度")
        updated = revise_travel_document(previous, proposed, now=now, confirmed_bookings=data.get("confirmed_bookings"))
    else:
        if not data.get("action_id") or data.get("confirmed_bookings"):
            raise ValueError("必须提供事项，预订变更需要确认计划")
        happened = datetime.fromisoformat(data["happened_at"].replace("Z", "+00:00")) if data.get("happened_at") else None
        updated = record_progress(previous, data["action_id"], progress, now=now, happened_at=happened)
    for field in LINK_FIELDS:
        if field in previous:
            updated[field] = copy.deepcopy(previous[field])
    updated["note_template"] = copy.deepcopy(TEMPLATE)
    return updated
