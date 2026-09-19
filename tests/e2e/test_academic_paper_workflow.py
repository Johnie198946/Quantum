from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest


SOURCES = json.loads(
    Path("tests/fixtures/document_e2e/verified_sources.json").read_text(encoding="utf-8")
)["academic_paper"]
CITATION_KEYS = {
    "(Munafò et al., 2017)": "MUN2017",
    "(Wilson et al., 2014)": "WIL2014",
    "(Wilkinson et al., 2016)": "WIL2016",
}


def _assert_citation_correspondence(paper: str) -> None:
    assert all(section in paper for section in (
        "Abstract", "Keywords", "Introduction", "Method", "Results",
        "Discussion", "Conclusion", "References",
    ))
    body, references = re.split(r"References\n+", paper, maxsplit=1)
    observed = set(re.findall(r"\([A-ZÀ-ÖØ-Ý][^()]+? et al\., 20\d{2}\)", body))
    assert observed == set(CITATION_KEYS)
    verified_ids = {source["id"] for source in SOURCES}
    assert set(CITATION_KEYS.values()) == verified_ids
    for marker, source_id in CITATION_KEYS.items():
        source = next(item for item in SOURCES if item["id"] == source_id)
        assert marker in body
        assert source["citation"] in references
        assert source["access_status"] == 200
        assert hashlib.sha256(source["excerpt"].encode()).hexdigest() == source["excerpt_sha256"]
    assert set(re.findall(r"https://doi\.org/[^\s]+", references)) == {
        source["url"].replace("https://www.nature.com/articles/s41562-016-0021", "https://doi.org/10.1038/s41562-016-0021")
        .replace("https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.1001745", "https://doi.org/10.1371/journal.pbio.1001745")
        .replace("https://www.nature.com/articles/sdata201618", "https://doi.org/10.1038/sdata.2016.18")
        for source in SOURCES
    }


@pytest.mark.asyncio
async def test_academic_paper_structure_and_verified_citation_correspondence(document_e2e_harness):
    await document_e2e_harness.create(
        "paper.academic.create_from_text",
        {
            "title": "A traceable workflow for reproducible computational research",
            "text_material": "Only the three verified publications in the evidence fixture may be cited.",
            "thesis": "Traceable planning, software practice, and reusable data jointly improve reproducibility.",
            "language": "en-US",
            "citation_style": "apa7",
            "evidence_policy": "verified_public_sources",
        },
    )
    references = "\n".join(source["citation"] for source in SOURCES)
    paper = (
        "Abstract\n\nThis paper synthesizes three verified sources to define a traceable computational research workflow. "
        "It argues that advance planning, maintainable software, and reusable data are complementary controls.\n\n"
        "Keywords\n\nreproducibility; preregistration; scientific software; FAIR data\f"
        "Introduction\n\nReproducibility reforms target methods, reporting, dissemination, evaluation, and incentives (Munafò et al., 2017).\n\n"
        "Method\n\nA bounded synthesis was performed over exactly three accessible publications; no unresolved source was admitted.\n\n"
        "Results\n\nScientific software practices improve reliability and productivity (Wilson et al., 2014). "
        "Machine-actionable findability and reuse strengthen data stewardship (Wilkinson et al., 2016).\f"
        "Discussion\n\nThe evidence supports layered controls rather than a single reproducibility intervention (Munafò et al., 2017).\n\n"
        "Conclusion\n\nA governed workflow should bind plans, code practice, and reusable data to verifiable receipts.\n\n"
        f"References\n\n{references}"
    )
    _assert_citation_correspondence(paper)
    rendered = await document_e2e_harness.render_revision(paper, 1, "academic-reproducibility-paper")
    downloaded = await document_e2e_harness.redownload(rendered.artifact)
    final_text = document_e2e_harness.docx_text(downloaded)

    _assert_citation_correspondence(final_text)
    assert document_e2e_harness.docx_page_breaks(downloaded) == 2
    assert rendered.artifact.content_hash == hashlib.sha256(downloaded).hexdigest()
