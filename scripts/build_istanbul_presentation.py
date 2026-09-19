#!/usr/bin/env python3
"""Build the deterministic Batch 1 Istanbul visual acceptance package."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import random
from io import BytesIO
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFilter

from backend.services.presentation_map import (
    generate_route_svg,
    resolve_istanbul_landmarks,
)
from backend.services.presentation_materials import validate_material_bytes
from backend.services.presentation_renderer import build_pptx, render_pptx_pdf
from backend.services.presentation_source_trace import (
    bind_claims_to_slides,
    build_source_claims,
    build_trace_manifest,
)
from backend.services.presentation_visual_gates import run_visual_gates

ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = "2026-09-15T12:00:00+08:00"


def _scene(seed: int, *, size: tuple[int, int], scene: str) -> bytes:
    randomizer = random.Random(seed)
    width, height = size
    image = Image.new("RGB", size)
    pixels = image.load()
    sky = [
        (40, 108, 145),
        (230, 163, 103),
        (70, 135, 150),
        (196, 119, 83),
        (55, 91, 121),
    ][seed % 5]
    for y in range(height):
        blend = y / height
        for x in range(width):
            grain = randomizer.randint(-7, 7)
            pixels[x, y] = tuple(
                max(
                    0,
                    min(
                        255,
                        int(channel * (1 - 0.34 * blend) + 235 * 0.34 * blend + grain),
                    ),
                )
                for channel in sky
            )
    draw = ImageDraw.Draw(image, "RGBA")
    horizon = int(height * 0.58)
    draw.rectangle((0, horizon, width, height), fill=(31, 103, 128, 255))
    for stripe in range(18):
        yy = horizon + stripe * max(2, (height - horizon) // 18)
        draw.line(
            (0, yy, width, yy + randomizer.randint(-3, 3)),
            fill=(210, 230, 220, 65),
            width=2,
        )
    # Generated skyline inspired by Istanbul without copying a photograph.
    for index in range(18):
        x = index * width / 17
        building_h = randomizer.randint(int(height * 0.08), int(height * 0.2))
        draw.rectangle(
            (x - width * 0.035, horizon - building_h, x + width * 0.035, horizon),
            fill=(31, 42, 47, 235),
        )
        if index % 4 == 0:
            draw.ellipse(
                (
                    x - width * 0.045,
                    horizon - building_h - width * 0.045,
                    x + width * 0.045,
                    horizon - building_h + width * 0.045,
                ),
                fill=(31, 42, 47, 235),
            )
            draw.rectangle(
                (
                    x - 3,
                    horizon - building_h - height * 0.17,
                    x + 3,
                    horizon - building_h,
                ),
                fill=(31, 42, 47, 235),
            )
    if scene in {"ferry", "cover"}:
        boat_y = int(height * 0.72)
        draw.polygon(
            [
                (width * 0.58, boat_y),
                (width * 0.83, boat_y),
                (width * 0.77, boat_y + height * 0.07),
                (width * 0.62, boat_y + height * 0.07),
            ],
            fill=(241, 235, 218, 255),
        )
        draw.rectangle(
            (width * 0.64, boat_y - height * 0.07, width * 0.76, boat_y),
            fill=(214, 74, 50, 255),
        )
    if scene == "market":
        for index, color in enumerate(
            [(210, 69, 49), (235, 176, 55), (64, 132, 104), (99, 70, 135)]
        ):
            cx = width * (0.22 + index * 0.16)
            draw.ellipse(
                (cx - 70, height * 0.73, cx + 70, height * 0.93), fill=(*color, 245)
            )
    if scene == "palace":
        draw.rectangle(
            (width * 0.16, height * 0.35, width * 0.84, horizon),
            fill=(210, 188, 145, 245),
        )
        for x in (0.21, 0.42, 0.63, 0.79):
            draw.ellipse(
                (width * x - 30, height * 0.39, width * x + 30, height * 0.51),
                fill=(31, 42, 47, 220),
            )
    image = image.filter(ImageFilter.GaussianBlur(radius=0.35))
    output = BytesIO()
    image.save(output, format="JPEG", quality=91, optimize=True)
    return output.getvalue()


def _svg_icon(kind: str) -> bytes:
    geometries = {
        "landmark": '<rect x="16" y="28" width="32" height="24" fill="#D85A3A"/><line x1="12" y1="28" x2="32" y2="10" stroke="#172A3A" stroke-width="4"/><line x1="32" y1="10" x2="52" y2="28" stroke="#172A3A" stroke-width="4"/>',
        "ferry": '<rect x="12" y="28" width="40" height="16" fill="#D85A3A"/><line x1="8" y1="46" x2="56" y2="46" stroke="#172A3A" stroke-width="4"/><rect x="24" y="18" width="18" height="10" fill="#172A3A"/>',
        "food": '<circle cx="32" cy="32" r="18" fill="none" stroke="#D85A3A" stroke-width="4"/><line x1="8" y1="12" x2="8" y2="54" stroke="#172A3A" stroke-width="4"/><line x1="56" y1="12" x2="56" y2="54" stroke="#172A3A" stroke-width="4"/>',
        "camera": '<rect x="10" y="20" width="44" height="32" fill="none" stroke="#172A3A" stroke-width="4"/><circle cx="32" cy="36" r="10" fill="#D85A3A"/><rect x="20" y="14" width="14" height="8" fill="#172A3A"/>',
        "walk": '<circle cx="32" cy="12" r="6" fill="#D85A3A"/><line x1="32" y1="18" x2="30" y2="38" stroke="#172A3A" stroke-width="4"/><line x1="30" y1="27" x2="18" y2="36" stroke="#172A3A" stroke-width="4"/><line x1="30" y1="38" x2="18" y2="54" stroke="#172A3A" stroke-width="4"/><line x1="30" y1="38" x2="46" y2="52" stroke="#172A3A" stroke-width="4"/>',
        "bridge": '<line x1="8" y1="48" x2="56" y2="48" stroke="#172A3A" stroke-width="4"/><line x1="14" y1="18" x2="14" y2="50" stroke="#D85A3A" stroke-width="4"/><line x1="50" y1="18" x2="50" y2="50" stroke="#D85A3A" stroke-width="4"/><line x1="14" y1="20" x2="50" y2="20" stroke="#172A3A" stroke-width="4"/>',
    }
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">{geometries[kind]}</svg>'.encode()


def _material(
    data: bytes,
    *,
    name: str,
    mime: str,
    source_url: str | None = None,
    author: str = "AI Lab deterministic asset generator",
    license_id: str = "generated",
    license_url: str = "generated://license/owned-output",
) -> dict:
    manifest = validate_material_bytes(
        data,
        declared_mime=mime,
        source_url=source_url or f"generated://istanbul-batch1/{name}",
        author=author,
        license_id=license_id,
        license_url=license_url,
        fetched_at=FIXED_TIME,
        commercial_use_allowed=True,
    )
    return {
        "data_uri": f"data:{mime};base64," + base64.b64encode(data).decode(),
        "manifest": manifest,
    }


def _theme() -> dict:
    raw = yaml.safe_load(
        (
            ROOT / "backend/contracts/presentation/themes/travel-editorial.yaml"
        ).read_text()
    )
    return {"colors": raw["colors"], "fonts": raw["fonts"]}


def build_package(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    assets = output / "assets"
    assets.mkdir(exist_ok=True)
    photo_catalog = {
        "cover": (
            "blue-mosque.jpg",
            "https://commons.wikimedia.org/wiki/File:Blue_Mosque_Courtyard_Dusk_Wikimedia_Commons.jpg",
            "Benh LIEU SONG",
            "CC-BY-SA-3.0",
            "https://creativecommons.org/licenses/by-sa/3.0/",
        ),
        "bosphorus": (
            "karakoy-ferry.jpg",
            "https://commons.wikimedia.org/wiki/File:Karak%C3%B6y_Mars_2013_02.jpg",
            "Arild Vågen",
            "CC-BY-SA-3.0",
            "https://creativecommons.org/licenses/by-sa/3.0/",
        ),
        "old-city": (
            "hagia-sophia.jpg",
            "https://commons.wikimedia.org/wiki/File:Hagia_Sophia_Mars_2013.jpg",
            "Arild Vågen",
            "CC-BY-SA-3.0",
            "https://creativecommons.org/licenses/by-sa/3.0/",
        ),
        "cistern": (
            "basilica-cistern.jpg",
            "https://commons.wikimedia.org/wiki/File:Cisterna_Bas%C3%ADlica,_Estambul,_Turqu%C3%ADa,_2024-09-28,_DD_58-60_HDR.jpg",
            "Diego Delso",
            "CC-BY-SA-4.0",
            "https://creativecommons.org/licenses/by-sa/4.0/",
        ),
        "palace": (
            "topkapi.jpg",
            "https://commons.wikimedia.org/wiki/File:Topkapi_Palace_Bosphorus.JPG",
            "Gryffindor",
            "Public-Domain",
            "https://commons.wikimedia.org/wiki/Template:PD-self",
        ),
    }
    photos = {}
    fixtures = ROOT / "tests/fixtures/presentation/assets"
    for name, (
        filename,
        source_url,
        author,
        license_id,
        license_url,
    ) in photo_catalog.items():
        data = (fixtures / filename).read_bytes()
        path = assets / filename
        path.write_bytes(data)
        photos[name] = _material(
            data,
            name=path.name,
            mime="image/jpeg",
            source_url=source_url,
            author=author,
            license_id=license_id,
            license_url=license_url,
        )
    icons = {}
    for name in ("landmark", "ferry", "food", "camera", "walk", "bridge"):
        data = _svg_icon(name)
        path = assets / f"icon-{name}.svg"
        path.write_bytes(data)
        icons[name] = _material(data, name=path.name, mime="image/svg+xml")
    route_points = resolve_istanbul_landmarks(
        ["Hagia Sophia", "Topkapi Palace", "Galata Tower", "Uskudar", "Kadikoy"]
    )
    route_svg = generate_route_svg(route_points)
    route_path = assets / "istanbul-route-map.svg"
    route_path.write_bytes(route_svg)
    route_manifest = _material(route_svg, name=route_path.name, mime="image/svg+xml")[
        "manifest"
    ]
    map_data = (fixtures / "istanbul-osm.png").read_bytes()
    map_path = assets / "istanbul-osm.png"
    map_path.write_bytes(map_data)
    map_material = _material(
        map_data,
        name=map_path.name,
        mime="image/png",
        source_url="https://www.openstreetmap.org/#map=13/41.025/28.990",
        author="OpenStreetMap contributors",
        license_id="ODbL-1.0",
        license_url="https://www.openstreetmap.org/copyright",
    )

    slides = [
        {
            "layout": "hero_photo",
            "title": "Istanbul · Between Continents",
            "subtitle": "A visual journey across Europe, Asia and the Bosphorus",
            "photo": photos["cover"],
            "caption": "Blue Mosque · Benh LIEU SONG · CC BY-SA 3.0",
        },
        {
            "layout": "data_story",
            "title": "Turkey’s largest city and economic center",
            "subtitle": "Source-bound city profile",
            "metric": "15+",
            "unit": " million",
            "body": "Istanbul spans both shores of the Bosphorus and remains a vital link between Western and Eastern civilizations.",
            "facts": [
                "Strategic commercial hub for millennia",
                "Modernity blended with centuries-old traditions",
            ],
        },
        {
            "layout": "timeline",
            "title": "Three names, two empires, one city",
            "subtitle": "Historical identity from the supplied material",
            "events": [
                {
                    "label": "Origins",
                    "title": "Byzantium",
                    "detail": "Historic city name",
                },
                {
                    "label": "Imperial era",
                    "title": "Constantinople",
                    "detail": "Capital of the Byzantine Empire",
                },
                {
                    "label": "Ottoman era",
                    "title": "Imperial capital",
                    "detail": "Capital of the Ottoman Empire",
                },
                {
                    "label": "Today",
                    "title": "Istanbul",
                    "detail": "Turkey’s largest city",
                },
            ],
        },
        {
            "layout": "photo_collage",
            "title": "Four scenes, one multicultural rhythm",
            "subtitle": "Commercial-use licensed photographs from Wikimedia Commons",
            "photos": [
                {
                    "material": photos["bosphorus"],
                    "caption": "Karaköy ferry · Arild Vågen · CC BY-SA 3.0",
                },
                {
                    "material": photos["old-city"],
                    "caption": "Hagia Sophia · Arild Vågen · CC BY-SA 3.0",
                },
                {
                    "material": photos["cistern"],
                    "caption": "Basilica Cistern · Diego Delso · CC BY-SA 4.0",
                },
                {
                    "material": photos["palace"],
                    "caption": "Topkapi Palace · Gryffindor · Public domain",
                },
            ],
        },
        {
            "layout": "geo_route_map",
            "title": "An editable route from Europe to Asia",
            "subtitle": "WGS84 route over a real OpenStreetMap base",
            "map": map_material,
            "attribution": "© OpenStreetMap contributors · ODbL 1.0",
            "points": [
                {
                    "name": p.name,
                    "longitude": p.longitude,
                    "latitude": p.latitude,
                    "side": p.side,
                    "detail": p.detail,
                }
                for p in route_points
            ],
        },
        {
            "layout": "icon_facts",
            "title": "A city read through six visual signals",
            "subtitle": "Each icon is parsed from safe SVG into native PowerPoint vectors",
            "items": [
                {"icon": icons[name], "title": title, "detail": detail}
                for name, title, detail in [
                    (
                        "landmark",
                        "Landmarks",
                        "Hagia Sophia, Blue Mosque, Topkapi Palace",
                    ),
                    ("ferry", "Bosphorus", "The strait links the city’s two shores"),
                    ("food", "Tradition", "Centuries-old culture remains visible"),
                    (
                        "camera",
                        "Multicultural heritage",
                        "Landmarks reflect a layered past",
                    ),
                    ("walk", "Living city", "Modern life meets historic fabric"),
                    ("bridge", "East × West", "A vital civilizational connection"),
                ]
            ],
        },
        {
            "layout": "quote_photo",
            "title": "Closing perspective",
            "quote": "A vital link between Western and Eastern civilizations, blending modernity with centuries-old traditions.",
            "attribution": "Approved Istanbul source material",
            "photo": photos["bosphorus"],
        },
    ]
    spec = {
        "title": "Istanbul · Between Continents",
        "subtitle": "Batch 1 visual acceptance artifact",
        "theme": _theme(),
        "slides": slides,
    }
    spec_path = output / "istanbul-deck-spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    pptx_path = output / "istanbul-batch1.pptx"
    pptx_path.write_bytes(build_pptx(json.dumps(spec, ensure_ascii=False)))
    pdf_path = output / "istanbul-batch1.pdf"
    pdf_path.write_bytes(render_pptx_pdf(pptx_path))

    source_text = (ROOT / "tests/fixtures/presentation/istanbul-source.md").read_text()
    claims = build_source_claims(
        source_text,
        source_id="fixture.istanbul.v1",
        source_client_session_id="session-istanbul",
        approval_state="approved",
    )
    bindings = [
        {
            "claim_id": claim["claim_id"],
            "slide_id": f"slide-{(index % len(slides)) + 1:03d}",
            "transform": "visualized",
        }
        for index, claim in enumerate(claims)
    ]
    trace = build_trace_manifest(bind_claims_to_slides(claims, bindings))
    trace_path = output / "source-trace.json"
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n")

    asset_entries = []
    for role, collection in (("photo", photos), ("icon", icons)):
        for name, material in collection.items():
            asset_entries.append(
                {"asset_id": name, "role": role, **material["manifest"]}
            )
    asset_entries.append(
        {
            "asset_id": "istanbul-route-map",
            "role": "editable-map-source",
            **route_manifest,
        }
    )
    asset_entries.append(
        {"asset_id": "istanbul-osm", "role": "real-map-base", **map_material["manifest"]}
    )
    material_manifest = {
        "schema_version": 1,
        "generator": "scripts/build_istanbul_presentation.py",
        "assets": asset_entries,
    }
    manifest_path = output / "material-manifest.json"
    manifest_path.write_text(
        json.dumps(material_manifest, ensure_ascii=False, indent=2) + "\n"
    )

    report_path = output / "visual-gate-report.json"
    report = run_visual_gates(
        pptx_path,
        pdf_path,
        report_path=report_path,
        render_dir=output / "rendered",
        montage_path=output / "montage.png",
    )
    artifact_manifest = {
        "schema_version": 1,
        "title": spec["title"],
        "source_trace": trace_path.name,
        "material_manifest": manifest_path.name,
        "visual_gate_report": report_path.name,
        "artifacts": {
            path.name: {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "byte_size": path.stat().st_size,
            }
            for path in (pptx_path, pdf_path, output / "montage.png")
        },
        "visual_gate_passed": report["passed"],
        "human_visual_approval": "pending",
    }
    artifact_path = output / "artifact-manifest.json"
    artifact_path.write_text(
        json.dumps(artifact_manifest, ensure_ascii=False, indent=2) + "\n"
    )
    return artifact_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts/acceptance/istanbul-batch1"
    )
    args = parser.parse_args()
    result = build_package(args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
