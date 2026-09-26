"""Narrow, schedule-bound WorkflowArtifact to publication handoff."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

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

SCHEMA_VERSION = "ai-toolkit-publication-content-v2"
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
HASH = re.compile(r"[0-9a-f]{64}\Z")
KIND = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
TOP_LEVEL_FIELDS = {
    "schema_version",
    "title",
    "summary",
    "body",
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


def validate_publication_artifact(raw: bytes) -> dict[str, Any]:
    """Validate the exact content-only artifact contract; reject control fields."""
    if not raw or len(raw) > MAX_ARTIFACT_BYTES:
        raise PublicationHandoffError("workflow artifact size is invalid")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicationHandoffError("workflow artifact must be UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != TOP_LEVEL_FIELDS:
        raise PublicationHandoffError("workflow artifact has missing, unknown, or forbidden fields")
    if value["schema_version"] not in {SCHEMA_VERSION, "publication-content-v1"}:
        raise PublicationHandoffError("workflow artifact schema version is invalid")
    for field, limit in (("title", 300), ("summary", 2000), ("body", MAX_ARTIFACT_BYTES)):
        item = value[field]
        if not isinstance(item, str) or not item.strip() or len(item.encode("utf-8")) > limit:
            raise PublicationHandoffError(f"workflow artifact {field} is invalid")
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
    publication_system_fields(value)
    return value


def validate_ai_toolkit_artifact(raw: bytes) -> dict[str, Any]:
    """Compatibility name for the original content-only contract."""
    return validate_publication_artifact(raw)


def configured_handoff_schedule(series_id: str = "ai-toolkit") -> str:
    from backend.services.knowledge_publication_store import SERIES

    config = SERIES.get(series_id)
    if not config or not config.get("enabled", True):
        raise PublicationHandoffError("publication series is unknown or disabled")
    value = config.get("workflow_schedule_id")
    if not value and series_id == "ai-toolkit":
        value = os.environ.get("PUBLICATION_AI_TOOLKIT_SCHEDULE_ID", "")
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,47}", value):
        raise PublicationHandoffError("publication series has no configured workflow schedule")
    for other_id, other in SERIES.items():
        other_schedule = other.get("workflow_schedule_id") or (os.environ.get("PUBLICATION_AI_TOOLKIT_SCHEDULE_ID") if other_id == "ai-toolkit" else None)
        if other_id != series_id and other.get("enabled", True) and other_schedule == value:
            raise PublicationHandoffError("publication schedule must belong to exactly one series")
    return value


def publication_occurrence(series_id: str, scheduled_for: datetime) -> dict[str, Any]:
    from backend.services.knowledge_publication_store import SERIES, publication_slot

    config = SERIES[series_id]
    if scheduled_for is None:
        raise PublicationHandoffError("scheduled publication occurrence is missing")
    if scheduled_for.tzinfo is None:
        scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)
    local = scheduled_for.astimezone(ZoneInfo("Asia/Shanghai"))
    slot = config.get("author_release_slot")
    if not slot:
        slot = next((item for item in sorted(config.get("release_times", ["12:00"]))
                     if item >= local.strftime("%H:%M")), None)
    if not slot:
        raise PublicationHandoffError("workflow occurrence has no same-day release slot")
    return {"series_id": series_id, "issue_date": local.date().isoformat(),
            **publication_slot(series_id, local.date().isoformat(), slot)}


def publication_system_fields(content: dict[str, Any], series_id: str = "ai-toolkit") -> dict[str, Any]:
    """Generate publication policy fields without involving the writing Agent."""
    urls: list[str] = []
    for document in content.get("source_documents", []):
        for token in re.findall(r"https://[^\s<>\]\[(){}（）“”‘’「」『』\"']+", document.get("content", "")):
            candidate = token.rstrip(".,;:!?，。；：！？")
            try:
                parsed = urlsplit(candidate)
            except ValueError:
                continue
            if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
                if candidate not in urls:
                    urls.append(candidate)
    if not urls:
        raise PublicationHandoffError("workflow artifact has no HTTPS source evidence")
    title = content["title"].strip()
    brief = {
        "genre": "tutorial",
        "question": f"普通读者如何按照《{title}》完成一个可复现、可验收的真实任务？",
        "thesis": "本教程必须用逐步操作、可复制输入、预期结果和验收标准证明任务可完成，并明确失败恢复路径。",
        "reader_value": "读者可以在不依赖隐含配置的前提下复现流程、核对结果，并判断何时应停止或改用其他方案。",
        "novelty": "价值不在罗列功能，而在把真实任务、操作步骤、证据、边界条件和验收方法编排成闭环。",
        "counterargument": "工具能力、账号权限、地区供应、成本与界面可能变化，因此教程不能把单次结果承诺为普遍结论。",
        "uncertainties": [
            "厂商界面、套餐、模型能力和地区可用性可能在发表后发生变化。",
            "未由执行证据覆盖的步骤只能作为操作说明，不能宣称已经实测成功。",
        ],
        "evidence_urls": urls[:20],
        "selection_reason": "候选材料至少包含一个可追溯来源，且能够支撑面向普通读者的完整任务教程。",
    }
    from backend.services.knowledge_publication_store import SERIES
    config = SERIES.get(series_id)
    if not config:
        raise PublicationHandoffError("publication series is unknown")
    genre = config.get("genre", "tutorial" if series_id == "ai-toolkit" else "feature")
    if genre != "tutorial":
        brief.update({
            "genre": genre,
            "question": f"《{title}》围绕哪些事实与解释展开，读者应该如何理解其背景、因果与争议？",
            "thesis": "文章必须以可追溯材料支撑主要论点，区分已知事实、解释与推测，呈现背景、因果、反例及结论适用边界。",
            "reader_value": "读者可以理解主题的发展脉络、关键事实与不同解释，并依据来源独立核对重要判断。",
            "novelty": "文章的价值来自证据组织、背景解释与观点比较，而非材料堆砌或未经验证的确定性叙述。",
            "counterargument": "材料存在选择偏差、时代背景和记录局限，单一来源不足以排除其他解释或建立普遍因果结论。",
            "uncertainties": ["材料覆盖范围及来源立场可能限制结论，应明确记载缺失和解释分歧。"],
            "selection_reason": "候选材料具有可追溯来源，足以围绕本系列主题提出问题、组织证据并解释其意义。",
        })
    reasons = validate_editorial_brief(brief)
    if reasons:
        raise PublicationHandoffError(
            f"deterministic editorial brief is invalid: {','.join(reasons)}"
        )
    return {
        "editorial_brief": brief,
        "learning_objectives": ([
            "按教程步骤完成一个真实任务，并得到可以回读和核对的输出结果。",
            "使用明确的验收标准判断结果是否合格，而不是把命令成功当成任务成功。",
            "识别失败恢复、隐私、成本、账号权限和地区可用性边界。",
        ] if genre == "tutorial" else [
            "梳理主题背景、关键事件与证据来源，区分事实、解释与尚未确认的推测。",
            "比较主要观点及其反例，理解结论适用范围，并能独立核对重要判断。",
        ]),
    }


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
    series_id: str | None = None,
) -> dict[str, Any]:
    scheduled_for = execution.scheduled_for
    if scheduled_for is not None and scheduled_for.tzinfo is None:
        scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)
    envelope = {
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

    if series_id is not None:
        if configured_handoff_schedule(series_id) != schedule.id:
            raise PublicationHandoffError("publication schedule binding mismatch")
        native_session = (execution.hermes_session_id or "").strip()
        if not native_session or native_session == "hermes:":
            raise PublicationHandoffError("workflow author native session is unavailable")
        writer_session = native_session if native_session.startswith("hermes:") else f"hermes:{native_session}"
        envelope.update(version="publication-workflow-handoff-v2",
                        writer_session=writer_session,
                        **publication_occurrence(series_id, scheduled_for))
    return envelope


async def _bound_rows(
    db: AsyncSession,
    schedule_id: str,
    *,
    execution_id: str | None = None,
    lock: bool = False,
    allow_completed: bool = False,
    allow_revision_queued: bool = False,
    missing_is_pending: bool = False,
    occurrence_series_id: str | None = None,
    issue_key: str | None = None,
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
    explicit_execution = execution_id is not None
    occurrence_requested = occurrence_series_id is not None and issue_key is not None
    if execution_id is None and not occurrence_requested and schedule.last_execution_id:
        execution_id = schedule.last_execution_id
    if execution_id is not None:
        execution_query = execution_query.where(WorkflowExecution.id == execution_id)
    if lock:
        execution_query = execution_query.with_for_update()
    executions = list((await db.execute(execution_query)).scalars().all())
    if occurrence_requested:
        matching = []
        for candidate in executions:
            try:
                occurrence = publication_occurrence(occurrence_series_id, candidate.scheduled_for)
            except PublicationHandoffError:
                continue
            if occurrence["issue_key"] == issue_key:
                matching.append(candidate)
        executions = matching
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
    if not explicit_execution and not occurrence_requested and schedule.last_execution_id not in {None, execution.id}:
        raise PublicationHandoffError("schedule last execution binding conflicts")
    return schedule, workflow, execution


async def _validate_terminal_artifact(db, schedule, execution, artifact):
    if artifact.kind == "draft":
        plan = await db.get(WorkflowPlanVersion, schedule.plan_id)
        node_run = await db.get(WorkflowNodeRun, artifact.node_run_id) if artifact.node_run_id else None
        dsl = plan.dsl if plan is not None and isinstance(plan.dsl, dict) else {}
        raw_nodes = dsl.get("nodes")
        raw_edges = dsl.get("edges")
        nodes = raw_nodes if isinstance(raw_nodes, list) else []
        edges = raw_edges if isinstance(raw_edges, list) else []
        node_ids = {
            str(node.get("id") or "") for node in nodes if isinstance(node, dict)
        }
        nonterminal_ids = {
            str(edge.get("source") or "") for edge in edges if isinstance(edge, dict)
        }
        terminal_ids = node_ids - nonterminal_ids
        if (
            node_run is None
            or node_run.execution_id != execution.id
            or node_run.node_id not in terminal_ids
        ):
            raise PublicationHandoffError("selected draft artifact is not a terminal Workflow result")


async def export_publication_handoff(db: AsyncSession, schedule_id: str, *, series_id: str | None = None, issue_key: str | None = None) -> dict[str, Any]:
    if series_id is not None and configured_handoff_schedule(series_id) != schedule_id:
        raise PublicationHandoffError("publication schedule binding mismatch")
    try:
        schedule, workflow, execution = await _bound_rows(
            db, schedule_id, missing_is_pending=True, lock=series_id is not None,
            allow_revision_queued=series_id is not None,
            occurrence_series_id=series_id, issue_key=issue_key,
        )
    except PublicationWorkflowPending:
        return {"status": "waiting_workflow", "available": False}
    if issue_key is not None and (series_id is None or publication_occurrence(series_id, execution.scheduled_for)["issue_key"] != issue_key):
        return {"status": "waiting_workflow", "available": False}
    if execution.status != "awaiting_review":
        prepared = list((await db.execute(select(WorkflowApproval).where(
            WorkflowApproval.execution_id == execution.id,
            WorkflowApproval.approval_type == "publication_revision",
            WorkflowApproval.decision == "prepared",
        ))).scalars().all())
        if not prepared:
            return {"status": "waiting_workflow", "available": False}
        if len(prepared) != 1:
            raise PublicationHandoffError("publication prepared revision state conflicts")
        binding = json.loads(prepared[0].comment)
        if binding.get("source") != "deterministic_preflight":
            return {"status": "waiting_workflow", "available": False}
        artifact = await db.get(WorkflowArtifact, binding["artifact_id"])
        if artifact is None or artifact.execution_id != execution.id:
            raise PublicationHandoffError("prepared preflight artifact is unavailable")
        envelope = _envelope(schedule, workflow, execution, artifact, series_id)
        if hashlib.sha256(canonical_json(envelope)).hexdigest() != binding["envelope_sha256"]:
            raise PublicationHandoffError("prepared preflight authority changed")
        await _validate_terminal_artifact(db, schedule, execution, artifact)
        root = run_root(execution).resolve()
        path = (root / artifact.relative_path).resolve()
        if root not in path.parents or not path.is_file() or path.is_symlink():
            raise PublicationHandoffError("prepared preflight artifact path is invalid")
        try:
            validate_publication_artifact(read_verified_artifact_bytes(path, artifact.content_hash))
        except (OSError, ValueError) as exc:
            raise PublicationHandoffError("prepared preflight artifact changed") from exc
        publication = {key: binding[key] for key in ("source", "attempt_id", "issue_id", "revision", "target_hash", "review_sha256")}
        result = await _dispatch_revision(db, schedule, workflow, execution, artifact,
                                         binding["envelope_sha256"], binding["attempt_id"],
                                         publication, binding["reviewer_gaps"])
        return {"status": "preflight_revision_requested", "available": False,
                "execution_id": execution.id, "revision": result["revision"]}
    artifacts = list(
        (
            await db.execute(
                select(WorkflowArtifact).where(
                    WorkflowArtifact.execution_id == execution.id,
                    WorkflowArtifact.selected_for_publish.is_(True),
                    WorkflowArtifact.kind.in_(("final", "draft")),
                )
            )
        ).scalars().all()
    )
    if len(artifacts) != 1:
        raise PublicationHandoffError("execution must have exactly one selected terminal artifact")
    artifact = artifacts[0]
    await _validate_terminal_artifact(db, schedule, execution, artifact)
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
    content = validate_publication_artifact(raw)
    envelope = _envelope(schedule, workflow, execution, artifact, series_id)
    envelope_raw = canonical_json(envelope)
    if series_id is not None:
        from backend.services.knowledge_publication_store import SERIES
        from backend.services.publication_editorial import make_editorial_contract, validate_editorial
        fields = publication_system_fields(content, series_id)
        contract = make_editorial_contract(content["body"], format=SERIES[series_id].get("format", "chapter"),
            writer_sessions=[envelope["writer_session"]], revision=1, **fields)
        reasons = [reason for reason in validate_editorial(content["body"], contract)
                   if reason.startswith("quality.")]
        if reasons:
            previous = list((await db.execute(select(WorkflowApproval).where(
                WorkflowApproval.execution_id == execution.id,
                WorkflowApproval.approval_type == "publication_revision",
            ))).scalars().all())
            if len(previous) >= 3:
                raise PublicationHandoffError("publication content revision budget exhausted: " + ",".join(reasons))
            feedback = [{"id": f"preflight_{index}",
                         "question": f"正文未通过程序质量门禁，请修订内容：{reason}",
                         "acceptance_criterion": f"按既有出版质量标准修订正文并通过检查 {reason}；禁止重复段落凑字数。"}
                        for index, reason in enumerate(reasons[:MAX_REVISION_GAPS], 1)]
            digest = hashlib.sha256(canonical_json({"artifact": artifact.content_hash, "reasons": reasons})).hexdigest()
            publication = {"source": "deterministic_preflight", "attempt_id": f"preflight_{digest}",
                           "issue_id": f"{series_id}:{envelope['issue_key']}", "revision": len(previous) + 1,
                           "target_hash": contract["target_hash"], "review_sha256": digest}
            result = await _dispatch_revision(db, schedule, workflow, execution, artifact,
                hashlib.sha256(envelope_raw).hexdigest(), publication["attempt_id"], publication, feedback)
            return {"status": "preflight_revision_requested", "available": False,
                    "execution_id": execution.id, "revision": result["revision"], "reasons": reasons}
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
    series_id: str = "ai-toolkit",
) -> dict[str, Any]:
    if not all(HASH.fullmatch(value or "") for value in (artifact_hash, envelope_hash)):
        raise PublicationHandoffError("handoff hashes are invalid")
    try:
        from backend.services.knowledge_publication_store import validate_bundle

        normalized, _ = validate_bundle(bundle)
        contract = normalized.get("quality_contract")
        if not isinstance(contract, dict) or contract.get("attempt_id") != attempt_id:
            raise PublicationHandoffError("publication attempt binding mismatch")
        system_fields = publication_system_fields(workflow_content, series_id)
        if (
            normalized.get("series_id") != series_id
            or normalized.get("title") != workflow_content["title"]
            or normalized.get("summary") != workflow_content["summary"]
            or normalized.get("body") != workflow_content["body"]
            or contract.get("editorial_brief") != system_fields["editorial_brief"]
            or contract.get("learning_objectives") != system_fields["learning_objectives"]
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


def _verify_occurrence_bundle(envelope: dict[str, Any], bundle: dict[str, Any]) -> None:
    if envelope["version"] != "publication-workflow-handoff-v2":
        return
    from backend.services.knowledge_publication_store import publication_slot
    try:
        occurrence = publication_slot(bundle.get("series_id"), bundle.get("issue_date"), bundle.get("issue_slot"))
        release_matches = datetime.fromisoformat(bundle["release_at"]) == datetime.fromisoformat(envelope["release_at"])
    except (ValueError, TypeError, KeyError, PublicationError) as exc:
        raise PublicationHandoffError("publication occurrence binding is invalid") from exc
    if (bundle.get("series_id") != envelope["series_id"] or occurrence["issue_key"] != envelope["issue_key"]
            or not release_matches
            or bundle.get("quality_contract", {}).get("writer_sessions") != [envelope["writer_session"]]):
        raise PublicationHandoffError("publication occurrence or author binding mismatch")


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
    series_id: str | None = None,
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
        or artifact.kind not in {"final", "draft"}
    ):
        raise PublicationHandoffError("workflow artifact acknowledgement binding mismatch")
    current_envelope = _envelope(schedule, workflow, execution, artifact, series_id)
    _verify_occurrence_bundle(current_envelope, bundle)
    current_envelope_hash = hashlib.sha256(canonical_json(current_envelope)).hexdigest()
    if current_envelope_hash != envelope_hash:
        raise PublicationHandoffError("workflow handoff envelope no longer matches current authority")
    await _validate_terminal_artifact(db, schedule, execution, artifact)
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
        workflow_content=workflow_content, series_id=series_id or "ai-toolkit",
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
    series_id: str = "ai-toolkit",
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    try:
        from backend.services.knowledge_publication_store import validate_bundle

        normalized, _ = validate_bundle(bundle)
        contract = normalized.get("quality_contract")
        if not isinstance(contract, dict) or contract.get("attempt_id") != attempt_id:
            raise PublicationHandoffError("publication attempt binding mismatch")
        system_fields = publication_system_fields(workflow_content, series_id)
        if (
            normalized.get("series_id") != series_id
            or normalized.get("title") != workflow_content["title"]
            or normalized.get("summary") != workflow_content["summary"]
            or normalized.get("body") != workflow_content["body"]
            or contract.get("editorial_brief") != system_fields["editorial_brief"]
            or contract.get("learning_objectives") != system_fields["learning_objectives"]
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
    series_id: str | None = None,
) -> dict[str, Any]:
    """Bind one terminal rejection to the same scheduled execution and retry it."""
    expected_fields = {
        "version", "schedule_id", "workflow_id", "execution_id", "plan_id",
        "plan_hash", "activation_revision", "primary_agent_id", "artifact_id",
        "artifact_sha256", "scheduled_for",
    }
    if series_id is not None:
        expected_fields.update({"series_id", "issue_date", "issue_key", "issue_slot", "release_at", "writer_session"})
    if not isinstance(envelope, dict) or set(envelope) != expected_fields:
        raise PublicationHandoffError("revision requires the exact handoff envelope")
    if envelope.get("schedule_id") != schedule_id or envelope.get("version") != ("publication-workflow-handoff-v2" if series_id is not None else "publication-workflow-handoff-v1"):
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
        or artifact.kind not in {"final", "draft"}
        or artifact.node_run_id is None
        or _envelope(schedule, workflow, execution, artifact, series_id) != envelope
    ):
        raise PublicationHandoffError("revision artifact is not the exact current selected final artifact")
    await _validate_terminal_artifact(db, schedule, execution, artifact)
    root = run_root(execution).resolve()
    artifact_path = (root / artifact.relative_path).resolve()
    if root not in artifact_path.parents or not artifact_path.is_file() or artifact_path.is_symlink():
        raise PublicationHandoffError("workflow artifact path is invalid")
    try:
        raw = read_verified_artifact_bytes(artifact_path, artifact.content_hash)
    except (OSError, ValueError) as exc:
        raise PublicationHandoffError("workflow artifact changed before revision") from exc
    workflow_content = validate_ai_toolkit_artifact(raw)
    _verify_occurrence_bundle(envelope, bundle)
    publication, feedback = _verify_terminal_rejection(
        store, bundle, review_raw, attempt_id=attempt_id,
        artifact_hash=artifact.content_hash, envelope_hash=envelope_hash,
        workflow_content=workflow_content, series_id=series_id or "ai-toolkit",
    )
    return await _dispatch_revision(db, schedule, workflow, execution, artifact,
                                    envelope_hash, attempt_id, publication, feedback)


async def _dispatch_revision(db, schedule, workflow, execution, artifact,
                             envelope_hash, attempt_id, publication, feedback):
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
            message="Publication content revision prepared for Workflow retry",
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
        message="Publication content revision dispatched to producing Workflow node",
        payload=binding,
    ))
    await db.commit()
    return {"status": "queued", **binding, "idempotent": False}
