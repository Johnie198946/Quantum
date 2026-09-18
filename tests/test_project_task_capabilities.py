from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from backend.services.capability_catalog import (
    execute_verified_capability,
    invoke_capability,
    load_catalog,
)
from backend.services.capability_gateway import (
    confirm_capability_proposal,
    create_capability_proposal,
    invocation_status,
)


AUTH = {
    "tenant_key": "tenant-qws",
    "user_id": "user-qws",
    "sub": "user-qws",
    "principal_type": "human",
    "amr": ["password"],
}
PROJECT = "prj_test"
TASK = "tsk_test"


def test_project_task_contracts_are_registered_on_the_shared_gateway():
    catalog = {item["id"]: item for item in load_catalog()["capabilities"]}
    expected = {
        "project.list", "project.create", "project.open", "project.update", "project.delete",
        "task.list", "task.create", "task.update", "task.delete", "task.status",
    }
    assert expected <= set(catalog)
    assert "task.execute" not in catalog
    for capability_id in {
        "project.create", "project.update", "project.delete",
        "task.create", "task.update", "task.delete",
    }:
        assert catalog[capability_id]["confirmation"] == "required"
        assert catalog[capability_id]["idempotency"] == "required"
        assert catalog[capability_id]["receipt"] == "required"


@pytest.mark.asyncio
async def test_project_reads_reuse_tenant_scoped_qws_apis():
    project = {"id": PROJECT, "tenant_id": "tenant-qws"}
    with (
        patch("backend.api.quantum_workspace.list_projects", new=AsyncMock(return_value=[project])) as listed,
        patch("backend.api.quantum_workspace.get_project", new=AsyncMock(return_value=project)) as opened,
    ):
        list_result = await execute_verified_capability(
            "project.list", {}, payload=AUTH, idempotency_key=None
        )
        open_result = await execute_verified_capability(
            "project.open", {"project_id": PROJECT}, payload=AUTH, idempotency_key=None
        )
    assert list_result["events"][0]["payload"] == {"projects": [project]}
    assert open_result["events"][0]["payload"] == {"project": project}
    assert listed.await_args.args == (AUTH,)
    assert opened.await_args.args == (PROJECT, AUTH)


@pytest.mark.asyncio
async def test_project_create_binds_domain_request_id_to_gateway_idempotency_key():
    response = JSONResponse(status_code=201, content={
        "project_id": PROJECT,
        "task_ids": [],
        "graph_ids": [],
        "template_version": "1.0.0",
        "created_at": "2026-09-18T00:00:00+00:00",
    })
    with patch(
        "backend.api.quantum_workspace.instantiate_project",
        new=AsyncMock(return_value=response),
    ) as create:
        result = await execute_verified_capability(
            "project.create",
            {"name": "Gateway", "goal": "Ship safely"},
            payload=AUTH,
            idempotency_key="project-create-001",
        )
    assert result["events"][0]["payload"]["project_id"] == PROJECT
    template_id, body, payload = create.await_args.args
    assert template_id == "ipd-product-development"
    assert body.request_id == "project-create-001"
    assert payload == AUTH


@pytest.mark.asyncio
async def test_task_reads_reuse_canonical_project_process_and_task_apis():
    task = {"id": TASK, "status": "TODO", "task_revision": 1}
    process = {"project_id": PROJECT, "process_revision": 3, "tasks": [task]}
    with (
        patch("backend.api.quantum_workspace.get_project_process", new=AsyncMock(return_value=process)),
        patch("backend.api.quantum_workspace.get_project_task", new=AsyncMock(return_value={**task, "project_id": PROJECT})),
    ):
        listed = await execute_verified_capability(
            "task.list", {"project_id": PROJECT}, payload=AUTH, idempotency_key=None
        )
        status = await execute_verified_capability(
            "task.status", {"project_id": PROJECT, "task_id": TASK},
            payload=AUTH, idempotency_key=None,
        )
    assert listed["events"][0]["payload"] == process
    assert status["events"][0]["payload"]["task"]["status"] == "TODO"


@pytest.mark.asyncio
async def test_task_create_reuses_qws_proposal_path_and_gateway_key():
    response = JSONResponse(status_code=202, content={
        "proposal": {"id": "proposal-1", "status": "PENDING"},
        "task_preview": {"id": TASK, "status": "WAITING_CLAIM"},
    })
    with patch(
        "backend.api.quantum_workspace.create_project_task",
        new=AsyncMock(return_value=response),
    ) as create:
        result = await execute_verified_capability(
            "task.create",
            {
                "project_id": PROJECT,
                "expected_revision": 3,
                "stage_id": "stage-1",
                "title": "Add Gateway",
                "summary": "Reuse the QWS truth source",
            },
            payload=AUTH,
            idempotency_key="task-create-001",
        )
    assert result["events"][0]["type"] == "task.change_proposed"
    project_id, body, payload = create.await_args.args
    assert project_id == PROJECT
    assert body.request_id == "task-create-001"
    assert body.expected_revision == 3
    assert payload == AUTH


@pytest.mark.asyncio
async def test_task_update_reuses_qws_contract_edit_proposal_path():
    response = JSONResponse(status_code=202, content={
        "proposal": {"id": "proposal-2", "status": "PENDING"},
        "task_preview": {"id": TASK, "title": "Updated"},
        "previous_stage_id": "stage-1",
    })
    with patch(
        "backend.api.quantum_workspace.edit_project_task",
        new=AsyncMock(return_value=response),
    ) as update:
        result = await execute_verified_capability(
            "task.update",
            {
                "project_id": PROJECT,
                "task_id": TASK,
                "expected_revision": 4,
                "stage_id": "stage-2",
                "title": "Updated",
                "summary": "Updated safely",
            },
            payload=AUTH,
            idempotency_key="task-update-001",
        )
    assert result["events"][0]["payload"]["proposal"]["id"] == "proposal-2"
    project_id, task_id, body, payload = update.await_args.args
    assert (project_id, task_id, body.request_id) == (PROJECT, TASK, "task-update-001")
    assert payload == AUTH


@pytest.mark.asyncio
async def test_project_update_reuses_qws_revisioned_proposal_path():
    response = JSONResponse(status_code=202, content={
        "proposal": {"id": "proposal-project-update", "status": "PROPOSED"},
    })
    with patch(
        "backend.api.quantum_workspace.update_project",
        new=AsyncMock(return_value=response),
    ) as update:
        result = await execute_verified_capability(
            "project.update",
            {
                "project_id": PROJECT,
                "expected_revision": 5,
                "name": "Governed project",
                "goal": "Keep one truth source",
                "desired_outputs": ["receipt"],
            },
            payload=AUTH,
            idempotency_key="project-update-001",
        )
    assert result["events"][0]["type"] == "project.change_proposed"
    project_id, body, payload = update.await_args.args
    assert (project_id, body.request_id, body.expected_revision) == (
        PROJECT, "project-update-001", 5
    )
    assert payload == AUTH


@pytest.mark.asyncio
async def test_project_delete_reuses_qws_archive_proposal_path():
    response = {
        "proposal": {"id": "proposal-project-delete", "status": "PROPOSED"},
        "project": {"id": PROJECT, "status": "active"},
    }
    with patch(
        "backend.api.quantum_workspace.propose_project_archive",
        new=AsyncMock(return_value=response),
    ) as archive:
        result = await execute_verified_capability(
            "project.delete",
            {"project_id": PROJECT, "expected_revision": 7},
            payload=AUTH,
            idempotency_key="project-delete-001",
        )
    assert result["events"][0]["payload"]["proposal"]["id"] == "proposal-project-delete"
    project_id, body, payload = archive.await_args.args
    assert (project_id, body.request_id, body.expected_revision) == (
        PROJECT, "project-delete-001", 7
    )
    assert payload == AUTH


@pytest.mark.asyncio
async def test_task_delete_is_soft_delete_via_qws_archive_proposal():
    response = JSONResponse(status_code=202, content={
        "proposal": {"id": "proposal-task-delete", "status": "PROPOSED"},
        "task_preview": {"id": TASK, "status": "CANCELLED"},
    })
    with patch(
        "backend.api.quantum_workspace.propose_project_task_archive",
        new=AsyncMock(return_value=response),
    ) as archive:
        result = await execute_verified_capability(
            "task.delete",
            {"project_id": PROJECT, "task_id": TASK, "expected_revision": 6},
            payload=AUTH,
            idempotency_key="task-delete-001",
        )
    assert result["events"][0]["payload"]["task_preview"]["status"] == "CANCELLED"
    project_id, task_id, body, payload = archive.await_args.args
    assert (project_id, task_id, body.request_id, body.action) == (
        PROJECT, TASK, "task-delete-001", "ARCHIVE"
    )
    assert body.expected_revision == 6
    assert payload == AUTH


@pytest.mark.asyncio
async def test_project_task_delete_cas_and_cross_tenant_fail_closed():
    with patch(
        "backend.api.quantum_workspace.propose_project_task_archive",
        new=AsyncMock(side_effect=HTTPException(
            status_code=409,
            detail={"error": "project_revision_conflict", "server_revision": 7},
        )),
    ):
        conflict = await execute_verified_capability(
            "task.delete",
            {"project_id": PROJECT, "task_id": TASK, "expected_revision": 6},
            payload=AUTH,
            idempotency_key="task-delete-cas-001",
        )
    assert conflict["status"] == "failed"
    assert conflict["error"]["code"] == "domain_rejected"

    proposal = await create_capability_proposal(
        "project.update",
        {
            "project_id": PROJECT, "expected_revision": 5,
            "name": "Safe", "goal": "Bound tenant",
        },
        payload=AUTH,
        session_id="project-session",
        request_id="project-cross-tenant-001",
        idempotency_key="project-cross-tenant-001",
        resource_versions={PROJECT: 5},
    )
    event = proposal["events"][0]["payload"]
    denied = await confirm_capability_proposal(
        event["proposal_id"], event["confirmation_token"],
        payload={**AUTH, "tenant_key": "other-tenant"},
        session_id="project-session",
    )
    assert denied["error"]["code"] == "confirmation_invalid"


@pytest.mark.asyncio
async def test_task_delete_replay_conflict_and_durable_receipt_readback():
    data = {"project_id": PROJECT, "task_id": TASK, "expected_revision": 8}

    async def proposal(arguments, request_id):
        return await create_capability_proposal(
            "task.delete", arguments, payload=AUTH,
            session_id="task-delete-session", request_id=request_id,
            idempotency_key="task-delete-durable-001",
            resource_versions={PROJECT: arguments["expected_revision"]},
        )

    first = await proposal(data, "task-delete-request-001")
    event = first["events"][0]["payload"]
    response = JSONResponse(status_code=202, content={
        "proposal": {"id": "domain-task-delete", "status": "PROPOSED"},
        "task_preview": {"id": TASK, "status": "CANCELLED"},
    })
    with patch(
        "backend.api.quantum_workspace.propose_project_task_archive",
        new=AsyncMock(return_value=response),
    ) as archive:
        completed = await confirm_capability_proposal(
            event["proposal_id"], event["confirmation_token"],
            payload=AUTH, session_id="task-delete-session",
        )
    archive.assert_awaited_once()
    assert completed["status"] == "completed"

    replay_proposal = await proposal(data, "task-delete-request-001")
    replay_event = replay_proposal["events"][0]["payload"]
    replay = await confirm_capability_proposal(
        replay_event["proposal_id"], replay_event["confirmation_token"],
        payload=AUTH, session_id="task-delete-session",
    )
    assert replay == completed

    changed = await proposal({**data, "expected_revision": 9}, "task-delete-request-002")
    changed_event = changed["events"][0]["payload"]
    idempotency_conflict = await confirm_capability_proposal(
        changed_event["proposal_id"], changed_event["confirmation_token"],
        payload=AUTH, session_id="task-delete-session",
    )
    assert idempotency_conflict["error"]["code"] == "idempotency_conflict"

    status = await invocation_status(completed["receipt"]["invocation_id"], payload=AUTH)
    assert status["status"] == "verified"
    assert status["result"]["events"][0]["payload"]["proposal"]["id"] == "domain-task-delete"


@pytest.mark.asyncio
async def test_project_task_mutations_require_durable_confirmation_flow():
    for capability_id, data in (
        ("project.update", {
            "project_id": PROJECT, "expected_revision": 1,
            "name": "Unsafe", "goal": "Must not execute",
        }),
        ("project.delete", {
            "project_id": PROJECT, "expected_revision": 1,
        }),
        ("task.delete", {
            "project_id": PROJECT, "task_id": TASK, "expected_revision": 1,
        }),
    ):
        result = await invoke_capability(
            capability_id, data, payload=AUTH,
            idempotency_key=f"{capability_id}-unsafe",
        )
        assert result["error"]["code"] == "confirmation_protocol_upgrade_required"


def test_ios_registry_declares_project_and_task_event_fallbacks():
    source = (
        __import__("pathlib").Path("ios/AIPlatformApp/Networking/APIClient.swift")
        .read_text(encoding="utf-8")
    )
    for event in (
        "project.snapshot", "project.created", "project.change_proposed",
        "task.snapshot", "task.change_proposed",
    ):
        assert f'"{event}": .init(path: .answer' in source
