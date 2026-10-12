from copy import deepcopy
from datetime import datetime, timezone
import io
import wave

import pytest

from backend.services.travel_plan import update_travel_client_state, revise_travel_document
from backend.services.document_sources import save_document_source, document_original_path, read_document_receipt, DocumentSourceError


def baseline():
    return {"schema_version": 2, "destination": "测试旅行", "actions": [
        {"id": "finished", "day_id": "day-1", "title": "已经结束", "kind": "experience", "status": "completed",
         "actual_end": "2026-10-01T12:00:00+00:00"}], "journal": "用户原话"}


def test_personal_state_cannot_supply_an_alternate_progress_history():
    old = baseline()
    state = {"version": 1, "profile": {"tripSession": {"phase": "during", "facts": {"invented": {"status": "completed"}}, "events": []},
                                      "budgetLedger": {"expenses": []}}, "entries": {"day-1": "我的记录"}}
    updated = update_travel_client_state(old, state)
    assert updated["actions"][0]["actual_end"] == "2026-10-01T12:00:00Z"
    assert updated["journal"] == old["journal"]
    assert updated["client_state"]["entries"] == state["entries"]
    assert "facts" not in updated["client_state"]["profile"]["tripSession"]
    assert "invented" in state["profile"]["tripSession"]["facts"]
    assert "client_state" not in old


def test_ai_revision_preserves_journal_and_ledger():
    old = update_travel_client_state(baseline(), {"version": 1, "entries": {"day-1": "我的记录"}, "profile": {"budgetLedger": {"expenses": [{"id": "paid", "amountMinor": 1500}]}}})
    proposal = deepcopy(old)
    proposal["client_state"] = {"version": 1}
    result = revise_travel_document(old, proposal, now=datetime.now(timezone.utc))
    assert result["client_state"] == old["client_state"]


@pytest.mark.parametrize("state", [{"version": 2}, {"version": 1, "large": "x" * 48001}, {"version": 1, "media": "data:image/jpeg;base64,AAA"}, {"version": 1, "rows": [0] * 1001}])
def test_unbounded_or_inline_media_state_is_rejected(state):
    with pytest.raises(ValueError):
        update_travel_client_state(baseline(), state)


def test_owned_recording_retains_bytes_without_fabricating_transcription(tmp_path, monkeypatch):
    import backend.services.document_sources as service
    monkeypatch.setattr(service, "note_directory", lambda tenant, user: tmp_path / tenant / user)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000); audio.writeframes(b"\x00\x00" * 800)
    original = buffer.getvalue()
    receipt = save_document_source(tenant_key="one", user_id="alice", filename="trip.wav", content_type="audio/wav", data=original)
    assert receipt["status"] == "ready" and receipt["text_available"] is False
    assert receipt["contribution_status"] == "excluded" and receipt["note_id"] is None
    path, _ = document_original_path("one", "alice", receipt["source_id"])
    assert path.read_bytes() == original
    with pytest.raises(DocumentSourceError):
        read_document_receipt("one", "bob", receipt["source_id"])
    with pytest.raises(DocumentSourceError):
        save_document_source(tenant_key="one", user_id="alice", filename="fake.wav", content_type="audio/wav", data=b"not audio")


def test_personal_state_api_uses_owner_cas_and_durable_receipt(tmp_path, monkeypatch):
    import asyncio
    import json
    from test_workflows_api import TestWorkflowsAPI
    from backend.db import SessionLocal
    from backend.models.workflow import WorkflowExecution, WorkflowPlanVersion
    from backend.services.workflow_artifacts import store_artifact
    import backend.api.workflows as api
    import backend.services.workflow_artifacts as storage
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    harness = TestWorkflowsAPI()
    harness.setUp()
    try:
        created = harness.request("POST", "/api/v1/workflows", json={"title": "个人手记", "description": "保存旅行中的原话和账本", "output_kind": "travel"})
        assert created.status_code == 201
        workflow_id = created.json()["workflow"]["id"]
        async def seed():
            async with SessionLocal() as db:
                plan = WorkflowPlanVersion(id="state-plan", workflow_id=workflow_id, version=1, dsl={}, goal="travel", deliverable="travel")
                db.add(plan); await db.flush()
                execution = WorkflowExecution(id="state-execution", workflow_id=workflow_id, plan_id=plan.id, tenant_key="tenant-alpha", status="completed", idempotency_key="state-seed")
                db.add(execution); await db.flush()
                artifact = store_artifact(execution, node_run_id=None, kind="output", title="手记", content=json.dumps(baseline()), extension="json", metadata={"render_type": "travel_plan_v2"})
                db.add(artifact); await db.commit()
                return artifact.id, artifact.content_hash
        identifier, digest = asyncio.run(seed())
        path = "/api/v1/workflow-executions/state-execution/travel-revisions"
        body = {"artifact_id": identifier, "expected_hash": digest, "request_id": "save-state-001", "reason": "用户保存记录", "client_state": {"version": 1, "entries": {"day-1": "自己的原话"}}}
        assert harness.request("POST", path, sub="beta", json=body).status_code == 404
        assert harness.request("POST", path, sub="gamma", json=body).status_code == 404
        saved = harness.request("POST", path, json=body)
        assert saved.status_code == 200, saved.text
        assert harness.request("POST", path, json=body).json()["id"] == saved.json()["id"]
        assert harness.request("POST", path, json={**body, "request_id": "stale-state-002"}).status_code == 409
        assert harness.request("POST", path, json={**body, "client_state": {"version": 1, "entries": {}}}).status_code == 409
        current = saved.json()
        mixed = {**body, "artifact_id": current["id"], "expected_hash": current["content_hash"], "request_id": "mixed-state-003", "progress": "completed", "action_id": "finished"}
        assert harness.request("POST", path, json=mixed).status_code == 422
        restored = harness.request("GET", f"/api/v1/workflow-executions/state-execution/artifacts/{current['id']}/content")
        document = json.loads(restored.json()["content"])
        assert document["client_state"]["entries"]["day-1"] == "自己的原话"
        assert document["actions"][0]["status"] == "completed"
        original = harness.request("GET", f"/api/v1/workflow-executions/state-execution/artifacts/{identifier}/content")
        assert "client_state" not in json.loads(original.json()["content"])
    finally:
        harness.tearDown()


def test_audio_upload_api_never_queues_untranscribed_content(tmp_path, monkeypatch):
    import asyncio
    import httpx
    from fastapi import FastAPI
    from backend.api.auth import require_auth
    import backend.api.documents as api
    import backend.services.document_sources as storage
    monkeypatch.setattr(storage, "note_directory", lambda tenant, user: tmp_path / tenant / user)
    async def forbidden(*args, **kwargs):
        pytest.fail("An original recording must not enter the text contribution queue")
    monkeypatch.setattr(api, "enqueue_contribution", forbidden)
    monkeypatch.setattr(api, "enqueue_and_schedule", forbidden)
    app = FastAPI(); app.include_router(api.router)
    app.dependency_overrides[require_auth] = lambda: {"tenant_key": "audio-tenant", "sub": "audio-owner"}
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000); audio.writeframes(b"\x00\x00" * 800)
    async def upload():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            return await client.post("/api/v1/documents", content=buffer.getvalue(), headers={"Content-Type": "audio/wav", "X-File-Name": "recording.wav", "X-File-Opt-Out": "false"})
    response = asyncio.run(upload())
    assert response.status_code == 201, response.text
    receipt = response.json()
    assert receipt["text_available"] is False and receipt["contribution_status"] == "excluded"
    original, _ = document_original_path("audio-tenant", "audio-owner", receipt["source_id"])
    assert original.read_bytes() == buffer.getvalue()
