from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.services.capability_gateway import (
    confirm_capability_proposal,
    create_capability_proposal,
    proposal_status,
)


PAYLOAD = {
    "tenant_key": "tenant-gateway",
    "user_id": "user-gateway",
    "knowledge_policy_version": "policy-v1",
}


async def _proposal(data: dict, *, key: str = "gateway-request-0001") -> dict:
    return await create_capability_proposal(
        "workflow.create",
        data,
        payload=PAYLOAD,
        session_id="chat-session-gateway",
        request_id="request-gateway-0001",
        idempotency_key=key,
        resource_versions={"workflow": "0"},
        renderer_version="qcp-ios@1",
    )


@pytest.mark.asyncio
async def test_confirmation_token_is_bound_single_use_and_durable():
    created = {
        "workflow": {"id": "wf-gateway", "status": "clarifying"},
        "clarification_session": {
            "id": "wfs-gateway", "phase": "awaiting_requirement_confirmation"
        },
    }
    proposal = await _proposal({"title": "Gateway", "description": "durable confirmation"})
    event = proposal["events"][0]["payload"]
    assert event["input"]["source_client_session_id"] == "chat-session-gateway"

    wrong_session = await confirm_capability_proposal(
        event["proposal_id"], event["confirmation_token"],
        payload=PAYLOAD, session_id="other-session",
    )
    assert wrong_session["error"]["code"] == "confirmation_invalid"

    with patch(
        "backend.capability_handlers._create_workflow", new=AsyncMock(return_value=created)
    ) as handler:
        completed = await confirm_capability_proposal(
            event["proposal_id"], event["confirmation_token"],
            payload=PAYLOAD, session_id="chat-session-gateway",
        )
    assert completed["status"] == "completed"
    assert completed["receipt"]["invocation_id"].startswith("qcp-")
    handler.assert_awaited_once()
    assert handler.await_args.kwargs["requirements_snapshot_overrides"] == {
        "source_client_session_id": "chat-session-gateway"
    }

    replay = await confirm_capability_proposal(
        event["proposal_id"], event["confirmation_token"],
        payload=PAYLOAD, session_id="chat-session-gateway",
    )
    assert replay["error"]["code"] == "confirmation_invalid"

    status = await proposal_status(event["proposal_id"], payload=PAYLOAD)
    assert status["status"] == "verified"
    assert status["result"]["receipt"] == completed["receipt"]


@pytest.mark.asyncio
async def test_same_idempotency_key_with_different_digest_fails_closed():
    first = await _proposal(
        {"title": "First", "description": "first payload"},
        key="gateway-shared-key",
    )
    first_event = first["events"][0]["payload"]
    created = {
        "workflow": {"id": "wf-first", "status": "clarifying"},
        "clarification_session": {"id": "wfs-first", "phase": "awaiting_requirement_confirmation"},
    }
    with patch(
        "backend.capability_handlers._create_workflow", new=AsyncMock(return_value=created)
    ):
        result = await confirm_capability_proposal(
            first_event["proposal_id"], first_event["confirmation_token"],
            payload=PAYLOAD, session_id="chat-session-gateway",
        )
    assert result["status"] == "completed"

    second = await _proposal(
        {"title": "Second", "description": "changed payload"},
        key="gateway-shared-key",
    )
    second_event = second["events"][0]["payload"]
    conflict = await confirm_capability_proposal(
        second_event["proposal_id"], second_event["confirmation_token"],
        payload=PAYLOAD, session_id="chat-session-gateway",
    )
    assert conflict["error"]["code"] == "idempotency_conflict"
