from __future__ import annotations

import importlib.util
import re
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
        "partial": 70,
        "absent": 0,
        "unverified": 0,
    }


def _renderer_paths():
    ios_source = (ROOT / "ios/AIPlatformApp/Networking/APIClient.swift").read_text()
    qws_source = (ROOT / "frontend/src/features/quantum-workspace/qcpEventRegistry.js").read_text()
    ios = dict(re.findall(
        r'"([a-z_]+)": \.init\(path: \.([A-Za-z]+), minimumVersion:',
        ios_source[ios_source.index("rendererRoutes"):ios_source.index("private static let routes")],
    ))
    qws = dict(re.findall(
        r'\["([a-z_]+)", \{ path: "([a-z_]+)", minimumVersion:',
        qws_source[qws_source.index("rendererRoutes"):qws_source.index("const routes")],
    ))
    return ios, qws


def _assert_semantic_renderer_coverage(rows, ios, qws):
    ios_expected = {
        "answer": "answer", "knowledge_action": "knowledgeAction",
        "workflow": "workflow", "presentation_review": "presentationReview",
        "bookshelf": "bookshelf", "hermes_session_list": "hermesSessionList",
        "hermes_session_detail": "hermesSessionDetail", "client_action": "clientAction",
        "artifact_card": "artifactCard", "data_analysis_card": "dataAnalysisCard",
        "image_card": "imageCard", "task_execution_card": "taskExecutionCard",
    }
    for row in rows:
        renderer = row["renderer"].partition("@")[0]
        assert ios.get(renderer) == ios_expected[renderer], row["capability"]
        assert qws.get(renderer) == renderer, row["capability"]


def test_every_scoped_capability_resolves_contract_renderer_on_ios_and_qws():
    _assert_semantic_renderer_coverage(module.generate()["capabilities"], *_renderer_paths())


def test_semantic_renderer_coverage_rejects_wrong_shared_event_mapping():
    rows = [row for row in module.generate()["capabilities"] if row["event"] == "artifact.generated"]
    ios, qws = _renderer_paths()
    qws["image_card"] = "artifact_card"
    try:
        _assert_semantic_renderer_coverage(rows, ios, qws)
    except AssertionError:
        pass
    else:
        raise AssertionError("wrong renderer mapping must fail semantic coverage")


def test_matrix_consumer_references_resolve_to_existing_code():
    for row in module.generate()["capabilities"]:
        for key in ("ios_consumer", "qws_consumer"):
            reference = row[key]
            path, _, symbol = reference.partition(":")
            source = ROOT / path
            assert source.is_file(), f"{row['capability']} {key}: missing {path}"
            if symbol:
                assert symbol in source.read_text(), (
                    f"{row['capability']} {key}: missing {symbol} in {path}"
                )
