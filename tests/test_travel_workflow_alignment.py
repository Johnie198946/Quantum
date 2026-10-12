"""Travel UI contract regressions against the real workflow API and worker helpers."""
from contextlib import contextmanager
from copy import deepcopy
import asyncio
import pytest


@contextmanager
def api_harness():
    from test_workflows_api import TestWorkflowsAPI
    harness = TestWorkflowsAPI(); harness.setUp()
    try:
        yield harness
    finally:
        harness.tearDown()


def test_creation_replay_is_owned_and_body_bound():
    with api_harness() as h:
        body = {"title": "青森", "description": "青森旅行，日期与航班未定", "output_kind": "travel", "request_id": "travel-create-replay-001"}
        first = h.request("POST", "/api/v1/workflows", json=body)
        assert first.status_code == 201, first.text
        again = h.request("POST", "/api/v1/workflows", json=body)
        assert again.status_code == 201 and again.json()["workflow"]["id"] == first.json()["workflow"]["id"]
        assert h.request("POST", "/api/v1/workflows", json={**body, "description": "同一请求偷偷改变目的地"}).status_code == 409
        for owner in ("beta", "gamma"):
            other = h.request("POST", "/api/v1/workflows", sub=owner, json=body)
            assert other.status_code == 201 and other.json()["workflow"]["id"] != first.json()["workflow"]["id"]


def test_start_rejects_stale_plan_hash_and_activation_revision():
    with api_harness() as h:
        ready = h.create_ready(); wid = ready["id"]; plan = ready["plan"]
        assert h.request("POST", f"/api/v1/workflows/{wid}/approve-plan", json={"comment": "确认"}).status_code == 201
        body = {"request_id": "travel-start-bound-001", "expected_hash": plan["content_hash"], "expected_revision": plan["activation_revision"]}
        path = f"/api/v1/workflows/{wid}/start"
        assert h.request("POST", path, json={**body, "expected_hash": "0" * 64}).status_code == 409
        assert h.request("POST", path, json={**body, "expected_revision": body["expected_revision"] + 1}).status_code == 409
        first = h.request("POST", path, json=body)
        assert first.status_code == 201, first.text
        assert h.request("POST", path, json=body).json()["id"] == first.json()["id"]


def test_transport_replan_updates_all_node_queries_and_requires_new_confirmation():
    from backend.db import SessionLocal
    from backend.models.workflow import WorkflowDefinition
    from backend.services.workflow_planning import process_next_once
    with api_harness() as h:
        ready = h.create_ready(); wid = ready["id"]
        async def mark_travel():
            async with SessionLocal() as db:
                workflow = await db.get(WorkflowDefinition, wid)
                workflow.requirements_snapshot = {**workflow.requirements_snapshot, "output_kind": "travel", "scenario_id": "travel-planning"}
                await db.commit()
        asyncio.run(mark_travel())
        description = "青森五天，两人。用户录入已有订单 ABC-123；抵达日期2026-11-01。日期以这次输入为准。"
        path = f"/api/v1/workflows/{wid}/replan"
        assert h.request("POST", path, sub="gamma", json={"description": description}).status_code == 404
        response = h.request("POST", path, json={"instruction": "交通条件更新", "description": description})
        assert response.status_code == 200, response.text
        assert h.request("GET", f"/api/v1/workflows/{wid}").json()["description"] == description
        asyncio.run(process_next_once())
        plan = h.request("GET", f"/api/v1/workflows/{wid}/plan").json()
        assert all(node["parameters"]["query"] == description for node in plan["dsl"]["nodes"])
        assert h.request("POST", f"/api/v1/workflows/{wid}/start", json={"request_id": "unconfirmed-travel-start"}).status_code == 409
        assert h.request("POST", f"/api/v1/workflows/{wid}/approve-plan", json={"comment": "确认新条件"}).status_code == 201
        assert h.request("POST", f"/api/v1/workflows/{wid}/start", json={"request_id": "confirmed-travel-start"}).status_code == 201
        assert h.request("POST", path, json={"instruction": "再修改", "description": description + "修改"}).status_code == 409


def test_generic_replan_cannot_replace_description_with_travel_context():
    with api_harness() as h:
        ready = h.create_ready()
        assert h.request("POST", f"/api/v1/workflows/{ready['id']}/replan", json={"description": "不属于旅行的完整条件"}).status_code == 422


def test_final_notebook_preserves_every_approved_fact_and_personal_field():
    from backend.services.travel_plan import finalize_travel_notebook
    from test_travel_client_state import baseline
    approved = {**baseline(), "companions": 2, "budget": "8000 CNY", "date_range": "未定", "style": "轻松", "days": [{"id": "day-1", "title": "原来的标题"}], "practical_guidance": [{"category": "transport", "title": "原资料", "details": "出发日期尚未确定，需要在实际出发前核对最新的当地交通资料。", "next_step": "核对实际日期"}], "budget_breakdown": [{"category": "stay", "value": "用户确认估算", "note": "用户自己的估算"}], "client_state": {"version": 1, "entries": {"day-1": "自己的原话"}}}
    from backend.services.travel_plan import validate_travel_document
    approved = validate_travel_document(approved)
    written = {**deepcopy(approved), "destination": "另一个城市", "companions": 99, "budget": "免费", "date_range": "明天", "style": "极限", "days": [], "practical_guidance": [], "budget_breakdown": [], "client_state": {}, "journal": "新的摄影参考", "open_questions": ["核对开放日期"]}
    result = finalize_travel_notebook(approved, written)
    for key, value in approved.items():
        if key not in {"actions", "open_questions"}:
            assert result[key] == value
    assert result["actions"][0]["status"] == "completed"
    assert result["notebook_supplement"] == "新的摄影参考"
    assert result["open_questions"] == ["核对开放日期"]
