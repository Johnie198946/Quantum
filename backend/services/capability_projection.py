"""Project capability truth from server facts only."""

from contextvars import ContextVar, Token
from datetime import datetime, timedelta, timezone
from typing import Any


_RUNTIME_ROUTING_SCOPE: ContextVar[dict[str, Any] | None] = ContextVar(
    "quantum_runtime_routing_scope", default=None
)

_RUNTIME_CAPABILITY_SELECTION: ContextVar[dict[str, Any] | None] = ContextVar(
    "quantum_runtime_capability_selection", default=None
)


def set_runtime_routing_scope(scope: dict[str, Any]) -> Token:
    """Bind server-authorized routing scope to the current Hermes request."""
    return _RUNTIME_ROUTING_SCOPE.set(dict(scope))


def get_runtime_routing_scope() -> dict[str, Any]:
    return dict(_RUNTIME_ROUTING_SCOPE.get() or {})


def reset_runtime_routing_scope(token: Token) -> None:
    _RUNTIME_ROUTING_SCOPE.reset(token)


def bind_runtime_capability_selection(
    *,
    skill_id: str | None,
    agent_id: str | None,
    decision_id: str,
    catalog_version: str,
    policy_version: str,
) -> None:
    """Expose one validated JEV result to deterministic execution guards.

    This carries no authority: QCP's routing scope and tool handlers remain the
    permission source. The value is overwritten on every pre-model decision and
    is automatically discarded with the request ContextVar context.
    """
    _RUNTIME_CAPABILITY_SELECTION.set({
        "skill_id": str(skill_id or "") or None,
        "agent_id": str(agent_id or "") or None,
        "decision_id": str(decision_id),
        "catalog_version": str(catalog_version),
        "policy_version": str(policy_version),
        "validated": True,
    })


def get_runtime_capability_selection() -> dict[str, Any]:
    return dict(_RUNTIME_CAPABILITY_SELECTION.get() or {})


def clear_runtime_capability_selection() -> None:
    """Clear the request-local JEV projection at a run boundary."""
    _RUNTIME_CAPABILITY_SELECTION.set(None)


def project_capability(*, connected: bool, checked_at: datetime | None, ttl_seconds: int, now: datetime | None = None) -> dict[str, object]:
    current = now or datetime.now(timezone.utc)
    if checked_at is None or checked_at.tzinfo is None:
        status = "UNCONNECTED"
    else:
        status = "CONNECTED" if connected and checked_at + timedelta(seconds=ttl_seconds) > current else "UNCONNECTED"
    return {"status": status, "truth": "LIVE" if status == "CONNECTED" else "UNCONNECTED", "checked_at": checked_at.isoformat() if checked_at else None}


def project_plan_capability(
    *,
    compiler_status: str,
    checked_at: datetime | None,
    ttl_seconds: int,
    now: datetime | None = None,
) -> dict[str, object]:
    """Project readiness from a server compiler check, never from model DSL fields."""
    return project_capability(
        connected=compiler_status == "compiled",
        checked_at=checked_at,
        ttl_seconds=ttl_seconds,
        now=now,
    )
