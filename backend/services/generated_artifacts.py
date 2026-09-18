"""Immutable owner-bound generated artifacts for governed capabilities."""

from __future__ import annotations

import hashlib
import io
import json
import os
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


class GeneratedArtifactError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _safe(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def _root() -> Path:
    configured = os.getenv("AI_LAB_GENERATED_ARTIFACT_ROOT")
    root = Path(configured) if configured else Path(
        os.getenv("AI_LAB_HOME", Path(__file__).resolve().parents[2] / "data" / "vault")
    ) / "generated-artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _owner_root(tenant_key: str, user_id: str) -> Path:
    if not tenant_key or not user_id:
        raise GeneratedArtifactError("invalid_owner", "tenant and user are required")
    path = _root() / _safe(tenant_key) / _safe(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save(
    *, tenant_key: str, user_id: str, filename: str, media_type: str,
    data: bytes, kind: str, metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not data:
        raise GeneratedArtifactError("empty_artifact", "generated artifact is empty")
    artifact_id = f"ga_{uuid.uuid4().hex}"
    directory = _owner_root(tenant_key, user_id) / artifact_id
    directory.mkdir(mode=0o700)
    suffix = Path(filename).suffix.lower()
    content_path = directory / f"content{suffix}"
    content_path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    receipt = {
        "artifact_id": artifact_id,
        "kind": kind,
        "filename": Path(filename).name,
        "media_type": media_type,
        "content_hash": digest,
        "byte_size": len(data),
        "revision": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
        "download_path": f"documents/generated/{artifact_id}/download",
    }
    (directory / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return receipt


def read_generated_artifact(tenant_key: str, user_id: str, artifact_id: str) -> dict[str, Any]:
    if not artifact_id.startswith("ga_") or len(artifact_id) != 35:
        raise GeneratedArtifactError("artifact_not_found", "artifact not found")
    path = _owner_root(tenant_key, user_id) / artifact_id / "receipt.json"
    if not path.is_file():
        raise GeneratedArtifactError("artifact_not_found", "artifact not found")
    return json.loads(path.read_text(encoding="utf-8"))


def generated_artifact_path(tenant_key: str, user_id: str, artifact_id: str) -> tuple[Path, dict[str, Any]]:
    receipt = read_generated_artifact(tenant_key, user_id, artifact_id)
    directory = _owner_root(tenant_key, user_id) / artifact_id
    matches = [item for item in directory.glob("content.*") if item.is_file()]
    if len(matches) != 1:
        raise GeneratedArtifactError("artifact_not_found", "artifact content not found")
    data = matches[0].read_bytes()
    if hashlib.sha256(data).hexdigest() != receipt["content_hash"]:
        raise GeneratedArtifactError("artifact_integrity_failed", "artifact hash mismatch")
    return matches[0], receipt


def create_spreadsheet(tenant_key: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    columns = data.get("columns") or []
    rows = data.get("rows") or []
    if not columns or len(columns) > 100 or len(rows) > 10_000:
        raise GeneratedArtifactError("invalid_spreadsheet", "columns and bounded rows are required")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = str(data.get("sheet_name") or "Sheet1")[:31]
    sheet.append([str(item) for item in columns])
    for row in rows:
        if not isinstance(row, list) or len(row) != len(columns):
            raise GeneratedArtifactError("invalid_spreadsheet", "row width must equal columns")
        sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    title = str(data.get("title") or "spreadsheet")
    return _save(
        tenant_key=tenant_key, user_id=user_id, filename=f"{title[:80]}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=stream.getvalue(), kind="spreadsheet", metadata={"row_count": len(rows)},
    )


def create_pdf(tenant_key: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    text = str(data.get("content") or "").strip()
    if not text or len(text) > 200_000:
        raise GeneratedArtifactError("invalid_pdf_content", "bounded content is required")
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4, pageCompression=1)
    width, height = A4
    y = height - 54
    for paragraph in text.splitlines() or [text]:
        for line in textwrap.wrap(paragraph, width=92) or [""]:
            safe_line = line.encode("latin-1", "replace").decode("latin-1")
            pdf.drawString(48, y, safe_line)
            y -= 15
            if y < 54:
                pdf.showPage()
                y = height - 54
    pdf.save()
    title = str(data.get("title") or "document")
    return _save(
        tenant_key=tenant_key, user_id=user_id, filename=f"{title[:80]}.pdf",
        media_type="application/pdf", data=stream.getvalue(), kind="pdf",
        metadata={"source_characters": len(text)},
    )


def analyze_data(tenant_key: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    columns = data.get("columns") or []
    rows = data.get("rows") or []
    if not columns or len(columns) > 100 or len(rows) > 100_000:
        raise GeneratedArtifactError("invalid_dataset", "bounded columns and rows are required")
    summary: dict[str, Any] = {"row_count": len(rows), "column_count": len(columns), "columns": {}}
    for index, column in enumerate(columns):
        values = [row[index] if isinstance(row, list) and index < len(row) else None for row in rows]
        numbers = [float(value) for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
        item: dict[str, Any] = {"missing": sum(value is None for value in values)}
        if numbers:
            item.update({"count": len(numbers), "min": min(numbers), "max": max(numbers), "mean": sum(numbers) / len(numbers)})
        summary["columns"][str(column)] = item
    raw = json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2).encode()
    receipt = _save(
        tenant_key=tenant_key, user_id=user_id, filename="analysis.json",
        media_type="application/json", data=raw, kind="data_analysis", metadata=summary,
    )
    return {**receipt, "analysis": summary}


def create_media(tenant_key: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    prompt = str(data.get("prompt") or "").strip()
    width = int(data.get("width") or 1200)
    height = int(data.get("height") or 675)
    if not prompt or len(prompt) > 2_000 or not (320 <= width <= 2048 and 320 <= height <= 2048):
        raise GeneratedArtifactError("invalid_media_request", "prompt and bounded dimensions are required")
    digest = hashlib.sha256(prompt.encode()).digest()
    background = tuple(32 + value % 160 for value in digest[:3])
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(18, min(width, height) // 24))
    lines = textwrap.wrap(prompt, width=max(20, width // 24))[:12]
    draw.multiline_text((width * 0.08, height * 0.12), "\n".join(lines), fill="white", font=font, spacing=8)
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=True)
    return _save(
        tenant_key=tenant_key, user_id=user_id, filename="generated-media.png",
        media_type="image/png", data=stream.getvalue(), kind="media",
        metadata={"width": width, "height": height, "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest()},
    )
