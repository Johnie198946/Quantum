"""Governed Workflow schedule, recovery, and worker enqueue tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.exc import IntegrityError

from backend import db as backend_db
from backend.db import Base, canonical_plan_hash
from backend.db import _migrate_workflow_schedule_schema
from backend.models.agent import Agent
from backend.models.tenant_agent import TenantAgentModel
from backend.models.workflow import (
    WorkflowApproval,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowExecution,
    WorkflowPlanVersion,
    WorkflowSchedule,
)
from backend.services import (
    agent_scheduler,
    workflow_execution_start,
    workflow_executor,
    workflow_scheduler,
)
from backend.services.workflow_execution_start import WorkflowStartError
from backend.services.workflow_executor import claim_next


@pytest_asyncio.fixture
async def schedule_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'schedule.db'}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(workflow_scheduler, "SessionLocal", maker)

    async def allow_policy(*args, **kwargs):
        return None

    monkeypatch.setattr(
        workflow_execution_start, "validate_plan_policy", allow_policy
    )
    yield maker
    await engine.dispose()


async def seed_ready_workflow(maker, suffix: str = "one"):
    workflow_id = f"wf_{suffix}"
    plan_id = f"wfp_{suffix}"
    agent_id = f"agent_{suffix}"
    dsl = {
        "plan_id": plan_id,
        "name": f"plan {suffix}",
        "version": "1.0.0",
        "nodes": [
            {
                "id": "run",
                "node_type": "LLM_INFERENCE",
                "name": "run",
                "parameters": {
                    "agent_id": "main_agent",
                    "instruction": "execute approved workflow",
                    "max_tokens": 1000,
                    "knowledge_scope": [],
                    "allow_network": False,
                },
            }
        ],
        "edges": [],
    }
    plan_hash = canonical_plan_hash(dsl)
    frozen_at = datetime.now(timezone.utc)
    async with maker() as db:
        workflow = WorkflowDefinition(
            id=workflow_id,
            tenant_key="tenant-a",
            created_by="owner-a",
            title=f"workflow {suffix}",
            description="approved recurring workflow",
            status="ready",
            active_plan_id=plan_id,
            primary_agent_id=agent_id,
        )
        db.add(workflow)
        await db.flush()
        plan = WorkflowPlanVersion(
            id=plan_id,
            workflow_id=workflow_id,
            version=1,
            dsl=dsl,
            content_hash=plan_hash,
            activation_revision=1,
            goal="execute approved workflow",
            deliverable="report",
            allow_network=False,
            max_tokens=1000,
            knowledge_scope=[],
            validation_errors=[],
            frozen_at=frozen_at,
        )
        db.add(plan)
        db.add(
            TenantAgentModel(
                id=agent_id,
                tenant_id="tenant-a",
                owner_user_id="owner-a",
                origin_workflow_id=workflow_id,
                visibility="private",
                base_agent_id="main_agent",
                composition_manifest={"plan_id": plan_id},
                is_active=True,
            )
        )
        db.add(
            WorkflowApproval(
                id=f"approval_{suffix}",
                workflow_id=workflow_id,
                plan_id=plan_id,
                plan_hash=plan_hash,
                activation_revision=1,
                approval_type="plan",
                decision="approved",
                actor_id="owner-a",
            )
        )
        await db.commit()
        return workflow_id


async def add_due_schedule(maker, workflow_id: str, *, schedule_id: str):
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    async with maker() as db:
        workflow = await db.get(WorkflowDefinition, workflow_id)
        plan = await db.get(WorkflowPlanVersion, workflow.active_plan_id)
        row = WorkflowSchedule(
            id=schedule_id,
            tenant_key=workflow.tenant_key,
            owner_user_id=workflow.created_by,
            workflow_id=workflow.id,
            plan_id=plan.id,
            plan_hash=plan.content_hash,
            activation_revision=plan.activation_revision,
            cron_expression="* * * * *",
            timezone="UTC",
            enabled=True,
            next_run_at=due,
            contract_id=workflow_scheduler.SCHEDULE_CONTRACT_ID,
            contract_version=workflow_scheduler.SCHEDULE_CONTRACT_VERSION,
            handler_id=workflow_scheduler.SCHEDULE_HANDLER_ID,
            handler_version=workflow_scheduler.SCHEDULE_HANDLER_VERSION,
        )
        db.add(row)
        await db.commit()
    return due


def test_due_calculation_is_timezone_aware_and_rejects_invalid_values():
    base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    next_run = workflow_scheduler.compute_next_run(
        "0 18 * * *", "Asia/Shanghai", base=base
    )
    assert next_run == datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="timezone"):
        workflow_scheduler.compute_next_run("0 18 * * *", "Mars/Olympus")
    with pytest.raises(ValueError, match="cron"):
        workflow_scheduler.compute_next_run("not-a-cron", "UTC")

    # APScheduler CronTrigger is authoritative for DST: a repeated local time
    # fires once in each fold. Production Asia/Shanghai has no DST transitions.
    first_fold = workflow_scheduler.compute_next_run(
        "30 1 * * *",
        "America/New_York",
        base=datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc),
    )
    second_fold = workflow_scheduler.compute_next_run(
        "30 1 * * *", "America/New_York", base=first_fold
    )
    assert first_fold == datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)
    assert second_fold == datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc)


def test_application_lifecycle_only_starts_governed_workflow_scheduler():
    root = Path(__file__).resolve().parents[1]
    main_source = (root / "backend/main.py").read_text(encoding="utf-8")
    scheduler_source = (
        root / "backend/services/workflow_scheduler.py"
    ).read_text(encoding="utf-8")
    assert "backend.services.workflow_scheduler" in main_source
    assert "legacy_schedule_allowlist" in main_source
    assert "start_legacy_agent_scheduler" in main_source
    assert "httpx" not in scheduler_source


@pytest.mark.asyncio
async def test_empty_scan_has_no_persistent_side_effects(schedule_db):
    await workflow_scheduler.scan_due_schedules()
    async with schedule_db() as db:
        assert await db.scalar(select(func.count(WorkflowSchedule.id))) == 0
        assert await db.scalar(select(func.count(WorkflowExecution.id))) == 0


@pytest.mark.asyncio
async def test_legacy_active_row_is_inert_without_explicit_allowlist(
    schedule_db, monkeypatch
):
    async with schedule_db() as db:
        db.add(
            Agent(
                id="new-untrusted-legacy-row",
                tenant_key="tenant-a",
                name="must not execute",
                mission="legacy",
                status="active",
                schedule="* * * * *",
            )
        )
        await db.commit()
    called: list[str] = []

    async def record(agent_id: str):
        called.append(agent_id)

    monkeypatch.delenv("LEGACY_AGENT_SCHEDULE_ALLOWLIST", raising=False)
    monkeypatch.setattr(backend_db, "SessionLocal", schedule_db)
    monkeypatch.setattr(agent_scheduler, "_run_agent_once", record)
    await agent_scheduler._scan_due()
    assert called == []
    inventory = await agent_scheduler.deprecated_inventory()
    assert inventory == [
        {
            "id": "new-untrusted-legacy-row",
            "name": "must not execute",
            "schedule": "* * * * *",
            "last_status": None,
            "allowlisted": False,
        }
    ]


@pytest.mark.asyncio
async def test_restart_and_concurrent_fire_create_one_worker_execution(schedule_db):
    workflow_id = await seed_ready_workflow(schedule_db)
    due = await add_due_schedule(schedule_db, workflow_id, schedule_id="wfsched_one")
    observed = datetime.now(timezone.utc)

    await asyncio.gather(
        workflow_scheduler.fire_schedule("wfsched_one", observed_at=observed),
        workflow_scheduler.fire_schedule("wfsched_one", observed_at=observed),
    )
    async with schedule_db() as db:
        assert await db.scalar(select(func.count(WorkflowExecution.id))) == 1
        schedule = await db.get(WorkflowSchedule, "wfsched_one")
        execution_id = schedule.last_execution_id
        assert schedule.last_result == "queued"
        execution = await db.get(WorkflowExecution, execution_id)
        assert execution.trigger_schedule_id == "wfsched_one"
        assert execution.scheduled_for.replace(tzinfo=timezone.utc) == due
        # Simulate a restart replaying the same persisted due instant.
        schedule.next_run_at = due
        await db.commit()

    await workflow_scheduler.fire_schedule("wfsched_one", observed_at=observed)
    async with schedule_db() as db:
        assert await db.scalar(select(func.count(WorkflowExecution.id))) == 1
        schedule = await db.get(WorkflowSchedule, "wfsched_one")
        assert schedule.last_execution_id == execution_id
        execution = await claim_next(db, owner="test-worker")
        assert execution is not None
        assert execution.id == execution_id
        assert execution.lease_owner == "test-worker"
        execution.status = "running"
        assert workflow_scheduler.schedule_out(
            schedule, execution_status=execution.status
        )["last_result"] == "running"


def test_execution_constraints_are_tenant_scoped_and_prevent_two_active_runs():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        common = {
            "workflow_id": "wf-shared",
            "plan_id": "plan-shared",
            "status": "completed",
            "idempotency_key": "same-request-key",
        }
        connection.execute(
            WorkflowExecution.__table__.insert(),
            [
                {"id": "exec-a", "tenant_key": "tenant-a", **common},
                {"id": "exec-b", "tenant_key": "tenant-b", **common},
            ],
        )
        connection.execute(
            WorkflowExecution.__table__.insert().values(
                id="exec-active-a",
                workflow_id="wf-active",
                plan_id="plan-active",
                tenant_key="tenant-a",
                status="queued",
                idempotency_key="request-a",
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                WorkflowExecution.__table__.insert().values(
                    id="exec-active-b",
                    workflow_id="wf-active",
                    plan_id="plan-active",
                    tenant_key="tenant-a",
                    status="running",
                    idempotency_key="request-b",
                )
            )


def test_empty_knowledge_scope_does_not_expand_to_tenant_defaults():
    class Policy:
        calls = 0

        def restrict(self, scope):
            self.calls += 1
            return ["green-default"] if not scope else list(scope)

    policy = Policy()
    assert workflow_executor._restrict_requested_knowledge_scope(policy, []) == []
    assert policy.calls == 0
    assert workflow_executor._restrict_requested_knowledge_scope(policy, ["green"]) == [
        "green"
    ]
    assert policy.calls == 1


@pytest.mark.asyncio
async def test_plan_drift_and_archived_or_disabled_workflows_fail_closed(schedule_db):
    drift_workflow = await seed_ready_workflow(schedule_db, "drift")
    await add_due_schedule(schedule_db, drift_workflow, schedule_id="wfsched_drift")
    async with schedule_db() as db:
        schedule = await db.get(WorkflowSchedule, "wfsched_drift")
        schedule.plan_hash = "0" * 64
        await db.commit()
    await workflow_scheduler.fire_schedule("wfsched_drift")

    archived_workflow = await seed_ready_workflow(schedule_db, "archived")
    await add_due_schedule(schedule_db, archived_workflow, schedule_id="wfsched_archived")
    async with schedule_db() as db:
        workflow = await db.get(WorkflowDefinition, archived_workflow)
        workflow.archived_at = datetime.now(timezone.utc)
        workflow.status = "archived"
        await db.commit()
    await workflow_scheduler.fire_schedule("wfsched_archived")

    disabled_workflow = await seed_ready_workflow(schedule_db, "disabled")
    await add_due_schedule(schedule_db, disabled_workflow, schedule_id="wfsched_disabled")
    async with schedule_db() as db:
        schedule = await db.get(WorkflowSchedule, "wfsched_disabled")
        schedule.enabled = False
        await db.commit()
    await workflow_scheduler.fire_schedule("wfsched_disabled")

    async with schedule_db() as db:
        drift = await db.get(WorkflowSchedule, "wfsched_drift")
        archived = await db.get(WorkflowSchedule, "wfsched_archived")
        disabled = await db.get(WorkflowSchedule, "wfsched_disabled")
        assert drift.last_result == "error"
        assert "schedule_plan_binding_drift" in drift.last_error
        assert archived.last_result == "error"
        assert "尚未就绪" in archived.last_error
        assert disabled.last_triggered_at is None
        assert await db.scalar(select(func.count(WorkflowExecution.id))) == 0


@pytest.mark.asyncio
async def test_dsl_tamper_with_stale_hash_fails_before_worker_dispatch(
    schedule_db, monkeypatch
):
    workflow_id = await seed_ready_workflow(schedule_db, "tamper")
    await add_due_schedule(schedule_db, workflow_id, schedule_id="wfsched_tamper")
    async with schedule_db() as db:
        workflow = await db.get(WorkflowDefinition, workflow_id)
        plan = await db.get(WorkflowPlanVersion, workflow.active_plan_id)
        plan.dsl = {**plan.dsl, "tampered": True}
        await db.commit()

    await workflow_scheduler.fire_schedule("wfsched_tamper")
    async with schedule_db() as db:
        schedule = await db.get(WorkflowSchedule, "wfsched_tamper")
        assert schedule.last_result == "error"
        assert "workflow_plan_content_hash_mismatch" in schedule.last_error
        assert await db.scalar(select(func.count(WorkflowExecution.id))) == 0

    worker_id = await seed_ready_workflow(schedule_db, "worker_tamper")
    await add_due_schedule(
        schedule_db, worker_id, schedule_id="wfsched_worker_tamper"
    )
    await workflow_scheduler.fire_schedule("wfsched_worker_tamper")

    async def forbidden_dispatch(*args, **kwargs):
        raise AssertionError("tampered DSL reached dispatch")

    async with schedule_db() as db:
        execution = await db.scalar(
            select(WorkflowExecution).where(
                WorkflowExecution.workflow_id == worker_id
            )
        )
        plan = await db.get(WorkflowPlanVersion, execution.plan_id)
        plan.dsl = {**plan.dsl, "tampered_after_queue": True}
        await db.commit()
        with pytest.raises(
            workflow_executor.ExecutionAuthorityError,
            match="workflow_plan_content_hash_mismatch",
        ):
            await workflow_executor.dispatch(execution, plan)
        monkeypatch.setattr(workflow_executor, "dispatch", forbidden_dispatch)
        await workflow_executor.sync_execution(execution.id, db)
        await db.refresh(execution)
        assert execution.status == "failed"
        assert "workflow_plan_content_hash_mismatch" in execution.error_message
        event = await db.scalar(
            select(WorkflowEvent).where(
                WorkflowEvent.execution_id == execution.id,
                WorkflowEvent.event_type == "authorization_failed",
            )
        )
        assert event is not None


@pytest.mark.asyncio
async def test_failure_isolation_and_fake_owner_rejection(schedule_db):
    bad_workflow = await seed_ready_workflow(schedule_db, "bad")
    good_workflow = await seed_ready_workflow(schedule_db, "good")
    await add_due_schedule(schedule_db, bad_workflow, schedule_id="a_bad")
    await add_due_schedule(schedule_db, good_workflow, schedule_id="b_good")
    async with schedule_db() as db:
        bad = await db.get(WorkflowSchedule, "a_bad")
        bad.handler_version = 999
        workflow = await db.get(WorkflowDefinition, good_workflow)
        with pytest.raises(WorkflowStartError, match="工作流不存在"):
            await workflow_scheduler.create_schedule(
                db,
                workflow=workflow,
                tenant_key="tenant-a",
                owner_user_id="forged-owner",
                cron_expression="0 18 * * *",
                timezone_name="UTC",
                enabled=True,
            )
        await db.commit()

    await workflow_scheduler.scan_due_schedules()
    async with schedule_db() as db:
        bad = await db.get(WorkflowSchedule, "a_bad")
        good = await db.get(WorkflowSchedule, "b_good")
        assert bad.last_result == "error"
        assert "contract_mismatch" in bad.last_error
        assert good.last_result == "queued"
        assert good.last_execution_id
        assert await db.scalar(select(func.count(WorkflowExecution.id))) == 1


@pytest.mark.asyncio
async def test_current_policy_and_primary_agent_are_rechecked(schedule_db, monkeypatch):
    policy_workflow = await seed_ready_workflow(schedule_db, "policy")
    await add_due_schedule(schedule_db, policy_workflow, schedule_id="policy_denied")

    async def deny_policy(*args, **kwargs):
        raise ValueError("current policy denied schedule scope")

    monkeypatch.setattr(
        workflow_execution_start, "validate_plan_policy", deny_policy
    )
    await workflow_scheduler.fire_schedule("policy_denied")

    async def allow_policy(*args, **kwargs):
        return None

    monkeypatch.setattr(
        workflow_execution_start, "validate_plan_policy", allow_policy
    )

    agent_workflow = await seed_ready_workflow(schedule_db, "inactive")
    await add_due_schedule(schedule_db, agent_workflow, schedule_id="agent_inactive")
    async with schedule_db() as db:
        workflow = await db.get(WorkflowDefinition, agent_workflow)
        agent = await db.get(TenantAgentModel, workflow.primary_agent_id)
        agent.is_active = False
        await db.commit()
    await workflow_scheduler.fire_schedule("agent_inactive")

    async with schedule_db() as db:
        policy = await db.get(WorkflowSchedule, "policy_denied")
        inactive = await db.get(WorkflowSchedule, "agent_inactive")
        assert policy.last_result == "error"
        assert "current policy denied" in policy.last_error
        assert inactive.last_result == "error"
        assert "primary_agent_binding_invalid" in inactive.last_error
        assert await db.scalar(select(func.count(WorkflowExecution.id))) == 0


@pytest.mark.asyncio
async def test_worker_dispatch_uses_server_owned_knowledge_capabilities(
    schedule_db, monkeypatch
):
    workflow_id = await seed_ready_workflow(schedule_db, "payload")
    await add_due_schedule(schedule_db, workflow_id, schedule_id="payload_schedule")
    async with schedule_db() as db:
        workflow = await db.get(WorkflowDefinition, workflow_id)
        plan = await db.get(WorkflowPlanVersion, workflow.active_plan_id)
        agent = await db.get(TenantAgentModel, workflow.primary_agent_id)
        plan.knowledge_scope = ["knowledge/product/public"]
        agent.subscribed_knowledge_packs = [
            "knowledge/product/public",
            "knowledge/private/other",
        ]
        # Tenant metadata cannot grant privileged tools to the Workflow runtime.
        agent.composition_manifest = {
            **(agent.composition_manifest or {}),
            "allowed_tools": ["knowledge_search", "terminal"],
            "allow_network": True,
        }
        await db.commit()

    await workflow_scheduler.fire_schedule("payload_schedule")
    captured: dict = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"hermes_session_id": "worker-session"}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, headers, json):
            captured.update({"url": url, "headers": headers, "json": json})
            return Response()

    class Policy:
        policy_version = "policy-test"

        def restrict(self, scopes):
            return frozenset(scopes)

    async def policy(*args, **kwargs):
        return Policy(), None

    monkeypatch.setattr(workflow_executor, "SessionLocal", schedule_db)
    monkeypatch.setattr(workflow_executor, "resolve_policy", policy)
    monkeypatch.setattr(workflow_executor, "compute_catalog", lambda: {})
    monkeypatch.setattr(
        workflow_executor,
        "mint_capability",
        lambda *args, **kwargs: {"token": "signed-test-capability"},
    )
    monkeypatch.setattr(workflow_executor.httpx, "AsyncClient", Client)

    async with schedule_db() as db:
        execution = (
            await db.execute(
                select(WorkflowExecution).where(
                    WorkflowExecution.workflow_id == workflow_id
                )
            )
        ).scalar_one()
        plan = await db.get(WorkflowPlanVersion, execution.plan_id)
        await workflow_executor.dispatch(execution, plan)

    payload = captured["json"]
    assert captured["url"].endswith("/v1/workflow-runs")
    assert "knowledge_search" in payload["agent_config"]["allowed_tools"]
    assert "terminal" not in payload["agent_config"]["allowed_tools"]
    assert payload["agent_config"]["knowledge_scope"] == [
        "knowledge/product/public"
    ]
    assert "knowledge/private/other" not in payload["agent_config"]["knowledge_scope"]
    assert payload["agent_config"]["allow_network"] is False
    assert payload["knowledge_capability"] == {
        "token": "signed-test-capability"
    }


def test_schedule_migration_does_not_convert_legacy_agents_and_is_rollback_safe():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        connection.execute(
            Agent.__table__.insert().values(
                id="legacy-one",
                tenant_key="tenant-a",
                name="legacy task",
                mission="legacy only",
                status="active",
                schedule="0 18 * * *",
            )
        )
        _migrate_workflow_schedule_schema(connection)
        _migrate_workflow_schedule_schema(connection)
        assert connection.execute(
            text("SELECT COUNT(*) FROM workflow_schedules")
        ).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM agents")).scalar_one() == 1
        connection.exec_driver_sql("DROP TABLE workflow_schedules")
        assert "workflow_schedules" not in set(inspect(connection).get_table_names())
