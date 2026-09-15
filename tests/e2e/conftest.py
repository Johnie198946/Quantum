from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from docx import Document
from sqlalchemy import select

from backend.api.tenant import current_tenant
from backend.api.workflows import download_artifact
from backend.db import SessionLocal, canonical_plan_hash
from backend.models.workflow import (
    WorkflowArtifact,
    WorkflowExecution,
    WorkflowNodeRun,
    WorkflowPlanVersion,
)
from backend.services.capability_catalog import invoke_capability
from backend.services.workflow_executor import project_event


WORD_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def docx_text(data: bytes) -> str:
    document = Document(BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def docx_page_breaks(data: bytes) -> int:
    with ZipFile(BytesIO(data)) as archive:
        document = archive.read("word/document.xml")
    return document.count(b'<w:br w:type="page"/>')


def assert_sha256(data: bytes, expected: str) -> None:
    assert len(expected) == 64
    assert hashlib.sha256(data).hexdigest() == expected


@dataclass
class RenderedRevision:
    artifact: WorkflowArtifact
    downloaded: bytes


class DocumentWorkflowHarness:
    """Runs the real PCM handler, artifact projector, DOCX renderer and download policy."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self.suffix = uuid.uuid4().hex
        self.tenant = f"pcm-batch5-{self.suffix[:12]}"
        self.user = f"user-{self.suffix[:12]}"
        self.payload = {"tenant_key": self.tenant, "user_id": self.user, "sub": self.user}
        self.output_dir = Path(os.environ.get("PCM_E2E_ARTIFACT_DIR", tmp_path / "artifacts"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("AI_LAB_HOME", str(tmp_path / "vault"))
        self.workflow_id = ""
        self.execution_id = ""
        self.node_id = "document_final"
        self._seq = 0

    docx_text = staticmethod(docx_text)
    docx_page_breaks = staticmethod(docx_page_breaks)

    async def create(self, capability_id: str, data: dict) -> dict:
        tenant_token = current_tenant.set(self.tenant)
        try:
            result = await invoke_capability(
                capability_id,
                data,
                payload=self.payload,
                confirmed=True,
                idempotency_key=f"batch5-{self.suffix}",
            )
        finally:
            current_tenant.reset(tenant_token)
        assert result["status"] == "completed", result
        event = result["events"][0]
        assert event["type"] == "document.created"
        receipt = event["payload"]
        assert receipt["delivery"] == {
            "artifact_extension": "docx",
            "artifact_mime_type": WORD_MIME,
            "download_return": "authenticated_artifact_download_reference",
            "version": "required",
            "content_hash": "required",
        }
        self.workflow_id = receipt["workflow"]["id"]
        self.execution_id = f"wfe_{self.suffix}"
        plan_id = f"wfp_{self.suffix}"
        node_run_id = f"wfn_{self.suffix}"
        dsl = {
            "plan_id": plan_id,
            "name": "Batch 5 deterministic document E2E",
            "version": "1.0.0",
            "nodes": [{
                "id": self.node_id,
                "node_type": "CONTENT_GENERATION",
                "name": "Final governed DOCX",
                "parameters": {"output_format": "word"},
            }],
            "edges": [],
        }
        async with SessionLocal() as db:
            plan = WorkflowPlanVersion(
                id=plan_id,
                workflow_id=self.workflow_id,
                version=1,
                dsl=dsl,
                content_hash=canonical_plan_hash(dsl),
                activation_revision=1,
                goal=data["title"],
                deliverable="Governed editable DOCX",
                allow_network=False,
                knowledge_scope=[],
                validation_errors=[],
            )
            execution = WorkflowExecution(
                id=self.execution_id,
                workflow_id=self.workflow_id,
                plan_id=plan_id,
                tenant_key=self.tenant,
                status="running",
                idempotency_key=f"execution-{self.suffix}",
            )
            node = WorkflowNodeRun(
                id=node_run_id,
                execution_id=self.execution_id,
                node_id=self.node_id,
                node_type="CONTENT_GENERATION",
                name="Final governed DOCX",
                agent_id="main_agent",
                status="pending",
                position=0,
            )
            db.add_all([plan, execution, node])
            await db.commit()
        return receipt

    async def render_revision(self, content: str, version: int, label: str) -> RenderedRevision:
        async with SessionLocal() as db:
            execution = await db.get(WorkflowExecution, self.execution_id)
            node = (
                await db.execute(
                    select(WorkflowNodeRun).where(
                        WorkflowNodeRun.execution_id == self.execution_id,
                        WorkflowNodeRun.node_id == self.node_id,
                    )
                )
            ).scalar_one()
            self._seq += 1
            await project_event(db, execution, {self.node_id: node}, {
                "seq": self._seq,
                "event_id": f"evt-{self.suffix}-{version}-start",
                "type": "node_started",
                "node_id": self.node_id,
                "message": f"Hermes revision {version} started",
            })
            self._seq += 1
            event_id = f"evt-{self.suffix}-{version}-done"
            await project_event(db, execution, {self.node_id: node}, {
                "seq": self._seq,
                "event_id": event_id,
                "type": "node_succeeded",
                "node_id": self.node_id,
                "progress": 100,
                "route": {"model": "deterministic-e2e", "provider": "test-fixture"},
                "usage": {},
                "artifact": {
                    "kind": "final",
                    "title": label,
                    "content": content,
                    "render_type": "word",
                    "artifact_version": version,
                    "source_kind": "hermes_output",
                },
                "message": f"Hermes revision {version} completed",
            })
            await db.commit()
            artifact = (
                await db.execute(
                    select(WorkflowArtifact).where(
                        WorkflowArtifact.execution_id == self.execution_id
                    )
                )
            ).scalars().all()
            artifact = next(
                item for item in artifact
                if (item.metadata_json or {}).get("bridge_event_id") == event_id
            )

        tenant_token = current_tenant.set(self.tenant)
        try:
            response = await download_artifact(self.execution_id, artifact.id, self.payload)
        finally:
            current_tenant.reset(tenant_token)
        downloaded = bytes(response.body)
        assert response.media_type == WORD_MIME
        assert response.headers["x-content-sha256"] == artifact.content_hash
        assert_sha256(downloaded, artifact.content_hash)
        target = self.output_dir / f"{label}-v{version}.docx"
        target.write_bytes(downloaded)
        (self.output_dir / f"{label}-v{version}.receipt.json").write_text(
            json.dumps({
                "workflow_id": self.workflow_id,
                "execution_id": self.execution_id,
                "artifact_id": artifact.id,
                "artifact_version": version,
                "content_hash": artifact.content_hash,
                "mime_type": response.media_type,
            }, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return RenderedRevision(artifact=artifact, downloaded=downloaded)

    async def redownload(self, artifact: WorkflowArtifact) -> bytes:
        tenant_token = current_tenant.set(self.tenant)
        try:
            response = await download_artifact(self.execution_id, artifact.id, self.payload)
        finally:
            current_tenant.reset(tenant_token)
        data = bytes(response.body)
        assert response.headers["x-content-sha256"] == artifact.content_hash
        assert_sha256(data, artifact.content_hash)
        return data


@pytest.fixture
def document_e2e_harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> DocumentWorkflowHarness:
    return DocumentWorkflowHarness(monkeypatch, tmp_path)
