"""Durable Proposal -> Confirm -> Execute gateway orchestration."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from backend.db import SessionLocal
from backend.models.capability_gateway import CapabilityInvocation, CapabilityProposal
from backend.models.workflow import WorkflowDefinition
from backend.services.capability_catalog import (
    CapabilityContractError,
    describe_capability,
    execute_verified_capability,
    validate_instance,
)

PROPOSAL_TTL = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _binding_digest(
    *,
    tenant: str,
    user: str,
    session_id: str,
    request_id: str,
    capability_id: str,
    capability_version: str,
    canonical_input: dict[str, Any],
    resource_versions: dict[str, Any],
    policy_version: str,
    renderer_version: str,
) -> str:
    """Digest every authority-bearing proposal field, including CAS state."""
    return _digest({
        "tenant": tenant,
        "user": user,
        "session_id": session_id,
        "request_id": request_id,
        "capability_id": capability_id,
        "capability_version": capability_version,
        "input": canonical_input,
        "resource_versions": resource_versions,
        "policy_version": policy_version,
        "renderer_version": renderer_version,
    })


def _principal(payload: dict[str, Any]) -> tuple[str, str]:
    tenant = str(payload.get("tenant_key") or "").strip()
    user = str(payload.get("user_id") or payload.get("sub") or "").strip()
    if not tenant or not user:
        raise CapabilityContractError("authenticated tenant and user required")
    return tenant, user


def _failure(capability_id: str, code: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed", "capability_id": capability_id, "events": [],
        "receipt": None, "error": {"code": code, "message": message[:300]},
    }


async def _workflow_resource_version(
    workflow_id: str, *, tenant: str, user: str
) -> str:
    """Read the owner-scoped CAS version without depending on the HTTP layer."""
    async with SessionLocal() as db:
        row = (
            await db.execute(
                select(WorkflowDefinition).where(
                    WorkflowDefinition.id == workflow_id,
                    WorkflowDefinition.tenant_key == tenant,
                    WorkflowDefinition.created_by == user,
                    WorkflowDefinition.archived_at.is_(None),
                )
            )
        ).scalar_one_or_none()
    if row is None:
        raise CapabilityContractError("current CAS resource version unavailable")
    value = row.active_plan_id or (
        row.updated_at.isoformat() if row.updated_at is not None else ""
    )
    if not value:
        raise CapabilityContractError("current CAS resource version unavailable")
    return str(value)


async def create_capability_proposal(
    capability_id: str,
    data: dict[str, Any],
    *,
    payload: dict[str, Any],
    session_id: str,
    request_id: str,
    idempotency_key: str | None,
    resource_versions: dict[str, Any] | None = None,
    renderer_version: str = "qcp-ios@1",
) -> dict[str, Any]:
    """Persist a non-executing proposal and return its one-time opaque token."""
    capability = describe_capability(capability_id)
    if capability is None:
        return _failure(capability_id, "capability_not_found", "Capability is not allowlisted")
    if capability["implementation_status"] != "implemented":
        return _failure(capability_id, "capability_not_executable", "Capability is discovery-only")
    try:
        tenant, user = _principal(payload)
        session_id = str(session_id or "").strip()
        request_id = str(request_id or "").strip()
        renderer_version = str(renderer_version or "").strip()
        if not session_id or len(session_id) > 128:
            raise CapabilityContractError("trusted session_id required")
        if not request_id or len(request_id) > 128:
            raise CapabilityContractError("trusted request_id required")
        if not renderer_version or len(renderer_version) > 64:
            raise CapabilityContractError("renderer_version required")
        if capability["idempotency"] == "required" and not idempotency_key:
            raise CapabilityContractError("idempotency_key required")
        # Session scope is trusted Gateway context, never model/client authority.
        # Capabilities that accept a source session always receive the bound
        # confirmation session, overriding any untrusted input value.
        canonical_input = dict(data)
        properties = capability["input_schema"].get("properties") or {}
        if "source_client_session_id" in properties:
            canonical_input["source_client_session_id"] = session_id
        validate_instance(canonical_input, capability["input_schema"])
        versions = dict(resource_versions or {})
        if len(versions) > 64 or any(
            not isinstance(key, str)
            or not key
            or len(key) > 160
            or not isinstance(value, (str, int))
            or isinstance(value, bool)
            or len(str(value)) > 256
            for key, value in versions.items()
        ):
            raise CapabilityContractError("resource_versions must be a bounded string/integer map")
        derived_versions: dict[str, str] = {}
        if capability_id in {"knowledge.note.update", "knowledge.note.archive"}:
            derived_versions[str(canonical_input.get("note_id") or "")] = str(
                canonical_input.get("base_hash") or ""
            )
        elif capability_id == "knowledge.note.merge":
            derived_versions = {
                str(canonical_input.get("target_note_id") or ""): str(
                    canonical_input.get("target_base_hash") or ""
                ),
                **{
                    str(key): str(value)
                    for key, value in (canonical_input.get("source_versions") or {}).items()
                },
            }
        elif capability_id == "workflow.start":
            workflow_id = str(canonical_input.get("workflow_id") or "")
            derived_versions[workflow_id] = await _workflow_resource_version(
                workflow_id, tenant=tenant, user=user
            )
        if "" in derived_versions or any(not value for value in derived_versions.values()):
            raise CapabilityContractError("current CAS resource version unavailable")
        if any(
            key in versions and str(versions[key]) != value
            for key, value in derived_versions.items()
        ):
            raise CapabilityContractError("resource_versions conflict with canonical input or current state")
        versions.update(derived_versions)
    except CapabilityContractError as exc:
        return _failure(capability_id, "contract_invalid", str(exc))

    canonical_input = json.loads(_canonical(canonical_input))
    canonical_resource_versions = json.loads(_canonical(versions))
    policy_version = str(payload.get("knowledge_policy_version") or "unknown")
    input_digest = _binding_digest(
        tenant=tenant,
        user=user,
        session_id=session_id,
        request_id=request_id,
        capability_id=capability_id,
        capability_version=str(capability["version"]),
        canonical_input=canonical_input,
        resource_versions=canonical_resource_versions,
        policy_version=policy_version,
        renderer_version=renderer_version,
    )
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    nonce = secrets.token_urlsafe(24)
    proposal_seed = f"{tenant}:{user}:{session_id}:{request_id}:{capability_id}:{nonce}"
    proposal_id = "qcp-proposal-" + hashlib.sha256(proposal_seed.encode()).hexdigest()[:32]
    expires_at = _now() + PROPOSAL_TTL
    row = CapabilityProposal(
        id=proposal_id,
        tenant_key=tenant,
        user_id=user,
        session_id=session_id,
        request_id=request_id,
        capability_id=capability_id,
        capability_version=str(capability["version"]),
        canonical_input=canonical_input,
        input_digest=input_digest,
        resource_versions=canonical_resource_versions,
        policy_version=policy_version,
        renderer_version=renderer_version,
        idempotency_key=idempotency_key,
        token_hash=token_hash,
        nonce=nonce,
        state="PENDING",
        expires_at=expires_at,
    )
    async with SessionLocal() as db:
        db.add(row)
        await db.commit()
    event_payload = {
        "proposal_id": proposal_id,
        "confirmation_token": token,
        "capability_id": capability_id,
        "capability_version": capability["version"],
        "input": canonical_input,
        "input_digest": input_digest,
        "resource_versions": canonical_resource_versions,
        "summary": capability["description"],
        "risk": capability["risk"],
        "state": "awaiting_confirmation",
        "expires_at": expires_at.isoformat(),
        "renderer_version": renderer_version,
    }
    return {
        "status": "awaiting_confirmation",
        "capability_id": capability_id,
        "events": [{"type": "capability.proposed", "version": 1, "payload": event_payload}],
        "receipt": None,
        "error": None,
    }


async def confirm_capability_proposal(
    proposal_id: str,
    confirmation_token: str,
    *,
    payload: dict[str, Any],
    session_id: str,
) -> dict[str, Any]:
    """Atomically consume a bound token, deduplicate, execute and persist receipt."""
    try:
        tenant, user = _principal(payload)
    except CapabilityContractError as exc:
        return _failure("", "not_authenticated", str(exc))
    now = _now()
    async with SessionLocal() as db:
        async with db.begin():
            if db.bind is not None and db.bind.dialect.name == "sqlite":
                await db.execute(text("BEGIN IMMEDIATE"))
            proposal = await db.scalar(
                select(CapabilityProposal).where(CapabilityProposal.id == proposal_id).with_for_update()
            )
            if proposal is None or proposal.tenant_key != tenant or proposal.user_id != user:
                return _failure("", "confirmation_invalid", "Proposal or confirmation token is invalid")
            capability_id = proposal.capability_id
            if proposal.session_id != str(session_id or ""):
                return _failure(capability_id, "confirmation_invalid", "Confirmation session mismatch")
            if proposal.state != "PENDING" or proposal.consumed_at is not None:
                return _failure(capability_id, "confirmation_invalid", "Confirmation token already consumed")
            expires_at = proposal.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                proposal.state = "EXPIRED"
                proposal.error_code = "confirmation_invalid"
                return _failure(capability_id, "confirmation_invalid", "Confirmation token expired")
            presented_hash = hashlib.sha256(str(confirmation_token).encode()).hexdigest()
            if not hmac.compare_digest(proposal.token_hash, presented_hash):
                return _failure(capability_id, "confirmation_invalid", "Proposal or confirmation token is invalid")
            capability = describe_capability(capability_id)
            if capability is None or str(capability["version"]) != proposal.capability_version:
                proposal.state = "RECONCILE_REQUIRED"
                proposal.error_code = "capability_not_found"
                return _failure(capability_id, "capability_not_found", "Capability version is unavailable")
            current_policy = str(payload.get("knowledge_policy_version") or "unknown")
            if current_policy != proposal.policy_version:
                proposal.state = "RECONCILE_REQUIRED"
                proposal.error_code = "confirmation_invalid"
                return _failure(capability_id, "confirmation_invalid", "Policy changed; create a new proposal")
            if _binding_digest(
                tenant=proposal.tenant_key,
                user=proposal.user_id,
                session_id=proposal.session_id,
                request_id=proposal.request_id,
                capability_id=proposal.capability_id,
                capability_version=proposal.capability_version,
                canonical_input=dict(proposal.canonical_input),
                resource_versions=dict(proposal.resource_versions or {}),
                policy_version=proposal.policy_version,
                renderer_version=proposal.renderer_version,
            ) != proposal.input_digest:
                proposal.state = "RECONCILE_REQUIRED"
                proposal.error_code = "contract_invalid"
                return _failure(capability_id, "contract_invalid", "Stored proposal digest mismatch")
            key = str(proposal.idempotency_key or proposal.id)
            key_hash = hashlib.sha256(key.encode()).hexdigest()
            existing = await db.scalar(select(CapabilityInvocation).where(
                CapabilityInvocation.tenant_key == tenant,
                CapabilityInvocation.user_id == user,
                CapabilityInvocation.capability_id == capability_id,
                CapabilityInvocation.capability_version == proposal.capability_version,
                CapabilityInvocation.idempotency_key_hash == key_hash,
            ).with_for_update())
            proposal.consumed_at = now
            if existing is not None:
                proposal.receipt_id = existing.id
                if existing.input_digest != proposal.input_digest:
                    proposal.state = "RECONCILE_REQUIRED"
                    proposal.error_code = "idempotency_conflict"
                    return _failure(capability_id, "idempotency_conflict", "Idempotency key payload conflict")
                if existing.result is not None:
                    proposal.state = "VERIFIED"
                    return dict(existing.result)
                proposal.state = "APPLYING"
                return _failure(capability_id, "execution_in_progress", "Invocation is already applying")
            invocation_id = "qcp-" + hashlib.sha256(
                f"{tenant}:{user}:{capability_id}:{proposal.capability_version}:{key_hash}".encode()
            ).hexdigest()[:40]
            invocation = CapabilityInvocation(
                id=invocation_id,
                proposal_id=proposal.id,
                tenant_key=tenant,
                user_id=user,
                capability_id=capability_id,
                capability_version=proposal.capability_version,
                idempotency_key_hash=key_hash,
                input_digest=proposal.input_digest,
                state="APPLYING",
            )
            db.add(invocation)
            proposal.state = "APPLYING"
            proposal.receipt_id = invocation_id
        await db.commit()

    result = await execute_verified_capability(
        capability_id,
        dict(proposal.canonical_input),
        payload=payload,
        idempotency_key=key,
        invocation_id=invocation_id,
        resource_versions=dict(proposal.resource_versions or {}),
    )
    terminal = "VERIFIED" if result.get("status") == "completed" else "RECONCILE_REQUIRED"
    async with SessionLocal() as db:
        async with db.begin():
            stored_invocation = await db.get(CapabilityInvocation, invocation_id, with_for_update=True)
            stored_proposal = await db.get(CapabilityProposal, proposal_id, with_for_update=True)
            if stored_invocation is not None:
                stored_invocation.state = terminal
                stored_invocation.result = result
                stored_invocation.error_code = ((result.get("error") or {}).get("code"))
                stored_invocation.error_detail = ((result.get("error") or {}).get("message"))
            if stored_proposal is not None:
                stored_proposal.state = terminal
                stored_proposal.error_code = ((result.get("error") or {}).get("code"))
        await db.commit()
    return result


async def proposal_status(
    proposal_id: str, *, payload: dict[str, Any]
) -> dict[str, Any]:
    try:
        tenant, user = _principal(payload)
    except CapabilityContractError as exc:
        return _failure("", "not_authenticated", str(exc))
    async with SessionLocal() as db:
        proposal = await db.get(CapabilityProposal, proposal_id)
        if proposal is None or proposal.tenant_key != tenant or proposal.user_id != user:
            return _failure("", "capability_not_found", "Proposal not found")
        result = None
        if proposal.receipt_id:
            invocation = await db.get(CapabilityInvocation, proposal.receipt_id)
            result = invocation.result if invocation is not None else None
        return {
            "status": proposal.state.casefold(),
            "capability_id": proposal.capability_id,
            "proposal_id": proposal.id,
            "receipt_id": proposal.receipt_id,
            "result": result,
            "error": None if not proposal.error_code else {"code": proposal.error_code},
        }


async def invocation_status(
    invocation_id: str, *, payload: dict[str, Any]
) -> dict[str, Any]:
    """Return a tenant/user-scoped durable execution and receipt state."""
    try:
        tenant, user = _principal(payload)
    except CapabilityContractError as exc:
        return _failure("", "not_authenticated", str(exc))
    async with SessionLocal() as db:
        invocation = await db.get(CapabilityInvocation, invocation_id)
        if (
            invocation is None
            or invocation.tenant_key != tenant
            or invocation.user_id != user
        ):
            return _failure("", "capability_not_found", "Invocation not found")
        return {
            "status": invocation.state.casefold(),
            "capability_id": invocation.capability_id,
            "capability_version": invocation.capability_version,
            "proposal_id": invocation.proposal_id,
            "invocation_id": invocation.id,
            "result": invocation.result,
            "error": None if not invocation.error_code else {
                "code": invocation.error_code,
                "message": invocation.error_detail,
            },
        }


async def reconcile_incomplete_invocations(*, limit: int = 100) -> int:
    """Idempotently finish APPLYING rows after a process crash.

    Domain handlers receive the original idempotency key through the proposal;
    therefore a crash after the side effect but before receipt persistence
    replays the domain receipt instead of duplicating the write.
    """
    async with SessionLocal() as db:
        rows = list((await db.execute(
            select(CapabilityInvocation)
            .where(CapabilityInvocation.state == "APPLYING")
            .order_by(CapabilityInvocation.created_at)
            .limit(max(1, min(limit, 1000)))
        )).scalars().all())
    reconciled = 0
    for row in rows:
        async with SessionLocal() as db:
            invocation = await db.get(CapabilityInvocation, row.id, with_for_update=True)
            if invocation is None or invocation.state != "APPLYING":
                continue
            proposal = await db.get(CapabilityProposal, invocation.proposal_id)
            if proposal is None:
                invocation.state = "RECONCILE_REQUIRED"
                invocation.error_code = "proposal_missing"
                invocation.error_detail = "Durable proposal is missing"
                await db.commit()
                continue
            payload = {
                "tenant_key": proposal.tenant_key,
                "user_id": proposal.user_id,
                "knowledge_policy_version": proposal.policy_version,
            }
            result = await execute_verified_capability(
                proposal.capability_id,
                dict(proposal.canonical_input),
                payload=payload,
                idempotency_key=str(proposal.idempotency_key or proposal.id),
                invocation_id=invocation.id,
                resource_versions=dict(proposal.resource_versions or {}),
            )
            terminal = "VERIFIED" if result.get("status") == "completed" else "RECONCILE_REQUIRED"
            invocation.state = terminal
            invocation.result = result
            invocation.error_code = ((result.get("error") or {}).get("code"))
            invocation.error_detail = ((result.get("error") or {}).get("message"))
            proposal.state = terminal
            proposal.error_code = invocation.error_code
            await db.commit()
            reconciled += 1
    return reconciled
