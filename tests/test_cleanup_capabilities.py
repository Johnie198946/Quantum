"""Cleanup reuses PCM confirmation, local knowledge signatures and QWS CAS."""
import hashlib
import uuid
import time
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.api import quantum_workspace as qws
from backend.db import SessionLocal
from backend.models.workspace import WorkspaceProject
from backend.services.capability_catalog import invoke_capability
from backend.services.capability_gateway import create_capability_proposal, confirm_capability_proposal
from backend.services.knowledge_action_capability import verify_knowledge_action_capability

AUTH = {"tenant_key": "cleanup-tenant", "user_id": "cleanup-user", "principal_type": "human", "amr": ["pwd"], "auth_time": int(time.time())}


@pytest.mark.asyncio
async def test_local_note_proposal_is_signed_without_cloud_mutation_and_rejects_drift():
    markdown = "# 本地尚未同步\n\n需要完整保留的内容"
    digest = hashlib.sha256(markdown.encode()).hexdigest()
    note = {"id": "local-note", "title": "本地尚未同步", "markdown": markdown, "content_hash": digest}
    args = dict(payload=AUTH, session_id="cleanup-device", request_id="cleanup-note-request", idempotency_key="cleanup-note-request")
    proposal = await create_capability_proposal("knowledge.note.archive", {"note_id": note["id"], "base_hash": digest}, local_notes=[note], **args)
    assert proposal["status"] == "awaiting_confirmation"
    event = proposal["events"][0]["payload"]
    claims = verify_knowledge_action_capability(event["knowledge_action_capability"])
    assert claims["tenant_key"] == AUTH["tenant_key"]
    assert claims["target_hashes"] == {note["id"]: digest}
    assert event["steps"][0]["kind"] == "archive_note"
    for snapshot in [[{**note, "markdown": "changed"}], [{**note, "id": "another-note"}], []]:
        result = await create_capability_proposal("knowledge.note.archive", {"note_id": note["id"], "base_hash": digest}, local_notes=snapshot, **args)
        assert result["status"] == "failed"
    denied = await create_capability_proposal("project.create", {"name": "x", "goal": "x"}, local_notes=[note], **args)
    assert denied["status"] == "failed"


@pytest.mark.asyncio
async def test_conversation_requires_confirmation_and_receipt_is_owner_bound():
    from backend.services.client_actions import record_client_action_receipt
    request = "cleanup-" + uuid.uuid4().hex
    data = {"lifecycle": "archived", "sessions": [{"session_id": "local-session", "version": "a" * 64}]}
    denied = await invoke_capability("conversation.lifecycle", data, payload=AUTH, idempotency_key=request)
    assert denied["status"] == "failed"
    result = await create_capability_proposal("conversation.lifecycle", data, payload=AUTH, session_id="cleanup", request_id=request, idempotency_key=request)
    proposal = result["events"][0]["payload"]
    confirmed = await confirm_capability_proposal(proposal["proposal_id"], proposal["confirmation_token"], payload=AUTH, session_id="cleanup")
    action = confirmed["events"][0]["payload"]
    assert action["state"] == "PENDING"  # Issued is not locally executed.
    assert action["payload"]["account_scope"] == hashlib.sha256(AUTH["tenant_key"].encode()).hexdigest()[:16] + ":" + hashlib.sha256(AUTH["user_id"].encode()).hexdigest()[:16]
    with pytest.raises(HTTPException) as error:
        await record_client_action_receipt(action["action_id"], "SUCCEEDED", {}, {**AUTH, "user_id": "other"})
    assert error.value.status_code == 404
    result = await record_client_action_receipt(action["action_id"], "SUCCEEDED", {"scope": "local_device"}, AUTH)
    assert result["state"] == "SUCCEEDED"
    oversized = {**data, "sessions": data["sessions"] * 33}
    rejected = await create_capability_proposal("conversation.lifecycle", oversized, payload=AUTH, session_id="cleanup", request_id=request, idempotency_key=request)
    assert rejected["status"] == "failed"


@pytest.mark.asyncio
async def test_task_batch_preserves_done_state_and_never_persists_partial_conflicts(monkeypatch):
    project_id = "p-" + uuid.uuid4().hex
    original = {"tasks": [{"id": "done", "title": "已完成", "status": "DONE"}, {"id": "open", "title": "未完成", "status": "TODO"}]}
    async with SessionLocal() as db:
        db.add(WorkspaceProject(id=project_id, tenant_key=AUTH["tenant_key"], owner_user_id=AUTH["user_id"], request_id=project_id, name="整理项目", goal="验证", process_revision=7, process_snapshot=original, intent_migration_state="CONFIRMED", active_intent_revision=1, active_intent_hash="a" * 64))
        await db.commit()
    captured = []
    async def create(_db, **kwargs):
        captured.append(deepcopy(kwargs["proposed_process"]))
        return SimpleNamespace(id="proposal")
    monkeypatch.setattr(qws, "_create_project_change_proposal", create)
    monkeypatch.setattr(qws, "_proposal_out", lambda value: {"id": value.id})
    request = qws.TaskOrganizationRequest(expected_revision=7, request_id="cleanup-project-001", operations=[{"action": "ARCHIVE", "task_id": "done"}, {"action": "ARCHIVE", "task_id": "open"}])
    await qws.propose_project_task_organization(project_id, request, AUTH)
    assert [task["status"] for task in captured[0]["tasks"]] == ["DONE", "CANCELLED"]
    assert [task["pre_archive_status"] for task in captured[0]["tasks"]] == ["DONE", "TODO"]
    for invalid in [request.model_copy(update={"expected_revision": 6}), qws.TaskOrganizationRequest(expected_revision=7, request_id="cleanup-project-002", operations=[{"action": "ARCHIVE", "task_id": "done"}, {"action": "RESTORE", "task_id": "done"}])]:
        with pytest.raises(HTTPException):
            await qws.propose_project_task_organization(project_id, invalid, AUTH)
    assert len(captured) == 1
    with pytest.raises(HTTPException):
        await qws.propose_project_task_organization(project_id, request, {**AUTH, "user_id": "other"})


@pytest.mark.asyncio
async def test_task_update_only_reports_applied_after_existing_project_decision(monkeypatch):
    from backend.capability_handlers import _task_update
    propose = AsyncMock(return_value={"proposal": {"id": "reviewed"}})
    decide = AsyncMock(return_value={"proposal": {"id": "reviewed", "status": "APPROVED"}})
    monkeypatch.setattr(qws, "propose_project_task_organization", propose)
    monkeypatch.setattr(qws, "decide_project_change_proposal", decide)
    data = {"project_id": "p", "expected_revision": 8, "operations": [{"action": "ARCHIVE", "task_id": "one"}, {"action": "ARCHIVE", "task_id": "two"}]}
    assert (await _task_update(data, AUTH, "cleanup-batch-key"))["applied"] is True
    assert len(propose.await_args.args[1].operations) == 2
    assert decide.await_args.args[2].expected_process_revision == 8
    decide.return_value = {"proposal": {"status": "NEEDS_REBASE"}}
    with pytest.raises(HTTPException):
        await _task_update(data, AUTH, "cleanup-batch-key")


@pytest.mark.asyncio
async def test_task_organization_commits_replays_and_restores_through_pcm(monkeypatch):
    from backend.capability_handlers import _task_update
    from backend.services.task_operating_loop import create_merge_preview
    monkeypatch.setattr(qws, "_enqueue_qws_source", AsyncMock(return_value={}))
    project_id = "cleanup-" + uuid.uuid4().hex
    async with SessionLocal() as db:
        db.add(WorkspaceProject(id=project_id, tenant_key=AUTH["tenant_key"], owner_user_id=AUTH["user_id"], request_id=project_id, name="归档恢复", goal="保留内容", process_revision=1, process_snapshot={"stages": [], "gates": [], "dependencies": [], "tasks": [{"id": "a", "stage_id": "s", "title": "检查报告", "status": "TODO"}, {"id": "b", "stage_id": "s", "title": "检查报告", "status": "TODO"}]}, intent_migration_state="CONFIRMED", active_intent_revision=1, active_intent_hash="b" * 64))
        await db.commit()
    async def snapshot():
        async with SessionLocal() as db:
            project = await db.get(WorkspaceProject, project_id)
            return project.process_revision, deepcopy(project.process_snapshot)
    async def apply(operations, key):
        revision, _ = await snapshot()
        data = {"project_id": project_id, "expected_revision": revision, "operations": operations}
        proposed = await create_capability_proposal("task.update", data, payload=AUTH, session_id="cleanup", request_id=key, idempotency_key=key)
        event = proposed["events"][0]["payload"]
        result = await confirm_capability_proposal(event["proposal_id"], event["confirmation_token"], payload=AUTH, session_id="cleanup")
        assert result["error"] is None, result
        assert result["events"][0]["payload"]["applied"] is True
        return data
    data = await apply([{"action": "ARCHIVE", "task_id": "a"}, {"action": "ARCHIVE", "task_id": "b"}], "archive-" + project_id)
    revision, state = await snapshot()
    assert revision == 2 and all(t.get("archived_at") for t in state["tasks"])
    await _task_update(data, AUTH, "archive-" + project_id)
    assert (await snapshot())[0] == revision
    await apply([{"action": "RESTORE", "task_id": "a"}, {"action": "RESTORE", "task_id": "b"}], "restore-" + project_id)
    _, state = await snapshot()
    assert all(not t.get("archived_at") and t["status"] == "TODO" for t in state["tasks"])
    preview = create_merge_preview(*state["tasks"], created_by="user:cleanup-user")
    choices = {item["field"]: "primary" for item in preview["conflicts"]}
    await apply([{"action": "MERGE", "task_id": "a", "secondary_task_id": "b", "field_choices": choices}], "merge-" + project_id)
    _, state = await snapshot()
    assert state["tasks"][1]["status"] == "MERGED"
    from backend.capability_handlers import _task_list
    listed = await _task_list({"project_id": project_id, "include_cleanup": True}, AUTH, None)
    assert listed["cleanup_merges"][0]["id"] == state["task_merges"][0]["id"]
    await apply([{"action": "REVERT_MERGE", "task_id": "a", "secondary_task_id": "b", "merge_id": state["task_merges"][0]["id"]}], "revert-" + project_id)
    _, state = await snapshot()
    assert all(t["status"] == "TODO" for t in state["tasks"])
