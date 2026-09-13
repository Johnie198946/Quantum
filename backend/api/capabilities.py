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


router = APIRouter(prefix="/api/v1/capabilities", tags=["capabilities"])


class CapabilityInvokeRequest(BaseModel):
    capability_id: str = Field(..., min_length=3, max_length=160)
    input: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False
    idempotency_key: str | None = Field(None, min_length=8, max_length=160)


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


@router.post("/invoke")
async def invoke(body: CapabilityInvokeRequest, payload: dict[str, Any] = Depends(require_auth)):
    return await invoke_capability(
        body.capability_id, body.input, payload=payload, confirmed=body.confirmed,
        idempotency_key=body.idempotency_key,
    )
