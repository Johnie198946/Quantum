import copy
import hashlib
import json
from pathlib import Path

import pytest

from backend.services.presentation_source_trace import (
    bind_claims_to_slides,
    build_source_claims,
    build_trace_manifest,
    validate_trace_matrix,
)


FIXTURE = Path("tests/fixtures/presentation/istanbul-source.md")
EXPECTED = Path("tests/fixtures/presentation/istanbul-trace.expected.yaml")


def _claims(state: str = "approved"):
    return build_source_claims(
        FIXTURE.read_text(encoding="utf-8"),
        source_id="fixture.istanbul.v1",
        source_client_session_id="session-istanbul",
        approval_state=state,
    )


def test_istanbul_source_claims_are_exact_deterministic_and_match_golden():
    first = _claims()
    second = _claims()
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert first == second == expected["claims"]
    source = FIXTURE.read_text(encoding="utf-8")
    canonical_source = source.rstrip("\r\n")
    assert hashlib.sha256(canonical_source.encode()).hexdigest() == expected["source_sha256"]
    assert all(source[item["span"]["start"]:item["span"]["end"]] == item["claim"] for item in first)


def test_trace_matrix_requires_approved_known_claims_and_explicit_slides():
    claims = _claims()
    bindings = [
        {"claim_id": claim["claim_id"], "slide_id": f"slide-{index // 3 + 1}", "transform": "summarized"}
        for index, claim in enumerate(claims)
    ]
    records = bind_claims_to_slides(claims, bindings)
    validated = validate_trace_matrix(
        records,
        source_texts={"fixture.istanbul.v1": FIXTURE.read_text(encoding="utf-8")},
        source_client_session_id="session-istanbul",
    )
    manifest = build_trace_manifest(validated)
    assert manifest["record_count"] == len(claims)
    assert manifest["source_ids"] == ["fixture.istanbul.v1"]
    assert len(manifest["slide_ids"]) >= 5

    with pytest.raises(ValueError, match="unknown source claim"):
        bind_claims_to_slides(claims, [{"claim_id": "missing", "slide_id": "slide-1"}])
    with pytest.raises(ValueError, match="not approved"):
        bind_claims_to_slides(_claims("pending"), bindings)


def test_one_claim_can_bind_to_multiple_slides_without_aliasing_trace_records():
    claims = _claims()
    claim_id = claims[0]["claim_id"]
    records = bind_claims_to_slides(
        claims,
        [
            {"claim_id": claim_id, "slide_id": "slide-1", "transform": "summarized"},
            {"claim_id": claim_id, "slide_id": "slide-2", "transform": "summarized"},
        ],
    )

    assert records[0] is not records[1]
    assert [record["slide_id"] for record in records] == ["slide-1", "slide-2"]
    validated = validate_trace_matrix(
        records,
        source_texts={"fixture.istanbul.v1": FIXTURE.read_text(encoding="utf-8")},
        source_client_session_id="session-istanbul",
    )
    assert len(validated) == 2


def test_trace_validation_fails_closed_for_tampering_and_cross_session_material():
    claim = _claims()[0]
    record = bind_claims_to_slides(
        [claim], [{"claim_id": claim["claim_id"], "slide_id": "slide-1"}]
    )[0]
    sources = {"fixture.istanbul.v1": FIXTURE.read_text(encoding="utf-8")}

    tampered = copy.deepcopy(record)
    tampered["claim"] += " unsupported"
    with pytest.raises(ValueError, match="tampered"):
        validate_trace_matrix(
            [tampered], source_texts=sources,
            source_client_session_id="session-istanbul"
        )

    with pytest.raises(ValueError, match="another client session"):
        validate_trace_matrix(
            [record], source_texts=sources,
            source_client_session_id="session-other"
        )


def test_unmapped_or_rejected_claim_cannot_enter_final_presentation():
    claim = _claims()[0]
    with pytest.raises(ValueError, match="approved and mapped"):
        validate_trace_matrix(
            [claim],
            source_texts={"fixture.istanbul.v1": FIXTURE.read_text(encoding="utf-8")},
            source_client_session_id="session-istanbul",
        )
