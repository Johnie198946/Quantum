"""Authoritative owner/session bindings for chat-originated workflows."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.db import SessionLocal
from backend.models.workflow import WorkflowClientSessionBinding

_CLIENT_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")


def _identity(payload: dict[str, Any]) -> tuple[str, str]:
    return (
        str(payload.get("tenant_key") or "public"),
        str(payload.get("user_id") or payload.get("sub") or "anonymous"),
    )


def _binding_id(tenant_key: str, session_id: str) -> str:
    digest = hashlib.sha256(f"{tenant_key}\0{session_id}".encode()).hexdigest()
    return f"wcs_{digest[:48]}"


def validate_client_session_id(session_id: str) -> str:
    value = session_id.strip()
    if not _CLIENT_SESSION_ID.fullmatch(value):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_client_session_id"},
        )
    return value


async def register_client_session(
    payload: dict[str, Any], session_id: str | None, request_id: str | None
) -> WorkflowClientSessionBinding | None:
    """Persist that the authenticated chat API observed this client session."""
    if not session_id:
        return None
    value = validate_client_session_id(session_id)
    tenant_key, owner_user_id = _identity(payload)
    binding_id = _binding_id(tenant_key, value)
    async with SessionLocal() as db:
        row = await db.get(WorkflowClientSessionBinding, binding_id)
        if row is not None:
            if row.owner_user_id != owner_user_id:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "client_session_owner_conflict"},
                )
            row.last_request_id = request_id
            await db.commit()
            await db.refresh(row)
            return row
        row = WorkflowClientSessionBinding(
            id=binding_id,
            tenant_key=tenant_key,
            owner_user_id=owner_user_id,
            session_id=value,
            last_request_id=request_id,
        )
        db.add(row)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail={"code": "client_session_owner_conflict"},
            ) from exc
        await db.refresh(row)
        return row


async def require_registered_client_session(
    payload: dict[str, Any], session_id: str
) -> WorkflowClientSessionBinding:
    """Fail closed unless the session was registered for this owner and tenant."""
    value = validate_client_session_id(session_id)
    tenant_key, owner_user_id = _identity(payload)
    async with SessionLocal() as db:
        row = await db.scalar(
            select(WorkflowClientSessionBinding).where(
                WorkflowClientSessionBinding.tenant_key == tenant_key,
                WorkflowClientSessionBinding.owner_user_id == owner_user_id,
                WorkflowClientSessionBinding.session_id == value,
            )
        )
        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "client_session_not_registered"},
            )
        return row
