from __future__ import annotations

from datetime import datetime, timezone

import jwt
import pytest
from fastapi import HTTPException

from backend.api import auth as auth_api
from backend.api import quantum_workspace as qws
from backend.capability_handlers import HANDLERS


def _data():
    return {
        "conversation_id": "conv-1",
        "task_id": "task-1",
        "expected_intent_hash": "a" * 64,
        "instruction": "Execute the confirmed task",
    }


@pytest.mark.asyncio
async def test_task_execute_uses_ephemeral_delegated_token_without_persisting_it(monkeypatch):
    monkeypatch.setattr(auth_api, "AUTHEN_JWT_SECRET", "s" * 32)
    captured = {}

    async def fake_queue(conversation_id, body, payload, authorization, **kwargs):
        captured.update(
            conversation_id=conversation_id,
            body=body,
            payload=payload,
            authorization=authorization,
            kwargs=kwargs,
        )
        return {"queued": True, "conversation_id": conversation_id}

    monkeypatch.setattr(qws, "queue_task_auto_execution", fake_queue)
    result = await HANDLERS["task.execute"](
        _data(), {"sub": "user-1", "tenant_key": "tenant-a"}, "request-12345678"
    )
    assert result == {"queued": True, "conversation_id": "conv-1"}
    assert "authorization" not in result
    raw = captured["authorization"].removeprefix("Bearer ")
    claims = jwt.decode(
        raw,
        "s" * 32,
        algorithms=[auth_api.AUTHEN_JWT_ALGORITHM],
        audience=auth_api.AUTHEN_JWT_AUDIENCE,
        issuer=auth_api.AUTHEN_JWT_ISSUER,
    )
    assert claims["purpose"] == "qcp_task_execute"
    assert claims["qcp_task_id"] == "task-1"
    assert claims["qcp_request_id"] == "request-12345678"
    assert claims["exp"] - claims["iat"] == 20 * 60
    assert datetime.fromtimestamp(claims["exp"], tz=timezone.utc) > datetime.now(timezone.utc)
    assert captured["kwargs"] == {
        "expected_task_id": "task-1",
        "expected_intent_hash": "a" * 64,
    }


@pytest.mark.asyncio
async def test_task_execute_fails_closed_without_delegation_secret(monkeypatch):
    monkeypatch.setattr(auth_api, "AUTHEN_JWT_SECRET", "")
    with pytest.raises(HTTPException) as exc:
        await HANDLERS["task.execute"](
            _data(), {"sub": "user-1", "tenant_key": "tenant-a"}, "request-12345678"
        )
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "delegation_unavailable"


@pytest.mark.asyncio
async def test_task_execute_requires_all_cas_inputs(monkeypatch):
    monkeypatch.setattr(auth_api, "AUTHEN_JWT_SECRET", "s" * 32)
    data = _data()
    data.pop("expected_intent_hash")
    with pytest.raises(HTTPException) as exc:
        await HANDLERS["task.execute"](
            data, {"sub": "user-1", "tenant_key": "tenant-a"}, "request-12345678"
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "missing_task_execution_cas"
