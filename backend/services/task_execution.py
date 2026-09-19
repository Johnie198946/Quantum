"""Ephemeral delegated credentials for governed task execution."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException


def mint_task_execution_token(
    data: dict[str, Any],
    payload: dict[str, Any],
    idempotency_key: str,
    *,
    secret: str,
    algorithm: str,
    issuer: str,
    audience: str,
) -> str:
    required = ("conversation_id", "task_id", "expected_intent_hash", "instruction")
    missing = [name for name in required if not str(data.get(name) or "").strip()]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"code": "missing_task_execution_cas", "fields": missing},
        )
    if not secret:
        raise HTTPException(
            status_code=503,
            detail={"code": "delegation_unavailable", "message": "JWT secret is unavailable"},
        )
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail={"code": "missing_user_identity"})
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user_id,
        "token_use": "access",
        "iss": issuer,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=20)).timestamp()),
        "jti": uuid.uuid4().hex,
        "purpose": "qcp_task_execute",
        "qcp_request_id": idempotency_key,
        "qcp_task_id": str(data["task_id"]),
        "qcp_conversation_id": str(data["conversation_id"]),
        "qcp_expected_intent_hash": str(data["expected_intent_hash"]),
    }
    return jwt.encode(claims, secret, algorithm=algorithm)
