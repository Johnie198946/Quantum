"""Travel chat-to-PCM lifecycle boundaries and private notebook preservation."""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from backend.services.capability_catalog import (
    describe_capability, execute_verified_capability, invoke_capability,
    load_catalog, routing_capability_cards,
)
from backend.services.capability_gateway import create_capability_proposal, confirm_capability_proposal
from scripts import hermes_bridge as bridge

IDS = {
    "workflow.clarification.read", "workflow.clarification.respond", "workflow.plan.read",
    "workflow.artifacts.list", "workflow.review", "workflow.retry", "travel.revise", "travel.notebook.save",
}
PAYLOAD = {"tenant_key": "travel-pcm", "user_id": "travel-pcm-owner"}
HASH = "a" * 64


def test_travel_lifecycle_is_discoverable_as_native_chat_capabilities():
    catalog = load_catalog()
    cards = {c["id"] for c in routing_capability_cards(IDS)}
    assert cards == IDS
    for name in IDS:
        capability = describe_capability(name)
        assert capability["implementation_status"] == "implemented"
        schema = bridge._app_capability_native_tool_schema(capability)
        assert schema["name"] == bridge._app_capability_native_tool_name(name)
        assert capability["input_schema"]["additionalProperties"] is False
        assert capability["negative_examples"]
        if capability["effect"] == "write":
            assert capability["confirmation"] == capability["receipt"] == capability["idempotency"] == "required"
    flow = next(c for c in catalog["consumptions"] if c["id"] == "travel.workflow_chat")
    assert flow["status"] == "partial"  # Graphical map has not been accepted.
    assert "assistant suggestions" in describe_capability("workflow.clarification.respond")["description"]


@pytest.mark.asyncio
async def test_chat_native_review_only_proposes_then_gateway_confirms_exact_version():
    events = []
    previous_loop = bridge._bridge_async_loop
    bridge._bridge_async_loop = asyncio.get_running_loop()
    data = {"execution_id": "wfr-real", "artifact_id": "wfa-real", "expected_hash": HASH,
            "artifact_version": 2, "decision": "approve", "comment": "采用第二版行程"}
    request = "travel-review-" + uuid.uuid4().hex
    def propose():
        bridge._client_context_tool_context.value = {
            "emit": events.append, "request_id": request, "client_session_id": "travel-session",
            "identity": PAYLOAD,
        }
        try:
            return json.loads(bridge._app_capability_invoke_tool({"capability_id": "workflow.review", "input": data}))
        finally:
            bridge._client_context_tool_context.value = None
    workflow = {"id": "wf-real", "status": "running"}
    execution = {"id": "wfr-real", "workflow_id": "wf-real", "status": "queued"}
    try:
        with patch("backend.capability_handlers.review_presentation_stage", new=AsyncMock(return_value=execution)) as review, \
             patch("backend.capability_handlers.get_execution", new=AsyncMock(return_value=execution)), \
             patch("backend.capability_handlers.get_workflow", new=AsyncMock(return_value=workflow)):
            proposed = await asyncio.to_thread(propose)
            assert proposed["status"] == "awaiting_confirmation"
            review.assert_not_awaited()
            proposal = proposed["events"][0]["payload"]
            result = await confirm_capability_proposal(proposal["proposal_id"], payload=PAYLOAD,
                                                      confirmation_token=proposal["confirmation_token"], session_id="travel-session")
            assert result["status"] == "completed"
            body = review.await_args.args[1]
            assert body.artifact_version == 2 and body.expected_hash == HASH and body.decision == "approve"
            assert result["events"][0]["payload"]["workflow"] == workflow
            assert result["events"][0]["payload"]["id"] == workflow["id"]
            replay = await confirm_capability_proposal(proposal["proposal_id"], payload=PAYLOAD,
                                                       confirmation_token=proposal["confirmation_token"], session_id="travel-session")
            assert replay["error"]["code"] == "confirmation_invalid"
            reissued = await asyncio.to_thread(propose)
            fresh = reissued["events"][0]["payload"]
            replay = await confirm_capability_proposal(fresh["proposal_id"], fresh["confirmation_token"],
                                                       payload=PAYLOAD, session_id="travel-session")
            assert replay == result
            review.assert_awaited_once()
    finally:
        bridge._bridge_async_loop = previous_loop
    assert any(e["type"] == "capability.proposed" for e in events)


@pytest.mark.asyncio
async def test_requirement_confirmation_is_round_bound_and_replay_does_not_reanswer():
    data = {"workflow_id": "wf-req", "expected_round": 3, "response": "日期尚未决定，公共交通",
            "intent": "confirm"}
    key = "travel-requirement-" + uuid.uuid4().hex
    with patch("backend.capability_handlers.respond_to_clarification", new=AsyncMock(return_value={"phase": "planning"})) as respond, \
         patch("backend.capability_handlers.get_workflow", new=AsyncMock(return_value={"id": "wf-req"})):
        assert (await invoke_capability("workflow.clarification.respond", data, payload=PAYLOAD, idempotency_key=key))["status"] == "failed"
        result = await execute_verified_capability("workflow.clarification.respond", data, payload=PAYLOAD, idempotency_key=key)
        replay = await execute_verified_capability("workflow.clarification.respond", data, payload=PAYLOAD, idempotency_key=key)
    assert result == replay
    respond.assert_awaited_once()
    assert respond.await_args.args[1].expected_round == 3
    assert respond.await_args.args[1].response == data["response"]


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["stale_artifact_approval", "owner_denied"])
async def test_review_domain_rejection_cannot_be_reported_as_adoption(code):
    with patch("backend.capability_handlers.review_presentation_stage", new=AsyncMock(side_effect=HTTPException(409, detail={"code": code}))):
        result = await execute_verified_capability("workflow.review", {
            "execution_id": "run-rejected", "artifact_id": "artifact-rejected", "expected_hash": HASH,
            "artifact_version": 1, "decision": "approve",
        }, payload=PAYLOAD, idempotency_key="review-rejected-" + uuid.uuid4().hex)
    assert result["status"] == "failed" and result["error"]["code"] == code
    assert not result.get("events")


@pytest.mark.asyncio
async def test_notebook_save_uses_verified_content_and_preserves_existing_private_journal():
    payload = {**PAYLOAD, "user_id": "note-owner-" + uuid.uuid4().hex}
    document = {"schema_version": 2, "destination": "鹿儿岛", "journal": "已有真实旅行资料"}
    content = json.dumps(document, ensure_ascii=False)
    digest = hashlib.sha256(content.encode()).hexdigest()
    execution_id = "wfr-" + uuid.uuid4().hex[:20]
    data = {"execution_id": execution_id, "artifact_id": "wfa-final", "expected_hash": digest}
    artifact = {"id": "wfa-final", "content_hash": digest, "created_at": "2026-10-10T00:00:00Z",
                "metadata": {"render_type": "travel_plan_v2"}}
    execution = {"id": execution_id, "workflow_id": "wf-saved", "status": "completed"}
    with patch("backend.capability_handlers.get_execution", new=AsyncMock(return_value=execution)), \
         patch("backend.capability_handlers.get_workflow", new=AsyncMock(return_value={"id": "wf-saved"})), \
         patch("backend.capability_handlers.list_artifacts", new=AsyncMock(return_value=[artifact])), \
         patch("backend.capability_handlers.get_artifact_content", new=AsyncMock(return_value={"content": content})):
        first = await execute_verified_capability("travel.notebook.save", data, payload=payload, idempotency_key="save-one-" + uuid.uuid4().hex)
        second = await execute_verified_capability("travel.notebook.save", data, payload=payload, idempotency_key="save-two-" + uuid.uuid4().hex)
        assert first["status"] == second["status"] == "completed"
        note_id = first["events"][0]["payload"]["note"]["note_id"]
        assert second["events"][0]["payload"]["note"]["note_id"] == note_id
        assert second["events"][0]["payload"]["note"]["reused"] is True
        artifact["content_hash"] = "b" * 64
        stale = await execute_verified_capability("travel.notebook.save", data, payload=payload, idempotency_key="save-stale-" + uuid.uuid4().hex)
        assert stale["status"] == "failed" and stale["error"]["code"] == "stale_travel_artifact"
        conflict = await execute_verified_capability("travel.notebook.save", {**data, "expected_hash": "b" * 64}, payload=payload, idempotency_key="save-conflict-" + uuid.uuid4().hex)
        assert conflict["status"] == "failed" and conflict["error"]["code"] == "linked_note_requires_review"


@pytest.mark.asyncio
async def test_travel_note_save_requires_adoption_before_reading_or_writing_note():
    with patch("backend.capability_handlers.get_execution", new=AsyncMock(return_value={"status": "awaiting_review"})), \
         patch("backend.capability_handlers.sync_note", new=AsyncMock()) as sync:
        result = await execute_verified_capability("travel.notebook.save", {"execution_id": "wfr-unadopted", "artifact_id": "wfa-unadopted", "expected_hash": HASH}, payload=PAYLOAD, idempotency_key="unadopted-" + uuid.uuid4().hex)
    assert result["status"] == "failed"
    sync.assert_not_awaited()
