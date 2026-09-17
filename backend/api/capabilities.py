"""Authenticated PCM discovery and QCP invocation endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.api.auth import require_auth
from backend.services.capability_catalog import (
    catalog_digest,
    describe_capability,
    invoke_capability,
    search_capabilities,
)
from backend.services.capability_gateway import (
    confirm_capability_proposal,
    create_capability_proposal,
    proposal_status,
)


router = APIRouter(prefix="/api/v1/capabilities", tags=["capabilities"])


class CapabilityInvokeRequest(BaseModel):
    capability_id: str = Field(..., min_length=3, max_length=160)
    input: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool | None = None
    idempotency_key: str | None = Field(None, min_length=8, max_length=160)


class CapabilityProposalRequest(BaseModel):
    capability_id: str = Field(..., min_length=3, max_length=160)
    input: dict[str, Any] = Field(default_factory=dict)
    session_id: str = Field(..., min_length=1, max_length=128)
    request_id: str = Field(..., min_length=1, max_length=128)
    idempotency_key: str | None = Field(None, min_length=8, max_length=160)
    resource_versions: dict[str, Any] = Field(default_factory=dict)
    renderer_version: str = Field("qcp-ios@1", min_length=1, max_length=64)


class CapabilityConfirmRequest(BaseModel):
    proposal_id: str = Field(..., min_length=16, max_length=64)
    confirmation_token: str = Field(..., min_length=32, max_length=256)
    session_id: str = Field(..., min_length=1, max_length=128)


@router.get("")
async def search(
    query: str = Query("", max_length=200),
    limit: int = Query(5, ge=1, le=10),
    _payload: dict[str, Any] = Depends(require_auth),
):
    return {"protocol": "qcp", "catalog_digest": catalog_digest(), "items": search_capabilities(query, limit=limit)}


@router.get("/{capability_id}")
async def describe(
    capability_id: str,
    _payload: dict[str, Any] = Depends(require_auth),
):
    capability = describe_capability(capability_id)
    if capability is None:
        raise HTTPException(status_code=404, detail={"code": "capability_not_found"})
    return capability


@router.post("/proposals")
async def propose(
    body: CapabilityProposalRequest, payload: dict[str, Any] = Depends(require_auth)
):
    return await create_capability_proposal(
        body.capability_id,
        body.input,
        payload=payload,
        session_id=body.session_id,
        request_id=body.request_id,
        idempotency_key=body.idempotency_key,
        resource_versions=body.resource_versions,
        renderer_version=body.renderer_version,
    )


@router.post("/confirm")
async def confirm(
    body: CapabilityConfirmRequest, payload: dict[str, Any] = Depends(require_auth)
):
    return await confirm_capability_proposal(
        body.proposal_id,
        body.confirmation_token,
        payload=payload,
        session_id=body.session_id,
    )


@router.get("/proposals/{proposal_id}/status")
async def status(proposal_id: str, payload: dict[str, Any] = Depends(require_auth)):
    return await proposal_status(proposal_id, payload=payload)


@router.post("/invoke")
async def invoke(body: CapabilityInvokeRequest, payload: dict[str, Any] = Depends(require_auth)):
    if body.confirmed is not None:
        return {
            "status": "failed", "capability_id": body.capability_id, "events": [],
            "receipt": None,
            "error": {
                "code": "confirmation_protocol_upgrade_required",
                "message": "confirmed is not an authorization signal; use proposals/confirm",
            },
        }
    return await invoke_capability(
        body.capability_id,
        body.input,
        payload=payload,
        idempotency_key=body.idempotency_key,
    )
