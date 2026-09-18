from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from backend.db import init_db
from backend.services.client_actions import (
    issue_client_action,
    record_client_action_receipt,
)


@pytest.mark.asyncio
async def test_client_action_issue_replay_owner_and_terminal_receipt():
    await init_db()
    suffix = uuid.uuid4().hex
    owner = {"tenant_key": f"tenant-{suffix}", "user_id": f"user-{suffix}"}
    other = {"tenant_key": owner["tenant_key"], "user_id": "other-user"}
    key = f"client-action-{suffix}"

    issued = await issue_client_action(
        "file.pick", {"allows_multiple": False}, owner, key
    )
    assert issued["state"] == "PENDING"
    replay = await issue_client_action(
        "file.pick", {"allows_multiple": False}, owner, key
    )
    assert replay["action_id"] == issued["action_id"]

    with pytest.raises(HTTPException) as conflict:
        await issue_client_action(
            "file.pick", {"allows_multiple": True}, owner, key
        )
    assert conflict.value.status_code == 409

    with pytest.raises(HTTPException) as hidden:
        await record_client_action_receipt(
            issued["action_id"], "SUCCEEDED", {"selection_count": "1"}, other
        )
    assert hidden.value.status_code == 404

    completed = await record_client_action_receipt(
        issued["action_id"], "SUCCEEDED", {"selection_count": "1"}, owner
    )
    assert completed["state"] == "SUCCEEDED"
    exact_replay = await record_client_action_receipt(
        issued["action_id"], "SUCCEEDED", {"selection_count": "1"}, owner
    )
    assert exact_replay == completed

    with pytest.raises(HTTPException) as receipt_conflict:
        await record_client_action_receipt(
            issued["action_id"], "CANCELLED", {}, owner
        )
    assert receipt_conflict.value.status_code == 409


def test_client_action_contracts_are_confirmed_and_registered():
    from backend.capability_handlers import HANDLERS
    from backend.services.capability_catalog import load_catalog

    expected = {"file.pick", "photo.capture", "photo.import", "voice.record", "share.present"}
    by_id = {item["id"]: item for item in load_catalog()["capabilities"]}
    assert expected <= set(HANDLERS)
    assert expected <= set(by_id)
    for capability_id in expected:
        contract = by_id[capability_id]
        assert contract["confirmation"] == "required"
        assert contract["receipt"] == "required"
        assert contract["renderer"] == "client_action"
