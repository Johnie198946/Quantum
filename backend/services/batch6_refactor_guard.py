"""Emergency execution kill switch for the Batch 6 structural refactor.

The switch blocks *new* workflow/QWS execution while leaving read, cancel, and
status paths available for recovery.  It does not select a second implementation
or duplicate a state machine.  Normal behavior is unchanged unless the explicit
environment variable is truthy.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from fastapi import HTTPException

BATCH6_KILL_SWITCH_ENV = "AI_LAB_BATCH6_EXECUTION_KILL_SWITCH"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def batch6_execution_killed(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return str(source.get(BATCH6_KILL_SWITCH_ENV, "")).strip().lower() in _TRUTHY


def require_batch6_execution_enabled(component: str) -> None:
    if batch6_execution_killed():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "batch6_execution_kill_switch",
                "component": component,
                "retryable": True,
            },
        )
