import json
from io import BytesIO
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from PIL import Image

from backend.services.presentation_materials import (
    cache_validated_material,
    validate_material_bytes,
)


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (320, 240), "#3A6EA5").save(output, format="PNG")
    return output.getvalue()


def _metadata(**overrides):
    value = {
        "declared_mime": "image/png",
        "source_url": "https://images.example.test/istanbul.png",
        "author": "Example Photographer",
        "license_id": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "fetched_at": "2026-09-15T11:00:00+08:00",
        "commercial_use_allowed": True,
    }
    value.update(overrides)
    return value


def _schema():
    return json.loads(
        Path("backend/contracts/presentation/material-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )


def test_valid_raster_material_records_license_hash_mime_dimensions_and_cache(tmp_path):
    data = _png()
    validated = validate_material_bytes(data, **_metadata())
    Draft202012Validator(_schema()).validate(validated)
    ready = cache_validated_material(data, validated, cache_root=tmp_path)
    Draft202012Validator(_schema()).validate(ready)
    cached = tmp_path / ready["cache_path"]
    assert cached.read_bytes() == data
    assert ready["mime_type"] == "image/png"
    assert (ready["width"], ready["height"]) == (320, 240)


def test_material_validation_fails_closed_for_license_mime_dimensions_and_credentials():
    data = _png()
    with pytest.raises(ValueError, match="license"):
        validate_material_bytes(data, **_metadata(commercial_use_allowed=False))
    with pytest.raises(ValueError, match="signature"):
        validate_material_bytes(data, **_metadata(declared_mime="image/jpeg"))
    with pytest.raises(ValueError, match="public HTTPS"):
        validate_material_bytes(
            data,
            **_metadata(source_url="https://user:secret@images.example.test/private.png"),
        )
    tiny = BytesIO()
    Image.new("RGB", (1, 1), "white").save(tiny, format="PNG")
    with pytest.raises(ValueError, match="dimensions"):
        validate_material_bytes(tiny.getvalue(), **_metadata())


def test_svg_must_be_real_safe_vector_without_external_resources(tmp_path):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><path d="M10 64L64 10L118 64L64 118Z"/></svg>'
    manifest = validate_material_bytes(
        svg,
        **_metadata(
            declared_mime="image/svg+xml",
            source_url="user://istanbul-route-icon",
            license_id="user-provided",
            license_url="user://license",
            author="Current user",
        ),
    )
    ready = cache_validated_material(svg, manifest, cache_root=tmp_path)
    assert ready["extension"] == "svg"
    assert ready["cache_path"].endswith(".svg")

    active = b'<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><script>alert(1)</script></svg>'
    with pytest.raises(ValueError, match="active content"):
        validate_material_bytes(
            active,
            **_metadata(
                declared_mime="image/svg+xml",
                source_url="user://active-svg",
                license_id="user-provided",
                license_url="user://license",
                author="Current user",
            ),
        )


def test_cache_rejects_tampered_bytes_and_corrupted_existing_entry(tmp_path):
    data = _png()
    manifest = validate_material_bytes(data, **_metadata())
    with pytest.raises(ValueError, match="do not match"):
        cache_validated_material(data + b"tamper", manifest, cache_root=tmp_path)
    ready = cache_validated_material(data, manifest, cache_root=tmp_path)
    (tmp_path / ready["cache_path"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="corruption"):
        cache_validated_material(data, manifest, cache_root=tmp_path)
