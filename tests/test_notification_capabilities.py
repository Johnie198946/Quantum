from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect

from backend.api.notifications import (
    NotificationPreferenceRequest,
    NotificationReadRequest,
    list_notifications,
    mark_read,
    update_preferences,
)
from backend.db import SessionLocal, _migrate_notification_owner_columns
from backend.models.notification import Notification
from backend.services.capability_catalog import execute_verified_capability, invoke_capability, load_catalog


@pytest.mark.asyncio
async def test_notifications_are_principal_bound_and_ownerless_rows_fail_closed():
    suffix = uuid.uuid4().hex
    tenant = f"tenant-{suffix}"
    owner = {"tenant_key": tenant, "user_id": "owner", "sub": "owner"}
    other = {"tenant_key": tenant, "user_id": "other", "sub": "other"}
    async with SessionLocal() as db:
        visible = Notification(
            tenant_key=tenant, user_id="owner", agent_id="agent",
            title="visible", content="owner", channel="inapp",
        )
        foreign = Notification(
            tenant_key=tenant, user_id="other", agent_id="agent",
            title="foreign", content="other", channel="inapp",
        )
        legacy = Notification(
            tenant_key=tenant, user_id=None, agent_id="agent",
            title="legacy", content="ownerless", channel="inapp",
        )
        db.add_all([visible, foreign, legacy])
        await db.commit()
        await db.refresh(visible)
        visible_id = visible.id

    snapshot = await list_notifications(limit=50, unread_only=False, payload=owner)
    assert [item["title"] for item in snapshot["items"]] == ["visible"]
    with pytest.raises(HTTPException) as denied:
        await mark_read(visible_id, NotificationReadRequest(), other)
    assert denied.value.status_code == 404


@pytest.mark.asyncio
async def test_notification_mark_read_has_domain_cas():
    suffix = uuid.uuid4().hex
    auth = {"tenant_key": f"tenant-{suffix}", "user_id": "owner", "sub": "owner"}
    async with SessionLocal() as db:
        row = Notification(
            tenant_key=auth["tenant_key"], user_id="owner", agent_id="agent",
            title="cas", content="body", channel="inapp",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        row_id = row.id
    changed = await mark_read(row_id, NotificationReadRequest(expected_read=False), auth)
    assert changed == {"ok": True, "id": row_id, "read": True}
    with pytest.raises(HTTPException) as conflict:
        await mark_read(row_id, NotificationReadRequest(expected_read=False), auth)
    assert conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_notification_preferences_have_revision_cas_and_owner_isolation():
    suffix = uuid.uuid4().hex
    auth = {"tenant_key": f"tenant-{suffix}", "user_id": "owner", "sub": "owner"}
    created = await update_preferences(NotificationPreferenceRequest(
        expected_revision=0, enabled=True, channels=["inapp", "feishu"]
    ), auth)
    assert created["revision"] == 1
    with pytest.raises(HTTPException) as stale:
        await update_preferences(NotificationPreferenceRequest(
            expected_revision=0, enabled=False, channels=["inapp"]
        ), auth)
    assert stale.value.status_code == 409
    other = await update_preferences(NotificationPreferenceRequest(
        expected_revision=0, enabled=False, channels=["inapp"]
    ), {**auth, "user_id": "other", "sub": "other"})
    assert other["revision"] == 1


def test_notification_pcm_contracts_are_governed():
    catalog = {item["id"]: item for item in load_catalog()["capabilities"]}
    expected = {
        "notification.list", "notification.mark_read", "notification.preferences.update"
    }
    assert expected <= set(catalog)
    for capability_id in expected - {"notification.list"}:
        item = catalog[capability_id]
        assert item["confirmation"] == "required"
        assert item["idempotency"] == "required"
        assert item["receipt"] == "required"


@pytest.mark.asyncio
async def test_notification_qcp_read_and_unconfirmed_write():
    suffix = uuid.uuid4().hex
    auth = {"tenant_key": f"tenant-{suffix}", "user_id": "owner", "sub": "owner"}
    read = await execute_verified_capability(
        "notification.list", {"limit": 5}, payload=auth, idempotency_key=None
    )
    assert read["status"] == "completed"
    assert read["events"][0]["type"] == "notification.snapshot"
    denied = await invoke_capability(
        "notification.preferences.update",
        {"expected_revision": 0, "enabled": True, "channels": ["inapp"]},
        payload=auth,
        idempotency_key="notification-write-001",
    )
    assert denied["error"]["code"] == "confirmation_protocol_upgrade_required"


def test_notification_migration_adds_owner_read_time_without_backfill(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE notifications ("
            "id VARCHAR(64) PRIMARY KEY, tenant_key VARCHAR(100) NOT NULL, "
            "read BOOLEAN NOT NULL DEFAULT 0)"
        )
        connection.exec_driver_sql(
            "INSERT INTO notifications (id, tenant_key, read) "
            "VALUES ('legacy', 'tenant-a', 0)"
        )
        _migrate_notification_owner_columns(connection)
        columns = {
            item["name"]
            for item in inspect(connection).get_columns("notifications")
        }
        assert {"user_id", "read_at"} <= columns
        row = connection.exec_driver_sql(
            "SELECT user_id, read_at FROM notifications WHERE id='legacy'"
        ).one()
        assert row == (None, None)
        indexes = {
            item["name"]
            for item in inspect(connection).get_indexes("notifications")
        }
        assert {"ix_notifications_user_id", "ix_notification_owner_read"} <= indexes
