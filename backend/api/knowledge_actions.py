"""Proposal ledger and idempotent commit protocol for local-first knowledge actions."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import require_auth
from backend.db import SessionLocal
from backend.models.knowledge_action import KnowledgeActionExecution
from backend.services.knowledge_action_capability import (
    KnowledgeActionDenied,
    canonical_digest,
    verify_knowledge_action_capability,
)


router = APIRouter(
    prefix="/api/v1/me/knowledge-actions", tags=["knowledge-actions"]
)


class KnowledgeActionCommitRequest(BaseModel):
    capability: str = Field(..., min_length=32, max_length=8192)
    action_digest: str = Field(..., min_length=64, max_length=64)
    result_digest: str = Field(..., min_length=64, max_length=64)
    result_note_ids: list[str] = Field(default_factory=list, max_length=64)
    status: Literal["local_applied", "synced", "sync_pending", "failed"]
    error_code: str | None = Field(None, max_length=80)


class KnowledgeActionDiscardRequest(BaseModel):
    capability: str = Field(..., min_length=32, max_length=8192)
    action_digest: str = Field(..., min_length=64, max_length=64)


class KnowledgeActionResumeRequest(BaseModel):
    action_digest: str = Field(..., min_length=64, max_length=64)
    result_digest: str = Field(..., min_length=64, max_length=64)
    result_note_ids: list[str] = Field(default_factory=list, max_length=64)
    status: Literal["sync_pending", "synced"]
    error_code: str | None = Field(None, max_length=80)


def _validated_local_notes(local_notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from backend.api.chat import LocalNoteContext
    from backend.services.capability_catalog import CapabilityContractError
    from pydantic import ValidationError

    try:
        notes = [LocalNoteContext.model_validate(item).model_dump() for item in local_notes]
    except ValidationError as exc:
        raise CapabilityContractError("invalid local note snapshot") from exc
    if len(notes) > 17 or sum(len(note["markdown"]) for note in notes) > 120_000:
        raise CapabilityContractError("local note snapshot exceeds bounds")
    if len({note["id"] for note in notes}) != len(notes):
        raise CapabilityContractError("duplicate local note identity")
    for note in notes:
        if note["content_hash"] != hashlib.sha256(note["markdown"].encode()).hexdigest():
            raise CapabilityContractError("local note version mismatch")
    return notes


class KnowledgeMergePreviewRequest(BaseModel):
    target_note_id: str = Field(..., min_length=1, max_length=128)
    source_note_id: str = Field(..., min_length=1, max_length=128)
    local_notes: list[dict[str, Any]] = Field(..., min_length=2, max_length=2)


@router.post("/merge-preview")
def preview_note_merge(body: KnowledgeMergePreviewRequest, payload: dict[str, Any] = Depends(require_auth)):
    """Read-only local snapshot comparison; creates neither a proposal nor a write."""
    from backend.services.capability_catalog import CapabilityContractError
    from backend.services.knowledge_action_capability import note_merge_preview

    try:
        notes = _validated_local_notes(body.local_notes)
        by_id = {note["id"]: note for note in notes}
        if (body.target_note_id == body.source_note_id
                or set(by_id) != {body.target_note_id, body.source_note_id}
                or any(note["archived"] for note in notes)):
            raise CapabilityContractError("preview requires two distinct active snapshots")
        return note_merge_preview(by_id[body.target_note_id], by_id[body.source_note_id])
    except CapabilityContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def propose_local_note_capability(
    capability_id: str, data: dict[str, Any], *, local_notes: list[dict[str, Any]],
    payload: dict[str, Any], session_id: str, request_id: str,
) -> dict[str, Any]:
    """Use the chat action ledger and executor for an explicit PCM button intent."""
    from backend.api.chat import _authorize_knowledge_action_event
    from backend.services.capability_catalog import CapabilityContractError
    from backend.services.knowledge_action_capability import note_capability_step

    step = note_capability_step(capability_id, data)
    if step is None:
        raise CapabilityContractError("local_notes require a personal note capability")
    notes = _validated_local_notes(local_notes)
    by_id = {note["id"]: note for note in notes}
    target = step["target_note_id"]
    sources = step["source_note_ids"]
    referenced = ({target} if target else set()) | set(sources)
    if len(by_id) != len(notes) or set(by_id) != referenced or target in sources:
        raise CapabilityContractError("local note targets must match the reviewed snapshot")
    if step["kind"] == "merge_notes" and not 1 <= len(sources) <= 16:
        raise CapabilityContractError("merge requires explicit sources")
    for note in notes:
        digest = hashlib.sha256(note["markdown"].encode()).hexdigest()
        expected = (step["original_content_hash"] if note["id"] == target
                    else step["source_content_hashes"].get(note["id"]))
        if note["content_hash"] != digest or (expected is not None and expected != digest):
            raise CapabilityContractError("local note version mismatch")
        if note["archived"] != (step["kind"] == "restore_note"):
            raise CapabilityContractError("local note lifecycle conflict")
    if target:
        step["original_content_hash"] = by_id[target]["content_hash"]
        step["title"] = by_id[target]["title"]
        step["tags"] = by_id[target]["tags"]
    if len(str(step.get("markdown") or "")) > 120_000:
        raise CapabilityContractError("revised note exceeds bounds")
    labels = {"archive_note": "归档笔记", "restore_note": "恢复笔记", "merge_notes": "合并笔记",
              "update_note": "更新笔记", "create_note": "新建笔记"}
    event = {
        "type": "knowledge_action_draft", "action_id": "ka-" + uuid.uuid4().hex,
        "summary": labels[step["kind"]], "steps": [step],
        "before_preview": "\n\n".join(note["markdown"] for note in notes)[:2000],
        "after_preview": str(step.get("markdown") or "内容保留，可在归档中恢复。")[:4000],
        "markdown_diff": "", "risk_level": "high" if sources else "medium",
        "suggested_navigation": {"destination": "knowledge_home"},
        "confirmation_status": "unsigned",
    }
    authorized = await _authorize_knowledge_action_event(
        event, payload=payload, session_id=session_id, request_id=request_id,
        policy_version=str(payload.get("knowledge_policy_version") or "unknown"),
        client_context={"local_notes": notes},
    )
    return {"status": "awaiting_confirmation", "capability_id": capability_id,
            "events": [{"type": "knowledge_action_draft", "version": 1,
                        "renderer": "knowledge_action", "renderer_version": 1,
                        "payload": authorized}], "receipt": None, "error": None}


def _identity(payload: dict[str, Any]) -> tuple[str, str]:
    return (
        str(payload.get("tenant_key") or ""),
        str(payload.get("user_id") or payload.get("sub") or ""),
    )


def _capability_digest(capability: str) -> str:
    return hashlib.sha256(capability.encode()).hexdigest()


async def persist_knowledge_action_proposal(
    *,
    tenant_key: str,
    user_id: str,
    session_id: str,
    request_id: str,
    policy_version: str,
    event: dict[str, Any],
    capability: str,
    action_hash: str,
    vault_revision: str,
) -> None:
    """Persist without body text; races converge on the tenant/user/action unique key."""
    action_id = str(event.get("action_id") or "")
    if not action_id:
        raise ValueError("knowledge action event missing action_id")
    steps = event.get("steps") if isinstance(event.get("steps"), list) else []
    target_ids = {
        str(step.get("target_note_id"))
        for step in steps
        if isinstance(step, dict) and step.get("target_note_id")
    }
    row = KnowledgeActionExecution(
        id=uuid.uuid4().hex,
        tenant_key=tenant_key,
        owner_user_id=user_id,
        action_id=action_id,
        session_id=session_id,
        request_id=request_id,
        policy_version=policy_version,
        action_digest=action_hash,
        capability_digest=_capability_digest(capability),
        vault_revision=vault_revision,
        status="proposed",
        operation_count=len(steps),
        target_count=len(target_ids),
    )
    async with SessionLocal() as db:
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await db.scalar(
                select(KnowledgeActionExecution).where(
                    KnowledgeActionExecution.tenant_key == tenant_key,
                    KnowledgeActionExecution.owner_user_id == user_id,
                    KnowledgeActionExecution.action_id == action_id,
                )
            )
            if existing is None or existing.action_digest != action_hash:
                raise ValueError("knowledge action id collision")


async def _owned_row(
    db: AsyncSession, tenant_key: str, user_id: str, action_id: str, *, lock: bool = False
) -> KnowledgeActionExecution:
    statement = select(KnowledgeActionExecution).where(
            KnowledgeActionExecution.tenant_key == tenant_key,
            KnowledgeActionExecution.owner_user_id == user_id,
            KnowledgeActionExecution.action_id == action_id,
        )
    if lock:
        statement = statement.with_for_update()
    row = await db.scalar(statement)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "action_not_found"})
    return row


def _verified_claims(
    capability: str, action_id: str, tenant_key: str, user_id: str, digest: str
) -> dict[str, Any]:
    try:
        claims = verify_knowledge_action_capability(capability)
    except KnowledgeActionDenied as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code}) from exc
    if (
        claims.get("tenant_key") != tenant_key
        or claims.get("user_id") != user_id
        or claims.get("action_id") != action_id
        or claims.get("action_hash") != digest
    ):
        raise HTTPException(status_code=403, detail={"code": "knowledge_action_scope_denied"})
    return claims


def _response(row: KnowledgeActionExecution) -> dict[str, Any]:
    return {
        "action_id": row.action_id,
        "status": row.status,
        "action_digest": row.action_digest,
        "result_digest": row.result_digest,
        "result_note_ids": row.result_note_ids or [],
        "error_code": row.error_code,
        "updated_at": row.updated_at,
    }


@router.get("/{action_id}")
async def get_knowledge_action(
    action_id: str,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    tenant_key, user_id = _identity(payload)
    async with SessionLocal() as db:
        return _response(await _owned_row(db, tenant_key, user_id, action_id))


@router.post("/{action_id}/commit")
async def commit_knowledge_action(
    action_id: str,
    body: KnowledgeActionCommitRequest,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    tenant_key, user_id = _identity(payload)
    claims = _verified_claims(
        body.capability, action_id, tenant_key, user_id, body.action_digest
    )
    # The result identity excludes transport status so sync_pending may later
    # advance to synced without becoming a conflicting payload.
    result_payload = {"result_note_ids": body.result_note_ids}
    if canonical_digest(result_payload) != body.result_digest:
        raise HTTPException(status_code=422, detail={"code": "result_digest_mismatch"})
    async with SessionLocal() as db:
        row = await _owned_row(db, tenant_key, user_id, action_id, lock=True)
        if row.action_digest != body.action_digest:
            raise HTTPException(status_code=409, detail={"code": "action_payload_conflict"})
        if row.capability_digest != _capability_digest(body.capability):
            raise HTTPException(status_code=409, detail={"code": "capability_replay_conflict"})
        if row.vault_revision and claims.get("vault_revision") != row.vault_revision:
            raise HTTPException(status_code=409, detail={"code": "vault_revision_conflict"})
        if row.result_digest:
            if row.result_digest != body.result_digest:
                raise HTTPException(status_code=409, detail={"code": "action_result_conflict"})
            if row.status in {"local_applied", "sync_pending", "failed"} and body.status == "synced":
                row.status = "synced"
                row.error_code = None
                await db.commit()
                await db.refresh(row)
            return _response(row)
        row.status = body.status
        row.result_digest = body.result_digest
        row.result_note_ids = body.result_note_ids
        row.error_code = body.error_code
        await db.commit()
        await db.refresh(row)
        return _response(row)


@router.post("/{action_id}/discard")
async def discard_knowledge_action(
    action_id: str,
    body: KnowledgeActionDiscardRequest,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    tenant_key, user_id = _identity(payload)
    _verified_claims(body.capability, action_id, tenant_key, user_id, body.action_digest)
    async with SessionLocal() as db:
        row = await _owned_row(db, tenant_key, user_id, action_id, lock=True)
        if row.action_digest != body.action_digest:
            raise HTTPException(status_code=409, detail={"code": "action_payload_conflict"})
        if row.status in {"local_applied", "synced", "sync_pending"}:
            raise HTTPException(status_code=409, detail={"code": "action_already_applied"})
        row.status = "discarded"
        await db.commit()
        await db.refresh(row)
        return _response(row)


@router.post("/{action_id}/resume-sync")
async def resume_knowledge_action_sync(
    action_id: str,
    body: KnowledgeActionResumeRequest,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Resume only the sync ledger after a local transaction survived app restart.

    This endpoint cannot alter the proposal or note content. JWT ownership, the
    immutable action digest and the stable local result IDs must all match.
    """
    tenant_key, user_id = _identity(payload)
    if canonical_digest({"result_note_ids": body.result_note_ids}) != body.result_digest:
        raise HTTPException(status_code=422, detail={"code": "result_digest_mismatch"})
    async with SessionLocal() as db:
        row = await _owned_row(db, tenant_key, user_id, action_id, lock=True)
        if row.action_digest != body.action_digest:
            raise HTTPException(status_code=409, detail={"code": "action_payload_conflict"})
        if row.status == "discarded":
            raise HTTPException(status_code=409, detail={"code": "action_discarded"})
        if row.result_digest and row.result_digest != body.result_digest:
            raise HTTPException(status_code=409, detail={"code": "action_result_conflict"})
        if row.status == "synced":
            return _response(row)
        row.result_digest = body.result_digest
        row.result_note_ids = body.result_note_ids
        row.status = body.status
        row.error_code = body.error_code
        await db.commit()
        await db.refresh(row)
        return _response(row)
