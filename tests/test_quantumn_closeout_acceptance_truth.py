from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / "ops/acceptance/20260916-quantumn-document-ppt-acceptance-matrix.json"
COMPLETION = ROOT / "ops/acceptance/20260916-quantumn-document-ppt-completion-manifest.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_istanbul_subtask_cannot_close_full_remediation_plan() -> None:
    acceptance = _load(ACCEPTANCE)
    completion = _load(COMPLETION)

    assert acceptance["scope"] == "istanbul_user_input_subtask_only"
    assert acceptance["passed"] == 8
    assert acceptance["full_remediation_plan_status"] == "no_go_partial"
    assert acceptance["full_remediation_plan_passed"] is False
    assert "not the full remediation plan" in acceptance["summary_semantics"]

    assert completion["istanbul_subtask_status"].startswith("passed_")
    assert completion["full_remediation_plan_status"] == (
        "gates_a_through_f_passed_gate_g_not_authorized"
    )
    assert completion["full_remediation_plan_passed"] is False
    assert completion["local_acceptance_gates_a_through_f_passed"] is True
    assert completion["superseded_by"].endswith(
        "20260917-quantumn-document-ppt-final-acceptance.json"
    )
    assert completion["overall_status"] == "local_acceptance_passed_release_no_go"


def test_invalid_or_legacy_test_evidence_is_explicitly_excluded() -> None:
    completion = _load(COMPLETION)
    excluded = " ".join(completion["excluded_from_full_plan_acceptance"])

    for marker in (
        "Build 38",
        "failed",
        "skipped",
        "interrupted",
        "timed-out",
        "SIGKILL",
        "exit-65",
        "Executed-0-tests",
        "incomplete xcresult",
        "8/8",
    ):
        assert marker in excluded
