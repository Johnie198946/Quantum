"""Owner-bound notification center and preferences."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.api.auth import require_auth

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationReadRequest(BaseModel):
    expected_read: bool = False


class NotificationPreferenceRequest(BaseModel):
    expected_revision: int = Field(..., ge=0)
    enabled: bool
    channels: list[str] = Field(default_factory=lambda: ["inapp"], min_length=1, max_length=4)


def _identity(payload: dict[str, Any]) -> tuple[str, str]:
    tenant = str(payload.get("tenant_key") or "").strip()
    user = str(payload.get("user_id") or payload.get("sub") or "").strip()
    if not tenant or not user:
        raise HTTPException(status_code=401, detail={"code": "not_authenticated"})
    return tenant, user


def _serialize_notification(value: Any) -> dict[str, Any]:
    return {
        "id": value.id,
        "agent_id": value.agent_id,
        "title": value.title,
        "content": value.content or "",
        "channel": value.channel,
        "read": value.read,
        "created_at": value.created_at.isoformat() if value.created_at else None,
    }


@router.get("")
async def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
    payload=Depends(require_auth),
) -> Dict[str, Any]:
    from sqlalchemy import func, select

    from backend.db import SessionLocal
    from backend.models.notification import Notification

    tenant_key, user_id = _identity(payload)
    owner = (
        Notification.tenant_key == tenant_key,
        Notification.user_id == user_id,
    )
    async with SessionLocal() as db:
        total = (await db.execute(
            select(func.count(Notification.id)).where(*owner)
        )).scalar_one()
        unread = (await db.execute(
            select(func.count(Notification.id)).where(*owner, Notification.read.is_(False))
        )).scalar_one()
        query = select(Notification).where(*owner).order_by(
            Notification.created_at.desc()
        ).limit(limit)
        if unread_only:
            query = query.where(Notification.read.is_(False))
        rows = (await db.execute(query)).scalars().all()
    return {
        "total": total,
        "unread": unread,
        "items": [_serialize_notification(item) for item in rows],
    }


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    body: NotificationReadRequest | None = None,
    payload=Depends(require_auth),
) -> Dict[str, Any]:
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.notification import Notification

    tenant_key, user_id = _identity(payload)
    expected_read = body.expected_read if body is not None else False
    async with SessionLocal() as db:
        row = (await db.execute(select(Notification).where(
            Notification.id == notification_id,
            Notification.tenant_key == tenant_key,
            Notification.user_id == user_id,
        ).with_for_update())).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "notification_not_found"})
        if row.read != expected_read:
            raise HTTPException(status_code=409, detail={"code": "notification_revision_conflict"})
        row.read = True
        await db.commit()
        await db.refresh(row)
    return {"ok": True, "id": notification_id, "read": row.read}


@router.post("/read-all")
async def mark_all_read(payload=Depends(require_auth)) -> Dict[str, Any]:
    from sqlalchemy import update

    from backend.db import SessionLocal
    from backend.models.notification import Notification

    tenant_key, user_id = _identity(payload)
    async with SessionLocal() as db:
        result = await db.execute(update(Notification).where(
            Notification.tenant_key == tenant_key,
            Notification.user_id == user_id,
            Notification.read.is_(False),
        ).values(read=True))
        await db.commit()
    return {"ok": True, "updated": int(result.rowcount or 0)}


@router.get("/preferences/me")
async def get_preferences(payload=Depends(require_auth)) -> Dict[str, Any]:
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.notification import NotificationPreference

    tenant_key, user_id = _identity(payload)
    async with SessionLocal() as db:
        row = (await db.execute(select(NotificationPreference).where(
            NotificationPreference.tenant_key == tenant_key,
            NotificationPreference.user_id == user_id,
        ))).scalar_one_or_none()
    if row is None:
        return {"enabled": True, "channels": ["inapp"], "revision": 0}
    return {
        "enabled": row.enabled,
        "channels": list(row.channels or []),
        "revision": row.revision,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.put("/preferences/me")
async def update_preferences(
    body: NotificationPreferenceRequest, payload=Depends(require_auth)
) -> Dict[str, Any]:
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.notification import NotificationPreference

    allowed = {"inapp", "feishu", "weixin", "email"}
    channels = sorted(set(body.channels))
    if any(item not in allowed for item in channels):
        raise HTTPException(status_code=422, detail={"code": "unsupported_notification_channel"})
    tenant_key, user_id = _identity(payload)
    async with SessionLocal() as db:
        row = (await db.execute(select(NotificationPreference).where(
            NotificationPreference.tenant_key == tenant_key,
            NotificationPreference.user_id == user_id,
        ).with_for_update())).scalar_one_or_none()
        current_revision = row.revision if row is not None else 0
        if current_revision != body.expected_revision:
            raise HTTPException(status_code=409, detail={"code": "notification_revision_conflict"})
        if row is None:
            row = NotificationPreference(
                tenant_key=tenant_key,
                user_id=user_id,
                revision=1,
                enabled=body.enabled,
                channels=channels,
            )
            db.add(row)
        else:
            row.enabled = body.enabled
            row.channels = channels
            row.revision += 1
        await db.commit()
        await db.refresh(row)
    return {
        "enabled": row.enabled,
        "channels": list(row.channels),
        "revision": row.revision,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
