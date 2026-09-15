"""Safe restricted SVG parsing for editable PowerPoint vector conversion."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

_ALLOWED_TAGS = {"svg", "g", "circle", "rect", "line", "polyline", "polygon", "path"}
_COLOR = re.compile(r"#[0-9A-Fa-f]{6}$")
_NUMBER = r"-?(?:\d+(?:\.\d+)?|\.\d+)"
_PATH_TOKEN = re.compile(rf"[MLHVZmlhvz]|{_NUMBER}")


@dataclass(frozen=True)
class VectorPrimitive:
    kind: str
    values: tuple[float, ...]
    fill: str | None
    stroke: str | None
    stroke_width: float


def _color(value: str | None, palette: dict[str, str]) -> str | None:
    if not value or value.lower() == "none":
        return None
    adapted = palette.get(value, palette.get(value.lower(), value))
    if not _COLOR.fullmatch(adapted):
        raise ValueError("SVG colors must be #RRGGBB or an approved palette token")
    return adapted.upper()


def _numbers(value: str) -> tuple[float, ...]:
    try:
        return tuple(float(item) for item in re.findall(_NUMBER, value))
    except ValueError as exc:
        raise ValueError("SVG geometry contains invalid numbers") from exc


def _path_points(value: str) -> tuple[float, ...]:
    """Accept only straight-line M/L/H/V/Z paths; curves/arcs fail closed."""
    tokens = _PATH_TOKEN.findall(value.replace(",", " "))
    residue = _PATH_TOKEN.sub(" ", value.replace(",", " "))
    if residue.strip() or not tokens:
        raise ValueError("SVG path contains unsupported commands")
    points: list[float] = []
    cursor = (0.0, 0.0)
    start = cursor
    command = ""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            command = token
            index += 1
            if command in "Zz":
                points.extend(start)
            continue
        if command in "MmLl":
            if index + 1 >= len(tokens) or tokens[index + 1].isalpha():
                raise ValueError("SVG path coordinate pair is incomplete")
            x, y = float(tokens[index]), float(tokens[index + 1])
            if command.islower():
                x, y = cursor[0] + x, cursor[1] + y
            cursor = (x, y)
            if command in "Mm" and not points:
                start = cursor
            points.extend(cursor)
            index += 2
        elif command in "Hh":
            x = float(token) + (cursor[0] if command == "h" else 0)
            cursor = (x, cursor[1])
            points.extend(cursor)
            index += 1
        elif command in "Vv":
            y = float(token) + (cursor[1] if command == "v" else 0)
            cursor = (cursor[0], y)
            points.extend(cursor)
            index += 1
        else:
            raise ValueError("SVG path contains unsupported commands")
    if len(points) < 4:
        raise ValueError("SVG path has insufficient geometry")
    return tuple(points)


def parse_editable_svg(
    data: bytes, *, palette: dict[str, str] | None = None
) -> tuple[tuple[float, float, float, float], list[VectorPrimitive]]:
    """Parse safe SVG into a bounded list of native-vector primitives."""
    if (
        len(data) > 1_000_000
        or b"<!DOCTYPE" in data.upper()
        or b"<!ENTITY" in data.upper()
    ):
        raise ValueError("SVG is too large or contains forbidden declarations")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError("SVG cannot be parsed") from exc
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise ValueError("SVG root is required")
    view = _numbers(root.get("viewBox") or "")
    if len(view) != 4 or view[2] <= 0 or view[3] <= 0:
        raise ValueError("editable SVG needs a positive viewBox")
    primitives: list[VectorPrimitive] = []
    palette = palette or {}
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag not in _ALLOWED_TAGS:
            raise ValueError(f"unsupported SVG element: {tag}")
        for key, value in element.attrib.items():
            key = key.rsplit("}", 1)[-1].lower()
            if key.startswith("on") or key in {
                "href",
                "style",
                "filter",
                "mask",
                "clip-path",
            }:
                raise ValueError("SVG active, external, or opaque styling is forbidden")
            if "url(" in str(value).lower() or "javascript:" in str(value).lower():
                raise ValueError("SVG external references are forbidden")
        if tag in {"svg", "g"}:
            continue
        fill = _color(element.get("fill"), palette)
        stroke = _color(element.get("stroke"), palette)
        try:
            stroke_width = float(element.get("stroke-width") or 1)
        except ValueError as exc:
            raise ValueError("SVG stroke width is invalid") from exc
        if not 0 <= stroke_width <= 32:
            raise ValueError("SVG stroke width is outside the safe range")
        if tag == "circle":
            values = tuple(float(element.get(key) or 0) for key in ("cx", "cy", "r"))
            if values[2] <= 0:
                raise ValueError("SVG circle radius must be positive")
        elif tag == "rect":
            values = tuple(
                float(element.get(key) or 0) for key in ("x", "y", "width", "height")
            )
            if values[2] <= 0 or values[3] <= 0:
                raise ValueError("SVG rectangle size must be positive")
        elif tag == "line":
            values = tuple(
                float(element.get(key) or 0) for key in ("x1", "y1", "x2", "y2")
            )
        elif tag in {"polyline", "polygon"}:
            values = _numbers(element.get("points") or "")
            if len(values) < 4 or len(values) % 2:
                raise ValueError("SVG point list is invalid")
        else:
            values = _path_points(element.get("d") or "")
        primitives.append(VectorPrimitive(tag, values, fill, stroke, stroke_width))
        if len(primitives) > 128:
            raise ValueError("SVG has too many editable primitives")
    if not primitives:
        raise ValueError("SVG has no editable vector primitives")
    return (view[0], view[1], view[2], view[3]), primitives
