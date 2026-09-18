from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ios_capability_matrix", ROOT / "scripts/generate_ios_capability_matrix.py"
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_ios_scope_is_pcm_manifest_driven_and_has_required_columns():
    result = module.generate()
    assert result["source"] == "backend/contracts/product-capabilities/manifest.yaml#ios_scope"
    assert result["total"] == 70
    assert len({row["capability"] for row in result["capabilities"]}) == result["total"]
    for row in result["capabilities"]:
        assert set(result["required_columns"]).issubset(row)
        assert row["status"] in {"implemented", "partial", "absent", "unverified"}


def test_ios_scope_covers_every_required_product_family():
    ids = {row["capability"] for row in module.generate()["capabilities"]}
    prefixes = {
        "bookshelf.", "agent.", "skill.", "memory.", "knowledge.note.",
        "workflow.", "project.", "task.", "document.", "report.", "paper.",
        "presentation.", "office.", "data.", "media.", "hermes.session.",
        "file.", "photo.", "voice.", "share.", "profile.", "notification.",
        "schedule.",
    }
    assert all(any(item.startswith(prefix) for item in ids) for prefix in prefixes)


def test_ios_matrix_truthfully_reports_release_blockers():
    result = module.generate()
    assert result["counts"] == {
        "implemented": 0,
        "partial": 53,
        "absent": 17,
        "unverified": 0,
    }
