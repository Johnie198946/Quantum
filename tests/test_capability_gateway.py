from __future__ import annotations

from unittest.mock import AsyncMock, patch
from datetime import timedelta

import pytest

from backend.services.capability_gateway import (
    confirm_capability_proposal,
    create_capability_proposal,
    invocation_status,
    proposal_status,
    reconcile_incomplete_invocations,
    _now,
)
from backend.db import SessionLocal
from backend.models.capability_gateway import CapabilityInvocation, CapabilityProposal


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


@pytest.mark.asyncio
async def test_resource_versions_are_token_bound_and_tampering_fails_closed():
    proposal = await _proposal(
        {"title": "CAS", "description": "resource binding"},
        key="gateway-cas-binding",
    )
    event = proposal["events"][0]["payload"]
    assert event["resource_versions"] == {"workflow": "0"}
    async with SessionLocal() as db:
        row = await db.get(CapabilityProposal, event["proposal_id"])
        row.resource_versions = {"workflow": "1"}
        await db.commit()
    result = await confirm_capability_proposal(
        event["proposal_id"], event["confirmation_token"],
        payload=PAYLOAD, session_id="chat-session-gateway",
    )
    assert result["error"]["code"] == "contract_invalid"


@pytest.mark.asyncio
async def test_expired_token_is_rejected_and_status_is_durable():
    proposal = await _proposal(
        {"title": "Expired", "description": "token expiry"},
        key="gateway-expired-token",
    )
    event = proposal["events"][0]["payload"]
    async with SessionLocal() as db:
        row = await db.get(CapabilityProposal, event["proposal_id"])
        row.expires_at = _now() - timedelta(seconds=1)
        await db.commit()
    result = await confirm_capability_proposal(
        event["proposal_id"], event["confirmation_token"],
        payload=PAYLOAD, session_id="chat-session-gateway",
    )
    assert result["error"]["code"] == "confirmation_invalid"
    status = await proposal_status(event["proposal_id"], payload=PAYLOAD)
    assert status["status"] == "expired"


@pytest.mark.asyncio
async def test_crash_reconciliation_replays_same_invocation_and_exposes_status():
    proposal = await _proposal(
        {"title": "Recover", "description": "crash reconciliation"},
        key="gateway-reconcile-incomplete",
    )
    event = proposal["events"][0]["payload"]
    invocation_id = "qcp-reconcile-test"
    async with SessionLocal() as db:
        proposal_row = await db.get(CapabilityProposal, event["proposal_id"])
        proposal_row.state = "APPLYING"
        proposal_row.consumed_at = _now()
        proposal_row.receipt_id = invocation_id
        db.add(CapabilityInvocation(
            id=invocation_id,
            proposal_id=proposal_row.id,
            tenant_key=proposal_row.tenant_key,
            user_id=proposal_row.user_id,
            capability_id=proposal_row.capability_id,
            capability_version=proposal_row.capability_version,
            idempotency_key_hash="a" * 64,
            input_digest=proposal_row.input_digest,
            state="APPLYING",
        ))
        await db.commit()
    created = {
        "workflow": {"id": "wf-recovered", "status": "clarifying"},
        "clarification_session": {"id": "wfs-recovered", "phase": "awaiting_requirement_confirmation"},
    }
    with patch(
        "backend.capability_handlers._create_workflow", new=AsyncMock(return_value=created)
    ) as handler:
        assert await reconcile_incomplete_invocations() >= 1
    handler.assert_awaited_once()
    status = await invocation_status(invocation_id, payload=PAYLOAD)
    assert status["status"] == "verified"
    assert status["result"]["receipt"]["version"] == 1
    assert status["result"]["receipt"]["event_version"] == 1
