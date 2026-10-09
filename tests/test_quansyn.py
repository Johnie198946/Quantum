"""Real DB/artifact round trips and transfer/device trust boundaries."""
import uuid
import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.api import quansyn
from backend.db import SessionLocal
from backend.models.tenant import TenantMapping
from backend.main import app
from backend.api.auth import require_auth
from backend.api.agreement import CURRENT_AGREEMENT_VERSION
from backend.models.quansyn import QuanSynDevice


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_GENERATED_ARTIFACT_ROOT", str(tmp_path / "files"))
    who = {"tenant_key": "qs-test", "user_id": uuid.uuid4().hex}
    async def authenticated():
        return dict(who)
    app.dependency_overrides[quansyn.principal] = authenticated
    app.dependency_overrides[require_auth] = authenticated
    async def mapping():
        async with SessionLocal() as db:
            db.add(TenantMapping(user_id=who["user_id"], tenant_key=who["tenant_key"]))
            await db.commit()
    asyncio.run(mapping())
    with TestClient(app, raise_server_exceptions=True) as c:
        assert c.put("/api/v1/me/agreement-acceptance", json={"agreement_version": CURRENT_AGREEMENT_VERSION, "idempotency_key": str(uuid.uuid4()), "source": "web"}).status_code == 200
        yield c, who
    app.dependency_overrides.pop(quansyn.principal, None)
    app.dependency_overrides.pop(require_auth, None)


def body(**kwargs):
    return {"request_id": uuid.uuid4().hex, "text": "真实流程测试", **kwargs}


def test_roundtrip_and_idempotency(client):
    c, who = client
    raw = b"hello QuanSyn\n"
    file = c.post("/api/v1/quansyn/files", content=raw, headers={"X-File-Name": "test.txt"}).json()
    payload = body(files=[{"artifact_id": file["artifact_id"]}])
    first = c.post("/api/v1/quansyn/transfers", json=payload)
    assert first.status_code == 201, first.text
    row = first.json()
    assert c.post("/api/v1/quansyn/transfers", json=payload).json()["id"] == row["id"]
    assert c.post("/api/v1/quansyn/transfers", json={**payload, "text": "different"}).status_code == 409
    claim = {"revision": row["revision"], "claim": uuid.uuid4().hex}
    leased = c.post(f'/api/v1/quansyn/transfers/{row["id"]}/claim', json=claim)
    assert leased.status_code == 200, leased.text
    assert c.post(f'/api/v1/quansyn/transfers/{row["id"]}/claim', json={**claim, "claim": uuid.uuid4().hex}).status_code == 409
    claim["revision"] = leased.json()["revision"]
    assert c.post(f'/api/v1/quansyn/transfers/{row["id"]}/imported', json=claim).json()["status"] == "imported"
    result = c.post("/api/v1/quansyn/transfers", json=body(direction="result", reply_to=row["id"],
        blocks=[{"kind": "chart", "labels": ["A", "B"], "values": [2, 4]}], files=payload["files"]))
    assert result.status_code == 201, result.text
    assert c.get(f'/api/v1/quansyn/files/{file["artifact_id"]}').content == raw
    assert c.get(f'/api/v1/quansyn/transfers/{row["id"]}').json()["status"] == "returned"
    who["user_id"] = uuid.uuid4().hex
    assert c.get("/api/v1/quansyn/transfers").json()["items"] == []
    assert c.get(f'/api/v1/quansyn/files/{file["artifact_id"]}').status_code == 404
    assert c.post("/api/v1/quansyn/transfers", json=body(files=payload["files"])).status_code == 404


def test_validation(client):
    c, _ = client
    assert c.post("/api/v1/quansyn/transfers", json=body(text="")).status_code == 422
    assert c.post("/api/v1/quansyn/transfers", json=body(blocks=[{"kind": "chart", "labels": ["x"], "values": []}])).status_code == 422
    assert c.post("/api/v1/quansyn/files", content=b"", headers={"X-File-Name": "a.txt"}).status_code == 422
    assert c.post("/api/v1/quansyn/files", content=b"x" * (quansyn.MAX_BYTES + 1), headers={"X-File-Name": "a.txt"}).status_code == 413
    extensionless = c.post("/api/v1/quansyn/files", content=b"hello", headers={"X-File-Name": "LICENSE"})
    assert extensionless.status_code == 201
    assert c.get('/api/v1/quansyn/files/' + extensionless.json()["artifact_id"]).content == b"hello"


def test_device_pair_scope_and_revocation(client):
    c, who = client
    ios = c.post("/api/v1/quansyn/transfers", json=body()).json()
    mac = c.post("/api/v1/quansyn/transfers", json=body(target="mac")).json()
    code = c.post("/api/v1/quansyn/devices/pair").json()["code"]
    pair_body = {"code": code, "sender_id": "feishu-owner"}
    paired = c.post("/api/v1/quansyn/devices/exchange", json=pair_body)
    assert paired.status_code == 200
    assert c.post("/api/v1/quansyn/devices/exchange", json=pair_body).status_code == 401
    device = paired.json()
    app.dependency_overrides.pop(quansyn.principal)
    headers = {"Authorization": "Bearer " + device["token"], "X-QuanSyn-Sender": "feishu-owner"}
    assert c.get("/api/v1/quansyn/transfers", headers=headers).json()["items"][0]["id"] == mac["id"]
    assert c.get('/api/v1/quansyn/transfers/' + ios["id"], headers=headers).status_code == 404
    assert c.get("/api/v1/quansyn/transfers", headers={**headers, "X-QuanSyn-Sender": "another"}).status_code == 401
    assert c.post("/api/v1/quansyn/transfers", json=body(), headers=headers).status_code == 403
    assert c.post("/api/v1/quansyn/devices/pair", headers=headers).status_code == 403
    async def authenticated():
        return dict(who)
    app.dependency_overrides[quansyn.principal] = authenticated
    assert c.delete('/api/v1/quansyn/devices/' + device["device_id"]).status_code == 204
    app.dependency_overrides.pop(quansyn.principal)
    assert c.get("/api/v1/quansyn/transfers", headers=headers).status_code == 401
    app.dependency_overrides[quansyn.principal] = authenticated


def test_expired_pair(client):
    c, _ = client
    code = c.post("/api/v1/quansyn/devices/pair").json()["code"]
    async def expire():
        async with SessionLocal() as db:
            row = await db.scalar(select(QuanSynDevice).where(QuanSynDevice.code_hash == quansyn.digest(code)))
            row.expires_at = quansyn.now() - timedelta(seconds=1)
            await db.commit()
    asyncio.run(expire())
    assert c.post("/api/v1/quansyn/devices/exchange", json={"code": code, "sender_id": "owner"}).status_code == 401


def test_device_cannot_bypass_withdrawal_or_attach_other_queue_file(client):
    c, who = client
    hidden = c.post("/api/v1/quansyn/files", content=b"private ios", headers={"X-File-Name": "private.txt"}).json()
    mac = c.post("/api/v1/quansyn/transfers", json=body(target="mac")).json()
    code = c.post("/api/v1/quansyn/devices/pair").json()["code"]
    device = c.post("/api/v1/quansyn/devices/exchange", json={"code": code, "sender_id": "owner"}).json()
    override = app.dependency_overrides.pop(quansyn.principal)
    headers = {"Authorization": "Bearer " + device["token"], "X-QuanSyn-Sender": "owner"}
    try:
        claim = {"revision": mac["revision"], "claim": uuid.uuid4().hex}
        leased = c.post('/api/v1/quansyn/transfers/' + mac["id"] + '/claim', json=claim, headers=headers)
        assert leased.status_code == 200
        claim["revision"] = leased.json()["revision"]
        assert c.post('/api/v1/quansyn/transfers/' + mac["id"] + '/imported', json=claim, headers=headers).status_code == 200
        assert c.post("/api/v1/quansyn/transfers", json=body(direction="result", target="mac", reply_to=mac["id"], files=[{"artifact_id": hidden["artifact_id"]}]), headers=headers).status_code == 403
        from backend.models.knowledge_contribution import KnowledgeContributionUserConsent
        async def withdraw():
            async with SessionLocal() as db:
                row = await db.get(KnowledgeContributionUserConsent, (who["tenant_key"], who["user_id"]))
                row.participation_enabled = False
                await db.commit()
        asyncio.run(withdraw())
        assert c.get("/api/v1/quansyn/transfers", headers=headers).status_code == 428
    finally:
        app.dependency_overrides[quansyn.principal] = override
