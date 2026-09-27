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


def test_merge_preview_highlights_changes_without_persisting_or_losing_text():
    from backend.api.knowledge_actions import KnowledgeMergePreviewRequest, preview_note_merge

    def note(id, body):
        markdown = f'---\nid: "{id}"\ntitle: "笔记"\n---\n\n{body}'
        return dict(id=id, title="笔记", markdown=markdown, content_hash=hashlib.sha256(markdown.encode()).hexdigest())

    left = note("target", "共同开头\n\n预算为 300 元。\n\n共同结尾\n\n")
    right = note("source", "共同开头\n\n预算为 500 元。\n\n共同结尾\n\n新增路线\n")
    req = KnowledgeMergePreviewRequest(target_note_id="target", source_note_id="source", local_notes=[left, right])
    preview = preview_note_merge(req, AUTH)
    segments = preview["segments"]
    assert "".join(s["before"] for s in segments) == "共同开头\n\n预算为 300 元。\n\n共同结尾\n\n"
    assert "".join(s["after"] for s in segments) == "共同开头\n\n预算为 500 元。\n\n共同结尾\n\n新增路线\n"
    changed = next(s for s in segments if s["kind"] == "replace")
    assert "".join(run["text"] for run in changed["before_runs"] if run["changed"]) == "3"
    assert "".join(run["text"] for run in changed["after_runs"] if run["changed"]) == "5"
    assert preview["target_hash"] == left["content_hash"]
    assert "action_id" not in preview and "knowledge_action_capability" not in preview
    for snapshots in [[left, {**right, "markdown": "drift"}], [left, left], [left, {**right, "archived": True}]]:
        with pytest.raises(HTTPException) as error:
            preview_note_merge(req.model_copy(update={"local_notes": snapshots}), AUTH)
        assert error.value.status_code == 422


def test_merge_preview_identical_unicode_and_fragment_limit_preserve_full_text():
    from backend.services.knowledge_action_capability import note_merge_preview
    text = "你好🙂\n\n- [x] 完成\n\n![图](attachment://image.png)\n"
    def note(id, body):
        return dict(id=id, markdown=body, content_hash=hashlib.sha256(body.encode()).hexdigest())
    result = note_merge_preview(note("a", text), note("b", text))
    assert all(s["kind"] == "equal" for s in result["segments"])
    code = "```python\nfirst = 1\n\nsecond = 2\n```\n\n结尾"
    result = note_merge_preview(note("a", code), note("b", code.replace("second = 2", "second = 3")))
    changed = next(s for s in result["segments"] if s["kind"] == "replace")
    assert changed["before"].count("```") == 2
    assert "".join(s["before"] for s in result["segments"]) == code
    fragmented = "\n\n".join(str(i) for i in range(300))
    result = note_merge_preview(note("a", fragmented), note("b", "different"))
    assert result["coarse"] is True
    assert result["segments"][0]["before"] == fragmented
    assert result["segments"][0]["kind"] == "replace"


@pytest.mark.asyncio
async def test_merge_preview_http_requires_auth_and_valid_snapshots():
    import httpx
    from backend.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/api/v1/me/knowledge-actions/merge-preview", json={})
    assert response.status_code == 401


def test_chat_compare_is_read_only_owner_scoped_and_rejects_incomplete_snapshots():
    import json
    from scripts import hermes_bridge as bridge
    from backend.services.capability_catalog import describe_capability, search_capabilities
    events = []
    notes = [{"id": key, "markdown": text, "content_hash": hashlib.sha256(text.encode()).hexdigest(), "archived": False}
             for key, text in [("target", "预算300元\n"), ("source", "预算500元\n")]]
    context = {"knowledge_action_v1": True, "inline_notes": notes, "emit": events.append}
    previous = getattr(bridge._client_context_tool_context, "value", None)
    bridge._client_context_tool_context.value = context
    def compare(source="source"):
        return json.loads(bridge._app_capability_invoke_tool({"capability_id": "knowledge.note.compare", "input": {"target_note_id": "target", "source_note_id": source}}))
    try:
        result = compare()
        assert result["success"] and result["segments"][0]["kind"] == "replace"
        assert events == [{"type": "knowledge_navigation", "destination": "note_comparison", "note_id": "target", "source_note_id": "source", "query": None}]
        events.clear()
        assert not compare("other-owner")["success"]
        assert not compare("target")["success"]
        notes[1]["markdown"] = "truncated"
        assert not compare()["success"]
        assert events == []
    finally:
        bridge._client_context_tool_context.value = previous
    assert describe_capability("knowledge.note.compare")["effect"] == "read"
    assert "knowledge.note.compare" in {item["id"] for item in search_capabilities("帮我比较这两篇笔记", limit=5)}


@pytest.mark.asyncio
async def test_signed_chat_diff_is_derived_from_snapshot_not_model_claim(monkeypatch):
    import importlib
    api = importlib.import_module("backend.api.chat")
    monkeypatch.setattr(api, "persist_knowledge_action_proposal", AsyncMock())
    original = "预算300元\n"
    note = {"id": "target", "markdown": original, "content_hash": hashlib.sha256(original.encode()).hexdigest()}
    step = {"kind": "merge_notes", "target_note_id": "target", "original_content_hash": note["content_hash"], "source_note_ids": [], "source_content_hashes": {}, "markdown": "预算500元\n"}
    event = {"action_id": "diff-check", "steps": [step], "markdown_diff": "没有任何变化"}
    kwargs = dict(payload=AUTH, session_id="diff-session", request_id="diff-request", policy_version="p", client_context={"local_notes": [note]})
    signed = await api._authorize_knowledge_action_event(event, **kwargs)
    assert "-预算300元" in signed["markdown_diff"] and "+预算500元" in signed["markdown_diff"]
    changed = await api._authorize_knowledge_action_event({**event, "steps": [{**step, "markdown": "预算600元\n"}]}, **kwargs)
    assert signed["action_digest"] != changed["action_digest"]
    assert "没有任何变化" not in signed["markdown_diff"]


@pytest.mark.asyncio
async def test_pcm_compare_uses_authenticated_sync_reader(monkeypatch):
    from backend import capability_handlers as handlers
    notes = [{"note_id": key, "markdown": value, "content_hash": hashlib.sha256(value.encode()).hexdigest(), "archived": False}
             for key, value in [("a", "before"), ("b", "after")]]
    reader = AsyncMock(return_value={"items": notes, "compile_status": "ready"})
    monkeypatch.setattr(handlers, "list_synced_notes", reader)
    result = await handlers._knowledge_compare({"target_note_id": "a", "source_note_id": "b"}, AUTH, None)
    assert result["target_note_id"] == "a"
    assert reader.await_count == 1
    assert all(call.args == (True, AUTH) for call in reader.call_args_list)
    with pytest.raises(HTTPException) as denied:
        await handlers._knowledge_compare({"target_note_id": "a", "source_note_id": "foreign"}, AUTH, None)
    assert denied.value.status_code == 404


@pytest.mark.asyncio
async def test_pcm_search_organization_mode_uses_the_same_owner_snapshot(monkeypatch):
    import backend.capability_handlers as handlers
    snapshot = AsyncMock(return_value={"compile_status": "private_index_ready", "items": [
        {"note_id": str(i), "markdown": "# Different title " + str(i) + "\n\nIdentical full body", "archived": False}
        for i in range(4)]})
    monkeypatch.setattr(handlers, "list_synced_notes", snapshot)
    result = await invoke_capability("knowledge.note.search", {"query": "整理", "mode": "organize", "limit": 20}, payload=AUTH)
    assert result["error"] is None, result
    report = result["events"][0]["payload"]["organization"]
    assert report["scanned_notes"] == 4
    assert len(report["candidates"][0]["notes"]) == 4
    assert snapshot.await_args.args == (False, AUTH)


@pytest.mark.asyncio
async def test_trash_uses_signed_existing_executor_and_freezes_note_version():
    markdown = "# 待删除\n\n可恢复的正文"
    digest = hashlib.sha256(markdown.encode()).hexdigest()
    note = {"id": "delete-note", "title": "待删除", "markdown": markdown, "content_hash": digest}
    proposal = await create_capability_proposal(
        "knowledge.note.trash", {"note_id": note["id"], "base_hash": digest},
        local_notes=[note], payload=AUTH, session_id="trash-device",
        request_id="trash-request", idempotency_key="trash-request",
    )
    assert proposal["status"] == "awaiting_confirmation", proposal
    event = proposal["events"][0]["payload"]
    assert event["steps"][0]["kind"] == "move_to_trash"
    claims = verify_knowledge_action_capability(event["knowledge_action_capability"])
    assert claims["target_hashes"] == {note["id"]: digest}


def test_merge_preview_keeps_target_chapter_order_and_preserves_new_material():
    from backend.services.knowledge_action_capability import note_merge_preview
    def note(key, text):
        return {"id": key, "markdown": text, "content_hash": hashlib.sha256(text.encode()).hexdigest()}
    left = "# 方案\n\n## 原理\n\n基础概念\n\n## 实践\n\n操作步骤\n"
    right = "# 方案\n\n## 实践\n\n操作步骤\n\n补充细节\n\n## 原理\n\n基础概念\n\n## 参考\n\n引用出处\n"
    result = note_merge_preview(note("a", left), note("b", right))
    merged = "".join(s["before"] if s["kind"] in {"equal", "delete"} else s["after"] for s in result["segments"])
    assert merged.index("## 原理") < merged.index("## 实践") < merged.index("## 参考")
    assert merged.count("基础概念") == 1 and merged.count("操作步骤") == 1
    assert "补充细节" in merged and "引用出处" in merged


@pytest.mark.asyncio
async def test_note_catalog_pages_every_note_and_uses_frontmatter_title(monkeypatch):
    import backend.capability_handlers as handlers
    snapshot = AsyncMock(return_value={"compile_status": "ready", "items": [
        {"note_id": str(i), "markdown": f"---\ntitle: 主题{i}\n---\n内容{i}", "content_hash": "a" * 64, "archived": False}
        for i in range(7)]})
    monkeypatch.setattr(handlers, "list_synced_notes", snapshot)
    ids = []
    offset = 0
    while True:
        result = await invoke_capability("knowledge.note.search", {"query": "完整目录", "mode": "catalog", "limit": 3, "offset": offset}, payload=AUTH)
        assert result["status"] == "completed"
        page = result["events"][0]["payload"]
        assert page["total_count"] == 7
        assert page["items"][0]["title"].startswith("主题")
        ids.extend(item["note_id"] for item in page["items"])
        if page["next_offset"] is None:
            break
        offset = page["next_offset"]
    assert ids == [str(i) for i in range(7)]


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", [False, True])
async def test_delete_all_freezes_scope_and_does_not_include_new_notes(tmp_path, monkeypatch, drift):
    import backend.api.knowledge_sync as sync
    from backend.services.capability_gateway import proposal_status
    monkeypatch.setattr(sync, "_sync_root", lambda: tmp_path)
    monkeypatch.setattr(sync, "enqueue_note_contribution", AsyncMock(return_value=None))
    monkeypatch.setattr(sync, "_withdraw_note_event", AsyncMock(return_value=[]))
    for key in ("first", "second"):
        text = f"# {key}"
        await sync.sync_note(key, sync.NoteSyncRequest(markdown=text, content_hash=hashlib.sha256(text.encode()).hexdigest()), AUTH)
    request = "batch-" + uuid.uuid4().hex
    proposed = await create_capability_proposal("knowledge.note.trash", {"all_active": True}, payload=AUTH,
        session_id=request, request_id=request, idempotency_key=request)
    event = proposed["events"][0]["payload"]
    assert set(event["input"]["note_versions"]) == {"first", "second"}
    assert "2篇" in event["summary"]
    text = "# newly created"
    await sync.sync_note("new", sync.NoteSyncRequest(markdown=text, content_hash=hashlib.sha256(text.encode()).hexdigest()), AUTH)
    if drift:
        text = "# first edited after review"
        await sync.sync_note("first", sync.NoteSyncRequest(markdown=text, content_hash=hashlib.sha256(text.encode()).hexdigest()), AUTH)
    result = await confirm_capability_proposal(event["proposal_id"], event["confirmation_token"], payload=AUTH, session_id=request)
    if drift:
        assert result["error"]["code"] == "resource_conflict"
        remaining = await sync.list_synced_notes(False, AUTH)
        assert {item["note_id"] for item in remaining["items"]} == {"first", "second", "new"}
        return
    assert result["status"] == "completed", result
    assert result["events"][0]["payload"]["count"] == 2
    remaining = await sync.list_synced_notes(False, AUTH)
    assert [item["note_id"] for item in remaining["items"]] == ["new"]
    all_notes = await sync.list_synced_notes(False, AUTH, include_trashed=True)
    assert {item["note_id"] for item in all_notes["items"] if item["trashed"]} == {"first", "second"}
    status = await proposal_status(event["proposal_id"], payload=AUTH)
    assert status["status"] == "verified"


def test_bridge_cloud_note_read_populates_workspace_for_followup_review(monkeypatch):
    import asyncio
    import json
    import scripts.hermes_bridge as bridge
    import backend.services.capability_catalog as catalog
    text = "# 云端独有笔记\n\n完整正文"
    context = {"knowledge_action_v1": True, "inline_notes": [], "identity": AUTH, "request_id": "cloud-read-123"}
    monkeypatch.setattr(bridge._client_context_tool_context, "value", context)
    async def read(capability_id, data, **kwargs):
        assert capability_id == "knowledge.note.read" and data == {"note_id": "cloud-note"}
        assert kwargs["payload"] == AUTH
        return {"status": "completed", "events": [{"type": "knowledge.note", "payload": {"note": {
            "note_id": "cloud-note", "title": "云端独有笔记", "markdown": text,
            "content_hash": hashlib.sha256(text.encode()).hexdigest(), "archived": False}}}]}
    monkeypatch.setattr(catalog, "invoke_capability", read)
    monkeypatch.setattr(bridge.contracts, "_run_bridge_coroutine", lambda coroutine, **kwargs: asyncio.run(coroutine))
    result = json.loads(bridge._app_capability_invoke_tool({"capability_id": "knowledge.note.read", "input": {"note_id": "cloud-note"}}))
    assert result["status"] == "completed"
    cached = json.loads(bridge._knowledge_workspace_read_tool({"operation": "read", "note_id": "cloud-note"}))
    assert cached["note"]["markdown"] == text
    assert context["knowledge_workspace_read_completed"] is True


@pytest.mark.asyncio
async def test_catalog_full_body_budget_pages_without_clipping_or_skipping(monkeypatch):
    import backend.capability_handlers as handlers
    bodies = ["first" * 6000, "second" * 6000, "oversize" * 7000, "last"]
    snapshot = AsyncMock(return_value={"compile_status": "ready", "items": [
        {"note_id": str(i), "markdown": body, "content_hash": hashlib.sha256(body.encode()).hexdigest(), "archived": False}
        for i, body in enumerate(bodies)]})
    monkeypatch.setattr(handlers, "list_synced_notes", snapshot)
    received = []
    offset = 0
    while True:
        result = await invoke_capability("knowledge.note.search", {
            "query": "完整语义整理", "mode": "catalog", "include_content": True,
            "limit": 100, "offset": offset}, payload=AUTH)
        assert result["error"] is None
        page = result["events"][0]["payload"]
        assert page["content_complete"]
        received.extend(item["markdown"] for item in page["items"])
        assert all(item["content_complete"] for item in page["items"])
        if page["next_offset"] is None:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    assert received == bodies
    assert all(call.args == (False, AUTH) for call in snapshot.call_args_list)
    denied = await invoke_capability("knowledge.note.search", {
        "query": "全部", "mode": "catalog", "include_content": True,
        "tenant_key": "foreign"}, payload=AUTH)
    assert denied["error"] is not None


def test_bridge_batch_catalog_reuses_complete_bodies_but_not_snippets(monkeypatch):
    import asyncio
    import json
    import scripts.hermes_bridge as bridge
    import backend.services.capability_catalog as catalog
    context = {"knowledge_action_v1": True, "inline_notes": [], "identity": AUTH, "request_id": "batch-catalog-test"}
    monkeypatch.setattr(bridge._client_context_tool_context, "value", context)
    async def read(capability_id, data, **kwargs):
        assert kwargs["payload"] == AUTH
        return {"status": "completed", "events": [{"type": "knowledge.results", "payload": {"items": [
            {"note_id": "full", "title": "Full", "markdown": "complete", "content_complete": True},
            {"note_id": "snippet", "title": "Partial", "snippet": "clipped", "content_complete": False},
        ]}}]}
    monkeypatch.setattr(catalog, "invoke_capability", read)
    monkeypatch.setattr(bridge.contracts, "_run_bridge_coroutine", lambda coroutine, **kwargs: asyncio.run(coroutine))
    bridge._app_capability_invoke_tool({"capability_id": "knowledge.note.search", "input": {"query": "all", "mode": "catalog", "include_content": True}})
    assert [n["id"] for n in context["inline_notes"]] == ["full"]
    assert json.loads(bridge._knowledge_workspace_read_tool({"operation": "read", "note_id": "full"}))["note"]["markdown"] == "complete"


def test_bridge_fast_audit_emits_actual_counts_before_final_answer(monkeypatch):
    import asyncio
    import scripts.hermes_bridge as bridge
    import backend.services.capability_catalog as catalog
    events = []
    context = {"knowledge_action_v1": True, "inline_notes": [], "identity": AUTH,
               "request_id": "quick-audit-progress", "emit": events.append}
    monkeypatch.setattr(bridge._client_context_tool_context, "value", context)
    async def read(*args, **kwargs):
        return {"status": "completed", "events": [{"type": "knowledge.results", "payload": {
            "organization": {"scanned_notes": 135, "total_candidates": 68,
                             "semantic_scan_complete": False}}}]}
    monkeypatch.setattr(catalog, "invoke_capability", read)
    monkeypatch.setattr(bridge.contracts, "_run_bridge_coroutine", lambda coroutine, **kwargs: asyncio.run(coroutine))
    bridge._app_capability_invoke_tool({"capability_id": "knowledge.note.search",
                                     "input": {"query": "快速体检", "mode": "organize"}})
    assert [event["type"] for event in events] == ["knowledge.results", "status"]
    assert events[-1]["detail"] == "已检查 135 篇笔记，发现 68 组候选；正在汇总核对范围。"
    assert not events[0]["payload"]["organization"]["semantic_scan_complete"]
    assert not context.get("knowledge_workspace_read_completed")


def test_full_catalog_rejects_guessed_offsets_and_counts_actual_bodies(monkeypatch):
    import asyncio
    import json
    import scripts.hermes_bridge as bridge
    import backend.services.capability_catalog as catalog

    events = []
    context = {"inline_notes": [], "identity": AUTH, "request_id": "catalog-continuity", "emit": events.append}
    monkeypatch.setattr(bridge._client_context_tool_context, "value", context)
    offsets = []

    async def read(_capability_id, data, **_kwargs):
        offset = data.get("offset", 0)
        offsets.append(offset)
        end = min(offset + 2, 5)  # Body budget can return fewer than limit=100.
        return {"status": "completed", "events": [{"type": "knowledge.results", "payload": {
            "items": [{"note_id": str(i), "markdown": "body", "snippet": "body" * 1000, "content_complete": True} for i in range(offset, end)],
            "total_count": 5, "next_offset": end if end < 5 else None,
        }}]}

    monkeypatch.setattr(catalog, "invoke_capability", read)
    monkeypatch.setattr(bridge.contracts, "_run_bridge_coroutine", lambda coroutine, **kwargs: asyncio.run(coroutine))

    def page(offset, archived=False):
        return json.loads(bridge._app_capability_invoke_tool({"capability_id": "knowledge.note.search", "input": {
            "query": "all", "mode": "catalog", "include_content": True,
            "offset": offset, "limit": 100, "include_archived": archived,
        }}))

    first_result = page(0)
    first = first_result["catalog_progress"]
    model_note = first_result["events"][0]["payload"]["items"][0]
    assert model_note["markdown"] == "body" and "snippet" not in model_note
    assert events[0]["payload"]["items"][0]["snippet"] == "body" * 1000
    assert context["inline_notes"][0]["snippet"] == "body" * 1000
    assert "evidence checkpoint" in first_result["review_instruction"]
    assert first["full_bodies_read"] == 2 and not first["all_bodies_read"]
    skipped = page(4)
    assert skipped["error"] == "catalog_page_out_of_sequence" and skipped["next_offset"] == 2
    assert offsets == [0]  # No skipped page was dispatched or marked read.
    assert page(2, archived=True)["next_offset"] == 0  # Different catalog scope starts afresh.
    assert page(2)["catalog_progress"]["full_bodies_read"] == 4
    complete = page(4)["catalog_progress"]
    assert complete == {"full_bodies_read": 5, "total_count": 5, "next_offset": None,
                        "all_bodies_read": True, "semantic_review_complete": False}
    assert offsets == [0, 2, 4]
    assert events[-1]["detail"] == "已读取 5/5 篇完整正文；正在核对内容。"
    assert page(0)["catalog_progress"]["full_bodies_read"] == 2  # Explicit restart resets coverage.
