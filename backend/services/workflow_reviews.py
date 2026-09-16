"""Structured workflow review validation and wire projection.

The API module owns HTTP routes and persistence.  This module owns the stable,
pure review document contract so review behavior has one testable source.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from backend.models.workflow import WorkflowReviewRevision

REVIEW_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
_REVIEW_FIELD_TYPES = {"text", "textarea", "choice", "number", "toggle"}


def validate_review_document(document: dict[str, Any]) -> dict[str, Any]:
    if set(document) != {"title", "fields", "values"}:
        raise HTTPException(status_code=422, detail="结构化审核文档字段不合法")
    title, fields, values = document["title"], document["fields"], document["values"]
    if not isinstance(title, str) or not title.strip() or len(title) > 160:
        raise HTTPException(status_code=422, detail="结构化审核标题不合法")
    if (
        not isinstance(fields, list)
        or not 1 <= len(fields) <= 100
        or not isinstance(values, dict)
    ):
        raise HTTPException(status_code=422, detail="结构化审核字段不合法")
    seen: set[str] = set()
    for field in fields:
        if (
            not isinstance(field, dict)
            or not {"id", "label", "type", "required"} <= set(field)
        ):
            raise HTTPException(status_code=422, detail="结构化审核字段定义不完整")
        if set(field) - {"id", "label", "type", "required", "options"}:
            raise HTTPException(status_code=422, detail="结构化审核字段包含未知属性")
        field_id = field.get("id")
        field_type = field.get("type")
        label = field.get("label")
        if (
            not isinstance(field_id, str)
            or not REVIEW_KEY.fullmatch(field_id)
            or field_id in seen
            or field_type not in _REVIEW_FIELD_TYPES
            or not isinstance(label, str)
            or not label.strip()
            or len(label) > 160
            or not isinstance(field.get("required"), bool)
        ):
            raise HTTPException(status_code=422, detail="结构化审核字段定义不合法")
        seen.add(field_id)
        options = field.get("options")
        if field_type == "choice":
            if (
                not isinstance(options, list)
                or not 1 <= len(options) <= 30
                or any(
                    not isinstance(item, str) or not item or len(item) > 160
                    for item in options
                )
                or len(set(options)) != len(options)
            ):
                raise HTTPException(status_code=422, detail="结构化审核选项不合法")
        elif options is not None:
            raise HTTPException(status_code=422, detail="仅 choice 字段允许 options")
    if len(values) > 100 or set(values) - seen:
        raise HTTPException(status_code=422, detail="结构化审核值包含未知字段")
    by_id = {field["id"]: field for field in fields}
    for field_id, value in values.items():
        field = by_id[field_id]
        expected = field["type"]
        valid = (
            value is None
            or (
                expected in {"text", "textarea"}
                and isinstance(value, str)
                and len(value) <= 12000
            )
            or (
                expected == "choice"
                and isinstance(value, str)
                and value in field["options"]
            )
            or (
                expected == "number"
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            )
            or (expected == "toggle" and isinstance(value, bool))
        )
        if not valid:
            raise HTTPException(
                status_code=422,
                detail=f"结构化审核值类型不匹配：{field_id}",
            )
    if len(
        json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")
    ) > 100_000:
        raise HTTPException(status_code=422, detail="结构化审核文档过大")
    return document


def review_etag(row: WorkflowReviewRevision) -> str:
    return f'"sr:{row.review_key}:{row.version}:{row.content_hash[:16]}"'


def review_out(row: WorkflowReviewRevision) -> dict[str, Any]:
    return {
        "workflow_id": row.workflow_id,
        "review_key": row.review_key,
        "schema_id": row.schema_id,
        "version": row.version,
        "parent_version": row.parent_version,
        "content_hash": row.content_hash,
        "document": row.document,
        "action": row.action,
        "receipt_id": row.receipt_id,
        "source_client_session_id": row.source_client_session_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
