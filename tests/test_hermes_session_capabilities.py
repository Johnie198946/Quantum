from __future__ import annotations

import hashlib
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from backend.services import hermes_sessions


class FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class FakeClient:
    response = FakeResponse(200, {})
    request = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json, headers):
        type(self).request = {"url": url, "json": json, "headers": headers}
        return type(self).response


def test_namespaced_session_key_matches_chat_contract():
    tenant, user, raw = "tenant-a", "user-a", "chat-123"
    expected = (
        f"t{hashlib.sha256(tenant.encode()).hexdigest()[:12]}-"
        f"u{hashlib.sha256(user.encode()).hexdigest()[:12]}-{raw}"
    )
    assert hermes_sessions.namespaced_session_key(raw, tenant, user) == expected


@pytest.mark.asyncio
async def test_owner_session_list_verifies_binding_and_sends_owner_headers(monkeypatch):
    observed = {}

    async def require(payload, session_id):
        observed["binding"] = (payload, session_id)
        return SimpleNamespace(session_id=session_id)

    monkeypatch.setattr(hermes_sessions, "require_registered_client_session", require)
    monkeypatch.setattr(hermes_sessions, "_INTERNAL_TOKEN", "internal-test-token")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    FakeClient.response = FakeResponse(200, {"hermes_session_id": "hs-1"})
    payload = {"tenant_key": "tenant-a", "user_id": "user-a"}
    result = await hermes_sessions.owner_session_action(
        "list", {"client_session_id": "chat-123"}, payload
    )
    assert result == {"sessions": [{"hermes_session_id": "hs-1"}], "count": 1}
    assert observed["binding"] == (payload, "chat-123")
    assert FakeClient.request["headers"] == {
        "X-Hermes-Internal-Token": "internal-test-token",
        "X-Tenant-ID": "tenant-a",
        "X-User-ID": "user-a",
    }
    assert FakeClient.request["json"]["session_key"].endswith("-chat-123")


@pytest.mark.asyncio
async def test_owner_session_list_maps_owner_scoped_not_found_to_empty(monkeypatch):
    async def require(payload, session_id):
        return SimpleNamespace(session_id=session_id)

    monkeypatch.setattr(hermes_sessions, "require_registered_client_session", require)
    monkeypatch.setattr(hermes_sessions, "_INTERNAL_TOKEN", "internal-test-token")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    FakeClient.response = FakeResponse(404, {"detail": "hermes_session_not_found"})
    result = await hermes_sessions.owner_session_action(
        "list", {"client_session_id": "chat-404"},
        {"tenant_key": "tenant-a", "user_id": "user-a"},
    )
    assert result == {"sessions": [], "count": 0}


@pytest.mark.asyncio
async def test_owner_binding_failure_stops_before_bridge(monkeypatch):
    async def reject(payload, session_id):
        raise HTTPException(status_code=404, detail={"code": "client_session_not_registered"})

    monkeypatch.setattr(hermes_sessions, "require_registered_client_session", reject)
    monkeypatch.setattr(hermes_sessions, "_INTERNAL_TOKEN", "internal-test-token")
    FakeClient.request = None
    with pytest.raises(HTTPException) as exc:
        await hermes_sessions.owner_session_action(
            "open", {"client_session_id": "foreign"},
            {"tenant_key": "tenant-a", "user_id": "user-a"},
        )
    assert exc.value.status_code == 404
    assert FakeClient.request is None


def test_session_contracts_and_handlers_are_registered():
    from backend.capability_handlers import HANDLERS
    from backend.services.capability_catalog import load_catalog

    catalog = load_catalog()
    ids = {item["id"] for item in catalog["capabilities"]}
    expected = {
        "hermes.session.list", "hermes.session.open",
        "hermes.session.resume", "hermes.session.delete",
    }
    assert expected <= ids
    assert expected <= set(HANDLERS)
    by_id = {item["id"]: item for item in catalog["capabilities"]}
    assert by_id["hermes.session.resume"]["confirmation"] == "required"
    assert by_id["hermes.session.delete"]["effect"] == "destructive"


def test_bridge_rejects_namespaced_key_for_different_owner(monkeypatch):
    from scripts import hermes_bridge as bridge

    monkeypatch.setattr(bridge, "_require_internal_strict", lambda token: None)
    body = bridge.OwnerSessionRequest(
        session_key=hermes_sessions.namespaced_session_key("chat", "tenant-b", "user-b")
    )
    with pytest.raises(HTTPException) as exc:
        bridge._require_owner_session(body, "token", "tenant-a", "user-a")
    assert exc.value.status_code == 403
    assert exc.value.detail == "session_owner_mismatch"


def test_bridge_snapshot_only_uses_bound_mapping(monkeypatch):
    from scripts import hermes_bridge as bridge

    class FakeDB:
        def get_session(self, session_id):
            assert session_id == "hs-owned"
            return {"id": session_id, "created_at": "created", "ended_at": None}

    key = hermes_sessions.namespaced_session_key("chat", "tenant-a", "user-a")
    monkeypatch.setitem(bridge._user_session_map, key, "hs-owned")
    monkeypatch.setattr(bridge, "_create_sandbox_session_db", lambda sandbox: FakeDB())
    result = bridge._owner_session_snapshot(key, object())
    assert result["hermes_session_id"] == "hs-owned"
    assert "messages" not in result
