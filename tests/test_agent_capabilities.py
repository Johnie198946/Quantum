from unittest.mock import AsyncMock, patch

import pytest

from backend.services.capability_catalog import execute_verified_capability, load_catalog


AUTH = {"tenant_key": "tenant-agent", "user_id": "user-agent", "sub": "user-agent", "principal_type": "human", "amr": ["password"]}


def test_agent_contracts_are_registered():
    catalog = load_catalog()
    ids = {item["id"] for item in catalog["capabilities"]}
    assert {"agent.list", "agent.create", "agent.update", "agent.delete", "agent.evaluate", "agent.evaluation_status"} <= ids


@pytest.mark.asyncio
async def test_agent_list_uses_tenant_api():
    row = {"id": "a1", "tenant_id": "tenant-agent"}
    with patch("backend.api.tenant_agents.list_tenant_agents", new=AsyncMock(return_value=[row])):
        result = await execute_verified_capability("agent.list", {}, payload=AUTH, idempotency_key=None)
    assert result["events"][0]["payload"] == {"agents": [row]}


@pytest.mark.asyncio
async def test_agent_create_uses_tenant_api():
    with patch("backend.api.tenant_agents.create_tenant_agent", new=AsyncMock(return_value={"id": "a1"})) as call:
        result = await execute_verified_capability("agent.create", {"base_agent_id": "main_agent"}, payload=AUTH, idempotency_key="agent-create-1")
    assert result["events"][0]["payload"]["id"] == "a1"
    assert call.await_count == 1


@pytest.mark.asyncio
async def test_agent_update_delete_and_evaluate_use_owned_api():
    with patch("backend.api.tenant_agents.update_tenant_agent", new=AsyncMock(return_value={"id": "a1"})) as update:
        result = await execute_verified_capability("agent.update", {"agent_id": "a1", "base_agent_id": "main_agent"}, payload=AUTH, idempotency_key="agent-update-1")
        assert result["events"][0]["payload"]["id"] == "a1"
        assert update.await_args.args[0] == "a1"
    with patch("backend.api.tenant_agents.delete_tenant_agent", new=AsyncMock(return_value=None)) as delete:
        result = await execute_verified_capability("agent.delete", {"agent_id": "a1"}, payload=AUTH, idempotency_key="agent-delete-1")
        assert result["events"][0]["payload"] == {"status": "deleted"}
        assert delete.await_args.args[0] == "a1"
    with patch("backend.api.tenant_agents.create_agent_evaluation", new=AsyncMock(return_value={"id": "run1", "status": "queued"})) as evaluate:
        result = await execute_verified_capability("agent.evaluate", {"agent_id": "a1", "request_id": "request-001"}, payload=AUTH, idempotency_key="agent-eval-1")
        assert result["events"][0]["payload"] == {"id": "run1", "status": "queued"}
        assert evaluate.await_args.args[0] == "a1"


@pytest.mark.asyncio
async def test_agent_evaluation_status_uses_owned_api():
    with patch("backend.api.tenant_agents.get_agent_evaluation", new=AsyncMock(return_value={"id": "run1", "status": "completed"})):
        result = await execute_verified_capability("agent.evaluation_status", {"run_id": "run1"}, payload=AUTH, idempotency_key=None)
    assert result["events"][0]["payload"] == {"id": "run1", "status": "completed"}
