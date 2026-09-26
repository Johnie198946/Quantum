"""Durable issuance and completion receipts for native client actions."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.db import SessionLocal
from backend.models.capability_gateway import ClientActionInvocation

_ACTIONS = {
    "conversation.lifecycle": "conversation_lifecycle",
    "file.pick": "file_picker",
    "photo.capture": "camera_capture",
    "photo.import": "photo_library",
    "voice.record": "voice_recorder",
    "share.present": "share_sheet",
}
_TERMINAL = {"SUCCEEDED", "CANCELLED", "FAILED"}


def _canonical_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _identity(payload: dict[str, Any]) -> tuple[str, str]:
    return (
        str(payload.get("tenant_key") or "public"),
        str(payload.get("user_id") or payload.get("sub") or "anonymous"),
    )


async def issue_client_action(
    capability_id: str,
    data: dict[str, Any],
    payload: dict[str, Any],
    idempotency_key: str | None,
) -> dict[str, Any]:
    if capability_id not in _ACTIONS:
        raise HTTPException(status_code=422, detail={"code": "unsupported_client_action"})
    if not idempotency_key:
        raise HTTPException(status_code=422, detail={"code": "idempotency_key_required"})
    tenant_key, user_id = _identity(payload)
    if capability_id == "conversation.lifecycle":
        sessions = data.get("sessions") or []
        if len({item["session_id"] for item in sessions}) != len(sessions):
            raise HTTPException(status_code=422, detail={"code": "duplicate_session"})
        data = {**data, "account_scope": hashlib.sha256(tenant_key.encode()).hexdigest()[:16]
                + ":" + hashlib.sha256(user_id.encode()).hexdigest()[:16]}
    key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
    input_digest = _canonical_digest(data)
    async with SessionLocal() as db:
        existing = await db.scalar(
            select(ClientActionInvocation).where(
                ClientActionInvocation.tenant_key == tenant_key,
                ClientActionInvocation.user_id == user_id,
                ClientActionInvocation.idempotency_key_hash == key_hash,
            )
        )
        if existing is not None:
            if existing.capability_id != capability_id or existing.input_digest != input_digest:
                raise HTTPException(status_code=409, detail={"code": "idempotency_conflict"})
            return _render(existing)
        row = ClientActionInvocation(
            id=f"ca_{uuid.uuid4().hex}",
            tenant_key=tenant_key,
            user_id=user_id,
            capability_id=capability_id,
            action_type=_ACTIONS[capability_id],
            idempotency_key_hash=key_hash,
            input_digest=input_digest,
            request_payload=data,
            state="PENDING",
        )
        db.add(row)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=409, detail={"code": "idempotency_race"}) from exc
        await db.refresh(row)
        return _render(row)


def _render(row: ClientActionInvocation) -> dict[str, Any]:
    return {
        "action_id": row.id,
        "capability_id": row.capability_id,
        "action_type": row.action_type,
        "state": row.state,
        "payload": row.request_payload,
        "input_digest": row.input_digest,
        "result_metadata": row.result_metadata,
        "error_code": row.error_code,
    }


async def record_client_action_receipt(
    action_id: str,
    status: str,
    result_metadata: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    terminal = status.upper()
    if terminal not in _TERMINAL:
        raise HTTPException(status_code=422, detail={"code": "invalid_client_action_status"})
    tenant_key, user_id = _identity(payload)
    result_digest = _canonical_digest({"status": terminal, "result_metadata": result_metadata})
    async with SessionLocal() as db:
        row = await db.scalar(
            select(ClientActionInvocation).where(
                ClientActionInvocation.id == action_id,
                ClientActionInvocation.tenant_key == tenant_key,
                ClientActionInvocation.user_id == user_id,
            ).with_for_update()
        )
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "client_action_not_found"})
        if row.state in _TERMINAL:
            if row.result_digest != result_digest:
                raise HTTPException(status_code=409, detail={"code": "client_action_receipt_conflict"})
            return _render(row)
        row.state = terminal
        row.result_metadata = result_metadata
        row.result_digest = result_digest
        row.error_code = (
            str(result_metadata.get("error_code") or "client_action_failed")
            if terminal == "FAILED" else None
        )
        row.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(row)
        return _render(row)
