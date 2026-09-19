from unittest.mock import AsyncMock, patch

import pytest

from backend.services.capability_catalog import execute_verified_capability, load_catalog


AUTH = {"tenant_key": "tenant-memory", "user_id": "user-memory"}
SNAPSHOT = {"items": [{"id": "memory-1", "target": "user", "content": "Prefer conclusions first"}]}


def test_memory_contracts_are_confirmed_and_owner_scoped():
    catalog = {item["id"]: item for item in load_catalog()["capabilities"]}
    assert set(catalog) >= {"memory.list", "memory.create", "memory.update", "memory.delete"}
    for capability_id in ("memory.create", "memory.update", "memory.delete"):
        assert catalog[capability_id]["confirmation"] == "required"
        assert catalog[capability_id]["idempotency"] == "required"
        assert catalog[capability_id]["receipt"] == "required"


@pytest.mark.asyncio
async def test_memory_handlers_reuse_the_authenticated_native_memory_facade():
    with patch("backend.api.hot_memory.get_memory", new=AsyncMock(return_value=SNAPSHOT)), patch(
        "backend.api.hot_memory.create_memory", new=AsyncMock(return_value=SNAPSHOT)
    ) as create, patch(
        "backend.api.hot_memory.replace_memory", new=AsyncMock(return_value=SNAPSHOT)
    ) as update, patch(
        "backend.api.hot_memory.remove_memory", new=AsyncMock(return_value={"items": []})
    ) as delete:
        listed = await execute_verified_capability(
            "memory.list", {}, payload=AUTH, idempotency_key=None
        )
        created = await execute_verified_capability(
            "memory.create", {"target": "user", "content": "Prefer conclusions first"},
            payload=AUTH, idempotency_key="memory-create-1",
        )
        updated = await execute_verified_capability(
            "memory.update", {"memory_id": "memory-1", "content": "Prefer concise conclusions"},
            payload=AUTH, idempotency_key="memory-update-1",
        )
        removed = await execute_verified_capability(
            "memory.delete", {"memory_id": "memory-1"},
            payload=AUTH, idempotency_key="memory-delete-1",
        )

    assert listed["status"] == created["status"] == updated["status"] == removed["status"] == "completed"
    assert listed["events"][0]["type"] == "memory.snapshot"
    assert created["events"][0]["type"] == "memory.changed"
    assert create.await_args.args[1] == AUTH
    assert update.await_args.args[0] == "memory-1"
    assert delete.await_args.args == ("memory-1", AUTH)


@pytest.mark.asyncio
async def test_memory_input_rejects_authority_and_oversized_content():
    injected = await execute_verified_capability(
        "memory.create",
        {"target": "user", "content": "safe", "user_id": "other"},
        payload=AUTH, idempotency_key="memory-injected-1",
    )
    oversized = await execute_verified_capability(
        "memory.create", {"target": "user", "content": "x" * 2201},
        payload=AUTH, idempotency_key="memory-oversized-1",
    )
    assert injected["error"]["code"] == oversized["error"]["code"] == "contract_invalid"
