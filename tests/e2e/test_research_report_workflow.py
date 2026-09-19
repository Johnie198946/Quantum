from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest


SOURCES = json.loads(
    Path("tests/fixtures/document_e2e/verified_sources.json").read_text(encoding="utf-8")
)["research_report"]


def _assert_sources_fail_closed(report: str) -> None:
    assert len(SOURCES) >= 3
    assert len({urlparse(source["url"]).hostname for source in SOURCES}) == len(SOURCES)
    assert len({source["publisher"] for source in SOURCES}) == len(SOURCES)
    cited = set(re.findall(r"\[(S\d+)\]", report))
    expected = {source["id"] for source in SOURCES}
    assert cited == expected
    for source in SOURCES:
        assert source["access_status"] == 200
        assert urlparse(source["url"]).scheme == "https"
        assert hashlib.sha256(source["excerpt"].encode()).hexdigest() == source["excerpt_sha256"]
        assert f"[{source['id']}] {source['publisher']}. {source['title']}. {source['url']}" in report


@pytest.mark.asyncio
async def test_research_report_three_accessible_sources_traceable_citations_and_revision(
    document_e2e_harness,
):
    await document_e2e_harness.create(
        "report.research.create_from_text",
        {
            "title": "Climate evidence decision brief",
            "text_material": "Use only the three verified source records supplied by the evidence fixture.",
            "research_question": "What does authoritative evidence establish about recent global warming?",
            "language": "en-US",
            "citation_style": "footnotes",
            "evidence_policy": "verified_public_sources",
        },
    )
    references = "\n".join(
        f"[{source['id']}] {source['publisher']}. {source['title']}. {source['url']}"
        for source in SOURCES
    )
    first_text = (
        "Research Question\n\nWhat does authoritative evidence establish about recent global warming?\n\n"
        "Method\n\nThree independently published, HTTPS-accessible institutional sources were compared.\n\n"
        "Evidence\n\nIPCC attributes observed warming unequivocally to human activities [S1]. "
        "NASA describes converging natural-record and instrument evidence [S2]. "
        "NOAA reports that the ten warmest years in its 175-year record occurred in 2015–2024 [S3].\f"
        "Analysis and Findings\n\nThe sources agree on warming while contributing distinct attribution, measurement, and trend evidence [S1] [S2] [S3].\n\n"
        "Limitations\n\nThis brief does not estimate local impacts or future emissions pathways.\n\n"
        "Recommendations\n\nUse the cited evidence as a baseline and commission a location-specific risk assessment.\f"
        f"References\n\n{references}"
    )
    revised_text = first_text.replace(
        "commission a location-specific risk assessment",
        "commission a location-specific risk assessment with annual indicator refreshes",
    )
    _assert_sources_fail_closed(first_text)
    _assert_sources_fail_closed(revised_text)

    first = await document_e2e_harness.render_revision(first_text, 1, "research-climate-brief")
    second = await document_e2e_harness.render_revision(revised_text, 2, "research-climate-brief")
    final_download = await document_e2e_harness.redownload(second.artifact)
    final_text = document_e2e_harness.docx_text(final_download)

    assert first.artifact.content_hash != second.artifact.content_hash
    assert "annual indicator refreshes" in final_text
    assert "annual indicator refreshes" not in document_e2e_harness.docx_text(first.downloaded)
    _assert_sources_fail_closed(final_text)
    assert (second.artifact.metadata_json or {})["artifact_version"] == 2
