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
_REVIEW_FIELD_TYPES_BY_SCHEMA = {
    "workflow.structured-review.v1": {"text", "textarea", "choice", "number", "toggle"},
    "workflow.structured-review.v2": {
        "text", "textarea", "choice", "number", "toggle", "list", "page_structure", "asset",
    },
}


def _valid_review_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= 100
        and all(isinstance(item, str) and len(item) <= 2000 for item in value)
    )


def _valid_page_structure(value: Any) -> bool:
    if not isinstance(value, list) or len(value) > 60:
        return False
    seen: set[str] = set()
    for page in value:
        if not isinstance(page, dict) or not {"id", "title"} <= set(page):
            return False
        if set(page) - {"id", "title", "summary"}:
            return False
        page_id, title, summary = page.get("id"), page.get("title"), page.get("summary", "")
        if (
            not isinstance(page_id, str)
            or not REVIEW_KEY.fullmatch(page_id)
            or page_id in seen
            or not isinstance(title, str)
            or not title.strip()
            or len(title) > 300
            or not isinstance(summary, str)
            or len(summary) > 2000
        ):
            return False
        seen.add(page_id)
    return True


def _valid_asset(value: Any) -> bool:
    if not isinstance(value, dict) or not {"id", "name", "url"} <= set(value):
        return False
    if set(value) - {"id", "name", "url", "source_url", "mime_type", "sha256", "license"}:
        return False
    asset_id, name, url = value.get("id"), value.get("name"), value.get("url")
    if (
        not isinstance(asset_id, str)
        or not REVIEW_KEY.fullmatch(asset_id)
        or not isinstance(name, str)
        or not name.strip()
        or len(name) > 300
        or not isinstance(url, str)
        or not url.startswith(("https://", "http://"))
        or len(url) > 2000
    ):
        return False
    for key, maximum in (("source_url", 2000), ("mime_type", 160), ("license", 300)):
        optional = value.get(key)
        if optional is not None and (not isinstance(optional, str) or len(optional) > maximum):
            return False
    source_url = value.get("source_url")
    if source_url and not source_url.startswith(("https://", "http://")):
        return False
    digest = value.get("sha256")
    return digest is None or (
        isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
    )


def validate_review_document(
    document: dict[str, Any], *, schema_id: str = "workflow.structured-review.v1"
) -> dict[str, Any]:
    field_types = _REVIEW_FIELD_TYPES_BY_SCHEMA.get(schema_id)
    if field_types is None:
        raise HTTPException(status_code=422, detail="不支持的结构化审核 schema_id")
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
            or field_type not in field_types
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
            or (expected == "list" and _valid_review_list(value))
            or (expected == "page_structure" and _valid_page_structure(value))
            or (expected == "asset" and _valid_asset(value))
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
