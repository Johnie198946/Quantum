import pytest

from backend.services.presentation_map import (
    generate_route_svg,
    project_point,
    resolve_istanbul_landmarks,
    validate_geo_points,
)
from backend.services.presentation_materials import validate_material_bytes


def test_istanbul_route_uses_real_coordinates_on_both_continents():
    points = resolve_istanbul_landmarks(
        ["Hagia Sophia", "Topkapi Palace", "Galata Tower", "Uskudar", "Kadikoy"]
    )
    projected = [project_point(point, width=1200, height=640) for point in points]
    assert {point.side for point in points} == {"europe", "asia"}
    assert projected[0][0] < projected[-1][0]
    assert len(set(projected)) == 5
    svg = generate_route_svg(points)
    assert b"EUROPE" in svg and b"ASIA" in svg and b"BOSPHORUS STRAIT" in svg
    assert svg.count(b"<circle") == 10
    manifest = validate_material_bytes(
        svg,
        declared_mime="image/svg+xml",
        source_url="generated://test/route.svg",
        author="test generator",
        license_id="generated",
        license_url="generated://license/owned-output",
        fetched_at="2026-09-15T12:00:00+08:00",
        commercial_use_allowed=True,
    )
    assert manifest["mime_type"] == "image/svg+xml"


def test_geo_route_fails_closed_for_unknown_or_fictional_points():
    with pytest.raises(ValueError, match="unknown Istanbul landmark"):
        resolve_istanbul_landmarks(["Hagia Sophia", "Imaginary Palace"])
    europe_only = validate_geo_points(
        [
            {"name": "A", "longitude": 28.98, "latitude": 41.01, "side": "europe"},
            {"name": "B", "longitude": 28.99, "latitude": 41.02, "side": "europe"},
        ]
    )
    assert {point.side for point in europe_only} == {"europe"}
    point = resolve_istanbul_landmarks(["Hagia Sophia", "Kadikoy"])[0]
    with pytest.raises(ValueError, match="outside Istanbul"):
        project_point(type(point)("Outside", 30.0, 42.0, "asia"), width=100, height=100)
