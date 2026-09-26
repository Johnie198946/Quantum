import asyncio
import copy
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.api import learning
from backend.db import Base
from backend.models.tenant import LearningExercise, LearningProfile

AUTH = {"tenant_key": "tenant-a", "user_id": "learner-a"}
TEXT = "合并计数器时，对每个分量取最大值。合并集合时，应当计算集合的并集。这些操作具有幂等性，重复合并同一个状态不会改变结果。"
VERSION = "a" * 64


def run(coro):
    return asyncio.run(coro)


def generated():
    qs = []
    for index, kind in enumerate(["choice", "judgement", "solution", "response"]):
        objective = kind in {"choice", "judgement"}
        ids = ["T", "F"] if kind == "judgement" else ["A", "B"]
        qs.append(dict(id=f"q{index+1}", kind=kind, body=f"问题{index+1}：如何合并？", knowledge_point="幂等合并", hint="先把同一份状态合并两次，观察哪些数值不应再变化。", difficulty=1, minutes=2,
                       source_excerpt="合并计数器时，对每个分量取最大值。", options=[dict(id=k, text=("正确" if k == "T" else "错误") if kind == "judgement" else k) for k in ids] if objective else [],
                       correct_ids=[ids[0]] if objective else [], reference_answer="分量取最大值。", explanation="重复取最大值不会改变结果，因此该操作具有幂等性。",
                       option_explanations={k: "取最大值满足幂等性，覆盖会丢失数据。" for k in ids} if objective else {},
                       rubric=[] if objective else [dict(description="解释最大值与幂等性的关系", max_points=3)]))
    return dict(summary="尚无独立作答记录，先用混合诊断题检查理解。", evidence_ids=["reading", "performance"], questions=qs)


@pytest.fixture
def env(monkeypatch, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'learning.db'}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(Base.metadata.create_all)  # additive migration is idempotent
    run(setup())
    monkeypatch.setattr(learning, "SessionLocal", maker)
    async def source(payload, book_id):
        if book_id != "book":
            raise HTTPException(404)
        return {"title": "合并状态"}, {"content_version": VERSION, "sections": [{"id": "chapter", "title": "幂等性", "markdown": TEXT}]}
    async def memory(payload):
        return {"items": [{"content": "正在学习分布式数据合并，想理解概念。"}]}
    async def notes(**kwargs):
        return {"items": [{"markdown": "book 我的问题：为什么不能覆盖？", "updated_at": "2026-09-25"}]}
    async def model(prompt, payload):
        if "criterion_feedback" in prompt:
            return json.dumps({"items": [{"question_id": k, "points": [2], "criterion_feedback": ["已说明最大值，缺少重复合并的具体例子。"], "explanation": "你的回答说明了最大值规则，但没有演示重复合并为什么不改变结果。", "next_step": "用两个相同状态演示一次重复合并。", "confidence": "medium"} for k in ["q3", "q4"]]}, ensure_ascii=False)
        return json.dumps(generated(), ensure_ascii=False)
    monkeypatch.setattr(learning.subscriptions, "_available_book_body", source)
    monkeypatch.setattr(learning.hot_memory, "get_memory", memory)
    monkeypatch.setattr(learning.knowledge_sync, "list_synced_notes", notes)
    monkeypatch.setattr(learning, "model_json", model)
    yield maker
    run(engine.dispose())


def create():
    return learning.CreateExercise(id=uuid4(), book_id="book", section_id="chapter", content_version=VERSION)


def answers(revision, *, assisted=False):
    return learning.SaveAnswers(revision=revision, answers={
        "q1": learning.Answer(selected=["A"], assisted=assisted), "q2": learning.Answer(selected=["F"]),
        "q3": learning.Answer(text="分量取最大值"), "q4": learning.Answer(text="重复合并不变"),
    })


def test_model_uses_existing_jev_chat_route_with_compact_platform_scope(monkeypatch):
    async def chat_route(request, payload):
        assert request.context_scope.mode == "platform_only"
        assert request.question == "请生成诊断题"
        assert payload == AUTH
        return learning.chat.ChatResponse(question=request.question, answer='{"ok":true}')
    monkeypatch.setattr(learning.chat, "chat", chat_route)
    assert run(learning.model_json("请生成诊断题", AUTH)) == '{"ok":true}'
    with pytest.raises(HTTPException) as exc:
        run(learning.model_json("长" * 11_501, AUTH))
    assert exc.value.status_code == 422


def test_mixed_set_private_keys_drafts_grading_and_idempotency(env):
    request = create()
    first = run(learning.create_exercise(request, AUTH))
    assert {q["kind"] for q in first["questions"]} == learning.KINDS
    assert all(q["hint"] for q in first["questions"])
    assert first["confidence"] == "low"
    assert "saved_dialogue" in first["evidence_kinds"] and "memory" in first["evidence_kinds"]
    assert not any(k in json.dumps(first) for k in ["correct_ids", "reference_answer", "rubric", "option_explanations"])
    assert run(learning.create_exercise(request, AUTH))["id"] == first["id"]
    draft = run(learning.save_draft(request.id, answers(first["revision"]), AUTH))
    assert run(learning.get_exercise(request.id, AUTH))["answers"] == draft["answers"]
    with pytest.raises(HTTPException) as stale:
        run(learning.save_draft(request.id, answers(first["revision"]), AUTH))
    assert stale.value.status_code == 409
    graded = run(learning.submit_exercise(request.id, answers(draft["revision"]), AUTH))
    assert graded["status"] == "graded"
    assert [r["score"] for r in graded["results"]] == [1, 0, 2, 2]
    assert graded["results"][2]["criterion_feedback"]
    assert graded["results"][0]["option_explanations"]["B"]
    assert run(learning.submit_exercise(request.id, answers(draft["revision"]), AUTH)) == graded
    assert run(learning.latest_exercise("book", "chapter", AUTH))["exercise"]["id"] == graded["id"]


def test_account_and_tenant_isolation(env):
    req = create()
    run(learning.create_exercise(req, AUTH))
    for other in [{**AUTH, "user_id": "learner-b"}, {**AUTH, "tenant_key": "tenant-b"}]:
        assert run(learning.latest_exercise("book", "chapter", other))["exercise"] is None
        for coro in [learning.get_exercise(req.id, other), learning.save_draft(req.id, answers(1), other), learning.submit_exercise(req.id, answers(1), other), learning.create_exercise(req, other)]:
            with pytest.raises(HTTPException) as exc:
                run(coro)
            assert exc.value.status_code == 404


def test_generation_rejects_missing_kind_source_fabrication_and_version(env, monkeypatch):
    req = create()
    with pytest.raises(HTTPException) as exc:
        run(learning.create_exercise(req.model_copy(update={"content_version": "b" * 64}), AUTH))
    assert exc.value.status_code == 409
    async def broken(prompt, payload):
        data = generated()
        data["questions"][0]["source_excerpt"] = "根本不存在的来源内容。"
        return json.dumps(data)
    monkeypatch.setattr(learning, "model_json", broken)
    with pytest.raises(HTTPException):
        run(learning.create_exercise(req, AUTH))
    row = run(learning.get_exercise(req.id, AUTH))
    assert row["status"] == "failed" and not row["questions"]
    async def fixed(prompt, payload):
        return json.dumps(generated())
    monkeypatch.setattr(learning, "model_json", fixed)
    assert run(learning.retry_generation(req.id, AUTH))["status"] == "draft"


def test_bad_mark_keeps_answers_and_allows_retry(env, monkeypatch):
    req = create()
    created = run(learning.create_exercise(req, AUTH))
    async def broken(prompt, payload):
        return '{"items": []}'
    monkeypatch.setattr(learning, "model_json", broken)
    with pytest.raises(HTTPException):
        run(learning.submit_exercise(req.id, answers(created["revision"]), AUTH))
    restored = run(learning.get_exercise(req.id, AUTH))
    assert restored["status"] == "draft" and len(restored["answers"]) == 4 and not restored["results"]
    assert restored["revision"] > created["revision"]


def test_judgement_contract_is_sent_to_model_and_missing_options_can_retry(env, monkeypatch):
    request = create()
    async def missing_options(prompt, payload):
        # Real model failure: optional JSON-schema fields omitted for judgement.
        data = generated()
        for key in ("options", "correct_ids", "option_explanations"):
            del data["questions"][1][key]
        return json.dumps(data)
    monkeypatch.setattr(learning, "model_json", missing_options)
    with pytest.raises(HTTPException) as exc:
        run(learning.create_exercise(request, AUTH))
    assert exc.value.status_code == 502

    async def instructed_model(prompt, payload):
        schema = json.loads(prompt.split("只返回一个完整 JSON 对象，符合此 schema，不加任何额外说明：\n", 1)[1].split("\n证据及限制：\n", 1)[0])
        fields = schema["$defs"]["Question"]["properties"]
        assert '[{"id":"T","text":"正确"},{"id":"F","text":"错误"}]' in fields["options"]["description"]
        assert '["T"] 或 ["F"]' in fields["correct_ids"]["description"]
        assert "所有选项id" in fields["option_explanations"]["description"]
        assert "至少一条评分规则" in fields["rubric"]["description"]
        return json.dumps(generated())
    monkeypatch.setattr(learning, "model_json", instructed_model)
    assert run(learning.retry_generation(request.id, AUTH))["status"] == "draft"


def test_independent_accuracy_excludes_repeats_and_assistance(env):
    first = create()
    created = run(learning.create_exercise(first, AUTH))
    assisted = run(learning.submit_exercise(first.id, answers(created["revision"], assisted=True), AUTH))
    assert assisted["results"][0]["score"] == 1
    assert "不计入独立掌握度" in assisted["results"][0]["next_step"]
    assert "不计入独立掌握度" not in assisted["results"][1]["next_step"]
    assert run(learning.get_exercise(first.id, AUTH))["results"] == assisted["results"]
    second = create()
    created2 = run(learning.create_exercise(second, AUTH))
    independent = run(learning.submit_exercise(second.id, answers(created2["revision"]), AUTH))
    assert [r["score"] for r in independent["results"]] == [r["score"] for r in assisted["results"]]
    async def history():
        async with env() as db:
            return list((await db.scalars(select(LearningExercise))).all())
    stats = learning.performance(run(history()))
    assert stats[0]["objective_count"] == 1  # assisted q1 excluded, repeated q2 excluded
    assert stats[0]["objective_accuracy"] == 0
    assert stats[0]["subjective_count"] == 2
    assert stats[0]["subjective_mean"] == pytest.approx(2/3)


def test_grading_prompt_keeps_scoring_evidence_without_repeated_explanations(env, monkeypatch):
    request = create()
    created = run(learning.create_exercise(request, AUTH))
    model = learning.model_json
    async def capture(prompt, payload):
        questions_text, answer_text = prompt.split("\n评分题目和原文：", 1)[1].split("\n用户作答：", 1)
        questions = json.loads(questions_text)
        for compact, original in zip(questions, generated()["questions"][2:]):
            assert set(compact) == {"id", "body", "source_excerpt", "reference_answer", "rubric"}
            assert all(value == original[key] for key, value in compact.items())
        assert json.loads(answer_text) == {"q3": "分量取最大值", "q4": "重复合并不变"}
        return await model(prompt, payload)
    monkeypatch.setattr(learning, "model_json", capture)
    assert run(learning.submit_exercise(request.id, answers(created["revision"], assisted=True), AUTH))["status"] == "graded"


def test_invalid_answer_and_incomplete_submit_do_not_change_draft(env):
    req = create()
    row = run(learning.create_exercise(req, AUTH))
    for bad in [learning.SaveAnswers(revision=row["revision"], answers={}),
                answers(row["revision"]).model_copy(update={"answers": {"q99": learning.Answer(text="伪造")}})]:
        with pytest.raises(HTTPException) as exc:
            run(learning.submit_exercise(req.id, bad, AUTH))
        assert exc.value.status_code == 422
    assert run(learning.get_exercise(req.id, AUTH))["revision"] == row["revision"]


def test_missing_kind_is_rejected(env, monkeypatch):
    async def broken(prompt, payload):
        data = generated()
        data["questions"][3]["kind"] = "solution"
        return json.dumps(data)
    monkeypatch.setattr(learning, "model_json", broken)
    with pytest.raises(HTTPException) as exc:
        run(learning.create_exercise(create(), AUTH))
    assert exc.value.status_code == 502


def test_grading_lease_recovery_and_invalid_points(env, monkeypatch):
    req = create()
    first = run(learning.create_exercise(req, AUTH))
    async def interrupted():
        async with env() as db:
            await db.execute(update(LearningExercise).where(LearningExercise.id == str(req.id)).values(
                status="grading", drafts={k: v.model_dump() for k, v in answers(first["revision"]).answers.items()},
                updated_at=learning.now() - timedelta(minutes=5)))
            await db.commit()
    run(interrupted())
    graded = run(learning.submit_exercise(req.id, answers(first["revision"]), AUTH))
    assert graded["status"] == "graded"
    req2 = create()
    fresh = run(learning.create_exercise(req2, AUTH))
    model = learning.model_json
    async def excessive(prompt, payload):
        data = json.loads(await model(prompt, payload))
        data["items"][0]["points"] = [999]
        return json.dumps(data)
    monkeypatch.setattr(learning, "model_json", excessive)
    with pytest.raises(HTTPException) as exc:
        run(learning.submit_exercise(req2.id, answers(fresh["revision"]), AUTH))
    assert exc.value.status_code == 502
    restored = run(learning.get_exercise(req2.id, AUTH))
    assert restored["status"] == "draft" and len(restored["answers"]) == 4


def test_version_change_hides_old_set_and_access_is_rechecked(env, monkeypatch):
    req = create()
    run(learning.create_exercise(req, AUTH))
    original = learning.subscriptions._available_book_body
    async def changed(payload, book_id):
        book, source = await original(payload, book_id)
        source["content_version"] = "b" * 64
        return book, source
    monkeypatch.setattr(learning.subscriptions, "_available_book_body", changed)
    assert run(learning.latest_exercise("book", "chapter", AUTH))["exercise"] is None
    async def revoked(payload, book_id):
        raise HTTPException(404)
    monkeypatch.setattr(learning.subscriptions, "_available_book_body", revoked)
    with pytest.raises(HTTPException) as exc:
        run(learning.get_exercise(req.id, AUTH))
    assert exc.value.status_code == 404


def test_concurrent_submit_claims_only_one_grading_job(env, monkeypatch):
    req = create()
    first = run(learning.create_exercise(req, AUTH))
    model = learning.model_json
    async def check():
        started, release = asyncio.Event(), asyncio.Event()
        async def slow(prompt, payload):
            started.set()
            await release.wait()
            return await model(prompt, payload)
        monkeypatch.setattr(learning, "model_json", slow)
        job = asyncio.create_task(learning.submit_exercise(req.id, answers(first["revision"]), AUTH))
        await asyncio.wait_for(started.wait(), timeout=5)
        try:
            with pytest.raises(HTTPException) as exc:
                await learning.submit_exercise(req.id, answers(first["revision"]), AUTH)
            assert exc.value.status_code == 409
        finally:
            release.set()
        assert (await job)["status"] == "graded"
    run(check())


def test_profile_updates_from_new_grade_once_and_reuses_compact_sources(env, monkeypatch, tmp_path):
    calls = {"memory": 0, "notes": 0}
    memory = learning.hot_memory.get_memory
    notes = learning.knowledge_sync.list_synced_notes
    async def counted_memory(payload):
        calls["memory"] += 1
        return await memory(payload)
    async def counted_notes(**kwargs):
        calls["notes"] += 1
        return await notes(**kwargs)
    monkeypatch.setattr(learning.hot_memory, "get_memory", counted_memory)
    monkeypatch.setattr(learning.knowledge_sync, "list_synced_notes", counted_notes)
    first = create().model_copy(update={"dialogue": [learning.Dialogue(role="user", content="为什么重复合并不变？")]})
    created = run(learning.create_exercise(first, AUTH))
    assert calls == {"memory": 1, "notes": 1}
    run(learning.submit_exercise(first.id, answers(created["revision"]), AUTH))
    second = create()
    run(learning.create_exercise(second, AUTH))
    assert calls == {"memory": 1, "notes": 1}
    async def snapshot():
        async with env() as db:
            return await db.get(LearningProfile, (AUTH["tenant_key"], AUTH["user_id"], "book", VERSION))
    profile = run(snapshot())
    assert len(profile.attempts) == 4
    assert [item["kind"] for item in profile.attempts] == ["choice", "judgement", "solution", "response"]
    assert any("重复合并" in item["text"] for item in profile.signals["recent_dialogue"])
    run(learning.refresh_profile(second, AUTH))
    assert len(run(snapshot()).attempts) == 4
    assert run(learning.refresh_profile(second, {**AUTH, "user_id": "other"})).attempts == []
    index = tmp_path / "private-index.json"
    index.write_text('{"index_hash":"changed-notes"}', encoding="utf-8")
    monkeypatch.setattr(learning.knowledge_sync, "private_note_index_path", lambda *args: index)
    run(learning.create_exercise(create(), AUTH))
    assert calls == {"memory": 2, "notes": 2}
    fresh_signals = run(snapshot()).signals
    assert fresh_signals["note_index_hash"] == "changed-notes"
    async def expire():
        async with env() as db:
            await db.execute(update(LearningProfile).where(LearningProfile.tenant_key == AUTH["tenant_key"],
                LearningProfile.owner_user_id == AUTH["user_id"]).values(
                signals_refreshed_at=learning.now() - timedelta(days=2)))
            await db.commit()
    run(expire())
    async def unavailable(payload):
        raise RuntimeError("temporarily unavailable")
    monkeypatch.setattr(learning.hot_memory, "get_memory", unavailable)
    run(learning.create_exercise(create(), AUTH))
    retained = run(snapshot()).signals
    assert retained["memory"] == fresh_signals["memory"]
    assert any("长期记忆" in notice for notice in retained["unavailable"])


def test_memory_write_invalidates_only_current_readers_profile(env, monkeypatch):
    run(learning.create_exercise(create(), AUTH))
    other = {**AUTH, "user_id": "other"}
    run(learning.refresh_profile(create(), other, refresh_sources=True))
    async def policy(payload):
        return "policy"
    async def write(*args, **kwargs):
        return {"id": "saved"}
    monkeypatch.setattr(learning.hot_memory, "_resolve_chat_policy", policy)
    monkeypatch.setattr(learning.hot_memory, "add_native_memory", write)
    assert run(learning.hot_memory.create_memory(
        learning.hot_memory.MemoryWriteRequest(target="memory", content="新学习目标"), AUTH)) == {"id": "saved"}
    async def timestamps():
        async with env() as db:
            ours = await db.get(LearningProfile, (AUTH["tenant_key"], AUTH["user_id"], "book", VERSION))
            theirs = await db.get(LearningProfile, (AUTH["tenant_key"], other["user_id"], "book", VERSION))
            return ours.signals_refreshed_at, theirs.signals_refreshed_at
    ours, theirs = run(timestamps())
    assert ours is None and theirs is not None
    async def refresh_marker():
        async with env() as db:
            await db.execute(update(LearningProfile).where(LearningProfile.tenant_key == AUTH["tenant_key"],
                LearningProfile.owner_user_id == AUTH["user_id"]).values(signals_refreshed_at=learning.now()))
            await db.commit()
    monkeypatch.setattr(learning.hot_memory, "replace_native_memory", write)
    monkeypatch.setattr(learning.hot_memory, "delete_native_memory", write)
    run(refresh_marker())
    run(learning.hot_memory.replace_memory("memory-id", learning.hot_memory.MemoryReplaceRequest(content="改动"), AUTH))
    assert run(timestamps())[0] is None
    run(refresh_marker())
    run(learning.hot_memory.remove_memory("memory-id", AUTH))
    assert run(timestamps())[0] is None


def test_prompt_bounds_reading_and_rejects_oversized_grading_without_losing_answers(env, monkeypatch):
    original = learning.subscriptions._available_book_body
    async def long_source(payload, book_id):
        book, source = await original(payload, book_id)
        source["sections"][0]["markdown"] = TEXT + ("扩展章节内容。" * 3000)
        return book, source
    monkeypatch.setattr(learning.subscriptions, "_available_book_body", long_source)
    prompts = []
    original_model = learning.model_json
    async def capture(prompt, payload):
        prompts.append(prompt)
        return await original_model(prompt, payload)
    monkeypatch.setattr(learning, "model_json", capture)
    req = create()
    created = run(learning.create_exercise(req, AUTH))
    assert created["status"] == "draft"
    assert len(prompts[0]) < 11_500
    assert "扩展章节内容。" * 1000 not in prompts[0]
    long_answers = answers(created["revision"])
    long_answers.answers["q3"].text = "解释" * 6000
    with pytest.raises(HTTPException) as exc:
        run(learning.submit_exercise(req.id, long_answers, AUTH))
    assert exc.value.status_code == 422
    restored = run(learning.get_exercise(req.id, AUTH))
    assert restored["status"] == "draft" and restored["answers"]["q3"]["text"] == long_answers.answers["q3"].text


def test_app_registers_the_client_learning_routes():
    from backend.main import app

    from fastapi.testclient import TestClient

    client = TestClient(app)
    for method, path in [
        ("GET", "/api/v1/me/learning-resume"),
        ("GET", "/api/v1/me/learning-exercises"),
        ("POST", "/api/v1/me/learning-exercises"),
    ]:
        assert client.request(method, path).status_code == 401


def test_hints_required_for_new_questions_and_optional_for_old_rows(env):
    from pydantic import ValidationError
    question = generated()["questions"][0]
    for invalid in ("", " " * 3, "字" * 241):
        with pytest.raises(ValidationError):
            learning.Question.model_validate({**question, "hint": invalid})
    del question["hint"]
    with pytest.raises(ValidationError):
        learning.Question.model_validate(question)
    req = create()
    run(learning.create_exercise(req, AUTH))
    async def legacy():
        async with env() as db:
            row = await db.get(LearningExercise, str(req.id))
            row.questions = [{k: v for k, v in q.items() if k != "hint"} for q in row.questions]
            await db.commit()
    run(legacy())
    restored = run(learning.get_exercise(req.id, AUTH))
    assert all(q["hint"] == "" for q in restored["questions"])
    assert run(learning.submit_exercise(req.id, answers(restored["revision"]), AUTH))["status"] == "graded"
