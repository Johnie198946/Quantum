from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from backend.services.capability_catalog import execute_verified_capability, invoke_capability, load_catalog
from backend.services.capability_gateway import (
    confirm_capability_proposal,
    create_capability_proposal,
    invocation_status,
)

AUTH = {
    "tenant_key": "tenant-schedule",
    "user_id": "user-schedule",
    "sub": "user-schedule",
    "principal_type": "human",
    "amr": ["password"],
    "knowledge_policy_version": "schedule-policy-v1",
}
PROJECT = "prj_schedule"
TASK = "tsk_schedule"
WRITE_INPUT = {
    "project_id": PROJECT,
    "task_id": TASK,
    "expected_revision": 7,
    "start_date": "2026-09-20",
    "due_date": "2026-09-22",
}


def test_schedule_and_notification_contracts_are_registered():
    catalog = {item["id"]: item for item in load_catalog()["capabilities"]}
    assert {"schedule.list", "schedule.create", "schedule.update", "schedule.delete"} <= set(catalog)
    assert {"notification.list", "notification.mark_read", "notification.preferences.update"} <= set(catalog)
    assert catalog["schedule.list"]["domain"] == "schedule"
    assert catalog["notification.list"]["domain"] == "notification"
    for capability_id in {"schedule.create", "schedule.update", "schedule.delete"}:
        assert catalog[capability_id]["confirmation"] == "required"
        assert catalog[capability_id]["idempotency"] == "required"
        assert catalog[capability_id]["receipt"] == "required"


@pytest.mark.asyncio
async def test_schedule_list_reuses_qws_tenant_user_state_owner():
    schedule = {"project_id": PROJECT, "process_revision": 7, "tasks": []}
    with patch(
        "backend.api.quantum_workspace.get_project_schedule",
        new=AsyncMock(return_value=schedule),
    ) as read:
        result = await execute_verified_capability(
            "schedule.list", {"project_id": PROJECT}, payload=AUTH, idempotency_key=None
        )
    assert result["events"][0] == {
        "type": "schedule.snapshot", "version": 1, "payload": {"schedule": schedule}
    }
    read.assert_awaited_once_with(PROJECT, AUTH)


@pytest.mark.asyncio
async def test_schedule_reads_require_authenticated_tenant_and_user():
    result = await execute_verified_capability(
        "schedule.list", {"project_id": PROJECT}, payload={}, idempotency_key=None
    )
    assert result["error"]["code"] == "not_authenticated"


@pytest.mark.asyncio
async def test_cross_tenant_schedule_read_fails_closed():
    with patch(
        "backend.api.quantum_workspace.get_project_schedule",
        new=AsyncMock(side_effect=HTTPException(status_code=404, detail="project not found")),
    ):
        result = await execute_verified_capability(
            "schedule.list",
            {"project_id": PROJECT},
            payload={**AUTH, "tenant_key": "other-tenant"},
            idempotency_key=None,
        )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "domain_rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("capability_id", "operation", "data"),
    [
        ("schedule.create", "CREATE", WRITE_INPUT),
        ("schedule.update", "UPDATE", WRITE_INPUT),
        (
            "schedule.delete",
            "DELETE",
            {"project_id": PROJECT, "task_id": TASK, "expected_revision": 7},
        ),
    ],
)
async def test_schedule_writes_reuse_qws_proposal_with_cas_and_gateway_key(
    capability_id, operation, data
):
    response = JSONResponse(
        status_code=202,
        content={"proposal": {"id": f"proposal-{operation.lower()}", "status": "PROPOSED"}},
    )
    with patch(
        "backend.api.quantum_workspace.propose_project_schedule",
        new=AsyncMock(return_value=response),
    ) as propose:
        result = await execute_verified_capability(
            capability_id, data, payload=AUTH, idempotency_key=f"schedule-{operation.lower()}-001"
        )
    assert result["status"] == "completed"
    project_id, body, payload = propose.await_args.args
    assert (project_id, body.operation, body.expected_revision, payload) == (
        PROJECT, operation, 7, AUTH
    )
    assert body.request_id == f"schedule-{operation.lower()}-001"
    assert body.entries[0]["task_id"] == TASK
    expected_start = None if operation == "DELETE" else "2026-09-20"
    assert body.entries[0]["start_date"] == expected_start


@pytest.mark.asyncio
async def test_schedule_invalid_input_and_direct_mutation_fail_closed():
    invalid = await execute_verified_capability(
        "schedule.create",
        {**WRITE_INPUT, "start_date": "20-09-2026"},
        payload=AUTH,
        idempotency_key="schedule-invalid-001",
    )
    assert invalid["error"]["code"] == "contract_invalid"
    unconfirmed = await invoke_capability(
        "schedule.create", WRITE_INPUT, payload=AUTH, idempotency_key="schedule-unconfirmed-001"
    )
    assert unconfirmed["error"]["code"] == "confirmation_protocol_upgrade_required"


async def _proposal(data, *, key, request_id):
    return await create_capability_proposal(
        "schedule.create",
        data,
        payload=AUTH,
        session_id="schedule-session",
        request_id=request_id,
        idempotency_key=key,
        resource_versions={PROJECT: 7},
        renderer_version="qcp-ios@1",
    )


@pytest.mark.asyncio
async def test_schedule_qcp_replay_conflict_cross_tenant_and_receipt_readback():
    response = JSONResponse(
        status_code=202,
        content={"proposal": {"id": "domain-schedule-proposal", "status": "PROPOSED"}},
    )
    first = await _proposal(WRITE_INPUT, key="schedule-shared-001", request_id="schedule-request-001")
    first_event = first["events"][0]["payload"]
    wrong_tenant = await confirm_capability_proposal(
        first_event["proposal_id"],
        first_event["confirmation_token"],
        payload={**AUTH, "tenant_key": "other-tenant"},
        session_id="schedule-session",
    )
    assert wrong_tenant["error"]["code"] == "confirmation_invalid"

    with patch(
        "backend.api.quantum_workspace.propose_project_schedule",
        new=AsyncMock(return_value=response),
    ) as propose:
        completed = await confirm_capability_proposal(
            first_event["proposal_id"],
            first_event["confirmation_token"],
            payload=AUTH,
            session_id="schedule-session",
        )
    assert completed["status"] == "completed"
    propose.assert_awaited_once()

    replay_proposal = await _proposal(
        WRITE_INPUT, key="schedule-shared-001", request_id="schedule-request-001"
    )
    replay_event = replay_proposal["events"][0]["payload"]
    replay = await confirm_capability_proposal(
        replay_event["proposal_id"], replay_event["confirmation_token"],
        payload=AUTH, session_id="schedule-session",
    )
    assert replay == completed

    changed = await _proposal(
        {**WRITE_INPUT, "due_date": "2026-09-23"},
        key="schedule-shared-001",
        request_id="schedule-request-002",
    )
    changed_event = changed["events"][0]["payload"]
    conflict = await confirm_capability_proposal(
        changed_event["proposal_id"], changed_event["confirmation_token"],
        payload=AUTH, session_id="schedule-session",
    )
    assert conflict["error"]["code"] == "idempotency_conflict"

    status = await invocation_status(completed["receipt"]["invocation_id"], payload=AUTH)
    assert status["status"] == "verified"
    assert status["result"]["events"][0]["payload"]["proposal"]["id"] == "domain-schedule-proposal"


def test_ios_schedule_events_use_shared_registry_with_unknown_version_fallback():
    source = __import__("pathlib").Path(
        "ios/AIPlatformApp/Networking/APIClient.swift"
    ).read_text(encoding="utf-8")
    for event in ("schedule.snapshot", "schedule.change_proposed"):
        assert f'"{event}": .init(path: .answer, minimumVersion: 1, fallback: .answer)' in source
