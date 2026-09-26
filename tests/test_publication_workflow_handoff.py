"""Local-only WorkflowArtifact to publication handoff regressions."""

from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.db import Base, canonical_plan_hash
from backend.models.tenant_agent import TenantAgentModel
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
from backend.services import workflow_execution_start, workflow_executor, workflow_scheduler
from backend.services.knowledge_publication_store import PublicationStore, receipt_set_hash
from backend.services.publication_workflow_handoff import (
    PublicationHandoffError,
    acknowledge_publication_handoff,
    canonical_json,
    export_publication_handoff,
    publication_system_fields,
    request_publication_revision,
    validate_ai_toolkit_artifact,
)
from backend.services.workflow_artifacts import store_artifact
from scripts import publication_editorial_remote
from scripts.publication_workflow_handoff import DB_FILE, materialize_export
from publication_editorial_fixture import approve_fixture
from test_publication_editorial_workflow import draft


def artifact_value() -> dict:
    return {
        "schema_version": "ai-toolkit-publication-content-v2",
        "title": "合成工具教程",
        "summary": "仅用于验证工作流到出版系统的内容交接。",
        "body": "## 合成工具教程\n\n" + "本段只用于自动化契约验证。" * 300,
        "source_documents": [{
            "kind": "source_snapshot",
            "content": "Synthetic source: https://example.org/ai-toolkit-source",
        }],
        "execution_documents": [{"kind": "execution_log", "content": "synthetic execution only"}],
    }


@pytest_asyncio.fixture
async def handoff_db(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path / "vault"))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'workflow.db'}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def allow_policy(*args, **kwargs):
        return None

    monkeypatch.setattr(workflow_execution_start, "validate_plan_policy", allow_policy)
    dsl = {
        "plan_id": "wfp_toolkit",
        "name": "ai toolkit publication",
        "version": "1.0.0",
        "nodes": [
            {
                "id": "author",
                "node_type": "LLM_INFERENCE",
                "name": "author",
                "parameters": {
                    "agent_id": "main_agent",
                    "instruction": "write content-only publication JSON",
                    "max_tokens": 1000,
                    "knowledge_scope": [],
                    "allow_network": False,
                },
            }
        ],
        "edges": [],
    }
    plan_hash = canonical_plan_hash(dsl)
    raw = canonical_json(artifact_value())
    async with maker() as db:
        workflow = WorkflowDefinition(
            id="wf_toolkit",
            tenant_key="tenant-a",
            created_by="owner-a",
            title="AI toolkit",
            description="content workflow",
            status="ready",
            active_plan_id="wfp_toolkit",
            primary_agent_id="agent_toolkit",
        )
        db.add(workflow)
        await db.flush()
        db.add(
            WorkflowPlanVersion(
                id="wfp_toolkit",
                workflow_id=workflow.id,
                version=1,
                dsl=dsl,
                content_hash=plan_hash,
                activation_revision=1,
                goal="write",
                deliverable="strict JSON",
                allow_network=False,
                max_tokens=1000,
                knowledge_scope=[],
                validation_errors=[],
                frozen_at=datetime.now(timezone.utc),
            )
        )
        db.add(
            TenantAgentModel(
                id="agent_toolkit",
                tenant_id="tenant-a",
                owner_user_id="owner-a",
                origin_workflow_id=workflow.id,
                visibility="private",
                base_agent_id="main_agent",
                composition_manifest={"plan_id": "wfp_toolkit"},
                is_active=True,
            )
        )
        db.add(
            WorkflowApproval(
                id="approval_toolkit",
                workflow_id=workflow.id,
                plan_id="wfp_toolkit",
                plan_hash=plan_hash,
                activation_revision=1,
                approval_type="plan",
                decision="approved",
                actor_id="owner-a",
            )
        )
        execution = WorkflowExecution(
            id="wfr_toolkit",
            workflow_id=workflow.id,
            plan_id="wfp_toolkit",
            tenant_key="tenant-a",
            status="awaiting_review",
            progress=100,
            idempotency_key="scheduled-toolkit",
            trigger_schedule_id="wfsched_toolkit",
            scheduled_for=datetime.now(timezone.utc),
        )
        db.add(execution)
        await db.flush()
        node = WorkflowNodeRun(
            id="wfn_author", execution_id=execution.id, node_id="author",
            node_type="LLM_INFERENCE", name="author", agent_id="main_agent",
            status="succeeded", position=0, attempt=1, max_tokens=1000,
        )
        db.add(node)
        await db.flush()
        artifact = store_artifact(
            execution,
            node_run_id=node.id,
            kind="final",
            title="AI toolkit content",
            content=raw,
            source_kind="hermes_output",
            metadata={"artifact_version": 1},
            extension="json",
        )
        artifact.id = "wfa_toolkit"
        db.add(artifact)
        db.add(
            WorkflowSchedule(
                id="wfsched_toolkit",
                tenant_key="tenant-a",
                owner_user_id="owner-a",
                workflow_id=workflow.id,
                plan_id="wfp_toolkit",
                plan_hash=plan_hash,
                activation_revision=1,
                cron_expression="5 8 * * *",
                timezone="Asia/Shanghai",
                enabled=True,
                last_execution_id=execution.id,
                contract_id=workflow_scheduler.SCHEDULE_CONTRACT_ID,
                contract_version=workflow_scheduler.SCHEDULE_CONTRACT_VERSION,
                handler_id=workflow_scheduler.SCHEDULE_HANDLER_ID,
                handler_version=workflow_scheduler.SCHEDULE_HANDLER_VERSION,
            )
        )
        await db.commit()
    yield maker, tmp_path
    await engine.dispose()


async def exported(maker):
    async with maker() as db:
        return await export_publication_handoff(db, "wfsched_toolkit")


def prepare_publication(store: PublicationStore, export: dict, tmp_path):
    envelope_raw = canonical_json(export["envelope"])
    artifact_raw = base64.b64decode(export["artifact_b64"])
    envelope_path = tmp_path / "workflow-envelope.json"
    artifact_path = tmp_path / "workflow-artifact.json"
    envelope_path.write_bytes(envelope_raw)
    artifact_path.write_bytes(artifact_raw)
    content = validate_ai_toolkit_artifact(artifact_raw)
    value = draft(store, body=content["body"])
    value["series_id"] = "ai-toolkit"
    value["title"] = content["title"]
    value["summary"] = content["summary"]
    system_fields = publication_system_fields(content)
    value["references"] = [
        {"title": f"Evidence {index}", "url": url}
        for index, url in enumerate(system_fields["editorial_brief"]["evidence_urls"], 1)
    ]
    value["quality_contract"] = {
        **value["quality_contract"],
        **system_fields,
    }
    value["source_receipts"].extend(
        [
            store.ingest_file(envelope_path, "workflow_handoff_envelope"),
            store.ingest_file(artifact_path, "workflow_artifact"),
        ]
    )
    value["source_snapshot_hash"] = receipt_set_hash(value["source_receipts"])
    draft_contract = copy.deepcopy(value["quality_contract"])
    value = approve_fixture(store, value, draft=draft_contract)
    value["state"] = "staged"
    staged = store.stage(value)
    return value, {**value["quality_contract"], "edition_id": staged["edition_id"]}


def reject_publication(store: PublicationStore, export: dict, tmp_path):
    envelope_raw = canonical_json(export["envelope"])
    artifact_raw = base64.b64decode(export["artifact_b64"])
    envelope_path = tmp_path / "rejected-workflow-envelope.json"
    artifact_path = tmp_path / "rejected-workflow-artifact.json"
    envelope_path.write_bytes(envelope_raw)
    artifact_path.write_bytes(artifact_raw)
    content = validate_ai_toolkit_artifact(artifact_raw)
    value = draft(store, body=content["body"])
    value.update(series_id="ai-toolkit", title=content["title"], summary=content["summary"])
    system_fields = publication_system_fields(content)
    value["references"] = [
        {"title": f"Evidence {index}", "url": url}
        for index, url in enumerate(system_fields["editorial_brief"]["evidence_urls"], 1)
    ]
    value["quality_contract"] = {
        **value["quality_contract"],
        **system_fields,
    }
    value["source_receipts"].extend([
        store.ingest_file(envelope_path, "workflow_handoff_envelope"),
        store.ingest_file(artifact_path, "workflow_artifact"),
    ])
    value["source_snapshot_hash"] = receipt_set_hash(value["source_receipts"])
    attempt = store.prepare_editorial(value)
    value["quality_contract"] = attempt["quality_contract"]
    review = {
        "decision": "rejected",
        "content_hash": value["body_hash"],
        "editorial_target_hash": attempt["target_hash"],
        "revision": attempt["revision"],
        "attempt_id": attempt["attempt_id"],
        "research_gaps": [{
            "id": "mechanism_gap",
            "question": "需要补充机制如何影响教程中的具体实例结果。",
            "acceptance_criterion": "用可核验来源和完整实例解释机制、边界与结果。",
        }],
    }
    review_raw = canonical_json(review)
    review_path = tmp_path / "rejected-review.json"
    review_path.write_bytes(review_raw)
    rejected = store.record_editorial_review(value, review_path)
    assert rejected["state"] == "rejected"
    return value, attempt, review_raw


def test_content_schema_rejects_unknown_authority_fields_and_non_json():
    value = artifact_value()
    value["tenant_key"] = "attacker"
    with pytest.raises(PublicationHandoffError, match="forbidden"):
        validate_ai_toolkit_artifact(canonical_json(value))
    with pytest.raises(PublicationHandoffError, match="UTF-8 JSON"):
        validate_ai_toolkit_artifact(b"not-json")


def test_system_fields_are_deterministic_and_forbidden_in_writer_artifact():
    content = artifact_value()
    first = publication_system_fields(validate_ai_toolkit_artifact(canonical_json(content)))
    second = publication_system_fields(copy.deepcopy(content))
    assert first == second
    assert first["editorial_brief"]["evidence_urls"] == [
        "https://example.org/ai-toolkit-source"
    ]
    assert len(first["learning_objectives"]) == 3

    content["editorial_brief"] = first["editorial_brief"]
    with pytest.raises(PublicationHandoffError, match="forbidden"):
        validate_ai_toolkit_artifact(canonical_json(content))

    no_source = artifact_value()
    no_source["source_documents"][0]["content"] = "no URL"
    with pytest.raises(PublicationHandoffError, match="no HTTPS source"):
        validate_ai_toolkit_artifact(canonical_json(no_source))


@pytest.mark.asyncio
async def test_export_is_exact_schedule_bound_and_rejects_revocation(handoff_db):
    maker, _ = handoff_db
    value = await exported(maker)
    raw = base64.b64decode(value["artifact_b64"])
    assert hashlib.sha256(raw).hexdigest() == value["envelope"]["artifact_sha256"]
    async with maker() as db:
        schedule = await db.get(WorkflowSchedule, "wfsched_toolkit")
        schedule.owner_user_id = "attacker"
        await db.commit()
    with pytest.raises(PublicationHandoffError, match="authority"):
        await exported(maker)
    async with maker() as db:
        schedule = await db.get(WorkflowSchedule, "wfsched_toolkit")
        schedule.owner_user_id = "owner-a"
        schedule.enabled = False
        await db.commit()
    with pytest.raises(PublicationHandoffError, match="revoked"):
        await exported(maker)


@pytest.mark.asyncio
async def test_export_accepts_selected_terminal_draft_from_llm_final_node(handoff_db):
    maker, _ = handoff_db
    async with maker() as db:
        artifact = await db.get(WorkflowArtifact, "wfa_toolkit")
        artifact.kind = "draft"
        await db.commit()
    value = await exported(maker)
    assert value["envelope"]["artifact_id"] == "wfa_toolkit"
    assert base64.b64decode(value["artifact_b64"])


@pytest.mark.asyncio
async def test_export_rejects_artifact_byte_hash_mismatch(handoff_db):
    maker, tmp_path = handoff_db
    async with maker() as db:
        artifact = await db.get(WorkflowArtifact, "wfa_toolkit")
        execution = await db.get(WorkflowExecution, "wfr_toolkit")
        path = (tmp_path / "vault" / "workflows" / execution.tenant_key / execution.workflow_id /
                "runs" / execution.id / artifact.relative_path)
        path.write_bytes(b"{}")
    with pytest.raises(PublicationHandoffError, match="do not match"):
        await exported(maker)


@pytest.mark.asyncio
async def test_export_and_local_fetch_treat_no_awaiting_workflow_as_normal(handoff_db):
    maker, tmp_path = handoff_db
    async with maker() as db:
        execution = await db.get(WorkflowExecution, "wfr_toolkit")
        execution.status = "running"
        await db.commit()
    result = await exported(maker)
    assert result == {"status": "waiting_workflow", "available": False}
    output = tmp_path / "not-created"
    assert materialize_export(
        result, output, expected_schedule_id="wfsched_toolkit"
    ) == result
    assert not output.exists()


def test_materializer_recovers_after_rename_crash_and_detects_conflict(tmp_path):
    raw = canonical_json(artifact_value())
    envelope = {
        "version": "publication-workflow-handoff-v1",
        "schedule_id": "wfsched_toolkit",
        "workflow_id": "wf_toolkit",
        "execution_id": "wfr_toolkit",
        "plan_id": "wfp_toolkit",
        "plan_hash": "1" * 64,
        "activation_revision": 1,
        "primary_agent_id": "agent_toolkit",
        "artifact_id": "wfa_toolkit",
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "scheduled_for": "2026-09-26T00:05:00+00:00",
    }
    envelope_raw = canonical_json(envelope)
    value = {
        "envelope": envelope,
        "envelope_sha256": hashlib.sha256(envelope_raw).hexdigest(),
        "artifact_b64": base64.b64encode(raw).decode("ascii"),
    }
    with pytest.raises(RuntimeError, match="synthetic crash"):
        materialize_export(
            value, tmp_path, expected_schedule_id="wfsched_toolkit", _fail_after_rename=True
        )
    result = materialize_export(value, tmp_path, expected_schedule_id="wfsched_toolkit")
    assert result["status"] == "waiting_assets"
    output = tmp_path / "ai-toolkit-wfa_toolkit"
    assert not (output / "draft-manifest.json").exists()
    assert not any(output.glob("*.png"))
    with sqlite3.connect(tmp_path / DB_FILE) as db:
        assert db.execute(
            "SELECT status FROM publication_workflow_consumptions WHERE artifact_id='wfa_toolkit'"
        ).fetchone()[0] == "waiting_assets"
    (output / "body.md").write_text("tampered", encoding="utf-8")
    with pytest.raises(PublicationHandoffError, match="conflicts"):
        materialize_export(value, tmp_path, expected_schedule_id="wfsched_toolkit")


def test_materialized_handoff_enters_existing_initial_builder(tmp_path):
    raw = canonical_json(artifact_value())
    envelope = {
        "version": "publication-workflow-handoff-v1",
        "schedule_id": "wfsched_toolkit",
        "workflow_id": "wf_toolkit",
        "execution_id": "wfr_toolkit",
        "plan_id": "wfp_toolkit",
        "plan_hash": "1" * 64,
        "activation_revision": 1,
        "primary_agent_id": "agent_toolkit",
        "artifact_id": "wfa_toolkit",
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "scheduled_for": "2026-09-26T00:05:00+00:00",
    }
    envelope_raw = canonical_json(envelope)
    export = {
        "envelope": envelope,
        "envelope_sha256": hashlib.sha256(envelope_raw).hexdigest(),
        "artifact_b64": base64.b64encode(raw).decode("ascii"),
    }
    result = materialize_export(export, tmp_path, expected_schedule_id="wfsched_toolkit")
    output = tmp_path / "ai-toolkit-wfa_toolkit"
    assert result["output_directory"] == str(output)
    media = {
        "shelf_cover": (1440, 2560),
        "reader_cover": (2560, 1440),
        "illustration_01": (1600, 900),
        "illustration_02": (1600, 900),
        "illustration_03": (1600, 900),
    }
    for role, size in media.items():
        Image.new("RGB", size, "#445566").save(output / f"{role}.jpg", "JPEG")
    manifest = publication_editorial_remote.build_initial(
        output / "content-submission.json",
        output,
        series_id="ai-toolkit",
        issue_date="2026-09-26",
        format="chapter",
        owner_policy_id="workflow-owner-policy",
        writer_session="workflow-assets-session",
    )
    item = json.loads(manifest.read_text(encoding="utf-8"))["items"][0]
    receipts = {(entry["kind"], entry["sha256"]) for entry in item["source_files"]}
    assert ("workflow_artifact", envelope["artifact_sha256"]) in receipts
    assert ("workflow_handoff_envelope", export["envelope_sha256"]) in receipts
    assert item["status"] == "prepared"


@pytest.mark.asyncio
async def test_ack_is_idempotent_conflict_safe_and_never_releases(handoff_db):
    maker, tmp_path = handoff_db
    export = await exported(maker)
    store = PublicationStore(tmp_path / "publication")
    bundle, attempt = prepare_publication(store, export, tmp_path)
    envelope = export["envelope"]
    async with maker() as db:
        first = await acknowledge_publication_handoff(
            db,
            store,
            "wfsched_toolkit",
            execution_id=envelope["execution_id"],
            artifact_id=envelope["artifact_id"],
            artifact_hash=envelope["artifact_sha256"],
            envelope_hash=export["envelope_sha256"],
            attempt_id=attempt["attempt_id"],
            bundle=bundle,
        )
        await db.commit()
    assert first["idempotent"] is False
    async with maker() as db:
        second = await acknowledge_publication_handoff(
            db,
            store,
            "wfsched_toolkit",
            execution_id=envelope["execution_id"],
            artifact_id=envelope["artifact_id"],
            artifact_hash=envelope["artifact_sha256"],
            envelope_hash=export["envelope_sha256"],
            attempt_id=attempt["attempt_id"],
            bundle=bundle,
        )
        await db.commit()
        assert second["idempotent"] is True
        assert await db.scalar(select(func.count(WorkflowEvent.id))) == 1
        approvals = list((await db.execute(select(WorkflowApproval).where(
            WorkflowApproval.approval_type == "publication_handoff"
        ))).scalars())
        assert len(approvals) == 1
        approvals[0].comment = "conflicting receipt"
        await db.commit()
    async with maker() as db:
        with pytest.raises(PublicationHandoffError, match="conflicts"):
            await acknowledge_publication_handoff(
                db,
                store,
                "wfsched_toolkit",
                execution_id=envelope["execution_id"],
                artifact_id=envelope["artifact_id"],
                artifact_hash=envelope["artifact_sha256"],
                envelope_hash=export["envelope_sha256"],
                attempt_id=attempt["attempt_id"],
                bundle=bundle,
            )
    report = store.status_report()
    assert report["editorial_attempts"][0]["state"] == "approved"
    assert report["items"][0]["state"] in {"staged", "scheduled"}
    assert not [item for item in report["items"] if item["state"] == "published"]


@pytest.mark.asyncio
async def test_ack_rejects_publication_body_not_authored_by_workflow(handoff_db):
    maker, tmp_path = handoff_db
    export = await exported(maker)
    store = PublicationStore(tmp_path / "publication")
    bundle, attempt = prepare_publication(store, export, tmp_path)
    bundle["body"] += "\n\nunauthorized local rewrite"
    bundle["body_hash"] = hashlib.sha256(bundle["body"].encode()).hexdigest()
    envelope = export["envelope"]
    async with maker() as db:
        with pytest.raises(PublicationHandoffError, match="does not match"):
            await acknowledge_publication_handoff(
                db,
                store,
                "wfsched_toolkit",
                execution_id=envelope["execution_id"],
                artifact_id=envelope["artifact_id"],
                artifact_hash=envelope["artifact_sha256"],
                envelope_hash=export["envelope_sha256"],
                attempt_id=attempt["attempt_id"],
                bundle=bundle,
            )


@pytest.mark.asyncio
async def test_ack_revalidates_schedule_and_receipt_hashes(handoff_db):
    maker, tmp_path = handoff_db
    export = await exported(maker)
    store = PublicationStore(tmp_path / "publication")
    bundle, attempt = prepare_publication(store, export, tmp_path)
    broken = copy.deepcopy(bundle)
    receipt = next(item for item in broken["source_receipts"] if item["kind"] == "workflow_artifact")
    receipt["sha256"] = "0" * 64
    envelope = export["envelope"]
    async with maker() as db:
        with pytest.raises(PublicationHandoffError, match="hash|source receipts"):
            await acknowledge_publication_handoff(
                db,
                store,
                "wfsched_toolkit",
                execution_id=envelope["execution_id"],
                artifact_id=envelope["artifact_id"],
                artifact_hash=envelope["artifact_sha256"],
                envelope_hash=export["envelope_sha256"],
                attempt_id=attempt["attempt_id"],
                bundle=broken,
            )
    async with maker() as db:
        schedule = await db.get(WorkflowSchedule, "wfsched_toolkit")
        schedule.deleted_at = datetime.now(timezone.utc)
        await db.commit()
    async with maker() as db:
        with pytest.raises(PublicationHandoffError, match="revoked"):
            await acknowledge_publication_handoff(
                db,
                store,
                "wfsched_toolkit",
                execution_id=envelope["execution_id"],
                artifact_id=envelope["artifact_id"],
                artifact_hash=envelope["artifact_sha256"],
                envelope_hash=export["envelope_sha256"],
                attempt_id=attempt["attempt_id"],
                bundle=bundle,
            )


def test_materializer_pins_schedule_and_records_local_issue_scope(tmp_path):
    raw = canonical_json(artifact_value())
    envelope = {
        "version": "publication-workflow-handoff-v1", "schedule_id": "wfsched_toolkit",
        "workflow_id": "wf_toolkit", "execution_id": "wfr_toolkit",
        "plan_id": "wfp_toolkit", "plan_hash": "1" * 64,
        "activation_revision": 1, "primary_agent_id": "agent_toolkit",
        "artifact_id": "wfa_toolkit",
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "scheduled_for": "2026-09-25T16:05:00+00:00",
    }
    envelope_raw = canonical_json(envelope)
    export = {"envelope": envelope, "envelope_sha256": hashlib.sha256(envelope_raw).hexdigest(),
              "artifact_b64": base64.b64encode(raw).decode("ascii")}
    with pytest.raises(PublicationHandoffError, match="pinned local schedule"):
        materialize_export(export, tmp_path, expected_schedule_id="other_schedule")
    materialize_export(export, tmp_path, expected_schedule_id="wfsched_toolkit")
    state = json.loads((tmp_path / "ai-toolkit-wfa_toolkit" /
                        "workflow-handoff-state.json").read_text(encoding="utf-8"))
    assert (state["series_id"], state["issue_date"]) == ("ai-toolkit", "2026-09-26")
    assert state["plan_hash"] == "1" * 64
    assert state["activation_revision"] == 1
    assert state["primary_agent_id"] == "agent_toolkit"
    tampered = copy.deepcopy(export)
    tampered["envelope"]["plan_hash"] = "2" * 64
    with pytest.raises(PublicationHandoffError, match="envelope hash mismatch"):
        materialize_export(tampered, tmp_path / "tampered", expected_schedule_id="wfsched_toolkit")


async def request_revision(maker, store, export, attempt, bundle, review_raw):
    async with maker() as db:
        result = await request_publication_revision(
            db, store, "wfsched_toolkit", envelope=export["envelope"],
            envelope_hash=export["envelope_sha256"], attempt_id=attempt["attempt_id"],
            bundle=bundle, review_raw=review_raw,
        )
        await db.commit()
        return result


@pytest.mark.asyncio
async def test_rejection_revision_is_bound_idempotent_and_deselects_old_artifact(
    handoff_db, monkeypatch
):
    maker, tmp_path = handoff_db
    export = await exported(maker)
    store = PublicationStore(tmp_path / "publication-rejected")
    bundle, attempt, review_raw = reject_publication(store, export, tmp_path)
    calls = []

    async def retry(execution_id, from_node_id=None, revision_comment=None):
        calls.append((execution_id, from_node_id, json.loads(revision_comment)))

    monkeypatch.setattr(workflow_executor, "retry_remote", retry)
    async with maker() as db:
        with pytest.raises(PublicationHandoffError, match="terminal rejected"):
            await request_publication_revision(
                db, store, "wfsched_toolkit", envelope=export["envelope"],
                envelope_hash=export["envelope_sha256"], attempt_id=attempt["attempt_id"],
                bundle=bundle, review_raw=review_raw.replace(b"mechanism_gap", b"different_gap"),
            )
        wrong = {**export["envelope"], "artifact_id": "wrong_artifact"}
        with pytest.raises(PublicationHandoffError, match="envelope hash"):
            await request_publication_revision(
                db, store, "wfsched_toolkit", envelope=wrong,
                envelope_hash=export["envelope_sha256"], attempt_id=attempt["attempt_id"],
                bundle=bundle, review_raw=review_raw,
            )
        frozen_tamper = {**export["envelope"], "activation_revision": 2}
        with pytest.raises(PublicationHandoffError, match="exact current selected"):
            await request_publication_revision(
                db, store, "wfsched_toolkit", envelope=frozen_tamper,
                envelope_hash=hashlib.sha256(canonical_json(frozen_tamper)).hexdigest(),
                attempt_id=attempt["attempt_id"], bundle=bundle, review_raw=review_raw,
            )
        with pytest.raises(PublicationHandoffError, match="attempt binding"):
            await request_publication_revision(
                db, store, "wfsched_toolkit", envelope=export["envelope"],
                envelope_hash=export["envelope_sha256"], attempt_id="attempt-wrong",
                bundle=bundle, review_raw=review_raw,
            )
    first = await request_revision(maker, store, export, attempt, bundle, review_raw)
    second = await request_revision(maker, store, export, attempt, bundle, review_raw)
    assert first["idempotent"] is False and second["idempotent"] is True
    assert len(calls) == 1 and calls[0][0:2] == ("wfr_toolkit", "author")
    assert calls[0][2]["reviewer_gaps"][0]["id"] == "mechanism_gap"
    async with maker() as db:
        execution = await db.get(WorkflowExecution, "wfr_toolkit")
        artifact = await db.get(WorkflowArtifact, "wfa_toolkit")
        node = await db.get(WorkflowNodeRun, "wfn_author")
        assert execution.status == "queued" and artifact.selected_for_publish is False
        assert node.status == "pending"
        assert await db.scalar(select(func.count(WorkflowApproval.id)).where(
            WorkflowApproval.approval_type == "publication_revision"
        )) == 1
    assert await exported(maker) == {"status": "waiting_workflow", "available": False}


@pytest.mark.asyncio
async def test_revision_remote_failure_leaves_durable_prepared_request_for_retry(
    handoff_db, monkeypatch
):
    maker, tmp_path = handoff_db
    export = await exported(maker)
    store = PublicationStore(tmp_path / "publication-retry")
    bundle, attempt, review_raw = reject_publication(store, export, tmp_path)
    calls = 0

    async def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        async with maker() as verify_db:
            execution = await verify_db.get(WorkflowExecution, "wfr_toolkit")
            artifact = await verify_db.get(WorkflowArtifact, "wfa_toolkit")
            approval = (await verify_db.execute(select(WorkflowApproval).where(
                WorkflowApproval.approval_type == "publication_revision"
            ))).scalar_one()
            assert execution.status == "queued"
            assert artifact.selected_for_publish is False
            assert approval.decision == "prepared"
        if calls == 1:
            raise OSError("synthetic bridge outage")
        async with maker() as advance_db:
            execution = await advance_db.get(WorkflowExecution, "wfr_toolkit")
            execution.status = "running"
            await advance_db.commit()

    monkeypatch.setattr(workflow_executor, "retry_remote", fail_once)
    with pytest.raises(PublicationHandoffError, match="remains prepared and queued"):
        await request_revision(maker, store, export, attempt, bundle, review_raw)
    async with maker() as db:
        execution = await db.get(WorkflowExecution, "wfr_toolkit")
        artifact = await db.get(WorkflowArtifact, "wfa_toolkit")
        approval = (await db.execute(select(WorkflowApproval).where(
            WorkflowApproval.approval_type == "publication_revision"
        ))).scalar_one()
        assert execution.status == "queued"
        assert artifact.selected_for_publish is False
        assert approval.decision == "prepared"
    recovered = await request_revision(maker, store, export, attempt, bundle, review_raw)
    assert recovered["status"] == "queued" and calls == 2
    async with maker() as db:
        approval = (await db.execute(select(WorkflowApproval).where(
            WorkflowApproval.approval_type == "publication_revision"
        ))).scalar_one()
        assert approval.decision == "requested"


@pytest.mark.asyncio
async def test_second_artifact_same_execution_materializes_without_overwrite(handoff_db, monkeypatch):
    maker, tmp_path = handoff_db
    first_export = await exported(maker)
    first_local = materialize_export(
        first_export, tmp_path / "handoffs", expected_schedule_id="wfsched_toolkit"
    )
    store = PublicationStore(tmp_path / "publication-revision")
    bundle, attempt, review_raw = reject_publication(store, first_export, tmp_path)

    async def retry(*args, **kwargs):
        return None

    monkeypatch.setattr(workflow_executor, "retry_remote", retry)
    await request_revision(maker, store, first_export, attempt, bundle, review_raw)
    revised_value = artifact_value()
    revised_value["body"] += "\n\n## 审稿修订\n\n补充机制、边界和完整实例。"
    async with maker() as db:
        execution = await db.get(WorkflowExecution, "wfr_toolkit")
        node = await db.get(WorkflowNodeRun, "wfn_author")
        revised = store_artifact(
            execution, node_run_id=node.id, kind="final", title="AI toolkit revised",
            content=canonical_json(revised_value), source_kind="hermes_output",
            metadata={"artifact_version": 2}, extension="json",
        )
        revised.id = "wfa_toolkit_revision_2"
        db.add(revised)
        node.status = "succeeded"
        execution.status = "awaiting_review"
        execution.progress = 100
        await db.commit()
    second_export = await exported(maker)
    assert second_export["envelope"]["artifact_id"] == "wfa_toolkit_revision_2"
    second_local = materialize_export(
        second_export, tmp_path / "handoffs", expected_schedule_id="wfsched_toolkit"
    )
    assert first_local["output_directory"] != second_local["output_directory"]
    assert Path(first_local["output_directory"]).is_dir()
    assert Path(second_local["output_directory"]).is_dir()
    with sqlite3.connect(tmp_path / "handoffs" / DB_FILE) as ledger:
        count = ledger.execute("SELECT COUNT(*) FROM publication_workflow_consumptions").fetchone()[0]
    assert count == 2
    second_store = PublicationStore(tmp_path / "publication-second-rejection")
    second_bundle, second_attempt, second_review = reject_publication(
        second_store, second_export, tmp_path
    )
    second_result = await request_revision(
        maker, second_store, second_export, second_attempt, second_bundle, second_review
    )
    assert second_result["artifact_id"] == "wfa_toolkit_revision_2"
    async with maker() as db:
        approvals = list((await db.execute(select(WorkflowApproval).where(
            WorkflowApproval.approval_type == "publication_revision"
        ))).scalars())
        assert len(approvals) == 2
        assert {approval.plan_id for approval in approvals} == {
            "wfa_toolkit", "wfa_toolkit_revision_2",
        }
