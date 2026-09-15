"""Fail-closed validation and deterministic caching for presentation materials."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

_RASTER_MIME = {"image/png": (b"\x89PNG\r\n\x1a\n", "png"), "image/jpeg": (b"\xff\xd8\xff", "jpg")}
_ALLOWED_LICENSES = {
    "CC0-1.0",
    "CC-BY-4.0",
    "Pexels",
    "Unsplash",
    "user-provided",
}
_MAX_BYTES = 8_000_000
_MAX_PIXELS = 24_000_000


def _safe_url(value: str, *, allow_user_source: bool) -> str:
    if allow_user_source and value.startswith("user://"):
        return value
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("material source URL must be public HTTPS or user-provided")
    return value


def _svg_dimensions(root: ET.Element) -> tuple[int, int]:
    def number(value: str | None) -> float | None:
        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)(?:px)?\s*", value or "")
        return float(match.group(1)) if match else None

    width, height = number(root.get("width")), number(root.get("height"))
    if width and height:
        return int(round(width)), int(round(height))
    parts = re.split(r"[ ,]+", (root.get("viewBox") or "").strip())
    if len(parts) == 4:
        try:
            view_width, view_height = float(parts[2]), float(parts[3])
        except ValueError as exc:
            raise ValueError("SVG viewBox is invalid") from exc
        if view_width > 0 and view_height > 0:
            return int(round(view_width)), int(round(view_height))
    raise ValueError("SVG needs positive width/height or viewBox")


def _validate_svg(data: bytes) -> tuple[int, int]:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("SVG document types and entities are forbidden")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError("SVG cannot be parsed") from exc
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise ValueError("material does not contain an SVG root")
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag in {"script", "foreignobject"}:
            raise ValueError("SVG active content is forbidden")
        for key, value in element.attrib.items():
            normalized_key = key.rsplit("}", 1)[-1].lower()
            normalized_value = str(value).strip().lower()
            if normalized_key.startswith("on") or normalized_value.startswith("javascript:"):
                raise ValueError("SVG event handlers are forbidden")
            if normalized_key == "href" and normalized_value.startswith(("http:", "https:", "data:", "file:")):
                raise ValueError("SVG external resources are forbidden")
    width, height = _svg_dimensions(root)
    if width < 16 or height < 16 or width * height > _MAX_PIXELS:
        raise ValueError("SVG dimensions are outside the safe range")
    return width, height


def validate_material_bytes(
    data: bytes,
    *,
    declared_mime: str,
    source_url: str,
    author: str,
    license_id: str,
    license_url: str,
    fetched_at: str,
    commercial_use_allowed: bool,
) -> dict[str, Any]:
    """Validate bytes, format, provenance, and commercial-use permission."""
    if not isinstance(data, bytes) or not 32 <= len(data) <= _MAX_BYTES:
        raise ValueError("material byte size is outside the safe range")
    if license_id not in _ALLOWED_LICENSES or not commercial_use_allowed:
        raise ValueError("material license does not permit commercial use")
    if not author.strip() or not fetched_at.strip():
        raise ValueError("material author and fetch time are required")
    user_source = license_id == "user-provided"
    _safe_url(source_url, allow_user_source=user_source)
    _safe_url(license_url, allow_user_source=user_source)

    if declared_mime in _RASTER_MIME:
        signature, extension = _RASTER_MIME[declared_mime]
        if not data.startswith(signature):
            raise ValueError("material signature does not match declared MIME")
        expected_format = "PNG" if declared_mime == "image/png" else "JPEG"
        try:
            with Image.open(BytesIO(data)) as image:
                width, height = image.size
                actual_format = image.format
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("material image cannot be decoded") from exc
        if actual_format != expected_format:
            raise ValueError("material decoded format does not match declared MIME")
        if width < 64 or height < 64 or width * height > _MAX_PIXELS:
            raise ValueError("material image dimensions are outside the safe range")
    elif declared_mime == "image/svg+xml":
        extension = "svg"
        width, height = _validate_svg(data)
    else:
        raise ValueError("material MIME is unsupported")

    digest = hashlib.sha256(data).hexdigest()
    return {
        "source_url": source_url,
        "author": author.strip(),
        "license_id": license_id,
        "license_url": license_url,
        "commercial_use_allowed": True,
        "fetched_at": fetched_at,
        "content_hash": digest,
        "mime_type": declared_mime,
        "byte_size": len(data),
        "width": width,
        "height": height,
        "extension": extension,
        "cache_status": "validated",
    }


def cache_validated_material(
    data: bytes, manifest: dict[str, Any], *, cache_root: Path
) -> dict[str, Any]:
    """Atomically cache only bytes that still match their validated manifest."""
    digest = hashlib.sha256(data).hexdigest()
    if manifest.get("cache_status") != "validated" or manifest.get("content_hash") != digest:
        raise ValueError("material bytes do not match validated manifest")
    extension = str(manifest.get("extension") or "")
    if extension not in {"png", "jpg", "svg"}:
        raise ValueError("material cache extension is invalid")
    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / f"{digest}.{extension}"
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("material cache collision or corruption detected")
    else:
        descriptor, temporary = tempfile.mkstemp(prefix=".material-", dir=cache_root)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {**manifest, "cache_status": "ready", "cache_path": target.name}
