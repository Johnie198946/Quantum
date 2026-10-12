"""Real private note storage, CAS, history and Chat PCM boundaries for revision68."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

import pytest

from backend.services.capability_catalog import execute_verified_capability, load_catalog, routing_capability_cards
from backend.services.travel_notebook import parse_notebook, serialize_notebook, update_notebook, TEMPLATE
from backend.services.travel_plan import validate_travel_document


def document():
    return validate_travel_document({"schema_version": 2, "destination": "青森", "journal": "自己的旅行文字",
        "actions": [{"id": "done", "day_id": "day-1", "title": "已发生的记录", "kind": "experience", "status": "completed", "actual_end": "2026-10-01T12:00:00Z"},
                    {"id": "next", "day_id": "day-1", "title": "剩余安排", "kind": "experience", "status": "planned"}],
        "workflow_id": "wf-source", "workflow_execution_id": "run-source", "note_template": TEMPLATE})


async def create_note(owner):
    result = await execute_verified_capability("knowledge.note.create", {"markdown": serialize_notebook(document())},
        payload=owner, idempotency_key="fixture-create-" + uuid.uuid4().hex)
    assert result["status"] == "completed", result
    return result["events"][0]["payload"]


async def read_note(owner, note_id, **extra):
    result = await execute_verified_capability("knowledge.note.read", {"note_id": note_id, **extra}, payload=owner, idempotency_key=None)
    return result


def test_entire_prototype_is_registered_and_new_note_operation_is_chat_discoverable():
    catalog = load_catalog()
    surface = next(s for s in catalog["consumptions"] if s["id"] == "travel.prototype_revision68")
    operations = surface["input_contract"]["operations"]
    assert len(operations) == 216
    assert len({op["id"] for op in operations}) == len(operations)
    ids = {cap["id"] for cap in catalog["capabilities"]}
    assert all(set(op["capabilities"]) <= ids for op in operations)
    assert {c["id"] for c in routing_capability_cards({"travel.notebook.update"})} == {"travel.notebook.update"}
    root = Path(__file__).resolve().parents[1]
    assert all((root / op["implementation"]).is_file() for op in operations)
    # Every interactive implementation surface has an explicit consumer entry.
    assert all((root / source).is_file() for source in surface["input_contract"]["interactive_components"])
    assert "WorkflowDashboardView.swift" not in json.dumps(catalog["consumptions"])


@pytest.mark.asyncio
async def test_note_updates_survive_new_chat_and_preserve_original_facts_with_exact_receipts():
    owner = {"tenant_key": "r68-note", "user_id": "owner-" + uuid.uuid4().hex}
    created = await create_note(owner)
    note_id = created["note_id"]
    before = (await read_note(owner, note_id))["events"][0]["payload"]["note"]
    state = {"version": 1, "saved": True, "noteTitle": "青森 · 我的旅行", "entries": {"day-1": "今天自己的原话"},
             "profile": {"budgetLedger": {"expenses": [{"id": "paid", "currency": "JPY", "amountMinor": 12000}]},
                         "tripSession": {"phase": "during", "facts": {"forged": {"status": "completed"}}}}}
    data = {"note_id": note_id, "expected_note_hash": before["content_hash"], "reason": "保存日记与花费", "client_state": state}
    key = "note-update-" + uuid.uuid4().hex
    result = await execute_verified_capability("travel.notebook.update", data, payload=owner, idempotency_key=key)
    assert result["status"] == "completed", result
    note = result["events"][0]["payload"]["note"]
    assert hashlib.sha256(note["markdown"].encode()).hexdigest() == note["content_hash"]
    stored = parse_notebook(note["markdown"])
    assert stored["note_template"] == TEMPLATE
    assert stored["workflow_execution_id"] == "run-source"
    assert stored["actions"] == document()["actions"]
    assert stored["client_state"]["entries"]["day-1"] == "今天自己的原话"
    assert "facts" not in stored["client_state"]["profile"]["tripSession"]
    assert "layout: travel" in note["markdown"] and "青森 · 我的旅行" in note["markdown"]
    replay = await execute_verified_capability("travel.notebook.update", data, payload=owner, idempotency_key=key)
    assert replay == result
    fresh = (await read_note(owner, note_id))["events"][0]["payload"]["note"]
    assert fresh["content_hash"] == note["content_hash"]
    partial = await execute_verified_capability("travel.notebook.update", {
        "note_id": note_id, "expected_note_hash": note["content_hash"], "reason": "更换手记封面",
        "client_state": {"version": 1, "notebookConfig": {"cover": "neutral"}},
    }, payload=owner, idempotency_key=uuid.uuid4().hex)
    assert partial["status"] == "completed"
    partial_note = partial["events"][0]["payload"]["note"]
    assert parse_notebook(partial_note["markdown"])["client_state"]["entries"] == stored["client_state"]["entries"]
    stale = await execute_verified_capability("travel.notebook.update", data, payload=owner, idempotency_key="stale-" + uuid.uuid4().hex)
    assert stale["status"] == "failed" and stale["error"]["code"] == "stale_travel_note"
    other = await read_note({**owner, "user_id": "other"}, note_id)
    assert other["status"] == "failed"
    history = (await read_note(owner, note_id, include_versions=True))["events"][0]["payload"]["versions"]
    assert {v["content_hash"] for v in history} == {before["content_hash"], note["content_hash"], partial_note["content_hash"]}
    old = (await read_note(owner, note_id, version_hash=before["content_hash"]))["events"][0]["payload"]["note"]
    assert old["markdown"] == before["markdown"]


@pytest.mark.asyncio
async def test_recorded_progress_uses_server_time_and_cannot_replace_completed_history():
    owner = {"tenant_key": "r68-progress", "user_id": uuid.uuid4().hex}
    created = await create_note(owner)
    data = {"note_id": created["note_id"], "expected_note_hash": created["content_hash"], "reason": "开始实际事项", "action_id": "next", "progress": "in_progress"}
    result = await execute_verified_capability("travel.notebook.update", data, payload=owner, idempotency_key=uuid.uuid4().hex)
    assert result["status"] == "completed", result
    note = result["events"][0]["payload"]["note"]
    updated = parse_notebook(note["markdown"])
    assert updated["actions"][1]["status"] == "in_progress"
    assert datetime.fromisoformat(updated["actions"][1]["actual_start"].replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    malicious = deepcopy(updated); malicious["actions"][0]["title"] = "修改已经发生的事实"
    rejected = await execute_verified_capability("travel.notebook.update", {"note_id": note["note_id"], "expected_note_hash": note["content_hash"], "reason": "修改计划", "proposed": malicious}, payload=owner, idempotency_key=uuid.uuid4().hex)
    assert rejected["status"] == "failed" and "frozen" in rejected["error"]["message"]
    assert (await read_note(owner, note["note_id"]))["events"][0]["payload"]["note"]["content_hash"] == note["content_hash"]


@pytest.mark.parametrize("extra", [
    {"client_state": {"version": 1}, "progress": "completed", "action_id": "next"},
    {"client_state": {"version": 2}},
    {"client_state": {"version": 1, "media": "data:image/jpeg;base64,AAAA"}},
    {"progress": "completed", "action_id": "done"},
])
def test_note_domain_rejects_mixed_facts_and_unbounded_personal_state(extra):
    with pytest.raises(ValueError):
        update_notebook(document(), extra, now=datetime.now(timezone.utc))
