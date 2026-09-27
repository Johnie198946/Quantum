"""Image validation and device-result coordination; pixel processing runs on iOS."""
from __future__ import annotations

import hashlib
import io
import re
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from backend.services.generated_artifacts import GeneratedArtifactError, _save, generated_artifact_path

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
FORMATS = {"PNG": ("png", "image/png"), "JPEG": ("jpg", "image/jpeg"), "WEBP": ("webp", "image/webp")}


class ImageEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["png", "jpg"] = "png"
    aspect_ratio: Literal["original", "16:9", "9:16", "1:1", "4:3", "3:4"] = "original"
    extract_subject: bool = False
    focus_x: float = Field(0.5, ge=0, le=1, allow_inf_nan=False)
    focus_y: float = Field(0.5, ge=0, le=1, allow_inf_nan=False)


def decode_image(data: bytes) -> tuple[Image.Image, str]:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise GeneratedArtifactError("image_size_invalid", "图片不能为空且不得超过 12 MB")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in FORMATS or getattr(source, "n_frames", 1) != 1:
                raise GeneratedArtifactError("image_type_invalid", "请选择静态 PNG、JPEG 或 WebP 图片")
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise GeneratedArtifactError("image_dimensions_invalid", "图片不得超过 2400 万像素")
            fmt = source.format
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGBA")
        return image, fmt
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise GeneratedArtifactError("image_decode_failed", "无法读取图片，请重新选择") from exc


def save_image(tenant_key: str, user_id: str, data: bytes) -> dict:
    image, fmt = decode_image(data)
    extension, mime = FORMATS[fmt]
    return _save(tenant_key=tenant_key, user_id=user_id, filename=f"original.{extension}",
                 media_type=mime, data=data, kind="image_source",
                 metadata={"width": image.width, "height": image.height, "has_alpha": image.getextrema()[3][0] < 255})


def workflow_image_source(tenant_key: str, user_id: str, source_id: str) -> dict:
    if not re.fullmatch(r"ga_[a-f0-9]{32}", source_id):
        raise GeneratedArtifactError("invalid_image_source", "图片引用无效")
    path, receipt = generated_artifact_path(tenant_key, user_id, source_id)
    if receipt["kind"] not in {"image_source", "image_processed"}:
        raise GeneratedArtifactError("invalid_image_source", "请选择已上传的图片")
    raw = path.read_bytes()
    image, _ = decode_image(raw)
    return {"artifact_id": source_id, "content_hash": hashlib.sha256(raw).hexdigest(),
            "width": image.width, "height": image.height}


def build_image_plan(workflow, *, plan_id: str) -> dict | None:
    snapshot = workflow.requirements_snapshot or {}
    if snapshot.get("output_kind") != "image":
        return None
    return {"plan_id": plan_id, "name": workflow.title, "version": "1.0.0",
            "scenario_id": "image-processing", "nodes": [{
                "id": "image_edit", "node_type": "OUTPUT_FORMAT", "name": "生成手机图片处理参数",
                "parameters": {"agent_id": "main_agent", "output_format": "image_edit",
                               **({"image_edit": snapshot["image_edit"]} if "image_edit" in snapshot else {}),
                               "knowledge_scope": [], "allow_network": False, "max_tokens": 1500,
                               "instruction": "将用户要求转换成图片编辑参数。保持原图像素，不生成或重画主体；未指明位置时用中心点。"},
            }], "edges": []}


async def image_device_action(db, execution, workflow, payload):
    """Resume the same owner-bound device task after reconnecting or relaunching."""
    from fastapi import HTTPException
    from sqlalchemy import select
    from backend.models.workflow import WorkflowArtifact
    from backend.services.client_actions import issue_client_action
    from backend.services.workflow_artifacts import read_verified_artifact, run_root

    if execution.status != "awaiting_approval" or (workflow.requirements_snapshot or {}).get("output_kind") != "image":
        raise HTTPException(409, "没有待处理的手机图片任务")
    artifacts = list((await db.scalars(select(WorkflowArtifact).where(
        WorkflowArtifact.execution_id == execution.id,
    ).order_by(WorkflowArtifact.created_at.desc()))).all())
    instruction = next((a for a in artifacts if (a.metadata_json or {}).get("render_type") == "image_edit"), None)
    if instruction is None:
        raise HTTPException(409, "图片参数尚未就绪")
    edit = ImageEdit.model_validate_json(read_verified_artifact(run_root(execution) / instruction.relative_path, instruction.content_hash))
    source = workflow.requirements_snapshot["source_image"]
    verified = workflow_image_source(execution.tenant_key, str(workflow.created_by), source["artifact_id"])
    if verified["content_hash"] != source["content_hash"]:
        raise HTTPException(409, "原图已变化")
    return await issue_client_action("media.process", {
        "execution_id": execution.id, "instruction_id": instruction.id,
        "artifact_id": source["artifact_id"], "source_hash": source["content_hash"],
        "image_edit": edit.model_dump(),
    }, payload, f"image:{execution.id}:{instruction.id}")


async def finish_device_image(db, action, status, metadata):
    """Validate saved bytes and atomically accept the device receipt and workflow result."""
    from datetime import datetime, timezone
    from fastapi import HTTPException
    from sqlalchemy import select
    from backend.models.workflow import WorkflowArtifact, WorkflowExecution, WorkflowNodeRun, WorkflowEvent
    from backend.services.workflow_artifacts import store_artifact

    request = action.request_payload
    execution = await db.scalar(select(WorkflowExecution).where(
        WorkflowExecution.id == request["execution_id"],
        WorkflowExecution.tenant_key == action.tenant_key,
    ).with_for_update())
    instruction = await db.get(WorkflowArtifact, request["instruction_id"])
    node = await db.get(WorkflowNodeRun, instruction.node_run_id) if instruction else None
    if (not execution or execution.status != "awaiting_approval" or not node
            or node.attempt != (instruction.metadata_json or {}).get("artifact_version")):
        raise HTTPException(409, "图片任务已变化，请刷新后重试")
    if status != "SUCCEEDED":
        execution.status = "cancelled" if status == "CANCELLED" else "failed"
        execution.finished_at = datetime.now(timezone.utc)
        return
    source = workflow_image_source(action.tenant_key, action.user_id, request["artifact_id"])
    if source["content_hash"] != request["source_hash"]:
        raise HTTPException(409, "原图校验失败")
    result_id = str(metadata.get("artifact_id") or "")
    workflow_image_source(action.tenant_key, action.user_id, result_id)
    path, receipt = generated_artifact_path(action.tenant_key, action.user_id, result_id)
    raw = path.read_bytes()
    image, fmt = decode_image(raw)
    edit = ImageEdit.model_validate(request["image_edit"])
    width, height = source["width"], source["height"]
    if edit.aspect_ratio != "original":
        rw, rh = map(int, edit.aspect_ratio.split(":"))
        scale = min(width // rw, height // rh)
        width, height = scale * rw, scale * rh
    alpha = image.getextrema()[3]
    if (FORMATS[fmt][0] != edit.format or image.size != (width, height)
            or (edit.extract_subject and (edit.format != "png" or alpha[0] == 255 or alpha[1] == 0))):
        raise HTTPException(422, "图片结果与任务格式、尺寸或透明背景要求不符")
    artifact = store_artifact(execution, node_run_id=node.id, kind="final", title="处理后的图片",
        content=raw, source_kind="ios_native", extension=edit.format,
        metadata={"render_type": "image", "mime_type": receipt["media_type"],
                  "artifact_version": node.attempt, "device_action_id": action.id,
                  "source_content_hash": source["content_hash"], "operations": edit.model_dump()})
    db.add(artifact)
    instruction.selected_for_publish = False
    execution.status = "awaiting_review"
    execution.progress = 100
    execution.artifact_count += 1
    execution.finished_at = datetime.now(timezone.utc)
    db.add(WorkflowEvent(execution_id=execution.id, event_type="device_image_completed",
        message="iPhone 已完成图片处理，结果已校验保存", payload={"artifact_id": artifact.id, "content_hash": artifact.content_hash}))
