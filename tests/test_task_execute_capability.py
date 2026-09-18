from __future__ import annotations

from datetime import datetime, timezone

import jwt
import pytest
from fastapi import HTTPException

from backend.api import auth as auth_api
from backend.api import quantum_workspace as qws
from backend.services import task_execution


@pytest.mark.asyncio
async def test_task_execute_uses_ephemeral_delegated_token_without_persisting_it(monkeypatch):
    secret = "task-execute-test-secret-that-is-long-enough"
    monkeypatch.setattr(auth_api, "AUTHEN_JWT_SECRET", secret)
    captured = {}

    async def fake_queue(conversation_id, body, payload, authorization, **expected):
        captured.update({
            "conversation_id": conversation_id,
            "body": body,
            "payload": payload,
            "authorization": authorization,
            **expected,
        })
        return {"request_id": body.request_id, "state": "queued"}

    monkeypatch.setattr(qws, "queue_task_auto_execution", fake_queue)
    intent_hash = "a" * 64
    result = await task_execution.execute_task(
        {
            "conversation_id": "conv-12345678",
            "task_id": "task-1",
            "expected_intent_hash": intent_hash,
            "instruction": "execute the accepted task",
        },
        {"tenant_key": "tenant-a", "user_id": "user-a"},
        "idem-12345678",
    )
    assert result["state"] == "queued"
    assert result["delegated_token_persisted"] is False
    assert "authorization" not in result
    assert captured["expected_task_id"] == "task-1"
    assert captured["expected_intent_hash"] == intent_hash
    token = captured["authorization"].removeprefix("Bearer ")
    claims = jwt.decode(
        token,
        secret,
        algorithms=[auth_api.AUTHEN_JWT_ALGORITHM],
        audience=auth_api.AUTHEN_JWT_AUDIENCE,
        issuer=auth_api.AUTHEN_JWT_ISSUER,
    )
    assert claims["sub"] == "user-a"
    assert claims["purpose"] == "qcp_task_execute"
    assert claims["delegation_request_id"] == "qcp-idem-12345678"
    assert claims["token_use"] == "access"
    assert claims["exp"] - int(datetime.now(timezone.utc).timestamp()) <= 20 * 60


@pytest.mark.asyncio
async def test_task_execute_fails_closed_without_secret_or_cas(monkeypatch):
    payload = {"tenant_key": "tenant-a", "user_id": "user-a"}
    complete = {
        "conversation_id": "conv-12345678",
        "task_id": "task-1",
        "expected_intent_hash": "a" * 64,
        "instruction": "execute",
    }
    monkeypatch.setattr(auth_api, "AUTHEN_JWT_SECRET", "")
    with pytest.raises(HTTPException) as secret_error:
        await task_execution.execute_task(complete, payload, "idem-12345678")
    assert secret_error.value.status_code == 503

    with pytest.raises(HTTPException) as input_error:
        await task_execution.execute_task(
            {**complete, "expected_intent_hash": ""}, payload, "idem-12345678"
        )
    assert input_error.value.status_code == 422
