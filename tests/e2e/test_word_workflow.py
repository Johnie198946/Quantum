from __future__ import annotations

import hashlib

import pytest


@pytest.mark.asyncio
async def test_word_multi_page_two_edits_redownload_and_hash(document_e2e_harness):
    await document_e2e_harness.create(
        "document.word.create_from_text",
        {
            "title": "Quarterly operating plan",
            "text_material": "Approved source: baseline revenue, retention, and delivery milestones.",
            "language": "en-US",
            "evidence_policy": "user_material_only",
        },
    )
    original = (
        "Quarterly Operating Plan\n\nExecutive Summary\n\n"
        "The approved revenue target is USD 2.0 million.\n\n"
        "Scope and assumptions are governed by the supplied operating baseline.\f"
        "Delivery Plan\n\nMilestone Alpha closes on 15 October.\n\n"
        "Owners will report progress every Friday.\f"
        "Controls and Sign-off\n\nFinance validates revenue; delivery validates milestones.\n\n"
        "Final approval is recorded in the workflow receipt."
    )
    revised = original.replace("USD 2.0 million", "USD 2.4 million").replace(
        "15 October", "22 October"
    )
    first = await document_e2e_harness.render_revision(original, 1, "word-operating-plan")
    second = await document_e2e_harness.render_revision(revised, 2, "word-operating-plan")
    redownloaded = await document_e2e_harness.redownload(second.artifact)

    assert first.downloaded != second.downloaded
    assert first.artifact.content_hash != second.artifact.content_hash
    assert hashlib.sha256(redownloaded).hexdigest() == second.artifact.content_hash
    assert redownloaded == second.downloaded
    assert document_e2e_harness.docx_page_breaks(first.downloaded) == document_e2e_harness.docx_page_breaks(second.downloaded) == 2
    final_text = document_e2e_harness.docx_text(redownloaded)
    assert "USD 2.4 million" in final_text and "22 October" in final_text
    assert "USD 2.0 million" not in final_text and "15 October" not in final_text
    assert (second.artifact.metadata_json or {})["artifact_version"] == 2
