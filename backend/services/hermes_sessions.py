"""Owner-bound access to Hermes sessions through the local bridge."""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

import httpx
from fastapi import HTTPException

from backend.services.workflow_session_scope import require_registered_client_session

_BASE_URL = os.environ.get("HERMES_BRIDGE_OWNER_SESSION_URL", "http://host.docker.internal:9118/v1/owner-sessions")
_INTERNAL_TOKEN = os.environ.get("HERMES_BRIDGE_INTERNAL_TOKEN", "")


def _identity(payload: dict[str, Any]) -> tuple[str, str]:
    return (
        str(payload.get("tenant_key") or "public"),
        str(payload.get("user_id") or payload.get("sub") or "anonymous"),
    )


def namespaced_session_key(client_session_id: str, tenant_key: str, user_id: str) -> str:
    base = re.sub(r"^t[0-9a-f]{12}-u[0-9a-f]{12}-", "", client_session_id, count=1)
    namespace = (
        f"t{hashlib.sha256(tenant_key.encode()).hexdigest()[:12]}-"
        f"u{hashlib.sha256(user_id.encode()).hexdigest()[:12]}"
    )
    candidate = f"{namespace}-{base}"
    if len(candidate) <= 100:
        return candidate
    lane = base.split("-", 1)[0][:24] or "session"
    digest = hashlib.sha256(base.encode()).hexdigest()[:40]
    return f"{namespace}-{lane}-h{digest}"


async def owner_session_action(
    action: str,
    data: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    client_session_id = str(data.get("client_session_id") or "")
    await require_registered_client_session(payload, client_session_id)
    tenant_key, user_id = _identity(payload)
    session_key = namespaced_session_key(client_session_id, tenant_key, user_id)
    if not _INTERNAL_TOKEN:
        raise HTTPException(status_code=503, detail={"code": "hermes_bridge_internal_token_missing"})
    endpoint = "resolve" if action in {"list", "open"} else action
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{_BASE_URL}/{endpoint}",
                json={"session_key": session_key},
                headers={
                    "X-Hermes-Internal-Token": _INTERNAL_TOKEN,
                    "X-Tenant-ID": tenant_key,
                    "X-User-ID": user_id,
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "hermes_bridge_unavailable"}) from exc
    if response.status_code == 404 and action == "list":
        return {"sessions": [], "count": 0}
    if response.status_code >= 400:
        detail: Any
        try:
            detail = response.json().get("detail")
        except Exception:
            detail = "hermes_bridge_error"
        raise HTTPException(status_code=response.status_code, detail=detail)
    result = response.json()
    if action == "list":
        return {"sessions": [result], "count": 1}
    return result
