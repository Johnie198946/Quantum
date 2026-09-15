from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "ops/acceptance/quantumn-document-ppt-baseline.yaml"
MATRIX = ROOT / "ops/acceptance/quantumn-document-ppt-gap-matrix.yaml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_every_baseline_failure_has_an_explicit_acceptance_probe() -> None:
    baseline = _load(BASELINE)
    matrix = _load(MATRIX)

    expected_probe_keys = {
        "source_fact_loss_or_unsupported_expansion",
        "cross_session_source_contamination",
        "tourism_visual_assets",
        "field_level_review_with_cas",
        "late_response_session_overwrite",
        "generic_agent_descriptions",
        "document_workflows_without_real_longform_or_citations",
    }
    assert len(baseline["known_failures"]) == len(expected_probe_keys)
    assert set(matrix["known_gap_probes"]) == expected_probe_keys


def test_open_acceptance_gates_are_never_reported_as_complete() -> None:
    matrix = _load(MATRIX)
    allowed = {"implemented", "partial", "absent", "unverified"}

    for probe in matrix["known_gap_probes"].values():
        assert probe["status"] in allowed
        if probe["status"] in {"partial", "unverified"}:
            assert probe.get("missing_exit_evidence"), probe

    release_gates = matrix["release_and_product_gates"]
    assert release_gates["simulator_ui_tests"]["status"] != "implemented"
    assert release_gates["physical_device"]["status"] != "implemented"
    assert release_gates["testflight"]["status"] != "implemented"
    assert release_gates["server_deployment"]["status"] != "implemented"
    assert release_gates["production_matrix"]["status"] != "implemented"
    assert release_gates["final_pptx_pdf_user_confirmation"]["status"] != "implemented"
