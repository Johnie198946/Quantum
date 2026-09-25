"""Authenticated private document upload, status, text, and original download."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

from backend.api.auth import require_auth
from backend.db import SessionLocal
from backend.models.knowledge_contribution import KnowledgeContributionOutbox
from backend.services.document_sources import (
    DocumentSourceError,
    MAX_DOCUMENT_BYTES,
    document_original_path,
    document_text,
    read_document_receipt,
    save_document_source,
    update_document_receipt,
)
from backend.services.generated_artifacts import (
    GeneratedArtifactError,
    generated_artifact_path,
    read_generated_artifact,
)
from backend.services.knowledge_candidate_ingest import enqueue_and_schedule
from backend.services.knowledge_contribution import (
    ContributionCandidate,
    enqueue_contribution,
)
from backend.services.voice import VoiceService

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
_voice_service: VoiceService | None = None


def _get_voice_service() -> VoiceService:
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceService()
    return _voice_service


def _identity(payload: dict) -> tuple[str, str]:
    return str(payload.get("tenant_key") or ""), str(
        payload.get("user_id") or payload.get("sub") or ""
    )


def _error(exc: DocumentSourceError) -> HTTPException:
    status = (
        404
        if exc.code == "document_not_found"
        else 413
        if exc.code == "document_too_large"
        else 422
    )
    return HTTPException(
        status_code=status, detail={"code": exc.code, "message": str(exc)}
    )


async def _with_current_contribution_status(
    receipt: dict, tenant_key: str, user_id: str
) -> dict:
    event_id = str(receipt.get("contribution_event_id") or "")
    if not event_id:
        return receipt
    async with SessionLocal() as db:
        event = await db.get(KnowledgeContributionOutbox, event_id)
    if event and (event.tenant_key, event.user_id) == (tenant_key, user_id):
        return {
            **receipt,
            "contribution_status": event.status,
            "contribution_error": event.last_error,
        }
    return receipt


@router.post("", status_code=201)
async def upload_document(
    request: Request,
    filename: str = Header(..., alias="X-File-Name"),
    content_hash: str = Header("", alias="X-Content-Hash"),
    file_opt_out: bool = Header(False, alias="X-File-Opt-Out"),
    payload: dict = Depends(require_auth),
):
    try:
        length = int(request.headers.get("content-length") or 0)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_content_length", "message": "上传长度无效"},
        ) from exc
    if length > MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"code": "document_too_large", "message": "文档超过 25 MB 上限"},
        )
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_DOCUMENT_BYTES:
            raise HTTPException(
                status_code=413,
                detail={"code": "document_too_large", "message": "文档超过 25 MB 上限"},
            )
        data.extend(chunk)
    tenant_key, user_id = _identity(payload)
    try:
        receipt = save_document_source(
            tenant_key=tenant_key,
            user_id=user_id,
            filename=unquote(filename),
            content_type=request.headers.get("content-type", ""),
            data=bytes(data),
            expected_hash=content_hash,
            file_opt_out=file_opt_out,
        )
    except DocumentSourceError as exc:
        raise _error(exc) from exc
    if receipt["status"] == "ready":
        candidate = ContributionCandidate(
            tenant_key=tenant_key,
            user_id=user_id,
            source_surface="ios",
            source_kind="uploaded_file",
            source_id=receipt["source_id"],
            source_revision=receipt["source_revision"],
            content_hash=receipt["content_hash"],
            source_changed_at=datetime.fromisoformat(receipt["created_at"]),
            file_opt_out=file_opt_out,
        )
        try:
            if file_opt_out:
                await enqueue_contribution(candidate)
                updates = {"contribution_status": "excluded"}
            else:
                text, _ = document_text(tenant_key, user_id, receipt["source_id"])
                contribution = await enqueue_and_schedule(
                    candidate, source_content=text
                )
                if contribution is None:
                    updates = {"contribution_status": "denied"}
                elif (
                    contribution.get("schedule_status") == "scheduled"
                    and contribution.get("event_id")
                    and contribution.get("run_id")
                ):
                    updates = {
                        "contribution_status": "queued",
                        "contribution_event_id": contribution["event_id"],
                        "contribution_run_id": contribution["run_id"],
                    }
                elif contribution.get("event_id"):
                    updates = {
                        "contribution_status": "pending",
                        "contribution_event_id": contribution["event_id"],
                        "contribution_error": str(
                            contribution.get("schedule_error") or "调度回执待确认"
                        )[:240],
                    }
                else:
                    updates = {
                        "contribution_status": "failed",
                        "contribution_error": "贡献入队回执无效",
                    }
            receipt = update_document_receipt(
                tenant_key, user_id, receipt["source_id"], **updates
            )
        except (
            Exception
        ) as exc:  # Contribution is independent from the private PPT flow.
            receipt = update_document_receipt(
                tenant_key,
                user_id,
                receipt["source_id"],
                contribution_status="failed",
                contribution_error=str(exc)[:240],
            )
    return receipt

def _generated_error(exc: GeneratedArtifactError) -> HTTPException:
    status = 404 if exc.code == "artifact_not_found" else 409
    return HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)})


@router.get("/generated/{artifact_id}")
async def get_generated_artifact(artifact_id: str, payload: dict = Depends(require_auth)):
    try:
        return read_generated_artifact(*_identity(payload), artifact_id)
    except GeneratedArtifactError as exc:
        raise _generated_error(exc) from exc


@router.get("/generated/{artifact_id}/download")
async def download_generated_artifact(artifact_id: str, payload: dict = Depends(require_auth)):
    try:
        path, receipt = generated_artifact_path(*_identity(payload), artifact_id)
    except GeneratedArtifactError as exc:
        raise _generated_error(exc) from exc
    return FileResponse(
        path,
        media_type=receipt["media_type"],
        filename=receipt["filename"],
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-SHA256": receipt["content_hash"],
        },
    )


@router.post("/voice/transcriptions")
async def transcribe_voice(
    request: Request,
    payload: dict = Depends(require_auth),
):
    tenant_key, user_id = _identity(payload)
    if not tenant_key or not user_id:
        raise HTTPException(status_code=401, detail={"code": "invalid_identity"})
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    formats = {
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/webm": "webm",
        "audio/m4a": "m4a",
        "audio/mp4": "m4a",
    }
    if content_type not in formats:
        raise HTTPException(status_code=415, detail={"code": "unsupported_audio_type"})
    audio = bytearray()
    async for chunk in request.stream():
        if len(audio) + len(chunk) > MAX_DOCUMENT_BYTES:
            raise HTTPException(status_code=413, detail={"code": "audio_too_large"})
        audio.extend(chunk)
    if not audio:
        raise HTTPException(status_code=422, detail={"code": "empty_audio"})
    try:
        text = await _get_voice_service().transcribe(bytes(audio), formats[content_type])
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "transcription_unavailable", "message": str(exc)},
        ) from exc
    if not text:
        raise HTTPException(status_code=422, detail={"code": "empty_transcription"})
    return {"text": text, "language": "zh", "status": "completed"}




@router.get("/{source_id}")
async def get_document(source_id: str, payload: dict = Depends(require_auth)):
    tenant_key, user_id = _identity(payload)
    try:
        receipt = read_document_receipt(tenant_key, user_id, source_id)
    except DocumentSourceError as exc:
        raise _error(exc) from exc
    return await _with_current_contribution_status(receipt, tenant_key, user_id)


@router.get("/{source_id}/text", response_class=PlainTextResponse)
async def get_document_text(source_id: str, payload: dict = Depends(require_auth)):
    try:
        text, _ = document_text(*_identity(payload), source_id)
        return PlainTextResponse(text, headers={"Cache-Control": "private, no-store"})
    except DocumentSourceError as exc:
        raise _error(exc) from exc


@router.get("/{source_id}/download")
async def download_document(source_id: str, payload: dict = Depends(require_auth)):
    try:
        path, receipt = document_original_path(*_identity(payload), source_id)
    except DocumentSourceError as exc:
        raise _error(exc) from exc
    return FileResponse(
        path,
        media_type=receipt["content_type"],
        filename=receipt["filename"],
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-SHA256": receipt["content_hash"],
            "X-Source-Revision": str(receipt["source_revision"]),
        },
    )
