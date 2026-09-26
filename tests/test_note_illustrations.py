import hashlib
import json

import pytest
from pydantic import ValidationError

from backend.services.note_illustrations import NoteIllustrationRequest, illustration_plan, execute_illustrations, media_directory
from scripts.chat_run_store import DurableChatRunStore


def request(content=None, **kwargs):
    content = content or ('学习需要把知识连接起来，而不仅仅是重复阅读。可以用概念之间的关系来组织一章的内容，并用自己的例子检验理解。' * 2)
    return NoteIllustrationRequest(note_id='note-1', request_id='request-1234', title='学习方法', content=content,
                                  source_hash=hashlib.sha256(content.encode()).hexdigest(), mode='auto', **kwargs)


def run(store, body, owner='owner'):
    row, _ = store.create_or_get(tenant_user_hash=owner, session_id='note-1', request_id=body.request_id,
                                execution_payload={'run_type': 'note_illustration', 'illustration': body.model_dump()})
    return row


def test_positions_exclude_code_existing_images_and_short_notes():
    assert illustration_plan(request('买牛奶')) == []
    text = '这段文字介绍学习过程与理解知识之间的联系。' * 6
    assert illustration_plan(request('```text\n' + text + '\n```')) == []
    assert illustration_plan(request(text + '\n\n![已有图片](Attachments/x.jpg)')) == []
    plan = illustration_plan(request(text + '\n\n结束。'))
    assert plan[0]['anchor'] == text
    assert '结束。' in plan[0]['prompt']
    assert '统一风格' in plan[0]['prompt']


def test_manual_includes_brief_full_note_and_neighbors():
    content = '文章主旨是保持专注。\n\n在宿舍读书。\n\n最后走到户外休息。'
    body = request(content).model_copy(update={'mode': 'manual', 'anchor': '在宿舍读书。', 'brief': '温暖夜灯，两个学生'})
    body = NoteIllustrationRequest.model_validate(body.model_dump())
    plan = illustration_plan(body)
    assert len(plan) == 1
    for text in ('保持专注', '户外休息', '温暖夜灯', '在宿舍读书'):
        assert text in plan[0]['prompt']
    with pytest.raises(ValidationError):
        NoteIllustrationRequest.model_validate({**body.model_dump(), 'source_hash': '0' * 64})
    with pytest.raises(ValidationError):
        NoteIllustrationRequest.model_validate({**body.model_dump(), 'anchor': '不存在'})


def test_travel_plan_keeps_structured_anchors_and_skips_existing():
    body = request(json.dumps({'stops': [{'name': '公园'}], 'illustrations': [{'anchor': 'overview'}]}), travel=True)
    assert [p['anchor'] for p in illustration_plan(body)] == ['stop:0']
    with pytest.raises(ValidationError):
        request('这不是行程 JSON', travel=True)


def test_durable_execution_reuses_successful_assets_and_is_owner_private(tmp_path):
    store = DurableChatRunStore(tmp_path / 'runs.db')
    body = request()
    row = run(store, body)
    calls = []
    def generate(prompt):
        calls.append(prompt)
        return b'fixture-image', 'test-provider', 'test-model'
    execute_illustrations(store, row, generate)
    result = json.loads(store.get_unchecked(row['run_id'])['final_answer'])
    asset = result['assets'][0]
    assert asset['sha256'] == hashlib.sha256(b'fixture-image').hexdigest()
    with pytest.raises(PermissionError):
        store.get(row['run_id'], tenant_user_hash='other-owner')
    retry = body.model_copy(update={'request_id': 'request-retry', 'retry_run_id': row['run_id']})
    next_row = run(store, retry)
    execute_illustrations(store, next_row, generate)
    assert len(calls) == 1
    next_result = json.loads(store.get_unchecked(next_row['run_id'])['final_answer'])
    assert next_result['assets'][0]['run_id'] == row['run_id']
    assert (media_directory(store, row['run_id']) / 'plan.json').exists()


def test_cancellation_never_inserts_a_result(tmp_path):
    store = DurableChatRunStore(tmp_path / 'runs.db')
    row = run(store, request())
    def generate(prompt):
        store.terminal(row['run_id'], status='cancelled')
        return b'fixture', 'test', 'test'
    execute_illustrations(store, row, generate)
    assert store.get_unchecked(row['run_id'])['status'] == 'cancelled'
    assert not (media_directory(store, row['run_id']) / '0.jpg').exists()


def test_failed_generation_is_not_reported_as_a_generated_picture(tmp_path):
    store = DurableChatRunStore(tmp_path / 'runs.db')
    row = run(store, request())
    def fail(prompt):
        raise RuntimeError('secret provider message must not reach user')
    execute_illustrations(store, row, fail)
    value = json.loads(store.get_unchecked(row['run_id'])['final_answer'])
    assert value['assets'] == []
    assert value['failed_indices'] == [0]
    assert 'secret' not in json.dumps(value)


def test_bridge_auth_scope_idempotency_and_cancel(tmp_path, monkeypatch):
    import asyncio
    from fastapi import HTTPException
    from scripts.hermes_bridge_runtime import note_illustrations as api
    store = DurableChatRunStore(tmp_path / 'runs.db')
    monkeypatch.setattr(api.session_runtime, '_chat_run_store', store)
    monkeypatch.setattr(api.contracts, '_require_durable_worker', lambda: None)
    monkeypatch.setattr(api.persistence, '_require_internal_strict', lambda token: None if token == 'internal' else (_ for _ in ()).throw(HTTPException(401)))
    body = request()
    first = asyncio.run(api.start(body, 'internal', 'tenant-a', 'user-a'))
    second = asyncio.run(api.start(body, 'internal', 'tenant-a', 'user-a'))
    assert first['run_id'] == second['run_id']
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.status(first['run_id'], 'internal', 'tenant-b', 'user-a'))
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.start(body, 'wrong', 'tenant-a', 'user-a'))
    assert error.value.status_code == 401
    cancelled = asyncio.run(api.cancel(first['run_id'], 'internal', 'tenant-a', 'user-a'))
    assert cancelled['status'] == 'cancelled'
    changed = body.model_copy(update={'brief': 'another request'})
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.start(changed, 'internal', 'tenant-a', 'user-a'))
    assert error.value.status_code == 409


def test_http_note_routes_preserve_owner_and_validate_body(monkeypatch):
    import asyncio
    import httpx
    from backend.main import app
    from backend.api.auth import require_auth
    from backend.api import knowledge_sync as api
    seen = []
    async def principal():
        return {'tenant_key': 'tenant-a', 'sub': 'user-a'}
    async def transport(payload, path, method='GET', body=None):
        seen.append((payload, path, method, body))
        return {'run_id': 'a' * 32, 'status': 'queued', 'message': 'queued', 'assets': [], 'failed_indices': [], 'error_code': ''}
    monkeypatch.setattr(api, '_illustration_bridge', transport)
    old = app.dependency_overrides.get(require_auth)
    app.dependency_overrides[require_auth] = principal
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/api/v1/me/knowledge-notes/illustrations/generate', json=request().model_dump())
            assert response.status_code == 202, response.text
            assert seen[-1][0]['sub'] == 'user-a'
            assert seen[-1][2] == 'POST'
            response = await client.post('/api/v1/me/knowledge-notes/illustrations/generate', json={**request().model_dump(), 'source_hash': '0'*64})
            assert response.status_code == 422
            response = await client.get('/api/v1/me/knowledge-notes/illustrations/not-a-run')
            assert response.status_code == 404
    try:
        asyncio.run(scenario())
    finally:
        if old is None:
            app.dependency_overrides.pop(require_auth, None)
        else:
            app.dependency_overrides[require_auth] = old


def test_existing_worker_dispatches_note_job_without_chat_agent(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    from backend.services import note_illustrations as service
    spec = importlib.util.spec_from_file_location('note_worker_test', Path(__file__).parents[1] / 'scripts/chat_run_worker.py')
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    async def placement(*args, **kwargs):
        return SimpleNamespace(bridge_config=lambda: {'shard_id': 'fixture'})
    monkeypatch.setattr(worker, 'resolve_runtime_placement', placement)
    monkeypatch.setattr(worker, 'claim_runtime_placement', placement)
    original = service.execute_illustrations
    monkeypatch.setattr(service, 'execute_illustrations', lambda store, row: original(store, row, lambda prompt: (b'fixture', 'test', 'test')))
    monkeypatch.setattr(worker.bridge, '_run_agent_sync', lambda *args: pytest.fail('note job must not enter the chat agent'))
    store = DurableChatRunStore(tmp_path / 'runs.db')
    row = run(store, request())
    worker.execute(store, store.claim_next('test-worker'))
    completed = store.get_unchecked(row['run_id'])
    assert completed['status'] == 'completed'
    assert len(json.loads(completed['final_answer'])['assets']) == 1
