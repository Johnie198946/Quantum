"""Narrow, schedule-bound WorkflowArtifact to publication handoff."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.workflow import (
    WorkflowApproval,
    WorkflowArtifact,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowExecution,
    WorkflowNodeRun,
    WorkflowPlanVersion,
    WorkflowSchedule,
)
from backend.services.knowledge_publication_store import PublicationError, PublicationStore
from backend.services.publication_editorial import validate_editorial_brief
from backend.services.workflow_artifacts import read_verified_artifact_bytes, run_root
from backend.services.workflow_execution_start import (
    WorkflowStartError,
    validate_workflow_execution_authority,
)
from backend.services.workflow_scheduler import (
    SCHEDULE_CONTRACT_ID,
    SCHEDULE_CONTRACT_VERSION,
    SCHEDULE_HANDLER_ID,
    SCHEDULE_HANDLER_VERSION,
)

SCHEMA_VERSION = "ai-toolkit-publication-content-v1"
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
HASH = re.compile(r"[0-9a-f]{64}\Z")
KIND = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
TOP_LEVEL_FIELDS = {
    "schema_version",
    "title",
    "summary",
    "body",
    "editorial_brief",
    "learning_objectives",
    "source_documents",
    "execution_documents",
}
DOCUMENT_FIELDS = {"kind", "content"}
MAX_REVISION_FEEDBACK_BYTES = 16 * 1024
MAX_REVISION_GAPS = 24
REVISION_DISPATCH_STATUSES = {"queued", "running", "awaiting_review"}


class PublicationHandoffError(ValueError):
    """A stable, fail-closed handoff validation error."""


class PublicationWorkflowPending(PublicationHandoffError):
    """The fixed schedule has not produced today's review candidate yet."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def validate_ai_toolkit_artifact(raw: bytes) -> dict[str, Any]:
    """Validate the exact content-only artifact contract; reject control fields."""
    if not raw or len(raw) > MAX_ARTIFACT_BYTES:
        raise PublicationHandoffError("workflow artifact size is invalid")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicationHandoffError("workflow artifact must be UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != TOP_LEVEL_FIELDS:
        raise PublicationHandoffError("workflow artifact has missing, unknown, or forbidden fields")
    if value["schema_version"] != SCHEMA_VERSION:
        raise PublicationHandoffError("workflow artifact schema version is invalid")
    for field, limit in (("title", 300), ("summary", 2000), ("body", MAX_ARTIFACT_BYTES)):
        item = value[field]
        if not isinstance(item, str) or not item.strip() or len(item.encode("utf-8")) > limit:
            raise PublicationHandoffError(f"workflow artifact {field} is invalid")
    objectives = value["learning_objectives"]
    if (
        not isinstance(objectives, list)
        or not 1 <= len(objectives) <= 32
        or any(not isinstance(item, str) or len(item.strip()) < 10 or len(item) > 1000 for item in objectives)
    ):
        raise PublicationHandoffError("workflow artifact learning objectives are invalid")
    brief = value["editorial_brief"]
    if validate_editorial_brief(brief):
        raise PublicationHandoffError("workflow artifact editorial brief is invalid")
    for field, require_item in (("source_documents", True), ("execution_documents", False)):
        documents = value[field]
        if (
            not isinstance(documents, list)
            or len(documents) > 64
            or (require_item and not documents)
        ):
            raise PublicationHandoffError(f"workflow artifact {field} is invalid")
        for document in documents:
            if (
                not isinstance(document, dict)
                or set(document) != DOCUMENT_FIELDS
                or not isinstance(document.get("kind"), str)
                or KIND.fullmatch(document["kind"]) is None
                or not isinstance(document.get("content"), str)
                or not document["content"]
                or len(document["content"].encode("utf-8")) > MAX_ARTIFACT_BYTES
            ):
                raise PublicationHandoffError(f"workflow artifact {field} entry is invalid")
    return value


def _schedule_contract_valid(schedule: WorkflowSchedule) -> bool:
    return (
        schedule.contract_id == SCHEDULE_CONTRACT_ID
        and schedule.contract_version == SCHEDULE_CONTRACT_VERSION
        and schedule.handler_id == SCHEDULE_HANDLER_ID
        and schedule.handler_version == SCHEDULE_HANDLER_VERSION
    )


def _envelope(
    schedule: WorkflowSchedule,
    workflow: WorkflowDefinition,
    execution: WorkflowExecution,
    artifact: WorkflowArtifact,
) -> dict[str, Any]:
    scheduled_for = execution.scheduled_for
    if scheduled_for is not None and scheduled_for.tzinfo is None:
        scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)
    return {
        "version": "publication-workflow-handoff-v1",
        "schedule_id": schedule.id,
        "workflow_id": workflow.id,
        "execution_id": execution.id,
        "plan_id": execution.plan_id,
        "plan_hash": schedule.plan_hash,
        "activation_revision": schedule.activation_revision,
        "primary_agent_id": workflow.primary_agent_id,
        "artifact_id": artifact.id,
        "artifact_sha256": artifact.content_hash,
        "scheduled_for": scheduled_for.isoformat() if scheduled_for else None,
    }


async def _bound_rows(
    db: AsyncSession,
    schedule_id: str,
    *,
    execution_id: str | None = None,
    lock: bool = False,
    allow_completed: bool = False,
    allow_revision_queued: bool = False,
    missing_is_pending: bool = False,
) -> tuple[WorkflowSchedule, WorkflowDefinition, WorkflowExecution]:
    schedule_query = select(WorkflowSchedule).where(WorkflowSchedule.id == schedule_id)
    if lock:
        schedule_query = schedule_query.with_for_update()
    schedule = (await db.execute(schedule_query)).scalar_one_or_none()
    if (
        schedule is None
        or not schedule.enabled
        or schedule.deleted_at is not None
        or not _schedule_contract_valid(schedule)
    ):
        raise PublicationHandoffError("configured workflow schedule is unavailable or revoked")
    workflow = await db.get(WorkflowDefinition, schedule.workflow_id)
    if workflow is None:
        raise PublicationHandoffError("configured workflow is unavailable")
    statuses = ["awaiting_review", "completed"] if allow_completed else ["awaiting_review"]
    if allow_revision_queued:
        statuses.extend(["queued", "running"])
    execution_query = select(WorkflowExecution).where(
        WorkflowExecution.trigger_schedule_id == schedule.id,
        WorkflowExecution.workflow_id == schedule.workflow_id,
        WorkflowExecution.plan_id == schedule.plan_id,
        WorkflowExecution.tenant_key == schedule.tenant_key,
        WorkflowExecution.status.in_(statuses),
    )
    if execution_id is not None:
        execution_query = execution_query.where(WorkflowExecution.id == execution_id)
    if lock:
        execution_query = execution_query.with_for_update()
    executions = list((await db.execute(execution_query)).scalars().all())
    if not executions and missing_is_pending:
        raise PublicationWorkflowPending("scheduled workflow has no awaiting-review artifact yet")
    if len(executions) != 1:
        raise PublicationHandoffError("configured schedule must have exactly one bound execution")
    execution = executions[0]
    try:
        await validate_workflow_execution_authority(
            db,
            workflow=workflow,
            tenant_key=schedule.tenant_key,
            owner_user_id=schedule.owner_user_id,
            expected_plan_id=schedule.plan_id,
            expected_plan_hash=schedule.plan_hash,
            expected_activation_revision=schedule.activation_revision,
        )
    except WorkflowStartError as exc:
        raise PublicationHandoffError(f"workflow authority revalidation failed: {exc.detail}") from exc
    if schedule.last_execution_id not in {None, execution.id}:
        raise PublicationHandoffError("schedule last execution binding conflicts")
    return schedule, workflow, execution


async def export_publication_handoff(db: AsyncSession, schedule_id: str) -> dict[str, Any]:
    try:
        schedule, workflow, execution = await _bound_rows(
            db, schedule_id, missing_is_pending=True
        )
    except PublicationWorkflowPending:
        return {"status": "waiting_workflow", "available": False}
    artifacts = list(
        (
            await db.execute(
                select(WorkflowArtifact).where(
                    WorkflowArtifact.execution_id == execution.id,
                    WorkflowArtifact.selected_for_publish.is_(True),
                    WorkflowArtifact.kind == "final",
                )
            )
        ).scalars().all()
    )
    if len(artifacts) != 1:
        raise PublicationHandoffError("execution must have exactly one selected final artifact")
    artifact = artifacts[0]
    if Path(artifact.relative_path).suffix.lower() != ".json":
        raise PublicationHandoffError("publication workflow artifact must be JSON")
    root = run_root(execution).resolve()
    path = (root / artifact.relative_path).resolve()
    if root not in path.parents or not path.is_file() or path.is_symlink():
        raise PublicationHandoffError("workflow artifact path is invalid")
    try:
        raw = read_verified_artifact_bytes(path, artifact.content_hash)
    except (OSError, ValueError) as exc:
        raise PublicationHandoffError("workflow artifact bytes do not match the registry") from exc
    validate_ai_toolkit_artifact(raw)
    envelope = _envelope(schedule, workflow, execution, artifact)
    envelope_raw = canonical_json(envelope)
    return {
        "envelope": envelope,
        "envelope_sha256": hashlib.sha256(envelope_raw).hexdigest(),
        "artifact_b64": base64.b64encode(raw).decode("ascii"),
    }


def verify_publication_staged(
    store: PublicationStore,
    bundle: dict[str, Any],
    *,
    attempt_id: str,
    artifact_hash: str,
    envelope_hash: str,
    workflow_content: dict[str, Any],
) -> dict[str, Any]:
    if not all(HASH.fullmatch(value or "") for value in (artifact_hash, envelope_hash)):
        raise PublicationHandoffError("handoff hashes are invalid")
    try:
        from backend.services.knowledge_publication_store import validate_bundle

        normalized, _ = validate_bundle(bundle)
        contract = normalized.get("quality_contract")
        if not isinstance(contract, dict) or contract.get("attempt_id") != attempt_id:
            raise PublicationHandoffError("publication attempt binding mismatch")
        if (
            normalized.get("series_id") != "ai-toolkit"
            or normalized.get("title") != workflow_content["title"]
            or normalized.get("summary") != workflow_content["summary"]
            or normalized.get("body") != workflow_content["body"]
            or contract.get("editorial_brief") != workflow_content["editorial_brief"]
            or contract.get("learning_objectives") != workflow_content["learning_objectives"]
        ):
            raise PublicationHandoffError("publication content does not match the workflow artifact")
        expected_receipts = {
            ("workflow_artifact", artifact_hash),
            ("workflow_handoff_envelope", envelope_hash),
        }
        actual_receipts = {
            (item.get("kind"), item.get("sha256"))
            for item in normalized.get("source_receipts", [])
            if isinstance(item, dict)
        }
        if not expected_receipts <= actual_receipts:
            raise PublicationHandoffError("publication source receipts do not bind the handoff")
        db = store._connect()
        try:
            if not store._bundle_receipts_valid(db, normalized):
                raise PublicationHandoffError("publication receipts are missing or hash-mismatched")
            row = db.execute(
                "SELECT * FROM editorial_attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if (
                row is None
                or row["state"] != "approved"
                or json.loads(row["contract_json"]) != contract
                or row["body_hash"] != normalized["body_hash"]
            ):
                raise PublicationHandoffError("exact approved publication attempt is unavailable")
            edition = db.execute(
                """SELECT * FROM editions
                WHERE issue_id=? AND content_hash=? AND state IN ('staged','scheduled','published')
                ORDER BY edition DESC LIMIT 1""",
                (row["issue_id"], normalized["body_hash"]),
            ).fetchone()
            if edition is None:
                raise PublicationHandoffError("exact staged publication edition is unavailable")
            frozen = json.loads(edition["bundle_json"])
            if frozen.get("quality_contract") != contract:
                raise PublicationHandoffError("staged publication contract mismatch")
            return {
                "attempt_id": row["attempt_id"],
                "issue_id": row["issue_id"],
                "revision": row["revision"],
                "target_hash": row["target_hash"],
                "body_hash": row["body_hash"],
                "publication_id": edition["publication_id"],
                "edition_id": edition["edition_id"],
                "edition_state": edition["state"],
            }
        finally:
            db.close()
    except PublicationError as exc:
        raise PublicationHandoffError(str(exc)) from exc


async def acknowledge_publication_handoff(
    db: AsyncSession,
    store: PublicationStore,
    schedule_id: str,
    *,
    execution_id: str,
    artifact_id: str,
    artifact_hash: str,
    envelope_hash: str,
    attempt_id: str,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    schedule, workflow, execution = await _bound_rows(
        db,
        schedule_id,
        execution_id=execution_id,
        lock=True,
        allow_completed=True,
    )
    artifact = await db.get(WorkflowArtifact, artifact_id)
    if (
        artifact is None
        or artifact.execution_id != execution.id
        or artifact.content_hash != artifact_hash
        or not artifact.selected_for_publish
        or artifact.kind != "final"
    ):
        raise PublicationHandoffError("workflow artifact acknowledgement binding mismatch")
    current_envelope_hash = hashlib.sha256(
        canonical_json(_envelope(schedule, workflow, execution, artifact))
    ).hexdigest()
    if current_envelope_hash != envelope_hash:
        raise PublicationHandoffError("workflow handoff envelope no longer matches current authority")
    root = run_root(execution).resolve()
    artifact_path = (root / artifact.relative_path).resolve()
    if root not in artifact_path.parents or not artifact_path.is_file() or artifact_path.is_symlink():
        raise PublicationHandoffError("workflow artifact path is invalid")
    try:
        raw = read_verified_artifact_bytes(artifact_path, artifact_hash)
    except (OSError, ValueError) as exc:
        raise PublicationHandoffError("workflow artifact changed before acknowledgement") from exc
    workflow_content = validate_ai_toolkit_artifact(raw)
    request_binding = {
        "schedule_id": schedule.id,
        "execution_id": execution.id,
        "artifact_id": artifact.id,
        "artifact_sha256": artifact_hash,
        "envelope_sha256": envelope_hash,
    }
    approvals = list(
        (
            await db.execute(
                select(WorkflowApproval).where(
                    WorkflowApproval.execution_id == execution.id,
                    WorkflowApproval.approval_type == "publication_handoff",
                )
            )
        ).scalars().all()
    )
    if approvals:
        try:
            prior_binding = json.loads(approvals[0].comment) if len(approvals) == 1 else None
        except json.JSONDecodeError:
            prior_binding = None
        if (
            not isinstance(prior_binding, dict)
            or approvals[0].decision != "approved"
            or any(prior_binding.get(key) != value for key, value in request_binding.items())
            or prior_binding.get("attempt_id") != attempt_id
        ):
            raise PublicationHandoffError("publication handoff acknowledgement conflicts")
        if execution.status != "completed":
            raise PublicationHandoffError("publication handoff completion state conflicts")
        return {"status": "completed", **prior_binding, "idempotent": True}
    if execution.status != "awaiting_review":
        raise PublicationHandoffError("workflow execution is no longer awaiting review")
    publication = verify_publication_staged(
        store,
        bundle,
        attempt_id=attempt_id,
        artifact_hash=artifact_hash,
        envelope_hash=envelope_hash,
        workflow_content=workflow_content,
    )
    binding = {**request_binding, **publication}
    comment = canonical_json(binding).decode("utf-8")
    now = datetime.now(timezone.utc)
    db.add(
        WorkflowApproval(
            id=f"wfa_{uuid.uuid4().hex}",
            workflow_id=workflow.id,
            execution_id=execution.id,
            plan_id=artifact.id,
            plan_hash=artifact_hash,
            activation_revision=int((artifact.metadata_json or {}).get("artifact_version") or 1),
            approval_type="publication_handoff",
            decision="approved",
            actor_id=schedule.owner_user_id,
            comment=comment,
        )
    )
    db.add(
        WorkflowEvent(
            execution_id=execution.id,
            event_type="publication_handoff_completed",
            message="Publication handoff verified and acknowledged",
            payload=binding,
        )
    )
    execution.status = "completed"
    execution.finished_at = now
    execution.lease_owner = None
    execution.lease_until = None
    workflow.status = "ready"
    schedule.last_result = "completed"
    await db.flush()
    return {"status": "completed", **binding, "idempotent": False}


def _revision_feedback(review: dict[str, Any]) -> list[dict[str, str]]:
    gaps = review.get("research_gaps")
    if not isinstance(gaps, list) or not 1 <= len(gaps) <= MAX_REVISION_GAPS:
        raise PublicationHandoffError("rejected review must contain bounded structured gaps")
    result = []
    for gap in gaps:
        if not isinstance(gap, dict):
            raise PublicationHandoffError("rejected review gaps are invalid")
        gap_id = gap.get("id")
        question = gap.get("question")
        acceptance = gap.get("acceptance_criterion") or gap.get("required_evidence") or question
        if (
            not isinstance(gap_id, str)
            or KIND.fullmatch(gap_id) is None
            or not isinstance(question, str)
            or not 10 <= len(question.strip()) <= 2000
            or not isinstance(acceptance, str)
            or not 10 <= len(acceptance.strip()) <= 2000
        ):
            raise PublicationHandoffError("rejected review gaps are invalid")
        result.append({
            "id": gap_id,
            "question": question.strip(),
            "acceptance_criterion": acceptance.strip(),
        })
    if len(canonical_json(result)) > MAX_REVISION_FEEDBACK_BYTES:
        raise PublicationHandoffError("rejected review feedback is too large")
    return result


def _verify_terminal_rejection(
    store: PublicationStore,
    bundle: dict[str, Any],
    review_raw: bytes,
    *,
    attempt_id: str,
    artifact_hash: str,
    envelope_hash: str,
    workflow_content: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    try:
        from backend.services.knowledge_publication_store import validate_bundle

        normalized, _ = validate_bundle(bundle)
        contract = normalized.get("quality_contract")
        if not isinstance(contract, dict) or contract.get("attempt_id") != attempt_id:
            raise PublicationHandoffError("publication attempt binding mismatch")
        if (
            normalized.get("series_id") != "ai-toolkit"
            or normalized.get("title") != workflow_content["title"]
            or normalized.get("summary") != workflow_content["summary"]
            or normalized.get("body") != workflow_content["body"]
            or contract.get("editorial_brief") != workflow_content["editorial_brief"]
            or contract.get("learning_objectives") != workflow_content["learning_objectives"]
        ):
            raise PublicationHandoffError("publication content does not match the workflow artifact")
        required_receipts = {
            ("workflow_artifact", artifact_hash),
            ("workflow_handoff_envelope", envelope_hash),
        }
        actual_receipts = {
            (item.get("kind"), item.get("sha256"))
            for item in normalized.get("source_receipts", [])
            if isinstance(item, dict)
        }
        if not required_receipts <= actual_receipts:
            raise PublicationHandoffError("publication source receipts do not bind the handoff")
        try:
            review = json.loads(review_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PublicationHandoffError("rejected review bytes are invalid") from exc
        feedback = _revision_feedback(review)
        review_hash = hashlib.sha256(review_raw).hexdigest()
        db = store._connect()
        try:
            if not store._bundle_receipts_valid(db, normalized):
                raise PublicationHandoffError("publication receipts are missing or hash-mismatched")
            row = db.execute(
                "SELECT * FROM editorial_attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            latest = db.execute(
                "SELECT * FROM editorial_attempts WHERE issue_id=(SELECT issue_id FROM editorial_attempts WHERE attempt_id=?) ORDER BY revision DESC LIMIT 1",
                (attempt_id,),
            ).fetchone()
            evidence = db.execute(
                "SELECT * FROM evidence WHERE sha256=? AND kind='content_review'", (review_hash,)
            ).fetchall()
            if (
                row is None
                or latest is None
                or latest["attempt_id"] != attempt_id
                or row["state"] != "rejected"
                or row["review_hash"] != review_hash
                or row["body_hash"] != normalized["body_hash"]
                or row["target_hash"] != contract.get("target_hash")
                or json.loads(row["contract_json"]) != contract
                or review.get("decision") not in {"reject", "rejected"}
                or review.get("content_hash") != row["body_hash"]
                or review.get("editorial_target_hash") != row["target_hash"]
                or review.get("revision") != row["revision"]
                or not any(
                    store._path(item["private_ref"]).is_file()
                    and store._path(item["private_ref"]).read_bytes() == review_raw
                    for item in evidence
                )
            ):
                raise PublicationHandoffError("exact terminal rejected publication review is unavailable")
            return {
                "attempt_id": row["attempt_id"],
                "issue_id": row["issue_id"],
                "revision": row["revision"],
                "target_hash": row["target_hash"],
                "review_sha256": review_hash,
            }, feedback
        finally:
            db.close()
    except PublicationError as exc:
        raise PublicationHandoffError(str(exc)) from exc


def _reset_node_ids(plan: dict[str, Any], producing_node_id: str) -> set[str]:
    from backend.services.workflow_executor import executable_plan_projection

    projected = executable_plan_projection(plan)
    node_ids = {str(node.get("id")) for node in projected.get("nodes", [])}
    if producing_node_id not in node_ids:
        raise PublicationHandoffError("artifact producing node is not in the approved plan")
    downstream = {producing_node_id}
    changed = True
    while changed:
        changed = False
        for edge in projected.get("edges", []):
            source, target = str(edge.get("source")), str(edge.get("target"))
            if source in downstream and target in node_ids and target not in downstream:
                downstream.add(target)
                changed = True
    return downstream


async def request_publication_revision(
    db: AsyncSession,
    store: PublicationStore,
    schedule_id: str,
    *,
    envelope: dict[str, Any],
    envelope_hash: str,
    attempt_id: str,
    bundle: dict[str, Any],
    review_raw: bytes,
) -> dict[str, Any]:
    """Bind one terminal rejection to the same scheduled execution and retry it."""
    if not isinstance(envelope, dict) or set(envelope) != {
        "version", "schedule_id", "workflow_id", "execution_id", "plan_id",
        "plan_hash", "activation_revision", "primary_agent_id", "artifact_id",
        "artifact_sha256", "scheduled_for",
    }:
        raise PublicationHandoffError("revision requires the exact handoff envelope")
    if envelope.get("schedule_id") != schedule_id or envelope.get("version") != "publication-workflow-handoff-v1":
        raise PublicationHandoffError("revision envelope schedule binding mismatch")
    if hashlib.sha256(canonical_json(envelope)).hexdigest() != envelope_hash:
        raise PublicationHandoffError("revision envelope hash mismatch")
    schedule, workflow, execution = await _bound_rows(
        db, schedule_id, execution_id=envelope.get("execution_id"), lock=True,
        allow_revision_queued=True,
    )
    if any(envelope.get(key) != value for key, value in {
        "workflow_id": workflow.id,
        "plan_id": execution.plan_id,
        "execution_id": execution.id,
    }.items()):
        raise PublicationHandoffError("revision envelope authority binding mismatch")
    artifact = await db.get(WorkflowArtifact, envelope.get("artifact_id"))
    if (
        artifact is None
        or artifact.execution_id != execution.id
        or artifact.content_hash != envelope.get("artifact_sha256")
        or artifact.kind != "final"
        or artifact.node_run_id is None
        or _envelope(schedule, workflow, execution, artifact) != envelope
    ):
        raise PublicationHandoffError("revision artifact is not the exact current selected final artifact")
    root = run_root(execution).resolve()
    artifact_path = (root / artifact.relative_path).resolve()
    if root not in artifact_path.parents or not artifact_path.is_file() or artifact_path.is_symlink():
        raise PublicationHandoffError("workflow artifact path is invalid")
    try:
        raw = read_verified_artifact_bytes(artifact_path, artifact.content_hash)
    except (OSError, ValueError) as exc:
        raise PublicationHandoffError("workflow artifact changed before revision") from exc
    workflow_content = validate_ai_toolkit_artifact(raw)
    publication, feedback = _verify_terminal_rejection(
        store, bundle, review_raw, attempt_id=attempt_id,
        artifact_hash=artifact.content_hash, envelope_hash=envelope_hash,
        workflow_content=workflow_content,
    )
    plan = await db.get(WorkflowPlanVersion, execution.plan_id)
    producer = await db.get(WorkflowNodeRun, artifact.node_run_id)
    if plan is None or producer is None or producer.execution_id != execution.id:
        raise PublicationHandoffError("artifact producing node is unavailable")
    reset_ids = _reset_node_ids(plan.dsl, producer.node_id)
    binding = {
        "schedule_id": schedule.id,
        "execution_id": execution.id,
        "artifact_id": artifact.id,
        "artifact_sha256": artifact.content_hash,
        "envelope_sha256": envelope_hash,
        "from_node_id": producer.node_id,
        **publication,
        "reviewer_gaps": feedback,
    }
    comment = canonical_json(binding).decode("utf-8")
    if len(comment.encode("utf-8")) > MAX_REVISION_FEEDBACK_BYTES * 2:
        raise PublicationHandoffError("revision request is too large")
    requests = list((await db.execute(select(WorkflowApproval).where(
        WorkflowApproval.execution_id == execution.id,
        WorkflowApproval.approval_type == "publication_revision",
    ))).scalars().all())
    matching: WorkflowApproval | None = None
    scope = (artifact.id, attempt_id, envelope_hash)
    for prior in requests:
        if prior.plan_id != artifact.id:
            continue
        try:
            prior_binding = json.loads(prior.comment)
        except json.JSONDecodeError:
            prior_binding = None
        prior_scope = (
            prior_binding.get("artifact_id"),
            prior_binding.get("attempt_id"),
            prior_binding.get("envelope_sha256"),
        ) if isinstance(prior_binding, dict) else None
        if prior_scope != scope or prior_binding != binding:
            raise PublicationHandoffError("publication revision request conflicts")
        if prior.decision not in {"prepared", "requested"} or matching is not None:
            raise PublicationHandoffError("publication revision request conflicts")
        matching = prior
    if matching is not None and matching.decision == "requested":
        if execution.status not in REVISION_DISPATCH_STATUSES or artifact.selected_for_publish:
            raise PublicationHandoffError("publication revision request state conflicts")
        return {"status": "queued", **binding, "idempotent": True}

    if matching is None:
        if execution.status != "awaiting_review" or not artifact.selected_for_publish:
            raise PublicationHandoffError("workflow artifact is no longer eligible for revision")
        nodes = list((await db.execute(select(WorkflowNodeRun).where(
            WorkflowNodeRun.execution_id == execution.id,
            WorkflowNodeRun.node_id.in_(reset_ids),
        ))).scalars().all())
        if {node.node_id for node in nodes} != reset_ids:
            raise PublicationHandoffError("approved plan node state is incomplete")
        for node in nodes:
            node.status = "pending"
            node.output_summary = ""
            node.error_message = None
            node.started_at = None
            node.finished_at = None
        artifact.selected_for_publish = False
        execution.status = "queued"
        execution.progress = min((node.position for node in nodes), default=0)
        execution.finished_at = None
        execution.error_message = None
        execution.lease_owner = None
        execution.lease_until = None
        workflow.status = "ready"
        schedule.last_result = "queued"
        matching = WorkflowApproval(
            id=f"wfa_{uuid.uuid4().hex}", workflow_id=workflow.id,
            execution_id=execution.id, plan_id=artifact.id,
            plan_hash=artifact.content_hash,
            activation_revision=int((artifact.metadata_json or {}).get("artifact_version") or 1),
            approval_type="publication_revision", decision="prepared",
            actor_id=schedule.owner_user_id, comment=comment,
        )
        db.add(matching)
        db.add(WorkflowEvent(
            execution_id=execution.id, event_type="publication_revision_prepared",
            message="Terminal independent-review rejection prepared for Workflow retry",
            payload=binding,
        ))
        await db.flush()
        await db.commit()
    else:
        if execution.status not in REVISION_DISPATCH_STATUSES or artifact.selected_for_publish:
            raise PublicationHandoffError("publication revision request state conflicts")
        # Release the row lock before contacting Hermes. The durable prepared row
        # is the retryable outbox marker if the process or network fails.
        await db.commit()

    from backend.services.workflow_executor import retry_remote

    try:
        await retry_remote(execution.id, producer.node_id, canonical_json({
            "publication_revision": publication,
            "reviewer_gaps": feedback,
        }).decode("utf-8"))
    except Exception as exc:
        raise PublicationHandoffError(
            "Hermes revision retry failed; durable request remains prepared and queued"
        ) from exc

    prepared = (await db.execute(
        select(WorkflowApproval).where(WorkflowApproval.id == matching.id)
        .execution_options(populate_existing=True).with_for_update()
    )).scalar_one_or_none()
    current_execution = (await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == execution.id)
        .execution_options(populate_existing=True).with_for_update()
    )).scalar_one_or_none()
    current_artifact = (await db.execute(
        select(WorkflowArtifact).where(WorkflowArtifact.id == artifact.id)
        .execution_options(populate_existing=True).with_for_update()
    )).scalar_one_or_none()
    if (
        prepared is None
        or prepared.decision != "prepared"
        or prepared.comment != comment
        or current_execution is None
        or current_execution.status not in REVISION_DISPATCH_STATUSES
        or current_artifact is None
        or current_artifact.selected_for_publish
    ):
        raise PublicationHandoffError("publication revision dispatch state conflicts")
    prepared.decision = "requested"
    db.add(WorkflowEvent(
        execution_id=execution.id, event_type="publication_revision_requested",
        message="Terminal independent-review rejection dispatched to producing Workflow node",
        payload=binding,
    ))
    await db.commit()
    return {"status": "queued", **binding, "idempotent": False}
