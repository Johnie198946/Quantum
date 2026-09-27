"""Direct image path: authenticated upload -> PCM workflow -> real file bytes."""
import io
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import select

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from backend.api.auth import require_auth
from backend.api.documents import router
from backend.api.tenant import current_tenant
from backend.db import SessionLocal
from backend.models.workflow import WorkflowDefinition, WorkflowExecution, WorkflowNodeRun, WorkflowArtifact
from backend.services.capability_catalog import invoke_capability
from backend.services.generated_artifacts import GeneratedArtifactError
from backend.services.image_processing import (
    ImageEdit, build_image_plan, decode_image, image_device_action,
)
from backend.services.workflow_artifacts import store_artifact
from backend.services.client_actions import record_client_action_receipt
from backend.services.workflow_executor import project_event


@pytest.mark.asyncio
@pytest.mark.parametrize("source_kind", ["generated", "document"])
@pytest.mark.parametrize("entry", ["chat", "workflow"])
async def test_upload_to_image_workflow_and_downloadable_jpeg(tmp_path, monkeypatch, source_kind, entry):
    monkeypatch.setenv("AI_LAB_GENERATED_ARTIFACT_ROOT", str(tmp_path / "generated"))
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path / "vault"))
    image = Image.new("RGBA", (640, 480), (200, 30, 50, 0))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    original = stream.getvalue()
    actor = {"tenant_key": "image-tenant", "user_id": "image-user", "sub": "image-user"}
    app = FastAPI()
    app.include_router(router)
    from backend.api.workflows import router as workflow_router
    app.include_router(workflow_router)
    app.dependency_overrides[require_auth] = lambda: actor
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        queued = []
        if source_kind == "document":
            import base64
            from backend.api import documents
            from backend.services import document_sources
            monkeypatch.setattr(document_sources, "note_directory", lambda tenant, user: tmp_path / tenant / user)
            async def enqueue(candidate, *, source_content):
                queued.append(candidate)
                return {"schedule_status": "scheduled", "event_id": "image-event", "run_id": "image-compile"}
            monkeypatch.setattr(documents, "enqueue_and_schedule", enqueue)
            upload = await client.post("/api/v1/documents", headers={"X-File-Name": "photo.png"},
                json={"data": base64.b64encode(original).decode(), "content_type": "image/png", "extracted_text": "图片测试说明"})
            assert upload.status_code == 201, upload.text
            document = upload.json()
            assert document["note_id"] == document["source_id"]
            assert document["contribution_status"] == "queued" and len(queued) == 1
            assert len(list(tmp_path.rglob("original.png"))) == 1
            assert not list((tmp_path / "generated").rglob("content.*"))
            receipt = {"artifact_id": document["source_id"], "download_path": f"documents/{document['source_id']}/download"}
            from backend.services.image_processing import workflow_image_source
            for tenant, user in [("other-tenant", actor["user_id"]), (actor["tenant_key"], "other")]:
                with pytest.raises(GeneratedArtifactError):
                    workflow_image_source(tenant, user, document["source_id"])
        else:
            upload = await client.post("/api/v1/documents/images", content=original)
            assert upload.status_code == 201, upload.text
            receipt = upload.json()
        downloaded = await client.get("/api/v1/" + receipt["download_path"])
        assert downloaded.content == original
        source_id = receipt["artifact_id"]
        edit = {"format": "jpg", "aspect_ratio": "16:9"}
        context = current_tenant.set(actor["tenant_key"])
        try:
            if entry == "chat":
                result = await invoke_capability("media.process", {"source_artifact_id": source_id, **edit}, payload=actor, idempotency_key=f"image-direct-check-{source_kind}")
            else:
                response = await client.post("/api/v1/workflows", json={"title": "图片处理", "description": "裁成16:9并转为JPG", "output_kind": "image", "source_image_id": source_id})
                assert response.status_code == 201, response.text
                result = {"status": "completed", "events": [{"renderer": "workflow", "payload": response.json()}]}
        finally:
            current_tenant.reset(context)
        assert result["status"] == "completed", str(result)
        assert result["events"][0]["renderer"] == "workflow"
        workflow_id = result["events"][0]["payload"]["workflow"]["id"]
        async with SessionLocal() as db:
            workflow = await db.get(WorkflowDefinition, workflow_id)
            plan = build_image_plan(workflow, plan_id="test-image-plan")
            if entry == "chat":
                assert plan["nodes"][0]["parameters"]["image_edit"]["aspect_ratio"] == "16:9"
        execution_id = result["events"][0]["payload"]["workflow"]["latest_execution"]["id"]
        context = current_tenant.set(actor["tenant_key"])
        try:
            if entry == "chat":
                replay = await invoke_capability("media.process", {"source_artifact_id": source_id, **edit}, payload=actor, idempotency_key=f"image-direct-check-{source_kind}")
                assert replay["events"][0]["payload"]["workflow"]["latest_execution"]["id"] == execution_id
        finally:
            current_tenant.reset(context)
        async with SessionLocal() as db:
            workflow = await db.get(WorkflowDefinition, workflow_id)
            execution = await db.get(WorkflowExecution, execution_id)
            assert execution.status == "queued"
            node = await db.scalar(select(WorkflowNodeRun).where(WorkflowNodeRun.execution_id == execution_id))
            node.attempt = 1
            node.status = "succeeded"
            instruction = store_artifact(execution, node_run_id=node.id, kind="draft", title="parameters",
                content=ImageEdit(**edit).model_dump_json(), extension="json",
                metadata={"render_type": "image_edit", "artifact_version": 1})
            db.add(instruction)
            await project_event(db, execution, {node.node_id: node}, {"type": "run_completed", "seq": 1})
            assert execution.status == "awaiting_approval" and execution.progress == 50
            assert execution.finished_at is None
            await db.commit()
            action = await image_device_action(db, execution, workflow, actor)
            replay = await image_device_action(db, execution, workflow, actor)
            assert replay["action_id"] == action["action_id"]
            assert action["payload"]["image_edit"]["aspect_ratio"] == "16:9"
        if source_kind == "generated" and entry == "chat":
            from unittest.mock import AsyncMock
            from backend.api import workflows
            remote_retry = AsyncMock()
            monkeypatch.setattr(workflows, "retry_remote", remote_retry)
            # Both device terminal failures happen after the parameter node succeeds.
            for terminal in ("CANCELLED", "FAILED"):
                old_action = action
                await record_client_action_receipt(action["action_id"], terminal, {}, actor)
                context = current_tenant.set(actor["tenant_key"])
                try:
                    # The exception must not change ordinary workflow retries.
                    async with SessionLocal() as db:
                        row = await db.get(WorkflowDefinition, workflow_id)
                        row.requirements_snapshot = {**row.requirements_snapshot, "output_kind": "general"}
                        await db.commit()
                    rejected = await client.post(f"/api/v1/workflow-executions/{execution_id}/retry")
                    assert rejected.status_code == 409
                    async with SessionLocal() as db:
                        row = await db.get(WorkflowDefinition, workflow_id)
                        row.requirements_snapshot = {**row.requirements_snapshot, "output_kind": "image"}
                        await db.commit()
                    remote_retry.side_effect = OSError("bridge unavailable")
                    unavailable = await client.post(f"/api/v1/workflow-executions/{execution_id}/retry")
                    assert unavailable.status_code == 503
                    async with SessionLocal() as db:
                        assert (await db.get(WorkflowExecution, execution_id)).status == ("cancelled" if terminal == "CANCELLED" else "failed")
                    remote_retry.side_effect = None
                    retried = await client.post(f"/api/v1/workflow-executions/{execution_id}/retry")
                    assert retried.status_code == 200, retried.text
                    assert retried.json()["status"] == "queued"
                    remote_retry.assert_called_with(execution_id, "image_edit")
                finally:
                    current_tenant.reset(context)
                async with SessionLocal() as db:
                    execution = await db.get(WorkflowExecution, execution_id)
                    node = await db.scalar(select(WorkflowNodeRun).where(WorkflowNodeRun.execution_id == execution_id))
                    previous_attempt = node.attempt
                    await project_event(db, execution, {node.node_id: node}, {"type": "node_started", "node_id": node.node_id})
                    assert node.attempt == previous_attempt + 1
                    node.status = "succeeded"
                    instruction = store_artifact(execution, node_run_id=node.id, kind="draft", title="parameters",
                        content=ImageEdit(**edit).model_dump_json(), extension="json",
                        metadata={"render_type": "image_edit", "artifact_version": node.attempt})
                    previous_instruction = await db.get(WorkflowArtifact, old_action["payload"]["instruction_id"])
                    instruction.created_at = previous_instruction.created_at
                    db.add(instruction)
                    await project_event(db, execution, {node.node_id: node}, {"type": "run_completed"})
                    await db.commit()
                    action = await image_device_action(db, execution, workflow, actor)
                    assert action["action_id"] != old_action["action_id"]
                    assert action["payload"]["instruction_id"] != old_action["payload"]["instruction_id"]
                with pytest.raises(HTTPException) as stale:
                    await record_client_action_receipt(old_action["action_id"], "SUCCEEDED", {"artifact_id": source_id}, actor)
                assert stale.value.status_code == 409
                assert (await record_client_action_receipt(old_action["action_id"], terminal, {}, actor))["state"] == terminal
                async with SessionLocal() as db:
                    assert (await db.get(WorkflowExecution, execution_id)).status == "awaiting_approval"
        # Invalid device bytes cannot move the workflow to success.
        with pytest.raises(HTTPException) as invalid:
            await record_client_action_receipt(action["action_id"], "SUCCEEDED", {"artifact_id": source_id}, actor)
        assert invalid.value.status_code == 422
        async with SessionLocal() as db:
            assert (await db.get(WorkflowExecution, execution_id)).status == "awaiting_approval"
        output = io.BytesIO()
        Image.new("RGB", (640, 360), "white").save(output, format="JPEG")
        result = (await client.post("/api/v1/documents/images", content=output.getvalue())).json()
        assert result["artifact_id"].startswith("ga_")
        assert len(queued) == (1 if source_kind == "document" else 0)
        metadata = {"artifact_id": result["artifact_id"]}
        with pytest.raises(HTTPException) as denied:
            await record_client_action_receipt(action["action_id"], "SUCCEEDED", metadata, {**actor, "user_id": "other"})
        assert denied.value.status_code == 404
        accepted = await record_client_action_receipt(action["action_id"], "SUCCEEDED", metadata, actor)
        assert accepted["state"] == "SUCCEEDED"
        assert await record_client_action_receipt(action["action_id"], "SUCCEEDED", metadata, actor) == accepted
        async with SessionLocal() as db:
            assert (await db.get(WorkflowExecution, execution_id)).status == "completed"
            outputs = list((await db.scalars(select(WorkflowArtifact).where(WorkflowArtifact.source_kind == "ios_native", WorkflowArtifact.execution_id == execution_id))).all())
            assert len(outputs) == 1 and outputs[0].metadata_json["operations"]["format"] == "jpg"
        context = current_tenant.set(actor["tenant_key"])
        try:
            download = await client.get(f"/api/v1/workflow-executions/{execution_id}/artifacts/{outputs[0].id}/download")
            assert download.status_code == 200, download.text
            assert download.content == output.getvalue()
        finally:
            current_tenant.reset(context)
        if source_kind == "document":
            from backend.services.document_sources import document_original_path
            path, _ = document_original_path(actor["tenant_key"], actor["user_id"], source_id)
            path.unlink()
            with pytest.raises(GeneratedArtifactError):
                workflow_image_source(actor["tenant_key"], actor["user_id"], source_id)
        actor["user_id"] = "other-user"
        assert (await client.get("/api/v1/" + receipt["download_path"])).status_code == 404


def test_alpha_and_invalid_input():
    image = Image.new("RGBA", (160, 90), (20, 80, 140, 100))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    decoded, fmt = decode_image(stream.getvalue())
    assert fmt == "PNG" and decoded.getpixel((0, 0))[3] == 100
    with pytest.raises(GeneratedArtifactError):
        decode_image(b"not an image")


def test_signed_image_context_preserves_policy_for_confirmation(monkeypatch, tmp_path):
    import queue
    import sys
    import types
    import scripts.hermes_bridge as bridge

    observed = {}
    gateway = types.ModuleType("gateway.session_context")
    gateway.declare_stateless_channel = lambda: None
    monkeypatch.setitem(sys.modules, "gateway.session_context", gateway)
    monkeypatch.setattr(bridge.session_runtime, "_update_session_mapping", lambda *a, **kw: None)

    def build(*args, **kwargs):
        observed.update(bridge.knowledge._client_context_tool_context.value["identity"])
        agent = SimpleNamespace(session_id="image-test", close=lambda: None,
                                run_conversation=lambda *a, **kw: {"final_response": "ready"})
        return agent, SimpleNamespace(close=lambda: None), {"triage": None}

    monkeypatch.setattr(bridge.agent_execution, "_build_in_process_agent", build)
    bridge._run_agent_sync(
        "裁成16:9", "image-session", "image-test", queue.Queue(), [None],
        client_session_context={"session_id": "image-session", "messages": [],
                                "active_image_artifact_id": "ga_" + "a" * 32},
        client_context_claims={"tenant_key": "image-tenant", "user_id": "image-user",
                               "request_id": "image-request", "policy_version": "signed-policy-v2"},
        sandbox=SimpleNamespace(state_db=tmp_path / "state.db"),
        qcp_enabled=True,
    )
    assert observed["knowledge_policy_version"] == "signed-policy-v2"


@pytest.mark.asyncio
async def test_image_direct_bridge_uses_trusted_session_and_replays_once(tmp_path, monkeypatch):
    import asyncio
    import json
    import scripts.hermes_bridge as bridge
    from backend.services.image_processing import save_image
    from backend.services.workflow_session_scope import register_client_session

    monkeypatch.setenv("AI_LAB_GENERATED_ARTIFACT_ROOT", str(tmp_path))
    actor = {"tenant_key": "direct-bridge", "user_id": "alice"}
    raw = io.BytesIO()
    Image.new("RGB", (160, 90), "blue").save(raw, format="PNG")
    source = save_image(actor["tenant_key"], actor["user_id"], raw.getvalue())
    events = []
    previous_loop = bridge._bridge_async_loop
    bridge._bridge_async_loop = asyncio.get_running_loop()

    def invoke(session_id, identity=actor, data=None):
        bridge._client_context_tool_context.value = {
            "identity": identity, "request_id": "direct-image-bridge-request",
            "client_session_id": session_id, "emit": events.append,
        }
        try:
            return json.loads(bridge._app_capability_invoke_tool({
                "capability_id": "media.process", "input": data if data is not None else {
                    "source_artifact_id": source["artifact_id"], "format": "jpg",
                    "source_client_session_id": "model-invented-session",
                },
            }))
        finally:
            bridge._client_context_tool_context.value = None

    try:
        missing_session = await asyncio.to_thread(invoke, None)
        assert missing_session["error"] == "trusted_invocation_context_required"
        missing_image = await asyncio.to_thread(invoke, "trusted-image-chat", data={"format": "jpg"})
        assert missing_image["error"] == "contract_invalid"
        await register_client_session({**actor, "user_id": "bob"}, "bob-image-chat", "bind-bob")
        foreign_session = await asyncio.to_thread(invoke, "bob-image-chat")
        assert foreign_session["status"] != "completed"
        first = await asyncio.to_thread(invoke, "trusted-image-chat")
        second = await asyncio.to_thread(invoke, "trusted-image-chat")
        assert first["status"] == second["status"] == "completed", str(first)
        workflow = first["events"][0]["payload"]["workflow"]
        replay = second["events"][0]["payload"]["workflow"]
        assert workflow["source_client_session_id"] == "trusted-image-chat"
        assert workflow["latest_execution"]["id"] == replay["latest_execution"]["id"]
        assert [event["type"] for event in events] == ["workflow.created", "workflow.created"]
    finally:
        bridge._bridge_async_loop = previous_loop


@pytest.mark.asyncio
async def test_image_exception_does_not_remove_other_mutation_confirmation():
    from backend.services.capability_catalog import describe_capability
    actor = {"tenant_key": "image-boundary", "user_id": "alice"}
    assert describe_capability("media.process")["confirmation"] == "none"
    for capability in ("knowledge.note.trash", "workflow.create", "workflow.start", "presentation.create_from_text", "media.create"):
        assert describe_capability(capability)["confirmation"] == "required"
        result = await invoke_capability(capability, {}, payload=actor, idempotency_key="image-boundary-check")
        assert result["error"]["code"] == "confirmation_protocol_upgrade_required"
    for data in ({"format": "jpg"}, {"source_artifact_id": "ga_" + "0" * 32}, {"source_artifact_id": "ga_" + "0" * 32, "focus_x": 2}):
        result = await invoke_capability("media.process", data, payload=actor, idempotency_key="image-invalid-check")
        assert result["status"] != "completed"
