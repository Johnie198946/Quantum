"""Shared, governed transaction for creating workflow executions.

Both the authenticated Workflow API and the schedule scanner call this module.  It
creates only the durable execution/outbox rows; the existing workflow worker owns
Bridge dispatch and event projection.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tenant_agent import TenantAgentModel
from backend.models.tenant_agent_schema import WorkflowDSLPlan
from backend.models.workflow import (
    WorkflowApproval,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowNodeRun,
    WorkflowPlanVersion,
)
from backend.models.workspace import WorkspaceWorkflowBinding
from backend.services.dsl_safety_compiler import DSLSafetyCompiler
from backend.services.workflow_contract import (
    PlanContractError,
    assert_plan_binding,
    canonical_plan_hash,
)
from backend.services.workflow_executor import executable_plan_projection
from backend.services.workflow_planner import validate_plan_policy

ACTIVE_EXECUTION_STATUSES = ("queued", "running", "awaiting_approval", "awaiting_review")


@dataclass(slots=True)
class WorkflowStartError(Exception):
    status_code: int
    detail: str

    def __str__(self) -> str:
        return self.detail


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


async def _execution_nodes(
    db: AsyncSession, execution_id: str
) -> list[WorkflowNodeRun]:
    return list(
        (
            await db.execute(
                select(WorkflowNodeRun)
                .where(WorkflowNodeRun.execution_id == execution_id)
                .order_by(WorkflowNodeRun.position)
            )
        ).scalars().all()
    )


async def validate_workflow_execution_authority(
    db: AsyncSession,
    *,
    workflow: WorkflowDefinition,
    tenant_key: str,
    owner_user_id: str,
    expected_plan_id: str | None = None,
    expected_plan_hash: str | None = None,
    expected_activation_revision: int | None = None,
) -> tuple[WorkflowPlanVersion, WorkflowDSLPlan]:
    """Resolve the current owner, plan, handler inputs, and policy scope."""
    if workflow.tenant_key != tenant_key or workflow.created_by != owner_user_id:
        raise WorkflowStartError(404, "工作流不存在")
    if workflow.archived_at is not None or workflow.status not in {"agent_ready", "ready"}:
        raise WorkflowStartError(409, "专属 Agent 尚未就绪")
    if not workflow.active_plan_id:
        raise WorkflowStartError(409, "专属 Agent 尚未就绪")

    plan = await db.get(WorkflowPlanVersion, workflow.active_plan_id)
    if plan is None or plan.workflow_id != workflow.id:
        raise WorkflowStartError(409, "当前计划不存在")
    try:
        actual_plan_hash = canonical_plan_hash(plan.dsl)
    except (TypeError, ValueError) as exc:
        raise WorkflowStartError(409, "workflow_plan_content_hash_invalid") from exc
    if actual_plan_hash != plan.content_hash:
        raise WorkflowStartError(409, "workflow_plan_content_hash_mismatch")
    if (
        (expected_plan_id is not None and plan.id != expected_plan_id)
        or (expected_plan_hash is not None and plan.content_hash != expected_plan_hash)
        or (
            expected_activation_revision is not None
            and plan.activation_revision != expected_activation_revision
        )
    ):
        raise WorkflowStartError(409, "schedule_plan_binding_drift")
    if plan.frozen_at is None:
        raise WorkflowStartError(409, "当前计划尚未冻结")

    qws_binding = await db.scalar(
        select(WorkspaceWorkflowBinding).where(
            WorkspaceWorkflowBinding.workflow_id == workflow.id,
            WorkspaceWorkflowBinding.status == "ACTIVE",
        )
    )
    if qws_binding is not None and (
        qws_binding.plan_id != plan.id
        or qws_binding.plan_hash != plan.content_hash
        or qws_binding.activation_revision != plan.activation_revision
    ):
        raise WorkflowStartError(
            409, "qws_workflow_plan_change_requires_project_proposal"
        )

    approval = (
        await db.execute(
            select(WorkflowApproval)
            .where(
                WorkflowApproval.workflow_id == workflow.id,
                WorkflowApproval.approval_type == "plan",
                WorkflowApproval.decision == "approved",
            )
            .order_by(WorkflowApproval.created_at.desc(), WorkflowApproval.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    try:
        assert_plan_binding(
            active_plan_id=plan.id,
            active_plan_hash=plan.content_hash,
            active_activation_revision=plan.activation_revision,
            approval_plan_id=approval.plan_id if approval else None,
            approval_plan_hash=approval.plan_hash if approval else None,
            approval_activation_revision=(approval.activation_revision if approval else None),
        )
    except PlanContractError as exc:
        raise WorkflowStartError(409, str(exc)) from exc

    agent = (
        await db.get(TenantAgentModel, workflow.primary_agent_id)
        if workflow.primary_agent_id
        else None
    )
    if (
        agent is None
        or agent.tenant_id != tenant_key
        or agent.owner_user_id != owner_user_id
        or agent.origin_workflow_id != workflow.id
        or not agent.is_active
    ):
        raise WorkflowStartError(409, "workflow_primary_agent_binding_invalid")

    try:
        compiled: WorkflowDSLPlan = DSLSafetyCompiler.compile_and_validate(
            executable_plan_projection(plan.dsl)
        )
        await validate_plan_policy(
            db,
            tenant_key,
            compiled,
            allow_network=plan.allow_network,
            max_tokens=plan.max_tokens,
            knowledge_scope=plan.knowledge_scope or [],
            owner_user_id=owner_user_id,
        )
    except Exception as exc:
        raise WorkflowStartError(422, str(exc)) from exc
    return plan, compiled


async def create_workflow_execution(
    db: AsyncSession,
    *,
    workflow: WorkflowDefinition,
    tenant_key: str,
    owner_user_id: str,
    request_key: str,
    expected_plan_id: str | None = None,
    expected_plan_hash: str | None = None,
    expected_activation_revision: int | None = None,
    trigger_schedule_id: str | None = None,
    scheduled_for: datetime | None = None,
) -> tuple[WorkflowExecution, list[WorkflowNodeRun], bool]:
    """Validate current authority and create one durable queued execution.

    Returns ``(execution, nodes, created)``.  The deterministic request key and
    database uniqueness are the final concurrency/restart guard.
    """
    if not request_key or len(request_key) > 160:
        raise WorkflowStartError(422, "request_id长度无效")
    plan, compiled = await validate_workflow_execution_authority(
        db,
        workflow=workflow,
        tenant_key=tenant_key,
        owner_user_id=owner_user_id,
        expected_plan_id=expected_plan_id,
        expected_plan_hash=expected_plan_hash,
        expected_activation_revision=expected_activation_revision,
    )

    existing = await db.scalar(
        select(WorkflowExecution).where(
            WorkflowExecution.idempotency_key == request_key,
            WorkflowExecution.tenant_key == tenant_key,
        )
    )
    if existing is not None:
        if existing.workflow_id != workflow.id or existing.plan_id != plan.id:
            raise WorkflowStartError(409, "同一request_id对应不同请求")
        return existing, await _execution_nodes(db, existing.id), False

    # Serialize all starts for one workflow in PostgreSQL. The partial unique
    # index remains the final invariant and is also the SQLite-compatible guard.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        await db.execute(
            select(WorkflowDefinition.id)
            .where(WorkflowDefinition.id == workflow.id)
            .with_for_update()
        )

    active = await db.scalar(
        select(WorkflowExecution)
        .where(
            WorkflowExecution.workflow_id == workflow.id,
            WorkflowExecution.tenant_key == tenant_key,
            WorkflowExecution.status.in_(ACTIVE_EXECUTION_STATUSES),
        )
        .limit(1)
    )
    if active is not None:
        raise WorkflowStartError(409, "该工作流已有活动执行，请先恢复或完成现有任务")

    execution = WorkflowExecution(
        id=_uid("wfr"),
        workflow_id=workflow.id,
        plan_id=plan.id,
        tenant_key=tenant_key,
        status="queued",
        token_budget=plan.max_tokens,
        idempotency_key=request_key,
        trigger_schedule_id=trigger_schedule_id,
        scheduled_for=scheduled_for,
    )
    order = DSLSafetyCompiler.check_dag_cycle_kahn(compiled)
    node_map = {node.id: node for node in compiled.nodes}
    nodes = [
        WorkflowNodeRun(
            id=_uid("wfn"),
            execution_id=execution.id,
            node_id=node_id,
            node_type=node_map[node_id].node_type.value,
            name=node_map[node_id].name or node_id,
            agent_id=str(node_map[node_id].parameters.get("agent_id") or "main_agent"),
            position=position,
            max_tokens=int(node_map[node_id].parameters.get("max_tokens", 4000)),
            input_refs=[edge.source for edge in compiled.edges if edge.target == node_id],
        )
        for position, node_id in enumerate(order)
    ]
    try:
        async with db.begin_nested():
            db.add(execution)
            await db.flush()
            db.add_all(nodes)
            await db.flush()
    except IntegrityError:
        existing = await db.scalar(
            select(WorkflowExecution).where(
                WorkflowExecution.idempotency_key == request_key,
                WorkflowExecution.tenant_key == tenant_key,
            )
        )
        if existing is not None:
            if existing.workflow_id != workflow.id or existing.plan_id != plan.id:
                raise WorkflowStartError(409, "同一request_id对应不同请求")
            return existing, await _execution_nodes(db, existing.id), False
        active = await db.scalar(
            select(WorkflowExecution).where(
                WorkflowExecution.workflow_id == workflow.id,
                WorkflowExecution.tenant_key == tenant_key,
                WorkflowExecution.status.in_(ACTIVE_EXECUTION_STATUSES),
            )
        )
        if active is not None:
            raise WorkflowStartError(409, "该工作流已有活动执行，请先恢复或完成现有任务")
        raise WorkflowStartError(409, "工作流执行并发冲突")

    workflow.status = "ready"
    return execution, nodes, True
