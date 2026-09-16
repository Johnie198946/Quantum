"""Deterministic, editable geographic route maps for presentations."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Iterable

ISTANBUL_BOUNDS = (28.85, 40.97, 29.13, 41.08)  # west, south, east, north


@dataclass(frozen=True)
class GeoPoint:
    name: str
    longitude: float
    latitude: float
    side: str
    detail: str = ""


ISTANBUL_LANDMARKS: dict[str, GeoPoint] = {
    "Hagia Sophia": GeoPoint("Hagia Sophia", 28.9800, 41.0086, "europe"),
    "Blue Mosque": GeoPoint("Blue Mosque", 28.9768, 41.0054, "europe"),
    "Blue Mosque / Hagia Sophia": GeoPoint(
        "蓝色清真寺 / Hagia Sophia", 28.9784, 41.0070, "europe"
    ),
    "Topkapi Palace": GeoPoint("Topkapi Palace", 28.9834, 41.0115, "europe"),
    "Galata Tower": GeoPoint("Galata Tower", 28.9741, 41.0256, "europe"),
    "Eminonu": GeoPoint("Eminönü", 28.9707, 41.0170, "europe"),
    "Uskudar": GeoPoint("Üsküdar", 29.0153, 41.0267, "asia"),
    "Kadikoy": GeoPoint("Kadıköy", 29.0250, 40.9909, "asia"),
    "Suleymaniye Mosque": GeoPoint("苏莱曼尼清真寺", 28.9638, 41.0162, "europe"),
    "Sarayburnu Park": GeoPoint("Sarayburnu Parkı", 28.9872, 41.0152, "europe"),
    "Galata Bridge": GeoPoint("加拉塔大桥", 28.9730, 41.0202, "europe"),
    "Grand Bazaar": GeoPoint("大巴扎", 28.9680, 41.0107, "europe"),
    "Balat Colorful Stairs": GeoPoint("巴拉特彩色街区", 28.9490, 41.0295, "europe"),
    "Seven Hills": GeoPoint("Seven Hills", 28.9797, 41.0058, "europe"),
    "Eminonu Ferry": GeoPoint("Eminönü 轮渡", 28.9708, 41.0172, "europe"),
    "Cemberlitas Hammam": GeoPoint("Çemberlitaş Hammam", 28.9715, 41.0085, "europe"),
    "Istiklal Street": GeoPoint("独立大街", 28.9762, 41.0340, "europe"),
    "Ortakoy Mosque": GeoPoint("奥塔科伊清真寺", 29.0270, 41.0472, "europe"),
    "Kuzguncuk": GeoPoint("Kuzguncuk", 29.0296, 41.0374, "asia"),
    "Nusr-Et Grand Bazaar": GeoPoint("Nusr-Et 大巴扎店", 28.9694, 41.0105, "europe"),
}


def resolve_istanbul_landmarks(names: Iterable[str]) -> list[GeoPoint]:
    """Resolve only curated landmarks; unknown names fail closed."""
    points: list[GeoPoint] = []
    for name in names:
        key = str(name).strip()
        point = ISTANBUL_LANDMARKS.get(key)
        if point is None:
            raise ValueError(f"unknown Istanbul landmark: {key}")
        points.append(point)
    if len(points) < 2:
        raise ValueError("a geographic route needs at least two landmarks")
    return points


def validate_geo_points(raw: Any) -> list[GeoPoint]:
    if not isinstance(raw, list) or not 2 <= len(raw) <= 10:
        raise ValueError("geo route map needs 2-10 points")
    points: list[GeoPoint] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) - {
            "name",
            "longitude",
            "latitude",
            "side",
            "detail",
        }:
            raise ValueError("geo route map point is invalid")
        try:
            longitude, latitude = float(item["longitude"]), float(item["latitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("geo route map point needs numeric coordinates") from exc
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            raise ValueError("geo route map coordinates are outside Earth bounds")
        side = str(item.get("side") or "")
        if side not in {"europe", "asia"}:
            raise ValueError("geo route map point needs a Europe or Asia side")
        name, detail = (
            str(item.get("name") or "").strip(),
            str(item.get("detail") or "").strip(),
        )
        if not name or len(name) > 60 or len(detail) > 100:
            raise ValueError("geo route map point text is invalid")
        points.append(GeoPoint(name, longitude, latitude, side, detail))
    return points


def project_point(
    point: GeoPoint, *, width: float, height: float, bounds=ISTANBUL_BOUNDS
) -> tuple[float, float]:
    west, south, east, north = bounds
    if not (west < east and south < north):
        raise ValueError("map bounds must be ordered as west, south, east, north")
    if not (west <= point.longitude <= east and south <= point.latitude <= north):
        raise ValueError(f"point outside Istanbul map bounds: {point.name}")
    x = (point.longitude - west) / (east - west) * width
    y = (north - point.latitude) / (north - south) * height
    return x, y


def generate_route_svg(
    points: list[GeoPoint], *, width: int = 1200, height: int = 640
) -> bytes:
    """Generate a safe SVG using projected WGS84 coordinates and editable primitives."""
    if len(points) < 2:
        raise ValueError("a geographic route needs at least two points")
    projected = [project_point(point, width=width, height=height) for point in points]
    route = " ".join(f"{x:.1f},{y:.1f}" for x, y in projected)
    # Simplified shoreline polygons are a geographic backdrop; route nodes use WGS84 projection.
    europe = "0,0 650,0 625,120 655,220 610,330 635,470 570,640 0,640"
    asia = "735,0 1200,0 1200,640 690,640 720,500 680,390 725,260 690,120"
    nodes = []
    for index, (point, (x, y)) in enumerate(zip(points, projected), 1):
        nodes.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="#E45B3B"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#FFFFFF"/>'
            f'<text x="{x + 16:.1f}" y="{y - 12:.1f}" font-size="18" fill="#172A3A">{index}. {html.escape(point.name)}</text>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        '<rect width="1200" height="640" fill="#A9D8E8"/>'
        f'<polygon points="{europe}" fill="#E8DFC8"/><polygon points="{asia}" fill="#D7D7BD"/>'
        '<text x="70" y="85" font-size="34" fill="#59636B">EUROPE</text>'
        '<text x="950" y="85" font-size="34" fill="#59636B">ASIA</text>'
        '<text x="650" y="90" font-size="20" fill="#255F76" transform="rotate(90 650 90)">BOSPHORUS STRAIT</text>'
        f'<polyline points="{route}" fill="none" stroke="#E45B3B" stroke-width="8"/>'
        + "".join(nodes)
        + "</svg>"
    )
    return svg.encode("utf-8")
