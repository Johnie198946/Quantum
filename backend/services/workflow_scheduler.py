"""Durable scanner for server-owned Workflow schedules.

The scanner never builds Bridge payloads and never calls ``/v1/chat``.  A due
row is re-authorized through the shared workflow start transaction, which queues
an ordinary WorkflowExecution for the existing worker.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.workflow import (
    WorkflowDefinition,
    WorkflowPlanVersion,
    WorkflowSchedule,
)
from backend.services.workflow_execution_start import (
    WorkflowStartError,
    create_workflow_execution,
    validate_workflow_execution_authority,
)

logger = logging.getLogger(__name__)

SCHEDULE_CONTRACT_ID = "workflow.schedule"
SCHEDULE_CONTRACT_VERSION = 1
SCHEDULE_HANDLER_ID = "workflow_executor.dispatch"
SCHEDULE_HANDLER_VERSION = 1
SCAN_INTERVAL_SECONDS = max(
    1, int(os.environ.get("WORKFLOW_SCHEDULE_SCAN_INTERVAL", "30"))
)
_scheduler: AsyncIOScheduler | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def validate_cron(cron_expression: str, timezone_name: str) -> None:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("unknown schedule timezone") from exc
    try:
        CronTrigger.from_crontab(cron_expression, timezone=zone)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid schedule cron expression") from exc


def compute_next_run(
    cron_expression: str,
    timezone_name: str,
    *,
    base: datetime | None = None,
) -> datetime:
    """Return the next wall-clock cron occurrence as an aware UTC datetime."""
    validate_cron(cron_expression, timezone_name)
    zone = ZoneInfo(timezone_name)
    reference = _aware_utc(base or utcnow()).astimezone(zone)
    # CronTrigger is the normative DST behavior: repeated wall-clock instants
    # fire once per fold, while the supplied base instant is strictly consumed.
    trigger = CronTrigger.from_crontab(cron_expression, timezone=zone)
    value = trigger.get_next_fire_time(None, reference.replace(microsecond=0))
    if value is not None and value <= reference:
        value = trigger.get_next_fire_time(value, reference)
    if value is None:
        raise ValueError("schedule cron has no next occurrence")
    return value.astimezone(timezone.utc)


def schedule_request_key(schedule: WorkflowSchedule, scheduled_for: datetime) -> str:
    instant = _aware_utc(scheduled_for).strftime("%Y%m%dT%H%M%S.%fZ")
    return (
        f"workflow-schedule:{schedule.id}:{instant}:"
        f"{schedule.plan_id}:{schedule.activation_revision}"
    )


def schedule_out(
    row: WorkflowSchedule, *, execution_status: str | None = None
) -> dict:
    return {
        "id": row.id,
        "workflow_id": row.workflow_id,
        "plan_id": row.plan_id,
        "plan_hash": row.plan_hash,
        "activation_revision": row.activation_revision,
        "cron": row.cron_expression,
        "timezone": row.timezone,
        "enabled": row.enabled,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "last_scheduled_for": (
            row.last_scheduled_for.isoformat() if row.last_scheduled_for else None
        ),
        "last_triggered_at": (
            row.last_triggered_at.isoformat() if row.last_triggered_at else None
        ),
        "last_execution_id": row.last_execution_id,
        "last_result": execution_status or row.last_result,
        "last_error": row.last_error,
        "contract": {"id": row.contract_id, "version": row.contract_version},
        "handler": {"id": row.handler_id, "version": row.handler_version},
        "version": row.version,
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def validate_schedule_binding(
    db,
    *,
    workflow: WorkflowDefinition,
    tenant_key: str,
    owner_user_id: str,
) -> WorkflowPlanVersion:
    """Validate and return the exact approved plan captured by a new schedule."""
    plan, _ = await validate_workflow_execution_authority(
        db,
        workflow=workflow,
        tenant_key=tenant_key,
        owner_user_id=owner_user_id,
    )
    return plan


async def create_schedule(
    db,
    *,
    workflow: WorkflowDefinition,
    tenant_key: str,
    owner_user_id: str,
    cron_expression: str,
    timezone_name: str,
    enabled: bool,
    reference_time: datetime | None = None,
) -> WorkflowSchedule:
    validate_cron(cron_expression, timezone_name)
    plan = await validate_schedule_binding(
        db,
        workflow=workflow,
        tenant_key=tenant_key,
        owner_user_id=owner_user_id,
    )
    row = WorkflowSchedule(
        id=f"wfsched_{uuid.uuid4().hex}",
        tenant_key=tenant_key,
        owner_user_id=owner_user_id,
        workflow_id=workflow.id,
        plan_id=plan.id,
        plan_hash=plan.content_hash,
        activation_revision=plan.activation_revision,
        cron_expression=cron_expression,
        timezone=timezone_name,
        enabled=enabled,
        next_run_at=(
            compute_next_run(
                cron_expression, timezone_name, base=reference_time or utcnow()
            )
            if enabled
            else None
        ),
        contract_id=SCHEDULE_CONTRACT_ID,
        contract_version=SCHEDULE_CONTRACT_VERSION,
        handler_id=SCHEDULE_HANDLER_ID,
        handler_version=SCHEDULE_HANDLER_VERSION,
    )
    db.add(row)
    return row


def _assert_schedule_contract(schedule: WorkflowSchedule) -> None:
    if (
        schedule.contract_id != SCHEDULE_CONTRACT_ID
        or schedule.contract_version != SCHEDULE_CONTRACT_VERSION
        or schedule.handler_id != SCHEDULE_HANDLER_ID
        or schedule.handler_version != SCHEDULE_HANDLER_VERSION
    ):
        raise WorkflowStartError(409, "workflow_schedule_contract_mismatch")


async def fire_schedule(schedule_id: str, *, observed_at: datetime | None = None) -> None:
    """Fire one due schedule in an isolated transaction and record its result."""
    observed_at = _aware_utc(observed_at or utcnow())
    async with SessionLocal() as db:
        schedule = (
            await db.execute(
                select(WorkflowSchedule)
                .where(WorkflowSchedule.id == schedule_id)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if (
            schedule is None
            or not schedule.enabled
            or schedule.next_run_at is None
            or _aware_utc(schedule.next_run_at) > observed_at
        ):
            return

        scheduled_for = _aware_utc(schedule.next_run_at)
        schedule.last_scheduled_for = scheduled_for
        schedule.last_triggered_at = observed_at
        # Advance from the later of the due instant and current observation.  This
        # avoids a restart causing an unbounded catch-up storm.
        schedule.next_run_at = compute_next_run(
            schedule.cron_expression,
            schedule.timezone,
            base=max(scheduled_for, observed_at),
        )
        try:
            _assert_schedule_contract(schedule)
            workflow = await db.get(WorkflowDefinition, schedule.workflow_id)
            if workflow is None:
                raise WorkflowStartError(409, "workflow_schedule_workflow_missing")
            execution, _, _ = await create_workflow_execution(
                db,
                workflow=workflow,
                tenant_key=schedule.tenant_key,
                owner_user_id=schedule.owner_user_id,
                request_key=schedule_request_key(schedule, scheduled_for),
                expected_plan_id=schedule.plan_id,
                expected_plan_hash=schedule.plan_hash,
                expected_activation_revision=schedule.activation_revision,
                trigger_schedule_id=schedule.id,
                scheduled_for=scheduled_for,
            )
            schedule.last_execution_id = execution.id
            schedule.last_result = "queued"
            schedule.last_error = None
        except Exception as exc:
            schedule.last_result = (
                "skipped_active"
                if isinstance(exc, WorkflowStartError)
                and "已有活动执行" in exc.detail
                else "error"
            )
            schedule.last_error = str(exc)[:2000]
            logger.warning(
                "workflow schedule trigger failed",
                extra={"schedule_id": schedule.id, "error": schedule.last_error},
            )
        await db.commit()


async def scan_due_schedules(*, observed_at: datetime | None = None) -> None:
    """Scan due ids, isolating every schedule in its own transaction."""
    observed_at = _aware_utc(observed_at or utcnow())
    try:
        async with SessionLocal() as db:
            ids = list(
                (
                    await db.execute(
                        select(WorkflowSchedule.id).where(
                            WorkflowSchedule.enabled.is_(True),
                            WorkflowSchedule.next_run_at.is_not(None),
                            WorkflowSchedule.next_run_at <= observed_at,
                        )
                    )
                ).scalars().all()
            )
    except Exception:
        logger.exception("workflow schedule scan failed")
        return
    for schedule_id in ids:
        try:
            await fire_schedule(schedule_id, observed_at=observed_at)
        except Exception:
            # A transaction-level/database error for one row must not stop peers.
            logger.exception(
                "workflow schedule transaction failed",
                extra={"schedule_id": schedule_id},
            )


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    scheduler.add_job(
        scan_due_schedules,
        "interval",
        seconds=SCAN_INTERVAL_SECONDS,
        id="workflow-schedule-scan",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "workflow schedule scanner started",
        extra={"interval_seconds": SCAN_INTERVAL_SECONDS},
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
