"""Project capability truth from server facts only."""

from contextvars import ContextVar, Token
from datetime import datetime, timedelta, timezone
from typing import Any


_RUNTIME_ROUTING_SCOPE: ContextVar[dict[str, Any] | None] = ContextVar(
    "quantum_runtime_routing_scope", default=None
)


def set_runtime_routing_scope(scope: dict[str, Any]) -> Token:
    """Bind server-authorized routing scope to the current Hermes request."""
    return _RUNTIME_ROUTING_SCOPE.set(dict(scope))


def get_runtime_routing_scope() -> dict[str, Any]:
    return dict(_RUNTIME_ROUTING_SCOPE.get() or {})


def reset_runtime_routing_scope(token: Token) -> None:
    _RUNTIME_ROUTING_SCOPE.reset(token)


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
