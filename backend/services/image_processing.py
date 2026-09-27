"""Image validation and device-result coordination; pixel processing runs on iOS."""
from __future__ import annotations

import hashlib
import io
import re
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.services.generated_artifacts import GeneratedArtifactError, _save, generated_artifact_path

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
FORMATS = {"PNG": ("png", "image/png"), "JPEG": ("jpg", "image/jpeg"), "WEBP": ("webp", "image/webp")}

class StudioPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)

class StudioCrop(BaseModel):
    model_config = ConfigDict(extra="forbid")
    corners: list[StudioPoint] = Field(min_length=4, max_length=4)
    width: int = Field(ge=1, le=12000)
    height: int = Field(ge=1, le=12000)

    @model_validator(mode="after")
    def convex_region(self):
        points = self.corners
        cross = [(points[(i+1)%4].x-points[i].x)*(points[(i+2)%4].y-points[(i+1)%4].y)
                 -(points[(i+1)%4].y-points[i].y)*(points[(i+2)%4].x-points[(i+1)%4].x) for i in range(4)]
        if not (all(x > 1e-10 for x in cross) or all(x < -1e-10 for x in cross)):
            raise ValueError("裁剪区域必须是非退化凸四边形")
        return self

class StudioStroke(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(max_length=80)
    points: list[StudioPoint] = Field(min_length=1, max_length=256)
    radius: float = Field(0.015, ge=0.001, le=0.08, allow_inf_nan=False)

class StudioLayer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(max_length=80)
    kind: Literal["text", "image"] = "text"
    text: str = Field("", max_length=2000)
    asset_id: str | None = Field(None, pattern=r"^(ga|doc)_[a-f0-9]{32}$")
    font: Literal["sans", "serif", "hand"] = "serif"
    font_size: float = Field(0.12, ge=0.01, le=0.5, allow_inf_nan=False)
    color: str = Field("FFF7EC", pattern=r"^[0-9a-fA-F]{6}$")
    x: float = Field(0.5, ge=0, le=1, allow_inf_nan=False)
    y: float = Field(0.2, ge=0, le=1, allow_inf_nan=False)
    width: float = Field(0.85, ge=0.02, le=2, allow_inf_nan=False)
    rotation: float = Field(0, ge=-360, le=360, allow_inf_nan=False)
    opacity: float = Field(1, ge=0, le=1, allow_inf_nan=False)
    visible: bool = True
    locked: bool = False
    alignment: Literal["left", "center", "right"] = "center"
    tracking: float = Field(0, ge=-0.05, le=0.1, allow_inf_nan=False)
    outline: float = Field(0, ge=0, le=0.1, allow_inf_nan=False)
    shadow: float = Field(0, ge=0, le=0.1, allow_inf_nan=False)
    blend: Literal["normal", "multiply", "screen", "overlay"] = "normal"

class StudioRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    crops: list[StudioCrop] = Field(default_factory=list, max_length=12)
    rotation: Literal[0, 90, 180, 270] = 0
    flip_horizontal: bool = False
    subject: bool = False
    subject_x: float = Field(0.5, ge=0, le=1, allow_inf_nan=False)
    subject_y: float = Field(0.5, ge=0, le=1, allow_inf_nan=False)
    exposure: float = Field(0, ge=-2, le=2, allow_inf_nan=False)
    contrast: float = Field(1, ge=0.5, le=2, allow_inf_nan=False)
    saturation: float = Field(1, ge=0, le=2, allow_inf_nan=False)
    temperature: float = Field(6500, ge=2500, le=10000, allow_inf_nan=False)
    shadows: float = Field(0, ge=0, le=1, allow_inf_nan=False)
    filter: Literal["original", "sunny", "mint", "film"] = "original"
    intensity: float = Field(1, ge=0, le=1, allow_inf_nan=False)
    layers: list[StudioLayer] = Field(default_factory=list, max_length=20)
    strokes: list[StudioStroke] = Field(default_factory=list, max_length=40)
    output_width: int | None = Field(None, ge=1, le=12000)
    output_height: int | None = Field(None, ge=1, le=12000)
    quality: float = Field(0.9, ge=0.1, le=1, allow_inf_nan=False)
    remove_location: bool = True

    @model_validator(mode="after")
    def validate_structure(self):
        if (self.output_width is None) != (self.output_height is None):
            raise ValueError("输出宽高必须同时指定")
        if self.output_width and self.output_width * self.output_height > MAX_IMAGE_PIXELS:
            raise ValueError("输出不得超过2400万像素")
        if any(c.width * c.height > MAX_IMAGE_PIXELS for c in self.crops):
            raise ValueError("裁剪不得超过2400万像素")
        if len({x.id for x in self.layers}) != len(self.layers):
            raise ValueError("图层ID必须唯一")
        if any(x.kind == "image" and not x.asset_id for x in self.layers):
            raise ValueError("图片图层缺少私有素材引用")
        return self


class ImageEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["png", "jpg"] = "png"
    aspect_ratio: Literal["original", "16:9", "9:16", "1:1", "4:3", "3:4"] = "original"
    studio: StudioRecipe | None = None
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
    if not re.fullmatch(r"(ga|doc)_[a-f0-9]{32}", source_id):
        raise GeneratedArtifactError("invalid_image_source", "图片引用无效")
    if source_id.startswith("doc_"):
        from backend.services.document_sources import DocumentSourceError, document_original_path
        try:
            path, receipt = document_original_path(tenant_key, user_id, source_id)
        except DocumentSourceError as exc:
            raise GeneratedArtifactError("invalid_image_source", "图片原件不可用") from exc
    else:
        path, receipt = generated_artifact_path(tenant_key, user_id, source_id)
        if receipt["kind"] not in {"image_source", "image_processed"}:
            raise GeneratedArtifactError("invalid_image_source", "请选择已上传的图片")
    raw = path.read_bytes()
    image, _ = decode_image(raw)
    return {"artifact_id": source_id, "content_hash": hashlib.sha256(raw).hexdigest(),
            "width": image.width, "height": image.height}


def validate_studio_assets(tenant_key: str, user_id: str, edit: ImageEdit) -> None:
    if edit.studio:
        for layer in edit.studio.layers:
            if layer.asset_id:
                workflow_image_source(tenant_key, user_id, layer.asset_id)


def expected_image_size(source: dict, edit: ImageEdit) -> tuple[int, int]:
    width, height = source["width"], source["height"]
    if edit.aspect_ratio != "original":
        rw, rh = map(int, edit.aspect_ratio.split(":"))
        scale = min(width // rw, height // rh)
        width, height = scale * rw, scale * rh
    if edit.studio:
        for crop in edit.studio.crops:
            if crop.width * crop.height > width * height:
                raise GeneratedArtifactError("invalid_crop", "裁剪不能放大图片")
            width, height = crop.width, crop.height
        if edit.studio.rotation in (90, 270):
            width, height = height, width
        if edit.studio.output_width:
            if edit.studio.output_width > width or edit.studio.output_height > height:
                raise GeneratedArtifactError("invalid_resize", "输出不能超过当前图像尺寸")
            width, height = edit.studio.output_width, edit.studio.output_height
    if width < 1 or height < 1:
        raise GeneratedArtifactError("invalid_dimensions", "图片尺寸无效")
    return width, height


def validate_processed_image(tenant_key: str, user_id: str, source_id: str, source_hash: str,
                             result_id: str, edit: ImageEdit):
    source = workflow_image_source(tenant_key, user_id, source_id)
    if source["content_hash"] != source_hash:
        raise GeneratedArtifactError("source_changed", "原图已变化")
    validate_studio_assets(tenant_key, user_id, edit)
    if not re.fullmatch(r"ga_[a-f0-9]{32}", result_id):
        raise GeneratedArtifactError("invalid_image_result", "结果引用无效")
    path, receipt = generated_artifact_path(tenant_key, user_id, result_id)
    raw = path.read_bytes()
    image, fmt = decode_image(raw)
    if image.size != expected_image_size(source, edit) or FORMATS[fmt][0] != edit.format:
        raise GeneratedArtifactError("result_mismatch", "结果格式或尺寸与编辑参数不符")
    alpha = image.getextrema()[3]
    if edit.extract_subject and edit.studio is None and (edit.format != "png" or alpha[0] == 255 or alpha[1] == 0):
        raise GeneratedArtifactError("result_alpha_invalid", "主体提取必须产生透明PNG")
    return raw, receipt, source


def save_processed_image(tenant_key: str, user_id: str, data: dict, key: str) -> dict:
    edit = ImageEdit.model_validate(data["edit"])
    raw, receipt, source = validate_processed_image(tenant_key, user_id, data["source_artifact_id"],
        data["source_hash"], data["result_artifact_id"], edit)
    filename = re.sub(r"[\\/\x00-\x1f]", "_", data.get("filename", "图片副本"))[:80]
    filename = filename.rsplit(".", 1)[0] + "." + edit.format
    return _save(tenant_key=tenant_key, user_id=user_id, data=raw, filename=filename,
        media_type=receipt["media_type"], kind="image_processed", idempotency_key="media.save_edit:" + key, metadata={
            "source_artifact_id": source["artifact_id"], "source_content_hash": source["content_hash"],
            "operations": edit.model_dump(), "execution_origin": "ios_native",
            "width": expected_image_size(source, edit)[0], "height": expected_image_size(source, edit)[1]})


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
    from backend.models.workflow import WorkflowArtifact, WorkflowNodeRun
    from backend.services.client_actions import issue_client_action
    from backend.services.workflow_artifacts import read_verified_artifact, run_root

    if execution.status != "awaiting_approval" or (workflow.requirements_snapshot or {}).get("output_kind") != "image":
        raise HTTPException(409, "没有待处理的手机图片任务")
    artifacts = list((await db.scalars(select(WorkflowArtifact).where(
        WorkflowArtifact.execution_id == execution.id,
    ).order_by(WorkflowArtifact.created_at.desc()))).all())
    instruction = None
    for candidate in artifacts:
        if (candidate.metadata_json or {}).get("render_type") != "image_edit":
            continue
        node = await db.get(WorkflowNodeRun, candidate.node_run_id)
        if node and node.attempt == (candidate.metadata_json or {}).get("artifact_version"):
            instruction = candidate
            break
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
    if not re.fullmatch(r"ga_[a-f0-9]{32}", result_id):
        raise HTTPException(422, "请上传处理后的图片")
    workflow_image_source(action.tenant_key, action.user_id, result_id)
    path, receipt = generated_artifact_path(action.tenant_key, action.user_id, result_id)
    raw = path.read_bytes()
    image, fmt = decode_image(raw)
    edit = ImageEdit.model_validate(request["image_edit"])
    try:
        validate_processed_image(action.tenant_key, action.user_id, request["artifact_id"],
            request["source_hash"], result_id, edit)
    except GeneratedArtifactError as exc:
        raise HTTPException(422, str(exc)) from exc
    artifact = store_artifact(execution, node_run_id=node.id, kind="final", title="处理后的图片",
        content=raw, source_kind="ios_native", extension=edit.format,
        metadata={"render_type": "image", "mime_type": receipt["media_type"],
                  "artifact_version": node.attempt, "device_action_id": action.id,
                  "source_content_hash": source["content_hash"], "operations": edit.model_dump()})
    db.add(artifact)
    instruction.selected_for_publish = False
    execution.status = "completed"
    execution.progress = 100
    execution.artifact_count += 1
    execution.finished_at = datetime.now(timezone.utc)
    db.add(WorkflowEvent(execution_id=execution.id, event_type="device_image_completed",
        message="iPhone 已完成图片处理，结果已校验保存", payload={"artifact_id": artifact.id, "content_hash": artifact.content_hash}))
