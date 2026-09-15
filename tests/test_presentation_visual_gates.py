import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend.services.presentation_visual_gates import inspect_pptx
from scripts.build_istanbul_presentation import build_package


def test_first_class_slide_schema_declares_seven_visual_layout_families():
    schema = json.loads(
        Path("backend/contracts/presentation/slide.schema.json").read_text()
    )
    Draft202012Validator.check_schema(schema)
    layouts = {branch["properties"]["layout"]["const"] for branch in schema["oneOf"]}
    assert layouts == {
        "hero_photo",
        "photo_collage",
        "geo_route_map",
        "timeline",
        "icon_facts",
        "quote_photo",
        "data_story",
    }


def test_real_istanbul_acceptance_package_passes_structural_and_rendered_gates(
    tmp_path,
):
    if not (shutil.which("soffice") or shutil.which("libreoffice")):
        pytest.skip("LibreOffice unavailable")
    pytest.importorskip("pypdfium2")
    manifest = build_package(tmp_path)
    assert manifest["visual_gate_passed"] is True
    assert manifest["human_visual_approval"] == "pending"
    for name in ("istanbul-batch1.pptx", "istanbul-batch1.pdf", "montage.png"):
        path = tmp_path / name
        assert path.is_file() and path.stat().st_size > 1000
        assert manifest["artifacts"][name]["byte_size"] == path.stat().st_size
    report = inspect_pptx(tmp_path / "istanbul-batch1.pptx")
    assert report["errors"] == []
    assert report["distinct_picture_count"] >= 5
    assert report["editable_vector_icon_count"] >= 6
    assert report["editable_map_landmark_count"] >= 4
    assert len(report["layout_families"]) >= 5
    materials = json.loads((tmp_path / "material-manifest.json").read_text())
    assert len(materials["assets"]) == 13
    map_assets = [
        item for item in materials["assets"] if item["role"] == "real-map-base"
    ]
    assert len(map_assets) == 1
    assert map_assets[0]["license_id"] == "ODbL-1.0"
    assert map_assets[0]["source_url"].startswith(
        "https://www.openstreetmap.org/"
    )
    photo_assets = [item for item in materials["assets"] if item["role"] == "photo"]
    assert len(photo_assets) == 5
    assert {item["license_id"] for item in photo_assets} == {
        "CC-BY-SA-3.0",
        "CC-BY-SA-4.0",
        "Public-Domain",
    }
    assert all(
        item["source_url"].startswith("https://commons.wikimedia.org/")
        for item in photo_assets
    )
    trace = json.loads((tmp_path / "source-trace.json").read_text())
    assert trace["record_count"] == 15
    assert all(record["approval_state"] == "approved" for record in trace["records"])


def test_visual_gate_rejects_deck_without_required_visual_system(tmp_path):
    from backend.services.presentation_renderer import build_pptx

    path = tmp_path / "plain.pptx"
    path.write_bytes(
        build_pptx(json.dumps({"slides": [{"layout": "title", "title": "Plain"}]}))
    )
    report = inspect_pptx(path)
    assert report["errors"]
    assert any("five layout" in error for error in report["errors"])
