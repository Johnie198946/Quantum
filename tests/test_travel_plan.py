from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.services.travel_plan import build_travel_plan, revise_travel_document, validate_travel_document

NOW = datetime(2030, 1, 2, 12, tzinfo=timezone.utc)


def document():
    return {
        "destination": "日本", "journal": "我的原文", "illustrations": [{"path": "private.jpg"}],
        "sources": [{"id": "official", "title": "旅馆官网", "url": "https://example.com"}],
        "stops": [{"id": "hotel", "name": "旅馆", "address": "已核实地址", "source_ids": ["official"]}],
        "actions": [
            {"id": "past", "day_id": "day-1", "title": "已入住", "kind": "hotel", "place_id": "hotel", "status": "completed", "actual_end": "2030-01-01T12:00:00+00:00"},
            {"id": "future", "day_id": "day-2", "title": "泡汤", "kind": "rest", "start": "2030-01-03T12:00:00+00:00", "end": "2030-01-03T14:00:00+00:00"},
        ],
    }


def test_future_revision_preserves_personal_writing_and_old_document():
    old = document()
    proposal = deepcopy(old)
    proposal["actions"][1]["title"] = "自由休息"
    proposal["journal"] = "AI 覆盖"
    proposal["illustrations"] = []
    updated = revise_travel_document(old, proposal, now=NOW)
    assert updated["actions"][1]["title"] == "自由休息"
    assert updated["journal"] == old["journal"]
    assert updated["illustrations"] == old["illustrations"]
    assert old["actions"][1]["title"] == "泡汤"


@pytest.mark.parametrize("field", ["title", "day_id", "details"])
def test_past_facts_cannot_be_changed(field):
    old = document()
    proposal = deepcopy(old)
    proposal["actions"][0][field] = "changed"
    with pytest.raises(ValueError, match="frozen"):
        revise_travel_document(old, proposal, now=NOW)


def test_indirect_past_place_and_evidence_changes_rejected():
    for collection, field in [("stops", "address"), ("sources", "url")]:
        old = document()
        proposal = deepcopy(old)
        proposal[collection][0][field] = "https://other.example" if field == "url" else "wrong"
        with pytest.raises(ValueError, match="indirectly"):
            revise_travel_document(old, proposal, now=NOW)


def test_elapsed_but_unconfirmed_plan_is_not_silently_rescheduled():
    old = document()
    old["actions"][1]["start"] = "2030-01-02T10:00:00+00:00"
    proposal = deepcopy(old)
    proposal["actions"][1]["start"] = "2030-01-03T10:00:00+00:00"
    with pytest.raises(ValueError, match="frozen"):
        revise_travel_document(old, proposal, now=NOW)


def test_locked_future_and_deleted_past_are_preserved():
    old = document()
    old["actions"][1]["locked"] = True
    proposal = deepcopy(old)
    proposal["actions"].pop(1)
    with pytest.raises(ValueError, match="frozen"):
        revise_travel_document(old, proposal, now=NOW)


def test_in_progress_only_remaining_time_can_change():
    old = document()
    old["actions"][1].update(status="in_progress", start="2030-01-02T11:00:00+00:00", actual_start="2030-01-02T11:15:00+00:00")
    proposal = deepcopy(old)
    proposal["actions"][1]["end"] = "2030-01-02T14:00:00+00:00"
    assert revise_travel_document(old, proposal, now=NOW)["actions"][1]["actual_start"] == "2030-01-02T11:15:00Z"
    proposal["actions"][1]["actual_start"] = "2030-01-02T11:30:00+00:00"
    with pytest.raises(ValueError, match="frozen"):
        revise_travel_document(old, proposal, now=NOW)


@pytest.mark.parametrize("start,end", [("2030-01-01T12:00:00", None), ("2030-01-01T12:00:00+09:00", "2030-01-01T11:00:00+09:00")])
def test_ambiguous_or_reversed_times_rejected(start, end):
    value = document()
    value["actions"][1].update(start=start, end=end)
    with pytest.raises(ValueError):
        validate_travel_document(value)


def test_cross_timezone_arrival_uses_actual_instant():
    value = document()
    value["actions"][1].update(start="2030-01-03T20:00:00+09:00", end="2030-01-03T08:00:00-08:00")
    assert validate_travel_document(value)


def test_missing_coordinates_remain_unknown_and_invalid_references_fail():
    value = document()
    assert validate_travel_document(value)["stops"][0]["latitude"] is None
    value["actions"][1]["place_id"] = "invented"
    with pytest.raises(ValueError, match="unknown travel place"):
        validate_travel_document(value)


def test_travel_uses_existing_dag_and_explicit_review_gate():
    workflow = SimpleNamespace(title="日本", description="安静温泉", requirements_snapshot={"scenario_id": "travel-planning"})
    plan = build_travel_plan(workflow, plan_id="p", knowledge_scope=[])
    assert plan["nodes"][1]["parameters"]["approval_gate"] == "itinerary"
    assert plan["nodes"][-1]["parameters"]["output_format"] == "travel_plan_v2"
    instruction = plan["nodes"][0]["parameters"]["instruction"]
    assert "云服务器的 Hermes 浏览器" in instruction
    assert "travelmode=transit" in instruction
    assert len(plan["edges"]) == 2


def test_cloud_browser_uses_service_proxy_and_writable_cache_without_affecting_desktop():
    from scripts.hermes_bridge import _configure_cloud_browser_environment
    desktop = {"PATH": "/usr/bin", "HTTPS_PROXY": "http://127.0.0.1:1234"}
    untouched = desktop.copy()
    _configure_cloud_browser_environment(desktop)
    assert desktop == untouched
    cloud = dict(desktop, AI_LAB_AGENT_OS_MODE="cloud_multi_tenant", HERMES_HOME="/srv/hermes")
    _configure_cloud_browser_environment(cloud)
    assert cloud["AGENT_BROWSER_PROXY"] == desktop["HTTPS_PROXY"]
    assert cloud["AGENT_BROWSER_EXECUTABLE_PATH"] == "/srv/hermes/browser-runtime/chrome"
    assert cloud["AGENT_BROWSER_SOCKET_DIR"] == "/srv/hermes/cache/browser-sockets"
    assert cloud["PATH"].split(":")[:2] == ["/srv/hermes/browser-runtime/node_modules/.bin", "/srv/hermes/node/bin"]
    cloud["AGENT_BROWSER_PROXY"] = "http://127.0.0.1:4321"
    _configure_cloud_browser_environment(cloud)
    assert cloud["AGENT_BROWSER_PROXY"] == "http://127.0.0.1:4321"


def test_bridge_and_storage_keep_travel_contract():
    from backend.services.workflow_executor import artifact_storage_contract
    from scripts.hermes_bridge import _workflow_artifact_contract
    contract = _workflow_artifact_contract({"parameters": {"output_format": "travel_plan_v2"}})
    node = SimpleNamespace(node_id="travel", agent_id="main_agent", model_used="m", provider_used="p", attempt=1)
    extension, metadata = artifact_storage_contract(contract, event_id="e", node=node)
    assert extension == "json"
    assert metadata["render_type"] == "travel_plan_v2"


def test_travel_revision_api_keeps_versions_and_enforces_owner_and_cas(tmp_path, monkeypatch):
    import asyncio
    import json
    from test_workflows_api import TestWorkflowsAPI
    from backend.db import SessionLocal
    from backend.models.workflow import WorkflowExecution, WorkflowPlanVersion, WorkflowNodeRun
    from backend.services.workflow_artifacts import store_artifact
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    harness = TestWorkflowsAPI()
    harness.setUp()
    try:
        created = harness.request("POST", "/api/v1/workflows", json={"title": "日本", "description": "安静的温泉旅行", "output_kind": "travel"})
        assert created.status_code == 201, created.text
        workflow_id = created.json()["workflow"]["id"]
        assert created.json()["workflow"]["requirements_snapshot"]["scenario_id"] == "travel-planning"

        async def seed():
            async with SessionLocal() as db:
                plan = WorkflowPlanVersion(id="travel-plan", workflow_id=workflow_id, version=1, dsl={}, goal="trip", deliverable="travel")
                db.add(plan)
                await db.flush()
                execution = WorkflowExecution(id="travel-execution", workflow_id=workflow_id, plan_id=plan.id, tenant_key="tenant-alpha", status="completed", idempotency_key="travel-seed")
                db.add(execution)
                await db.flush()
                db.add(WorkflowNodeRun(id="travel-node", execution_id=execution.id, node_id="travel_itinerary", node_type="LLM_INFERENCE", name="行程", status="succeeded", position=0))
                artifact = store_artifact(execution, node_run_id=None, kind="output", title="日本", content=json.dumps(document()), extension="json", metadata={"render_type": "travel_plan_v2"})
                db.add(artifact)
                await db.commit()
                return artifact.id, artifact.content_hash
        artifact_id, digest = asyncio.run(seed())
        path = "/api/v1/workflow-executions/travel-execution/travel-revisions"
        proposed = document()
        proposed["actions"][1]["title"] = "休息"
        body = {"artifact_id": artifact_id, "expected_hash": digest, "request_id": "travel-edit-001", "reason": "少一点安排", "proposed": proposed}
        forbidden = harness.request("POST", path, sub="beta", json=body)
        assert forbidden.status_code == 404
        forbidden = harness.request("POST", path, sub="gamma", json=body)
        assert forbidden.status_code == 404
        response = harness.request("POST", path, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["metadata"]["parent_artifact_id"] == artifact_id
        assert harness.request("POST", path, json=body).json()["id"] == response.json()["id"]
        body["request_id"] = "travel-edit-002"
        assert harness.request("POST", path, json=body).status_code == 409
        old = harness.request("GET", f"/api/v1/workflow-executions/travel-execution/artifacts/{artifact_id}/content")
        assert old.status_code == 200, old.text
        assert json.loads(old.json()["content"])["actions"][1]["title"] == "泡汤"
        baseline_history = validate_travel_document(json.loads(old.json()["content"]))["actions"][0]
        saved_versions = [(artifact_id, old.json()["content"])]
        for turn in range(10):
            current = response.json()
            loaded = harness.request("GET", f"/api/v1/workflow-executions/travel-execution/artifacts/{current['id']}/content")
            assert loaded.status_code == 200, loaded.text
            saved_versions.append((current["id"], loaded.json()["content"]))
            proposal = json.loads(loaded.json()["content"])
            proposal["actions"][1]["details"] = f"第 {turn + 1} 次调整：保留休息，减少移动"
            proposal["journal"] = "模型不应覆盖原文"
            request = {"artifact_id": current["id"], "expected_hash": current["content_hash"],
                       "request_id": f"travel-round-{turn:03}", "reason": f"用户第 {turn + 1} 轮意见", "proposed": proposal}
            response = harness.request("POST", path, json=request)
            assert response.status_code == 200, response.text
            # Simulate loss of the response and a fresh HTTP request on reconnect.
            assert harness.request("POST", path, json=request).json()["id"] == response.json()["id"]
            stale = {**request, "request_id": f"stale-round-{turn:03}"}
            assert harness.request("POST", path, json=stale).status_code == 409
            fresh = harness.request("GET", f"/api/v1/workflow-executions/travel-execution/artifacts/{response.json()['id']}/content")
            latest_document = json.loads(fresh.json()["content"])
            assert latest_document["journal"] == "我的原文"
            assert latest_document["actions"][0] == baseline_history
        for version_id, original_content in saved_versions:
            persisted = harness.request("GET", f"/api/v1/workflow-executions/travel-execution/artifacts/{version_id}/content")
            assert persisted.json()["content"] == original_content
            assert harness.request("GET", f"/api/v1/workflow-executions/travel-execution/artifacts/{version_id}/content", sub="gamma").status_code == 404
        delay = {"artifact_id": response.json()["id"], "expected_hash": response.json()["content_hash"],
                 "request_id": "travel-delay-001", "reason": "尚未开始，延后", "action_id": "future", "progress": "delayed"}
        response = harness.request("POST", path, json=delay)
        assert response.status_code == 200, response.text
        delayed = harness.request("GET", f"/api/v1/workflow-executions/travel-execution/artifacts/{response.json()['id']}/content")
        delayed_action = json.loads(delayed.json()["content"])["actions"][1]
        assert delayed_action["status"] == "delayed"
        assert delayed_action["actual_start"] is None and delayed_action["actual_end"] is None
        from unittest.mock import AsyncMock
        from backend.api import workflows as api
        remote = AsyncMock(side_effect=RuntimeError("offline"))
        monkeypatch.setattr(api, "retry_remote", remote)
        revision_path = "/api/v1/workflow-executions/travel-execution/request-revision"
        revision = {"node_id": "travel_itinerary", "comment": "下午休息，晚餐保留",
                    "artifact_id": response.json()["id"], "expected_hash": response.json()["content_hash"]}
        assert harness.request("POST", revision_path, json={**revision, "expected_hash": "0" * 64}).status_code == 409
        assert harness.request("POST", revision_path, json=revision).status_code == 503
        state = harness.request("GET", "/api/v1/workflow-executions/travel-execution")
        assert state.json()["status"] == "completed"
        remote.side_effect = None
        replanned = harness.request("POST", revision_path, json=revision)
        assert replanned.status_code == 200, replanned.text
        assert replanned.json()["status"] == "queued"
        baseline = remote.call_args.kwargs["travel_baseline"]
        assert baseline["document"]["actions"][0]["status"] == "completed"
        assert baseline["revision"] == 12
        assert harness.request("POST", revision_path, json=revision).status_code == 409
        # A lost response remains recoverable after a later replan has started.
        replay = harness.request("POST", path, json=delay)
        assert replay.status_code == 200, replay.text
        assert replay.json()["id"] == response.json()["id"]
        assert harness.request("POST", path, json={**delay, "reason": "different"}).status_code == 409
    finally:
        harness.tearDown()


def test_invalid_timezone_and_indirect_ongoing_place_rejected():
    value = document()
    value['actions'][1]['timezone'] = 'Invented/Zone'
    with pytest.raises(ValueError, match='timezone'):
        validate_travel_document(value)
    old = document()
    old['actions'][1].update(status='in_progress', place_id='hotel', actual_start='2030-01-02T11:00:00Z')
    proposal = deepcopy(old)
    proposal['stops'][0]['address'] = 'Changed'
    with pytest.raises(ValueError):
        revise_travel_document(old, proposal, now=NOW)


def test_travel_prompt_keeps_full_upstream_and_frozen_baseline():
    import json
    from scripts.hermes_bridge_runtime.workflow_artifacts import _workflow_node_prompt
    workflow = SimpleNamespace(title='日本', description='安静', requirements_snapshot={'scenario_id': 'travel-planning'})
    plan = build_travel_plan(workflow, plan_id='p', knowledge_scope=[])
    evidence = '证据' * 3000 + '末尾关键地址'
    run = {'plan': plan, 'nodes': {'travel_research': {'status': 'succeeded', 'output': evidence}},
           'travel_baseline': {'document': document()}, 'agent_config': {}, 'goal': 'test'}
    prompt = _workflow_node_prompt(run, plan['nodes'][1])
    assert '末尾关键地址' in prompt
    assert '我的原文' in prompt
    assert '已入住' in prompt


def test_photo_evidence_requires_existing_sources_and_safe_url_scheme():
    value = document()
    value['photo_references'] = [{'id': 'p', 'place_id': 'hotel', 'source_id': 'official', 'caption': '网络参考', 'image_url': 'file:///etc/passwd'}]
    with pytest.raises(ValueError):
        validate_travel_document(value)
    value['photo_references'][0]['image_url'] = 'https://example.com/photo.jpg'
    assert validate_travel_document(value)['photo_references'][0]['source_id'] == 'official'
    value['photo_references'][0]['source_id'] = 'invented'
    with pytest.raises(ValueError, match='photo'):
        validate_travel_document(value)


def test_replanning_cannot_fabricate_or_erase_booking_facts():
    old = document()
    old['actions'][1]['booking_reference'] = 'confirmed-123'
    proposed = deepcopy(old)
    proposed['actions'][1]['booking_reference'] = ''
    with pytest.raises(ValueError, match='booking'):
        revise_travel_document(old, proposed, now=NOW)
    proposed = deepcopy(old)
    proposed['actions'].pop()
    with pytest.raises(ValueError, match='booked'):
        revise_travel_document(old, proposed, now=NOW)


def test_travel_budget_and_browser_fallback_reuse_authorized_runtime():
    from scripts import hermes_bridge as bridge
    node = {"node_type": "KNOWLEDGE_RETRIEVAL", "parameters": {"scenario_id": "travel-planning", "allow_network": True}}
    config = bridge.TrustedAgentConfig(allowed_tools=["web_search", "browser_navigate"], allow_network=True)
    assert bridge._workflow_toolsets(node, config) == ["web", "browser"]
    config.allow_network = False
    assert bridge._workflow_toolsets(node, config) == ["__workflow_no_tools__"]
    node["parameters"].update(output_format="travel_plan_v2", max_tokens=10000)
    assert bridge._workflow_turn_token_cap(node) == 10000


def test_only_explicit_user_confirmation_can_update_future_booking():
    old = document()
    proposed = deepcopy(old)
    proposed["actions"][1]["booking_reference"] = "HOTEL-123"
    with pytest.raises(ValueError, match="booking facts"):
        revise_travel_document(old, proposed, now=NOW)
    updated = revise_travel_document(old, proposed, now=NOW, confirmed_bookings={"future": "HOTEL-123"})
    assert updated["actions"][1]["booking_reference"] == "HOTEL-123"
    assert old["actions"][1].get("booking_reference", "") == ""
    proposed = deepcopy(old)
    proposed["actions"][0]["booking_reference"] = "REWRITE-PAST"
    with pytest.raises(ValueError, match="only future"):
        revise_travel_document(old, proposed, now=NOW, confirmed_bookings={"past": "REWRITE-PAST"})


def test_travel_prompt_rejects_oversize_instead_of_losing_history():
    from scripts.hermes_bridge_runtime.workflow_artifacts import _workflow_node_prompt
    workflow = SimpleNamespace(title="trip", description="quiet", requirements_snapshot={"scenario_id": "travel-planning"})
    plan = build_travel_plan(workflow, plan_id="p", knowledge_scope=[])
    run = {"plan": plan, "nodes": {}, "agent_config": {}, "goal": "x" * 100000}
    with pytest.raises(RuntimeError, match="禁止静默截断"):
        _workflow_node_prompt(run, plan["nodes"][1])


def test_invalid_model_schema_enters_existing_bounded_repair_loop():
    import json
    from scripts.hermes_bridge_runtime.workflow_artifacts import _workflow_output_incomplete
    node = {"node_type": "LLM_INFERENCE", "parameters": {"output_format": "travel_plan_v2"}}
    assert _workflow_output_incomplete(node, '{"destination":"日本","style":["quiet"]}')
    assert not _workflow_output_incomplete(node, json.dumps(document()))


def test_user_recorded_delay_can_reschedule_without_fabricating_actual_departure():
    old = document()
    old["actions"][1].update(status="delayed", start="2030-01-02T10:00:00Z")
    proposed = deepcopy(old)
    proposed["actions"][1]["start"] = "2030-01-02T16:00:00Z"
    result = revise_travel_document(old, proposed, now=NOW)
    assert result["actions"][1]["actual_start"] is None
    assert result["actions"][1]["status"] == "delayed"
    assert result["actions"][0]["status"] == "completed"


def test_multiple_attachments_cross_bridge_validation_and_reach_research():
    from scripts.hermes_bridge_runtime.contracts import WorkflowRunRequest
    from scripts.hermes_bridge_runtime.workflow_artifacts import _workflow_node_prompt
    workflow = SimpleNamespace(title="旅行", description="安静", requirements_snapshot={"scenario_id": "travel-planning"})
    plan = build_travel_plan(workflow, plan_id="test", knowledge_scope=[])
    attachments = [{"source_id": "doc_" + char * 32, "source_revision": 1,
                    "content_hash": char * 64, "filename": name, "text": text}
                   for char, name, text in [("a", "flight.pdf", "原始航班：用户提供"), ("b", "hotel.docx", "旅馆地址：用户提供")]]
    body = dict(tenant_id="test", execution_id="test-run", idempotency_key="test-request",
                goal="旅行", deliverable="旅行笔记", plan=plan,
                knowledge_capability="x" * 30, knowledge_policy_version="test-policy",
                agent_config={"id": "main_agent"}, source_documents=attachments)
    request = WorkflowRunRequest.model_validate(body)
    run = request.model_dump()
    run["nodes"] = {}
    prompt = _workflow_node_prompt(run, plan["nodes"][0])
    assert all(item["text"] in prompt and item["source_id"] in prompt for item in attachments)
    assert run["source_documents"] == attachments
    itinerary_prompt = _workflow_node_prompt(run, plan["nodes"][1])
    assert all(item["text"] in itinerary_prompt for item in attachments)
    broken = deepcopy(body)
    broken["source_documents"][0].pop("source_id")
    with pytest.raises(ValueError):
        WorkflowRunRequest.model_validate(broken)
    oversized = deepcopy(body)
    for item in oversized["source_documents"]:
        item["text"] = "x" * 41000
    with pytest.raises(ValueError, match="80000"):
        WorkflowRunRequest.model_validate(oversized)


def test_recorded_real_bridge_events_project_into_owner_readable_artifacts(tmp_path, monkeypatch):
    import asyncio
    import json
    from pathlib import Path
    from test_workflows_api import TestWorkflowsAPI
    from backend.db import SessionLocal
    from backend.models.workflow import WorkflowExecution, WorkflowPlanVersion, WorkflowNodeRun
    from backend.services.workflow_executor import project_event
    fixture = json.loads((Path(__file__).parents[1] / "ops/acceptance/receipts/travel-notes-20260927/real-bridge-events.json").read_text())
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    harness = TestWorkflowsAPI()
    harness.setUp()
    try:
        created = harness.request("POST", "/api/v1/workflows", json={"title": "真实事件验收", "description": "检查旅行成果回读", "output_kind": "travel"})
        assert created.status_code == 201, created.text
        workflow_id = created.json()["workflow"]["id"]
        async def project():
            async with SessionLocal() as db:
                plan = WorkflowPlanVersion(id="real-travel-plan", workflow_id=workflow_id, version=1, dsl={}, goal="trip", deliverable="travel")
                db.add(plan)
                await db.flush()
                execution = WorkflowExecution(id="real-travel-execution", workflow_id=workflow_id, plan_id=plan.id, tenant_key="tenant-alpha", status="queued", idempotency_key="real-travel-fixture")
                db.add(execution)
                await db.flush()
                nodes = {}
                for index, source in enumerate(fixture["nodes"]):
                    row = WorkflowNodeRun(id="recorded-"+source["id"], execution_id=execution.id, node_id=source["id"], node_type=source["node_type"], name=source["name"], status="pending", position=index)
                    nodes[source["id"]] = row
                    db.add(row)
                await db.flush()
                for event in fixture["events"]:
                    await project_event(db, execution, nodes, event)
                    await db.flush()
                assert execution.status == "awaiting_review"
                assert all(row.status == "succeeded" for row in nodes.values())
                await db.commit()
        asyncio.run(project())
        path = "/api/v1/workflow-executions/real-travel-execution/artifacts"
        response = harness.request("GET", path)
        assert response.status_code == 200, response.text
        artifacts = response.json()
        assert len(artifacts) == 3
        for artifact in artifacts:
            read = harness.request("GET", path+"/"+artifact["id"]+"/content")
            assert read.status_code == 200, read.text
            if artifact["metadata"].get("render_type") == "travel_plan_v2":
                validate_travel_document(json.loads(read.json()["content"]))
            assert harness.request("GET", path+"/"+artifact["id"]+"/content", sub="gamma").status_code == 404
    finally:
        harness.tearDown()


def test_first_workflow_registers_session_without_cross_owner_claim(tmp_path, monkeypatch):
    from test_workflows_api import TestWorkflowsAPI
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    harness = TestWorkflowsAPI()
    harness.setUp()
    try:
        body = {"title": "首次旅行", "description": "安静温泉", "output_kind": "travel", "source_client_session_id": "first-travel-owner-session"}
        first = harness.request("POST", "/api/v1/workflows", json=body)
        assert first.status_code == 201, first.text
        assert first.json()["workflow"]["source_client_session_id"] == body["source_client_session_id"]
        again = harness.request("POST", "/api/v1/workflows", json=body)
        assert again.status_code == 201, again.text
        other = harness.request("POST", "/api/v1/workflows", sub="gamma", json=body)
        assert other.status_code == 409, other.text
    finally:
        harness.tearDown()
