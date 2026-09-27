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
from backend.models.workflow import WorkflowDefinition, WorkflowPlanVersion, WorkflowExecution, WorkflowNodeRun, WorkflowArtifact
from backend.services.capability_catalog import execute_verified_capability
from backend.services.generated_artifacts import GeneratedArtifactError
from backend.services.image_processing import (
    ImageEdit, build_image_plan, decode_image, image_device_action,
)
from backend.services.workflow_artifacts import store_artifact
from backend.services.client_actions import record_client_action_receipt
from backend.services.workflow_executor import project_event


@pytest.mark.asyncio
async def test_upload_to_image_workflow_and_downloadable_jpeg(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_GENERATED_ARTIFACT_ROOT", str(tmp_path / "generated"))
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path / "vault"))
    image = Image.new("RGBA", (640, 480), (200, 30, 50, 0))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    original = stream.getvalue()
    actor = {"tenant_key": "image-tenant", "user_id": "image-user", "sub": "image-user"}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_auth] = lambda: actor
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        upload = await client.post("/api/v1/documents/images", content=original)
        assert upload.status_code == 201, upload.text
        receipt = upload.json()
        downloaded = await client.get("/api/v1/" + receipt["download_path"])
        assert downloaded.content == original
        source_id = receipt["artifact_id"]
        edit = {"format": "jpg", "aspect_ratio": "16:9"}
        context = current_tenant.set(actor["tenant_key"])
        try:
            result = await execute_verified_capability("media.process", {"source_artifact_id": source_id, **edit}, payload=actor, idempotency_key="image-direct-check")
        finally:
            current_tenant.reset(context)
        assert result["status"] == "completed", result
        assert result["events"][0]["renderer"] == "workflow"
        workflow_id = result["events"][0]["payload"]["workflow"]["id"]
        async with SessionLocal() as db:
            workflow = await db.get(WorkflowDefinition, workflow_id)
            plan = build_image_plan(workflow, plan_id="test-image-plan")
            assert plan["nodes"][0]["parameters"]["image_edit"]["aspect_ratio"] == "16:9"
        async with SessionLocal() as db:
            workflow = await db.get(WorkflowDefinition, workflow_id)
            version = WorkflowPlanVersion(id="image-plan", workflow_id=workflow_id, version=1,
                dsl=plan, goal="crop", deliverable="image")
            execution = WorkflowExecution(id="image-run", workflow_id=workflow_id, plan_id=version.id,
                tenant_key=actor["tenant_key"], status="awaiting_approval", idempotency_key="image-test")
            node = WorkflowNodeRun(id="image-node", execution_id=execution.id, node_id="image_edit",
                node_type="OUTPUT_FORMAT", name="parameters", attempt=1)
            db.add(version)
            await db.flush()
            db.add(execution)
            await db.flush()
            db.add(node)
            await db.flush()
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
        # Invalid device bytes cannot move the workflow to success.
        with pytest.raises(HTTPException) as invalid:
            await record_client_action_receipt(action["action_id"], "SUCCEEDED", {"artifact_id": source_id}, actor)
        assert invalid.value.status_code == 422
        async with SessionLocal() as db:
            assert (await db.get(WorkflowExecution, "image-run")).status == "awaiting_approval"
        output = io.BytesIO()
        Image.new("RGB", (640, 360), "white").save(output, format="JPEG")
        result = (await client.post("/api/v1/documents/images", content=output.getvalue())).json()
        metadata = {"artifact_id": result["artifact_id"]}
        with pytest.raises(HTTPException) as denied:
            await record_client_action_receipt(action["action_id"], "SUCCEEDED", metadata, {**actor, "user_id": "other"})
        assert denied.value.status_code == 404
        accepted = await record_client_action_receipt(action["action_id"], "SUCCEEDED", metadata, actor)
        assert accepted["state"] == "SUCCEEDED"
        assert await record_client_action_receipt(action["action_id"], "SUCCEEDED", metadata, actor) == accepted
        async with SessionLocal() as db:
            assert (await db.get(WorkflowExecution, "image-run")).status == "awaiting_review"
            outputs = list((await db.scalars(select(WorkflowArtifact).where(WorkflowArtifact.source_kind == "ios_native"))).all())
            assert len(outputs) == 1 and outputs[0].metadata_json["operations"]["format"] == "jpg"
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
