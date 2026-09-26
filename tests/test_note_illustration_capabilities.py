import asyncio
import hashlib
import json
from unittest.mock import AsyncMock

import pytest

from backend.services.capability_catalog import describe_capability, CapabilityContractError
from backend.services.knowledge_action_capability import note_capability_step, note_presentation_fields
from scripts.hermes_bridge_runtime import knowledge


@pytest.fixture
def workspace(monkeypatch):
    body = '宿舍夜读时，我们在暖灯下交流想法。\n\n第二天去图书馆整理。'
    note = {'id': 'note-a', 'title': '校园生活', 'markdown': body, 'content_hash': hashlib.sha256(body.encode()).hexdigest(), 'tags': [], 'archived': False}
    events = []
    context = {'knowledge_action_v1': True, 'transcript': {'note_illustration_v1': True}, 'inline_notes': [note], 'request_id': 'request-1234', 'emit': events.append}
    monkeypatch.setattr(knowledge._client_context_tool_context, 'value', context, raising=False)
    return note, context, events


def invoke(action, data):
    return json.loads(knowledge._app_capability_invoke_tool({'capability_id': 'knowledge.note.illustration.' + action, 'input': data}))


def test_native_generate_is_reviewable_single_proposal_without_generation(workspace):
    note, _, events = workspace
    result = invoke('generate', {'note_id': note['id'], 'base_hash': note['content_hash'], 'anchor': note['markdown'].split('\n\n')[0], 'brief': '温暖的宿舍夜读', 'insert': True})
    assert result['status'] == 'awaiting_user_confirmation'
    assert result['applied'] is False
    step = events[0]['steps'][0]
    assert step['kind'] == 'illustrate_note' and step['illustration_insert'] is True
    assert step['title'] == note['title']
    assert events[0]['summary'] == '生成插图并插入笔记'
    assert events[0]['before_preview'] == note['markdown']


def test_old_client_foreign_note_stale_version_and_illegal_input_fail_closed(workspace):
    note, context, events = workspace
    data = {'note_id': note['id'], 'base_hash': note['content_hash']}
    context['transcript'] = {}
    assert invoke('generate', data)['error'] == 'note_client_upgrade_required'
    context['transcript'] = {'note_illustration_v1': True}
    assert invoke('generate', {**data, 'note_id': 'foreign'})['error'] == 'note_not_found'
    assert invoke('generate', {**data, 'base_hash': '0' * 64})['error'] == 'note_version_conflict'
    assert invoke('generate', {**data, 'user_id': 'other'})['error'] == 'contract_invalid'
    assert invoke('generate', {**data, 'anchor': '位置'})['error'] == 'illustration_brief_required'
    assert not events


@pytest.mark.parametrize('action', ['cancel', 'apply', 'undo'])
def test_control_is_bound_to_specific_run_and_note_version(workspace, action):
    note, _, events = workspace
    data = {'note_id': note['id'], 'base_hash': note['content_hash']}
    assert invoke(action, data)['error'] == 'contract_invalid'
    assert invoke(action, {**data, 'run_id': 'a' * 32})['success'] is True
    assert events[-1]['steps'][0]['illustration_run_id'] == 'a' * 32
    assert events[-1]['steps'][0]['original_content_hash'] == note['content_hash']


def test_travel_and_preference_are_typed_and_preserved(workspace):
    note, _, events = workspace
    result = json.loads(knowledge._app_capability_invoke_tool({'capability_id': 'knowledge.note.create', 'input': {'markdown': '我的真实游记', 'title': '杭州之旅', 'tags': ['大学生活'], 'layout': 'travel', 'automatic_illustrations': False}}))
    assert result['success'] is True
    step = events[-1]['steps'][0]
    assert step['layout'] == 'travel' and step['automatic_illustrations'] is False
    assert step['tags'] == ['大学生活'] and step['title'] == '杭州之旅'
    assert invoke('configure', {'note_id': note['id'], 'base_hash': note['content_hash'], 'enabled': False})['success'] is True
    assert events[-1]['summary'] == '关闭本篇自动配图'
    with pytest.raises(CapabilityContractError):
        note_presentation_fields({'kind': 'illustrate_note', 'illustration_action': 'cancel'})


def test_catalog_controls_are_confirmed_and_retry_reuses_generation_contract():
    for name in ['generate', 'cancel', 'apply', 'undo', 'configure']:
        cap = describe_capability('knowledge.note.illustration.' + name)
        assert cap['confirmation'] == cap['receipt'] == cap['idempotency'] == 'required'
    assert describe_capability('knowledge.note.illustration.status')['effect'] == 'read'
    step = note_capability_step('knowledge.note.illustration.generate', {'note_id': 'note-a', 'retry_run_id': 'a' * 32})
    assert step['illustration_action'] == 'retry'


def test_api_will_not_sign_new_steps_for_old_clients(monkeypatch):
    from backend.api.chat import _authorize_knowledge_action_event
    from backend.api import knowledge_actions
    monkeypatch.setattr(knowledge_actions, 'persist_knowledge_action_proposal', AsyncMock())
    event = {'action_id': 'action-123', 'steps': [{'kind': 'illustrate_note', 'target_note_id': 'note-a', 'illustration_action': 'generate', 'original_content_hash': 'a' * 64}]}
    with pytest.raises(ValueError, match='note_client_upgrade_required'):
        asyncio.run(_authorize_knowledge_action_event(event, payload={'tenant_key': 'a', 'user_id': 'u'}, session_id='s', request_id='request-1', policy_version='v1', client_context={}))


def test_latest_status_is_owner_scoped_and_does_not_claim_insertion(tmp_path, monkeypatch):
    from scripts.chat_run_store import DurableChatRunStore
    from scripts.hermes_bridge_runtime import note_illustrations as api
    store = DurableChatRunStore(tmp_path / 'runs.db')
    monkeypatch.setattr(api.session_runtime, '_chat_run_store', store)
    monkeypatch.setattr(api.persistence, '_require_internal_strict', lambda token: None)
    owner = store.tenant_user_hash('tenant', 'user')
    run, _ = store.create_or_get(tenant_user_hash=owner, session_id='note-illustration-note-a', request_id='request-123', execution_payload={'run_type': 'note_illustration'})
    result = asyncio.run(api.latest('note-a', 'internal', 'tenant', 'user'))
    assert result['run_id'] == run['run_id'] and result['insertion_status'] == 'device_owned'
    other = asyncio.run(api.latest('note-a', 'internal', 'tenant', 'other'))
    assert other['status'] == 'not_started' and 'run_id' not in other


def test_gateway_requires_device_snapshot_and_negotiates_new_fields(monkeypatch):
    from backend.services.capability_gateway import create_capability_proposal
    from backend.api import knowledge_actions
    proposal = AsyncMock(return_value={"status": "awaiting_user_confirmation"})
    monkeypatch.setattr(knowledge_actions, "propose_local_note_capability", proposal)
    async def run():
        kwargs = dict(payload={"tenant_key": "t", "user_id": "u"}, session_id="s", request_id="r", idempotency_key="r")
        data = {"note_id": "note-a", "base_hash": "a" * 64}
        missing = await create_capability_proposal("knowledge.note.illustration.generate", data, **kwargs)
        assert missing["error"] is not None
        proposal.assert_not_awaited()
        for renderer, expected in [("qcp-ios@1", False), ("qcp-ios-notes@1", True)]:
            await create_capability_proposal("knowledge.note.illustration.generate", data, **kwargs, local_notes=[], renderer_version=renderer)
            assert proposal.await_args.kwargs["note_illustration_v1"] is expected
    asyncio.run(run())
