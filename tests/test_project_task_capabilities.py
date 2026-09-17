from unittest.mock import AsyncMock, patch

import pytest
from fastapi.responses import JSONResponse

from backend.services.capability_catalog import (
    execute_verified_capability,
    invoke_capability,
    load_catalog,
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
        "project.list", "project.create", "project.open",
        "task.list", "task.create", "task.update", "task.status",
    }
    assert expected <= set(catalog)
    assert "task.execute" not in catalog
    for capability_id in {"project.create", "task.create", "task.update"}:
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
async def test_project_task_mutations_require_durable_confirmation_flow():
    result = await invoke_capability(
        "task.create",
        {
            "project_id": PROJECT,
            "expected_revision": 1,
            "stage_id": "stage-1",
            "title": "Unsafe",
            "summary": "Must not execute",
        },
        payload=AUTH,
        idempotency_key="task-create-unsafe",
    )
    assert result["error"]["code"] == "confirmation_protocol_upgrade_required"


def test_ios_registry_declares_project_and_task_event_fallbacks():
    source = (
        __import__("pathlib").Path("ios/AIPlatformApp/Networking/APIClient.swift")
        .read_text(encoding="utf-8")
    )
    for event in (
        "project.snapshot", "project.created", "task.snapshot", "task.change_proposed"
    ):
        assert f'"{event}": .init(path: .answer' in source
