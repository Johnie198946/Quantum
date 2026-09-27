from pathlib import Path

import pytest

from backend.api.chat import ChatContextScope, LocalNoteContext, _resolve_source_context
from backend.services.knowledge_policy import KnowledgePolicy
from backend.services.knowledge_policy import verify_capability
from backend.services.user_note_context import (
    note_paths, read_user_notes_by_ids, search_user_notes,
    persist_generated_private_note,
)
from backend.services.user_note_context import (
    LOCAL_NOTE_CONTEXT_MAX_CHARS,
    render_local_note_context,
)


def policy() -> KnowledgePolicy:
    return KnowledgePolicy(
        tenant_key="tenant-a",
        org_id="org-a",
        plan_id="free",
        plan_status="active",
        wallet=frozenset(),
        entitled_yellow=frozenset(),
        effective_categories=frozenset({"wiki"}),
        policy_version="policy-test",
        entitlement_stale=False,
    )


def test_search_user_notes_isolates_tenant_and_user(tmp_path: Path):
    own, own_meta = note_paths("tenant-a", "user-a", "note-1", tmp_path)
    own.parent.mkdir(parents=True)
    own.write_text("---\ntitle: 我的会议\n---\n\n- [ ] 给客户回信\n", encoding="utf-8")
    own_meta.write_text('{"client_updated_at":"2026-08-22T01:00:00Z"}', encoding="utf-8")

    other, _ = note_paths("tenant-a", "user-b", "note-2", tmp_path)
    other.parent.mkdir(parents=True)
    other.write_text("---\ntitle: 他人机密\n---\n\n- [ ] 不可见\n", encoding="utf-8")

    results = search_user_notes(
        tenant_key="tenant-a", user_id="user-a", query="整理最近待办", root=tmp_path
    )
    assert [item["title"] for item in results] == ["我的会议"]
    assert "他人机密" not in str(results)


def test_read_user_notes_by_ids_returns_exact_full_note_only(tmp_path: Path):
    own, own_meta = note_paths("tenant-a", "user-a", "active-doc", tmp_path)
    own.parent.mkdir(parents=True)
    body = "---\ntitle: 长文档\n---\n\n" + ("正文" * 12_000) + "\nTAIL-SENTINEL"
    own.write_text(body, encoding="utf-8")
    own_meta.write_text('{"client_updated_at":"2026-09-23T01:00:00Z"}', encoding="utf-8")
    other, _ = note_paths("tenant-a", "user-b", "active-doc", tmp_path)
    other.parent.mkdir(parents=True)
    other.write_text("PRIVATE-OTHER-USER", encoding="utf-8")

    results = read_user_notes_by_ids(
        tenant_key="tenant-a",
        user_id="user-a",
        note_ids=["active-doc", "../escape"],
        root=tmp_path,
    )

    assert [item["id"] for item in results] == ["active-doc"]
    assert results[0]["markdown"].endswith("TAIL-SENTINEL")
    assert "PRIVATE-OTHER-USER" not in results[0]["markdown"]
    assert len(results[0]["content_hash"]) == 64


def test_render_local_context_compacts_long_note_and_preserves_tasks():
    context = render_local_note_context([{
        "id": "large-note",
        "title": "超长本地笔记",
        "markdown": "普通正文" * 12_000 + "\n## 最后待办\n- [ ] 给客户发送复盘",
    }])
    assert len(context) <= LOCAL_NOTE_CONTEXT_MAX_CHARS
    assert "## 最后待办" in context
    assert "- [ ] 给客户发送复盘" in context
    assert context.endswith("</local_notes>")


def test_high_confidence_research_is_idempotently_ingested_as_private_knowledge(tmp_path: Path):
    content = "# 华为半年报分析\n\n" + "有证据支撑的经营分析。" * 20
    first = persist_generated_private_note(
        tenant_key="tenant-a", user_id="user-a", session_id="session-1",
        request_id="request-1", kind="research", content=content,
        confidence=0.84, root=tmp_path,
    )
    second = persist_generated_private_note(
        tenant_key="tenant-a", user_id="user-a", session_id="session-1",
        request_id="request-1", kind="research", content=content,
        confidence=0.84, root=tmp_path,
    )
    assert first == second
    assert first is not None
    note, metadata = note_paths("tenant-a", "user-a", first["note_id"], tmp_path)
    assert note.is_file() and metadata.is_file()
    assert note.stat().st_mode & 0o777 == 0o644
    assert metadata.stat().st_mode & 0o777 == 0o644
    assert note.parent.stat().st_mode & 0o777 == 0o755
    assert (note.parent / ".private-index.json").stat().st_mode & 0o777 == 0o644
    assert "security_level: red" in note.read_text(encoding="utf-8")
    assert not note_paths("tenant-a", "user-b", first["note_id"], tmp_path)[0].exists()


def test_low_confidence_result_is_not_ingested(tmp_path: Path):
    assert persist_generated_private_note(
        tenant_key="tenant-a", user_id="user-a", session_id="session-1",
        request_id="request-2", kind="solution", content="方案正文",
        confidence=0.59, root=tmp_path,
    ) is None


@pytest.mark.asyncio
async def test_local_only_never_calls_platform_wiki(monkeypatch):
    import backend.api.chat as chat

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("local_only must not query platform Wiki")

    monkeypatch.setattr(chat, "_knowledge_context", forbidden)
    resolved = await _resolve_source_context(
        scope=ChatContextScope(
            mode="local_only",
            local_notes=[LocalNoteContext(
                id="note-1", title="本地计划", markdown="# 本地计划\n- [ ] 复盘"
            )],
        ),
        payload={"tenant_key": "tenant-a", "user_id": "user-a"},
        subject_id="session-a",
        question="整理我的本地待办",
        policy=policy(),
    )
    claims = verify_capability(resolved.capability or "")
    assert claims["sources"] == ["user_notes"]
    assert claims["user_id"] == "user-a"
    assert resolved.knowledge_query == "整理我的本地待办"
    assert "本地计划" in resolved.evidence
    assert resolved.sources[0]["source"] == "user_note"


@pytest.mark.asyncio
async def test_auto_defers_source_selection_to_hermes(monkeypatch):
    import backend.api.chat as chat

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("auto must not prefetch a platform source")

    monkeypatch.setattr(chat, "_knowledge_context", forbidden)
    resolved = await _resolve_source_context(
        scope=ChatContextScope(mode="auto"),
        payload={"tenant_key": "tenant-a", "user_id": "user-a"},
        subject_id="session-a",
        question="超聚变是做什么的",
        policy=policy(),
    )
    claims = verify_capability(resolved.capability or "")
    assert set(claims["sources"]) == {"tenant_knowledge", "user_notes"}
    assert claims["user_id"] == "user-a"
    assert resolved.knowledge_query == "超聚变是做什么的"
    assert resolved.sources == []


def test_organization_checks_all_members_preserves_code_and_pages_evidence():
    from backend.services.user_note_context import organize_note_candidates
    def note(id, title, body, **extra):
        return {"note_id": id, "title": title, "markdown": body, **extra}
    shared = "This shared paragraph contains enough text to represent a meaningful reference."
    notes = [note("a", "Title A", "# A\n\nSame body"),
             note("b", "Title B", "# B\n\nSame body"),
             note("c", "Title C", "Same body"),
             note("archived", "Old", "Same body", archived=True),
             note("d", "Topic", shared + "\n\nIndependent idea D"),
             note("e", "Topic", shared + "\n\nIndependent idea E"),
             note("f", "Reference", "Read [[Title A#Section]] for details."),
             note("upper", "Code A", "```python\nVALUE = 1\n```"),
             note("lower", "Code B", "```python\nvalue = 1\n```")]
    result = organize_note_candidates(notes, limit=100)
    assert result["scanned_notes"] == 8
    assert result["semantic_scan_complete"] is False
    duplicates = [c for c in result["candidates"] if c["relation"] == "duplicate"]
    assert len(duplicates) == 1
    assert {n["note_id"] for n in duplicates[0]["notes"]} == {"a", "b", "c"}
    assert any(c["relation"] == "partial_overlap" and c["requires_semantic_review"] for c in result["candidates"])
    assert any(c["relation"] == "reference" for c in result["candidates"])
    first = organize_note_candidates(notes, limit=1)
    second = organize_note_candidates(notes, offset=first["next_offset"], limit=100)
    assert first["candidates"] + second["candidates"] == result["candidates"]
    assert organize_note_candidates(list(reversed(notes)), limit=100)["candidates"] == result["candidates"]


def test_organization_recalls_reworded_and_contained_notes_without_claiming_duplicates():
    from backend.services.user_note_context import organize_note_candidates
    common = "项目上线前，需要负责人核对预算、交付时间和验收条件，确认依赖任务完成后再通知客户。"
    notes = [
        {"id": "original", "title": "发布核对", "markdown": common},
        {"id": "rewrite", "title": "上线准备", "markdown": "项目上线之前，负责人需要核对预算、交付时间和验收条件；确认依赖任务完成之后再通知客户。"},
        {"id": "quote", "title": "客户协作", "markdown": common + "另一个独立主题是客户服务的工作流程，包括如何登记问题、分析原因和跟踪满意度。"},
        {"id": "unrelated", "title": "旅行", "markdown": "京都旅行计划：周六参观寺庙，周日坐火车去大阪。"},
    ]
    result = organize_note_candidates(notes, limit=100)
    groups = {frozenset(n["note_id"] for n in g["notes"]): g for g in result["candidates"]}
    assert groups[frozenset(("original", "rewrite"))]["relation"] == "similar_content_candidate"
    assert groups[frozenset(("original", "quote"))]["relation"] == "partial_overlap"
    assert all(g["requires_semantic_review"] for g in groups.values())
    assert all("unrelated" not in ids for ids in groups)
    assert not result["semantic_scan_complete"]
