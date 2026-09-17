from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from backend.services.capability_catalog import describe_capability, execute_verified_capability
from backend.services.capability_gateway import (
    confirm_capability_proposal,
    create_capability_proposal,
)


PAYLOAD = {"tenant_key": "tenant-workflow", "user_id": "owner-workflow"}
PLAN_HASH = "a" * 64
PLAN_DSL = {
    "plan_id": "plan-1",
    "name": "Revised plan",
    "version": "1.0.0",
    "nodes": [],
    "edges": [],
}


def test_workflow_approve_and_revise_are_registered_but_cancel_remains_absent():
    approve = describe_capability("workflow.approve")
    revise = describe_capability("workflow.revise")
    assert approve and approve["implementation_status"] == "implemented"
    assert revise and revise["implementation_status"] == "implemented"
    assert describe_capability("workflow.cancel") is None
    assert approve["preconditions"] == [
        "authenticated_owner", "awaiting_plan_approval", "plan_revision_cas"
    ]
    assert revise["preconditions"] == [
        "authenticated_owner", "editable_plan", "plan_revision_cas"
    ]


@pytest.mark.asyncio
async def test_workflow_approve_reuses_domain_handler_with_cas_and_idempotency():
    domain_result = {
        "workflow": {"id": "wf-approve", "status": "agent_ready"},
        "agent": {"id": "agent-1"},
    }
    data = {
        "workflow_id": "wf-approve",
        "expected_plan_hash": PLAN_HASH,
        "expected_plan_revision": 3,
        "comment": "approved",
    }
    with patch(
        "backend.capability_handlers.approve_plan", new=AsyncMock(return_value=domain_result)
    ) as approve:
        result = await execute_verified_capability(
            "workflow.approve", data, payload=PAYLOAD,
            idempotency_key="approve-request-1",
        )
    assert result["status"] == "completed"
    assert result["events"][0]["type"] == "workflow.approved"
    body = approve.await_args.args[1]
    assert body.request_id == "approve-request-1"
    assert body.expected_hash == PLAN_HASH
    assert body.expected_revision == 3


@pytest.mark.asyncio
async def test_workflow_approve_requires_bound_confirmation_and_durably_replays():
    arguments = {
        "workflow_id": "wf-qcp-approve",
        "expected_plan_hash": PLAN_HASH,
        "expected_plan_revision": 3,
    }

    async def proposal():
        return await create_capability_proposal(
            "workflow.approve", arguments, payload=PAYLOAD,
            session_id="workflow-session", request_id="workflow-request",
            idempotency_key="workflow-approve-durable", renderer_version="qcp-ios@1",
        )

    first = await proposal()
    event = first["events"][0]["payload"]
    denied = await confirm_capability_proposal(
        event["proposal_id"], event["confirmation_token"],
        payload={**PAYLOAD, "tenant_key": "other-tenant"},
        session_id="workflow-session",
    )
    assert denied["error"]["code"] == "confirmation_invalid"

    domain_result = {
        "workflow": {"id": "wf-qcp-approve", "status": "agent_ready"},
        "agent": {"id": "agent-qcp"},
    }
    with patch(
        "backend.capability_handlers.approve_plan",
        new=AsyncMock(return_value=domain_result),
    ) as approve:
        completed = await confirm_capability_proposal(
            event["proposal_id"], event["confirmation_token"],
            payload=PAYLOAD, session_id="workflow-session",
        )
        second = await proposal()
        second_event = second["events"][0]["payload"]
        replay = await confirm_capability_proposal(
            second_event["proposal_id"], second_event["confirmation_token"],
            payload=PAYLOAD, session_id="workflow-session",
        )
    assert completed["status"] == "completed"
    assert completed["receipt"]["status"] == "completed"
    assert replay == completed
    approve.assert_awaited_once()


@pytest.mark.asyncio
async def test_workflow_revise_reuses_versioned_plan_edit_and_replays_request_id():
    domain_result = {
        "id": "plan-2", "workflow_id": "wf-revise", "version": 2,
        "content_hash": "b" * 64, "activation_revision": 4,
    }
    data = {
        "workflow_id": "wf-revise",
        "dsl": PLAN_DSL,
        "deliverable": "Reviewed report",
        "allow_network": False,
        "max_tokens": 5000,
        "knowledge_scope": ["tenant"],
        "expected_plan_hash": PLAN_HASH,
        "expected_plan_revision": 3,
    }
    with patch(
        "backend.capability_handlers.edit_plan", new=AsyncMock(return_value=domain_result)
    ) as revise:
        result = await execute_verified_capability(
            "workflow.revise", data, payload=PAYLOAD,
            idempotency_key="revise-request-1",
        )
    assert result["status"] == "completed"
    assert result["events"][0]["type"] == "workflow.revised"
    body = revise.await_args.args[1]
    assert body.request_id == "revise-request-1"
    assert body.expected_hash == PLAN_HASH
    assert body.expected_revision == 3


@pytest.mark.asyncio
async def test_workflow_lifecycle_domain_denial_is_fail_closed():
    with patch(
        "backend.capability_handlers.approve_plan",
        new=AsyncMock(side_effect=HTTPException(status_code=404, detail={"code": "workflow_not_found"})),
    ):
        result = await execute_verified_capability(
            "workflow.approve",
            {
                "workflow_id": "other-tenant-workflow",
                "expected_plan_hash": PLAN_HASH,
                "expected_plan_revision": 1,
            },
            payload=PAYLOAD,
            idempotency_key="approve-cross-tenant",
        )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "workflow_not_found"


@pytest.mark.asyncio
async def test_workflow_approve_invalid_transition_is_fail_closed():
    with patch(
        "backend.capability_handlers.approve_plan",
        new=AsyncMock(side_effect=HTTPException(status_code=409, detail="当前没有待确认的计划")),
    ):
        result = await execute_verified_capability(
            "workflow.approve",
            {
                "workflow_id": "wf-already-running",
                "expected_plan_hash": PLAN_HASH,
                "expected_plan_revision": 1,
            },
            payload=PAYLOAD,
            idempotency_key="approve-invalid-transition",
        )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "domain_rejected"
