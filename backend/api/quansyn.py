"""Manual QuanSyn delivery on existing auth, database and private artifact storage."""
from __future__ import annotations
import hashlib
import secrets
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import unquote
from pathlib import Path
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from backend.contracts.quansyn import Block, FileRef, TransferBody
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from backend.api.agreement import require_current_agreement
from backend.api.auth import require_auth, security
from backend.db import SessionLocal
from backend.models.quansyn import QuanSynDevice, QuanSynTransfer
from backend.models.tenant import TenantMapping
from backend.services.generated_artifacts import GeneratedArtifactError, _owner_root, _save, generated_artifact_path

router = APIRouter(prefix="/api/v1/quansyn", tags=["quansyn"])


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


async def principal(credentials=Depends(security), sender: str = Header("", alias="X-QuanSyn-Sender")):
    if credentials and credentials.credentials.startswith("qs_"):
        async with SessionLocal() as db:
            device = await db.scalar(select(QuanSynDevice).where(
                QuanSynDevice.token_hash == digest(credentials.credentials),
                QuanSynDevice.revoked.is_(False), QuanSynDevice.expires_at > now()))
            mapping = await db.get(TenantMapping, device.user_id) if device else None
        if not device or not mapping or mapping.tenant_key != device.tenant_key or not secrets.compare_digest(device.sender_id or "", sender):
            raise HTTPException(401, "设备凭证无效、已撤销或身份不符")
        return await require_current_agreement({"tenant_key": device.tenant_key, "user_id": device.user_id, "device_id": device.id})
    payload = await require_auth(credentials)
    if not payload.get("tenant_key") or not (payload.get("user_id") or payload.get("sub")):
        raise HTTPException(401, "请使用真实账号登录 QuanSyn")
    return await require_current_agreement(payload)


def owner(p):
    return str(p["tenant_key"]), str(p.get("user_id") or p["sub"])


def scope(p):
    tenant, user = owner(p)
    filters = [QuanSynTransfer.tenant_key == tenant, QuanSynTransfer.user_id == user]
    if p.get("device_id"):
        filters.append(QuanSynTransfer.target == "mac")
    return filters


def interactive(p):
    if p.get("device_id"):
        raise HTTPException(403, "设备凭证不能执行账号管理")




def serialize(row):
    return {key: getattr(row, key) for key in (
        "id", "direction", "target", "reply_to", "text", "blocks", "files", "status", "revision", "created_at")}


async def owned_row(db, transfer_id, p):
    row = await db.scalar(select(QuanSynTransfer).where(QuanSynTransfer.id == transfer_id, *scope(p)))
    if not row:
        raise HTTPException(404, "传递记录不存在")
    return row


@router.post("/transfers", status_code=201)
async def create_transfer(body: TransferBody, p=Depends(principal)):
    if p.get("device_id") and (body.direction != "result" or body.target != "mac" or not body.reply_to):
        raise HTTPException(403, "Mac 凭证只能回传关联结果")
    tenant, user = owner(p)
    fingerprint = digest(body.model_dump_json())
    async with SessionLocal() as db:
        # Serialize attachment references and cleanup for this account.
        await db.scalar(select(TenantMapping).where(TenantMapping.user_id == user).with_for_update())
        previous = await db.scalar(select(QuanSynTransfer).where(
            QuanSynTransfer.tenant_key == tenant, QuanSynTransfer.user_id == user,
            QuanSynTransfer.request_id == body.request_id))
        if previous:
            if previous.digest != fingerprint:
                raise HTTPException(409, "重试标识对应的内容已改变")
            return serialize(previous)
        files = []
        for ref in body.files:
            try:
                _, receipt = await run_in_threadpool(generated_artifact_path, tenant, user, ref.artifact_id)
            except GeneratedArtifactError as exc:
                raise HTTPException(404, "附件不存在或无权访问") from exc
            files.append(receipt)
        if body.reply_to:
            parent = await owned_row(db, body.reply_to, p)
            if parent.direction != "request" or parent.target != body.target:
                raise HTTPException(409, "回传关联的需求或目的端不符")
            if p.get("device_id") and parent.status not in {"imported", "returned"}:
                raise HTTPException(409, "请先领取并导入该需求")
            if p.get("device_id"):
                allowed = {f["artifact_id"] for f in parent.files}
                if any(f["artifact_id"] not in allowed and f.get("metadata", {}).get("device_id") != p["device_id"] for f in files):
                    raise HTTPException(403, "附件不属于当前需求或设备")
        row = QuanSynTransfer(id="qs_" + secrets.token_hex(16), tenant_key=tenant, user_id=user,
            request_id=body.request_id, digest=fingerprint, direction=body.direction, target=body.target,
            reply_to=body.reply_to, text=body.text, blocks=[b.model_dump() for b in body.blocks],
            files=files, status="pending", created_at=now())
        db.add(row)
        if body.reply_to:
            parent.status = "returned"
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            previous = await db.scalar(select(QuanSynTransfer).where(
                QuanSynTransfer.tenant_key == tenant, QuanSynTransfer.user_id == user,
                QuanSynTransfer.request_id == body.request_id))
            if not previous or previous.digest != fingerprint:
                raise HTTPException(409, "提交发生冲突，请刷新后重试") from None
            return serialize(previous)
        return serialize(row)


@router.get("/transfers")
async def list_transfers(target: Literal["ios", "mac"] | None = None, pending: bool = False,
                         before: datetime | None = None, limit: int = Query(50, ge=1, le=100), p=Depends(principal)):
    filters = scope(p)
    if target:
        filters.append(QuanSynTransfer.target == target)
    if pending:
        filters.extend([QuanSynTransfer.direction == "request", QuanSynTransfer.status.in_(["pending", "claimed"])])
    if before:
        filters.append(QuanSynTransfer.created_at < before)
    async with SessionLocal() as db:
        rows = (await db.scalars(select(QuanSynTransfer).where(*filters)
            .order_by(QuanSynTransfer.created_at.desc()).limit(limit))).all()
    return {"items": [serialize(row) for row in rows], "next": rows[-1].created_at if len(rows) == limit else None}


@router.get("/transfers/{transfer_id}")
async def get_transfer(transfer_id: str, p=Depends(principal)):
    async with SessionLocal() as db:
        return serialize(await owned_row(db, transfer_id, p))


class ClaimBody(BaseModel):
    revision: int = Field(ge=1)
    claim: str = Field(min_length=32, max_length=100)


@router.post("/transfers/{transfer_id}/claim")
async def claim_transfer(transfer_id: str, body: ClaimBody, p=Depends(principal)):
    async with SessionLocal() as db:
        row = await owned_row(db, transfer_id, p)
        if row.claim_hash == digest(body.claim) and (row.status in {"imported", "returned"} or (row.status == "claimed" and row.claim_until > now())):
            return serialize(row)
        result = await db.execute(update(QuanSynTransfer).where(QuanSynTransfer.id == transfer_id,
            *scope(p), QuanSynTransfer.direction == "request", QuanSynTransfer.revision == body.revision,
            or_(QuanSynTransfer.status == "pending", (QuanSynTransfer.status == "claimed") & (QuanSynTransfer.claim_until < now()))
        ).values(status="claimed", claim_hash=digest(body.claim), claim_until=now() + timedelta(minutes=10),
                 revision=QuanSynTransfer.revision + 1))
        if result.rowcount != 1:
            raise HTTPException(409, "需求已领取或版本已改变")
        await db.commit()
        await db.refresh(row)
        return serialize(row)


@router.post("/transfers/{transfer_id}/imported")
async def confirm_import(transfer_id: str, body: ClaimBody, p=Depends(principal)):
    async with SessionLocal() as db:
        tenant, user = owner(p)
        await db.scalar(select(TenantMapping).where(TenantMapping.user_id == user).with_for_update())
        row = await owned_row(db, transfer_id, p)
        if row.status in {"imported", "returned"} and row.claim_hash == digest(body.claim):
            return serialize(row)
        result = await db.execute(update(QuanSynTransfer).where(QuanSynTransfer.id == transfer_id,
            *scope(p), QuanSynTransfer.status == "claimed", QuanSynTransfer.claim_hash == digest(body.claim),
            QuanSynTransfer.revision == body.revision, QuanSynTransfer.claim_until > now()
        ).values(status="imported", revision=QuanSynTransfer.revision + 1))
        if result.rowcount != 1:
            raise HTTPException(409, "领取凭证已失效，未确认导入")
        other_files = (await db.scalars(select(QuanSynTransfer.files).where(
            QuanSynTransfer.tenant_key == tenant, QuanSynTransfer.user_id == user,
            QuanSynTransfer.id != transfer_id))).all()
        shared = {f["artifact_id"] for files in other_files for f in files}
        try:
            for file in row.files:
                if file.get("kind") == "quansyn_file" and file["artifact_id"] not in shared:
                    directory = _owner_root(tenant, user) / file["artifact_id"]
                    # A previous attempt may have deleted bytes before its DB commit failed.
                    if directory.exists():
                        await run_in_threadpool(shutil.rmtree, directory)
        except OSError as exc:
            raise HTTPException(507, "临时附件清理失败，本地资料已保存，请重试导入确认") from exc
        row.text, row.blocks, row.files = "", [], []
        await db.commit()
        await db.refresh(row)
        return serialize(row)


@router.delete("/transfers/{transfer_id}", status_code=204)
async def delete_transfer(transfer_id: str, p=Depends(principal)):
    interactive(p)
    async with SessionLocal() as db:
        row = await owned_row(db, transfer_id, p)
        await db.delete(row)
        await db.commit()


@router.post("/files", status_code=201)
async def upload_file(request: Request, filename: str = Header(..., alias="X-File-Name"), p=Depends(principal)):
    name = unquote(filename).replace("\\", "/").split("/")[-1].strip()
    if not name or len(name) > 240 or any(ord(c) < 32 for c in name):
        raise HTTPException(422, "文件名无效")
    storage_name = name if Path(name).suffix else name + ".bin"
    try:
        with tempfile.TemporaryFile(dir=_owner_root(*owner(p))) as data:
            content_hash = hashlib.sha256()
            async for chunk in request.stream():
                await run_in_threadpool(data.write, chunk)
                content_hash.update(chunk)
            data.seek(0)
            async with SessionLocal() as db:
                await db.scalar(select(TenantMapping).where(TenantMapping.user_id == owner(p)[1]).with_for_update())
                return await run_in_threadpool(_save, tenant_key=owner(p)[0], user_id=owner(p)[1],
                    filename=storage_name, media_type="application/octet-stream", data=data,
                    kind="quansyn_file", metadata={"original_name": name, "device_id": p.get("device_id", "")},
                    idempotency_key="quansyn:" + digest(name + content_hash.hexdigest() + p.get("device_id", "")))
    except GeneratedArtifactError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(507, "文件保存失败，请稍后重试或联系管理员检查存储空间") from exc


@router.get("/files/{artifact_id}")
async def download_file(artifact_id: str, p=Depends(principal)):
    if p.get("device_id"):
        async with SessionLocal() as db:
            rows = (await db.scalars(select(QuanSynTransfer).where(*scope(p)))).all()
        if not any(f.get("artifact_id") == artifact_id for row in rows for f in row.files):
            raise HTTPException(404, "附件不在 Mac 传递范围内")
    try:
        path, receipt = await run_in_threadpool(generated_artifact_path, *owner(p), artifact_id)
    except GeneratedArtifactError as exc:
        raise HTTPException(404, "附件不可用") from exc
    return FileResponse(path, filename=receipt.get("metadata", {}).get("original_name", receipt["filename"]),
        media_type="application/octet-stream", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.post("/devices/pair", status_code=201)
async def start_pair(p=Depends(principal)):
    interactive(p)
    code = secrets.token_urlsafe(24)
    row = QuanSynDevice(id="qd_" + secrets.token_hex(16), tenant_key=owner(p)[0], user_id=owner(p)[1],
        code_hash=digest(code), expires_at=now() + timedelta(minutes=10), revoked=False)
    async with SessionLocal() as db:
        db.add(row)
        await db.commit()
    return {"id": row.id, "code": code, "expires_at": row.expires_at}


class PairBody(BaseModel):
    code: str = Field(min_length=20, max_length=100)
    sender_id: str = Field(min_length=1, max_length=128)


@router.post("/devices/exchange")
async def exchange_pair(body: PairBody):
    token = "qs_" + secrets.token_urlsafe(32)
    async with SessionLocal() as db:
        row = await db.scalar(select(QuanSynDevice).where(QuanSynDevice.code_hash == digest(body.code)))
        if not row:
            raise HTTPException(401, "配对码无效")
        result = await db.execute(update(QuanSynDevice).where(QuanSynDevice.id == row.id,
            QuanSynDevice.token_hash.is_(None), QuanSynDevice.expires_at > now(), QuanSynDevice.revoked.is_(False)
        ).values(token_hash=digest(token), sender_id=body.sender_id, expires_at=now() + timedelta(days=30)))
        if result.rowcount != 1:
            raise HTTPException(401, "配对码已使用或已过期")
        await db.commit()
    return {"device_id": row.id, "token": token, "expires_in": 30 * 86400}


@router.get("/devices")
async def list_devices(p=Depends(principal)):
    interactive(p)
    async with SessionLocal() as db:
        rows = (await db.scalars(select(QuanSynDevice).where(QuanSynDevice.tenant_key == owner(p)[0],
            QuanSynDevice.user_id == owner(p)[1], QuanSynDevice.revoked.is_(False), QuanSynDevice.token_hash.is_not(None)))).all()
    return {"items": [{"id": r.id, "sender_id": r.sender_id, "expires_at": r.expires_at} for r in rows]}


@router.delete("/devices/{device_id}", status_code=204)
async def revoke_device(device_id: str, p=Depends(principal)):
    interactive(p)
    async with SessionLocal() as db:
        result = await db.execute(update(QuanSynDevice).where(QuanSynDevice.id == device_id,
            QuanSynDevice.tenant_key == owner(p)[0], QuanSynDevice.user_id == owner(p)[1]).values(revoked=True))
        if not result.rowcount:
            raise HTTPException(404, "设备不存在")
        await db.commit()
