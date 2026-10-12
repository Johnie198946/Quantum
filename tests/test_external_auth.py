from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.api import external_auth


def _request(query: dict[str, str] | None = None, source: str = "127.0.0.1") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/callback",
            "query_string": urlencode(query or {}).encode("utf-8"),
            "headers": [],
            "client": (source, 123),
        }
    )


def _enable_dev_login(monkeypatch, allowed_ip: str = "203.0.113.10") -> None:
    values = {
        "DEV_LOGIN_ENABLED": "true",
        "DEV_LOGIN_ALLOWED_IP": allowed_ip,
        "DEV_LOGIN_EXPIRES_AT": (
            datetime.now(timezone.utc) + timedelta(minutes=10)
        ).isoformat(),
        "DEV_LOGIN_PHONE": "configured-phone",
        "DEV_LOGIN_CODE": "configured-code",
        "DEV_LOGIN_USER_ID": "configured-user",
        "DEV_LOGIN_USERNAME": "configured-name",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("13800138000", "+8613800138000"),
        ("+86 138-0013-8000", "+8613800138000"),
        ("8613800138000", "+8613800138000"),
    ],
)
def test_normalize_phone(value, expected):
    assert external_auth._normalize_phone(value) == expected


def test_normalize_phone_rejects_invalid_number():
    with pytest.raises(HTTPException) as exc:
        external_auth._normalize_phone("123")
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_phone_login_provisions_tenant_and_returns_platform_token(monkeypatch):
    calls = []
    monkeypatch.setenv("DEV_LOGIN_ENABLED", "false")

    async def fake_authen(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"user": {"id": "phone-user"}, "is_new_user": True}

    async def fake_provision(user_id):
        assert user_id == "phone-user"
        return "tenant-phone"

    monkeypatch.setattr(external_auth, "_authen_request", fake_authen)
    monkeypatch.setattr(external_auth, "_provision_tenant", fake_provision)

    payload = await external_auth.phone_login(
        external_auth.PhoneLoginRequest(phone="13800138000", code="123456"),
        _request(),
    )

    assert payload["user_id"] == "phone-user"
    assert payload["tenant_key"] == "tenant-phone"
    assert payload["token"]
    assert payload["is_new_user"] is True
    assert calls[0][:2] == ("POST", "/api/v1/auth/login/phone-code")
    assert calls[0][2]["json"]["phone"] == "+8613800138000"


@pytest.mark.asyncio
async def test_capabilities_advertises_phone_for_allowed_dev_source(monkeypatch):
    _enable_dev_login(monkeypatch)

    async def fake_authen(*args, **kwargs):
        return {"phone": {"enabled": False}, "oauth": {}}

    monkeypatch.setattr(external_auth, "_authen_request", fake_authen)

    payload = await external_auth.capabilities(_request(source="203.0.113.10"))

    assert payload["phone"]["enabled"] is True


@pytest.mark.asyncio
async def test_capabilities_keeps_upstream_phone_for_disallowed_source(monkeypatch):
    _enable_dev_login(monkeypatch)
    upstream = {"phone": {"enabled": False}, "oauth": {}}

    async def fake_authen(*args, **kwargs):
        return upstream

    monkeypatch.setattr(external_auth, "_authen_request", fake_authen)

    payload = await external_auth.capabilities(_request(source="203.0.113.11"))

    assert payload["phone"]["enabled"] is False


@pytest.mark.asyncio
async def test_phone_login_uses_controlled_dev_session_without_authen(monkeypatch):
    _enable_dev_login(monkeypatch)

    async def fail_authen(*args, **kwargs):
        pytest.fail("Authen must not be called for controlled dev login")

    async def fake_provision(user_id):
        assert user_id == "configured-user"
        return "configured-tenant"

    monkeypatch.setattr(external_auth, "_authen_request", fail_authen)
    monkeypatch.setattr(external_auth, "_provision_tenant", fake_provision)

    payload = await external_auth.phone_login(
        external_auth.PhoneLoginRequest(
            phone="configured-phone", code="configured-code"
        ),
        _request(source="203.0.113.10"),
    )

    assert payload["user_id"] == "configured-user"
    assert payload["tenant_key"] == "configured-tenant"
    assert payload["token"]
    import jwt

    from backend.api import auth

    claims = jwt.decode(
        payload["token"],
        auth.AUTHEN_JWT_SECRET,
        algorithms=["HS256"],
        audience=auth.AUTHEN_JWT_AUDIENCE,
        issuer=auth.AUTHEN_JWT_ISSUER,
    )
    assert claims["username"] == "configured-name"
    assert claims["amr"] == ["dev_code"]


@pytest.mark.asyncio
async def test_phone_login_rejects_dev_mismatch_without_authen(monkeypatch):
    _enable_dev_login(monkeypatch)

    async def fail_authen(*args, **kwargs):
        pytest.fail("Authen must not be called for controlled dev login")

    monkeypatch.setattr(external_auth, "_authen_request", fail_authen)

    with pytest.raises(HTTPException) as exc:
        await external_auth.phone_login(
            external_auth.PhoneLoginRequest(phone="configured-phone", code="wrong"),
            _request(source="203.0.113.10"),
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_phone_login_routes_real_phone_to_authen_from_allowed_dev_source(monkeypatch):
    _enable_dev_login(monkeypatch)
    calls = []

    async def fake_authen(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"user": {"id": "real-phone-user"}, "is_new_user": False}

    async def fake_provision(user_id):
        assert user_id == "real-phone-user"
        return "real-phone-tenant"

    monkeypatch.setattr(external_auth, "_authen_request", fake_authen)
    monkeypatch.setattr(external_auth, "_provision_tenant", fake_provision)

    payload = await external_auth.phone_login(
        external_auth.PhoneLoginRequest(phone="13800138000", code="123456"),
        _request(source="203.0.113.10"),
    )

    assert payload["user_id"] == "real-phone-user"
    assert payload["tenant_key"] == "real-phone-tenant"
    assert calls[0][:2] == ("POST", "/api/v1/auth/login/phone-code")


@pytest.mark.asyncio
async def test_oauth_state_and_ticket_are_single_use(monkeypatch):
    captured = {}

    async def fake_authen(method, path, **kwargs):
        if path.endswith("/authorize"):
            captured.update(kwargs["params"])
            return {"authorization_url": "https://provider.example/authorize"}
        return {"user": {"id": "oauth-user"}, "is_new_user": True}

    async def fake_provision(user_id):
        assert user_id == "oauth-user"
        return "tenant-oauth"

    monkeypatch.setenv("AUTH_PUBLIC_BASE_URL", "https://login.example.com")
    monkeypatch.setenv("AUTH_WEB_RETURN_URL", "https://app.example.com/login")
    monkeypatch.setattr(external_auth, "_authen_request", fake_authen)
    monkeypatch.setattr(external_auth, "_provision_tenant", fake_provision)

    started = await external_auth.oauth_start("wechat", "web")
    assert started["authorization_url"].startswith("https://provider.example")

    response = await external_auth.oauth_callback(
        "wechat", _request({"state": captured["state"], "code": "provider-code"})
    )
    location = response.headers["location"]
    ticket = parse_qs(urlsplit(location).query)["oauth_ticket"][0]
    assert "access_token" not in location

    completed = await external_auth.oauth_complete(
        external_auth.TicketRequest(ticket=ticket)
    )
    assert completed["user_id"] == "oauth-user"
    assert completed["tenant_key"] == "tenant-oauth"

    with pytest.raises(HTTPException) as exc:
        await external_auth.oauth_complete(external_auth.TicketRequest(ticket=ticket))
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        await external_auth.oauth_callback(
            "wechat", _request({"state": captured["state"], "code": "replay"})
        )
    assert exc.value.status_code == 400

@pytest.mark.asyncio
async def test_quantum_app_login_proxies_authen_without_local_ticket_signing(monkeypatch):
    from backend.api.auth import require_auth
    from backend.main import app
    from fastapi.testclient import TestClient
    calls = []
    flow = "a" * 64
    identity = {"user_id": "app-user", "tenant_key": "app-login-test", "principal_type": "human"}
    async def principal(): return identity
    async def authen(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path.endswith("/start"): return {"state": "s" * 43, "expires_at": 12345}
        if path.endswith("/pending"): return {"items": [{"id": flow, "code": "123456"}]}
        if path.endswith("/status"): return {"status": "approved", "ticket": "t" * 43}
        if path.endswith("/complete"): return {"access_token": "authen-issued-token", "user": {"id": "app-user"}}
        return {"success": True}
    async def provision(uid):
        assert uid == "app-user"
        return "app-login-test"
    def forbidden_signing(*args, **kwargs):
        raise AssertionError("App approval token must be issued by Authen")
    monkeypatch.setattr(external_auth, "_authen_request", authen)
    monkeypatch.setattr(external_auth, "_provision_tenant", provision)
    monkeypatch.setattr(external_auth, "_issue_jwt", forbidden_signing)
    app.dependency_overrides[require_auth] = principal
    try:
        c = TestClient(app)
        assert c.post("/api/v1/auth/quantum/start", json={"phone": "13800138000"}).status_code == 200
        assert calls[-1] == ("POST", "/api/v1/auth/app-login/start", {"json": {"phone": "+8613800138000"}})
        c.headers["Authorization"] = "Bearer app-token"
        assert c.get("/api/v1/auth/quantum/pending").status_code == 200
        assert calls[-1][2]["headers"] == {"Authorization": "Bearer app-token"}
        assert c.post(f"/api/v1/auth/quantum/{flow}/confirm", json={"code": "123456"}).status_code == 200
        assert calls[-1][1].endswith("/confirm") and calls[-1][2]["json"] == {"code": "123456"}
        assert c.post(f"/api/v1/auth/quantum/{flow}/cancel").status_code == 200
        assert c.post("/api/v1/auth/quantum/status", json={"state": "s" * 43}).status_code == 200
        result = c.post("/api/v1/auth/quantum/complete", json={"ticket": "t" * 43})
        assert result.status_code == 200 and result.json()["access_token"] == "authen-issued-token"
        assert result.json()["tenant_key"] == "app-login-test"
        before = len(calls)
        identity["principal_type"] = "service"
        assert c.get("/api/v1/auth/quantum/pending").status_code == 403
        assert len(calls) == before
    finally:
        app.dependency_overrides.pop(require_auth, None)
