from unittest.mock import AsyncMock, patch

import pytest

from backend.services.capability_catalog import execute_verified_capability, load_catalog


AUTH = {"tenant_key": "tenant-profile", "user_id": "user-profile"}
PROFILE = {"user_id": "user-profile", "tenant_key": "tenant-profile", "username": "Johnie"}


def test_profile_contracts_are_registered_and_update_is_confirmed():
    catalog = {item["id"]: item for item in load_catalog()["capabilities"]}
    assert set(catalog) >= {"profile.read", "profile.update"}
    assert catalog["profile.read"]["confirmation"] == "none"
    assert catalog["profile.update"]["confirmation"] == "required"
    assert catalog["profile.update"]["idempotency"] == "required"


@pytest.mark.asyncio
async def test_profile_handlers_reuse_authenticated_me_facade():
    with patch("backend.api.me.me", new=AsyncMock(return_value=PROFILE)) as read, patch(
        "backend.api.me.patch_me", new=AsyncMock(return_value=PROFILE)
    ) as update:
        snapshot = await execute_verified_capability(
            "profile.read", {}, payload=AUTH, idempotency_key=None
        )
        changed = await execute_verified_capability(
            "profile.update", {"username": "Johnie"},
            payload=AUTH, idempotency_key="profile-update-1",
        )
    assert snapshot["status"] == changed["status"] == "completed"
    assert snapshot["events"][0]["type"] == "profile.snapshot"
    assert changed["events"][0]["type"] == "profile.changed"
    assert read.await_args.args == (AUTH,)
    assert update.await_args.args[1] == AUTH
    assert update.await_args.args[0].username == "Johnie"


@pytest.mark.asyncio
async def test_profile_update_rejects_empty_and_authority_fields():
    empty = await execute_verified_capability(
        "profile.update", {}, payload=AUTH, idempotency_key="profile-empty-1"
    )
    injected = await execute_verified_capability(
        "profile.update", {"username": "safe", "tenant_key": "other"},
        payload=AUTH, idempotency_key="profile-injected-1",
    )
    assert empty["error"]["code"] == injected["error"]["code"] == "contract_invalid"
