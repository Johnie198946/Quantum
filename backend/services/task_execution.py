"""Governed task execution using an ephemeral delegated user token."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException

from backend.api import auth as auth_api


def _mint_delegated_token(payload: dict[str, Any], request_id: str) -> str:
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    if not user_id or not auth_api.AUTHEN_JWT_SECRET:
        raise HTTPException(status_code=503, detail={"code": "delegated_auth_unavailable"})
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=20),
            "iss": auth_api.AUTHEN_JWT_ISSUER,
            "aud": auth_api.AUTHEN_JWT_AUDIENCE,
            "token_use": "access",
            "purpose": "qcp_task_execute",
            "delegation_request_id": request_id,
            "jti": uuid.uuid4().hex,
        },
        auth_api.AUTHEN_JWT_SECRET,
        algorithm=auth_api.AUTHEN_JWT_ALGORITHM,
    )


async def execute_task(
    data: dict[str, Any], payload: dict[str, Any], idempotency_key: str | None
) -> dict[str, Any]:
    from backend.api.quantum_workspace import (
        AutoExecuteTaskRequest,
        queue_task_auto_execution,
    )

    conversation_id = str(data.get("conversation_id") or "")
    task_id = str(data.get("task_id") or "")
    instruction = str(data.get("instruction") or "")
    expected_intent_hash = str(data.get("expected_intent_hash") or "")
    if not all((conversation_id, task_id, instruction, expected_intent_hash, idempotency_key)):
        raise HTTPException(status_code=422, detail={"code": "task_execution_input_incomplete"})
    request_id = f"qcp-{idempotency_key}"[:100]
    delegated = _mint_delegated_token(payload, request_id)
    result = await queue_task_auto_execution(
        conversation_id,
        AutoExecuteTaskRequest(instruction=instruction, request_id=request_id),
        payload,
        f"Bearer {delegated}",
        expected_task_id=task_id,
        expected_intent_hash=expected_intent_hash,
    )
    return {
        **result,
        "conversation_id": conversation_id,
        "task_id": task_id,
        "intent_hash": expected_intent_hash,
        "delegated_token_persisted": False,
    }
