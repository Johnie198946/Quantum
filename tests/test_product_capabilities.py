from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib
import json
import queue
import sys
import threading
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import httpx
import jwt

from backend.services.capability_catalog import (
    CapabilityContractError,
    describe_capability,
    invoke_capability,
    load_catalog,
    search_capabilities,
    validate_catalog,
)
from scripts import hermes_bridge as bridge


def test_catalog_is_complete_unique_and_progressively_disclosed():
    catalog = load_catalog()
    assert len(catalog["capabilities"]) == 20
    result = search_capabilities("knowledge note", limit=3)
    assert result and "input_schema" not in result[0]
    described = describe_capability(result[0]["id"])
    assert described and described["input_schema"]["type"] == "object"
    broken = copy.deepcopy(catalog)
    broken["capabilities"][1]["id"] = broken["capabilities"][0]["id"]
    with pytest.raises(CapabilityContractError, match="duplicate capability"):
        validate_catalog(broken)
    unsafe = copy.deepcopy(catalog)
    unsafe["capabilities"][2]["receipt"] = "none"
    with pytest.raises(CapabilityContractError, match="unsafe mutation"):
        validate_catalog(unsafe)
    bad_refs = copy.deepcopy(catalog)
    bad_refs["consumptions"][0]["gates"] *= 2
    with pytest.raises(CapabilityContractError, match="invalid consumption references"):
        validate_catalog(bad_refs)
    bad_event = copy.deepcopy(catalog)
    bad_event["events"][1]["id"] = bad_event["events"][0]["id"]
    with pytest.raises(CapabilityContractError, match="duplicate event"):
        validate_catalog(bad_event)
    bad_fallback = copy.deepcopy(catalog)
    bad_fallback["renderers"][0]["fallback"] = "missing"
    with pytest.raises(CapabilityContractError, match="invalid renderer fallback"):
        validate_catalog(bad_fallback)


def test_capability_yaml_keys_match_declared_repository_schema():
    schema = json.loads(
        Path("backend/contracts/product-capabilities/capability.schema.json").read_text()
    )
    allowed = set(schema["properties"])
    required = set(schema["required"])
    for capability in load_catalog()["capabilities"]:
        assert required <= set(capability), capability["id"]
        assert not set(capability) - allowed, capability["id"]


@pytest.mark.asyncio
async def test_capability_api_requires_auth_and_rejects_authority_in_input():
    from backend.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/v1/capabilities?query=knowledge")).status_code == 401
        assert (await client.get("/api/v1/capabilities/workflow.create")).status_code == 401
        token = jwt.encode(
            {"sub": "qcp-user", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "test-secret", algorithm="HS256",
        )
        headers = {"Authorization": f"Bearer {token}"}
        found = await client.get("/api/v1/capabilities?query=knowledge", headers=headers)
        assert found.status_code == 200
        response = await client.post("/api/v1/capabilities/invoke", headers=headers, json={
            "capability_id": "knowledge.note.search",
            "input": {"query": "x", "tenant_key": "attacker"},
        })
    assert response.status_code == 200
    assert response.json()["error"]["code"] == "contract_invalid"


@pytest.mark.asyncio
async def test_capability_api_maps_domain_dto_validation_to_contract_failure():
    from backend.main import app

    token = jwt.encode(
        {"sub": "qcp-user", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "test-secret", algorithm="HS256",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        pcm_response = await client.post(
            "/api/v1/capabilities/invoke",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "capability_id": "workflow.create",
                "input": {"title": "x" * 161, "description": "valid description"},
                "confirmed": True,
                "idempotency_key": "dto-validation",
            },
        )
        with patch("backend.services.capability_catalog.validate_instance"):
            dto_response = await client.post(
                "/api/v1/capabilities/invoke",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "capability_id": "workflow.create",
                    "input": {"title": "x" * 161, "description": "valid description"},
                    "confirmed": True,
                    "idempotency_key": "dto-validation-catch",
                },
            )

    assert pcm_response.status_code == dto_response.status_code == 200
    assert pcm_response.json()["error"] == {
        "code": "contract_invalid", "message": "input.title: too long",
    }
    assert dto_response.json()["error"] == {
        "code": "contract_invalid", "message": "Domain input validation failed",
    }


@pytest.mark.asyncio
async def test_invoke_rejects_authority_fields_and_missing_confirmation():
    payload = {"tenant_key": "tenant-a", "user_id": "user-a"}
    injected = await invoke_capability(
        "knowledge.note.search", {"query": "x", "tenant_key": "other"},
        payload=payload, confirmed=False, idempotency_key=None,
    )
    assert injected["error"]["code"] == "contract_invalid"
    unconfirmed = await invoke_capability(
        "knowledge.note.create", {"markdown": "# safe"}, payload=payload,
        confirmed=False, idempotency_key="request-123",
    )
    assert unconfirmed["error"]["code"] == "contract_invalid"


@pytest.mark.asyncio
async def test_text_to_presentation_uses_governed_defaults_and_delivery_contract():
    created = {
        "workflow": {"id": "wf-text", "status": "clarifying"},
        "clarification_session": {
            "id": "wfs-text", "phase": "awaiting_requirement_confirmation"
        },
    }
    with patch(
        "backend.capability_handlers._create_workflow", new=AsyncMock(return_value=created)
    ) as create:
        result = await invoke_capability(
            "presentation.create_from_text",
            {"title": "因特拉肯旅行攻略", "text_material": "湖泊、雪山与少女峰路线"},
            payload={"tenant_key": "tenant-a", "user_id": "user-a"},
            confirmed=True,
            idempotency_key="interlaken-deck-1",
        )

    assert result["status"] == "completed"
    assert result["events"][0]["type"] == "presentation.created"
    payload = result["events"][0]["payload"]
    assert payload["delivery"]["artifact_extension"] == "pptx"
    assert payload["delivery"]["preview_extension"] == "pdf"
    assert create.await_args is not None
    body = create.await_args.args[0]
    call_options = create.await_args.kwargs
    assert call_options["requirements_explicit"] is True
    assert call_options["requirements_snapshot_overrides"]["text_material"] == "湖泊、雪山与少女峰路线"
    assert call_options["requirements_snapshot_overrides"]["artifact_contract"]["extension"] == "pptx"
    assert body.output_kind == "presentation"
    assert "management_briefing" in body.description
    assert "clean_professional_16_9" in body.description
    assert "湖泊、雪山与少女峰路线" not in body.description
    assert "私有需求快照" in body.description
    from backend.api.workflows import requirement_is_explicit
    assert requirement_is_explicit(body.description)

    with patch(
        "backend.capability_handlers._create_workflow", new=AsyncMock(return_value=created)
    ) as clarify_create:
        await invoke_capability(
            "presentation.create_from_text",
            {
                "title": "因特拉肯旅行攻略",
                "text_material": "湖泊、雪山与少女峰路线",
                "clarification_strategy": "ask_before_planning",
            },
            payload={"tenant_key": "tenant-a", "user_id": "user-a"},
            confirmed=True,
            idempotency_key="interlaken-deck-ask",
        )
    assert clarify_create.await_args is not None
    assert clarify_create.await_args.kwargs["requirements_explicit"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("capability_id", "focus_field", "document_kind", "citation_style"),
    [
        ("document.word.create_from_text", None, "word", "none"),
        ("report.research.create_from_text", "research_question", "research_report", "apa7"),
        ("paper.academic.create_from_text", "thesis", "academic_paper", "apa7"),
    ],
)
async def test_first_class_document_capabilities_bind_format_evidence_and_review_contracts(
    capability_id, focus_field, document_kind, citation_style
):
    created = {
        "workflow": {"id": "wf-doc", "status": "clarifying"},
        "clarification_session": {
            "id": "wfs-doc", "phase": "awaiting_requirement_confirmation"
        },
    }
    text_material = "V" * 32_000 if document_kind == "word" else "Verified source material"
    data = {
        "title": "Governed document",
        "text_material": text_material,
        "source_client_session_id": "chat-session-a",
    }
    if focus_field:
        data[focus_field] = "What does the evidence support?"
    with patch(
        "backend.capability_handlers._create_workflow", new=AsyncMock(return_value=created)
    ) as create:
        result = await invoke_capability(
            capability_id,
            data,
            payload={"tenant_key": "tenant-a", "user_id": "user-a"},
            confirmed=True,
            idempotency_key=f"{document_kind}-1",
        )

    assert result["status"] == "completed"
    assert result["events"][0]["type"] == "document.created"
    assert result["events"][0]["payload"]["delivery"]["artifact_extension"] == "docx"
    body = create.await_args.args[0]
    options = create.await_args.kwargs
    profile = options["requirements_snapshot_overrides"]["document_profile"]
    artifact = options["requirements_snapshot_overrides"]["artifact_contract"]
    assert body.output_kind == "document"
    assert profile["kind"] == document_kind
    assert profile["citation_style"] == citation_style
    assert profile["review_gates"] == ["outline", "content", "final_output"]
    assert artifact["extension"] == "docx"
    assert artifact["version"] == artifact["content_hash"] == "required"
    assert options["requirements_snapshot_overrides"]["text_material"] == text_material
    assert options["requirements_snapshot_overrides"]["source_client_session_id"] == "chat-session-a"
    assert text_material not in body.description


def test_workflow_creation_capabilities_accept_bounded_client_session_provenance():
    catalog = {item["id"]: item for item in load_catalog()["capabilities"]}
    for capability_id in (
        "workflow.create",
        "presentation.create_from_document",
        "presentation.create_from_text",
        "document.word.create_from_text",
        "report.research.create_from_text",
        "paper.academic.create_from_text",
    ):
        field = catalog[capability_id]["input_schema"]["properties"][
            "source_client_session_id"
        ]
        assert field == {
            "type": "string",
            "minLength": 1,
            "maxLength": 100,
            "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$",
        }
        assert "source_client_session_id" not in catalog[capability_id]["input_schema"][
            "required"
        ]


def test_bridge_mutations_only_emit_identity_free_confirmation_proposals():
    events = []
    bridge._client_context_tool_context.value = {"emit": events.append}
    try:
        created = json.loads(bridge._app_capability_invoke_tool({
            "capability_id": "workflow.create",
            "input": {"title": "QCP workflow", "description": "valid workflow description"},
        }))
        started = json.loads(bridge._app_capability_invoke_tool({
            "capability_id": "workflow.start", "input": {"workflow_id": "wf-1"},
        }))
        presentation = json.loads(bridge._app_capability_invoke_tool({
            "capability_id": "presentation.create_from_document",
            "input": {
                "source_document_id": "source-document-1",
                "title": "QCP deck", "description": "turn source into a deck",
            },
        }))
    finally:
        bridge._client_context_tool_context.value = None
    assert {created["status"], started["status"], presentation["status"]} == {
        "awaiting_confirmation"
    }
    assert all(item["receipt"] is None for item in (created, started, presentation))
    assert [event["type"] for event in events] == ["capability.proposed"] * 3
    serialized = json.dumps(events)
    assert not {"tenant_key", "user_id", "confirmed", "idempotency_key"} & set(
        key for event in events for key in event["payload"]
    )
    assert "tenant_key" not in serialized and "user_id" not in serialized


def test_bridge_knowledge_mutations_preserve_caller_cas_versions():
    stale_target = "a" * 64
    stale_source = "b" * 64
    events = []
    bridge._client_context_tool_context.value = {
        "knowledge_action_v1": True,
        "request_id": "request-cas-regression",
        "emit": events.append,
        "inline_notes": [
            {"id": "target", "content_hash": "c" * 64},
            {"id": "source", "content_hash": "d" * 64},
        ],
    }
    try:
        for capability_id, data in (
            ("knowledge.note.update", {
                "note_id": "target", "markdown": "# revised", "base_hash": stale_target,
            }),
            ("knowledge.note.archive", {"note_id": "target", "base_hash": stale_target}),
            ("knowledge.note.merge", {
                "target_note_id": "target", "target_base_hash": stale_target,
                "source_versions": {"source": stale_source},
                "revised_content": "# merged",
            }),
        ):
            assert json.loads(bridge._app_capability_invoke_tool({
                "capability_id": capability_id, "input": data,
            }))["success"] is True
    finally:
        bridge._client_context_tool_context.value = None

    update, archive, merge = (event["steps"][0] for event in events)
    assert update["original_content_hash"] == stale_target
    assert archive["original_content_hash"] == stale_target
    assert merge["original_content_hash"] == stale_target
    assert merge["source_content_hashes"] == {"source": stale_source}


def test_bridge_reads_require_trusted_context_and_fail_closed():
    bridge._client_context_tool_context.value = None
    denied = json.loads(bridge._app_capability_invoke_tool({
        "capability_id": "workflow.open", "input": {"workflow_id": "wf-1"},
    }))
    unsupported = json.loads(bridge._app_capability_invoke_tool({
        "capability_id": "system.rpc", "input": {},
    }))
    assert denied["error"] == "trusted_invocation_context_required"
    assert unsupported["error"] == "capability_not_found"


def test_bridge_compiles_every_implemented_capability_as_a_native_tool(monkeypatch):
    registered = {}

    class Registry:
        def register(self, **kwargs):
            registered[kwargs["name"]] = kwargs

    monkeypatch.setitem(sys.modules, "tools.registry", types.SimpleNamespace(registry=Registry()))
    monkeypatch.setattr(bridge, "_app_capability_tools_registered", False)
    bridge._ensure_app_capability_tools_registered()
    implemented = {
        item["id"]: item for item in load_catalog()["capabilities"]
        if item["implementation_status"] == "implemented"
    }
    expected = {
        bridge._app_capability_native_tool_name(capability_id)
        for capability_id in implemented
    }
    assert set(registered) == expected
    assert not {
        "app_capability_search", "app_capability_describe", "app_capability_invoke",
    } & set(registered)
    presentation = registered["app_presentation_create_from_document"]
    assert presentation["schema"]["parameters"] == implemented[
        "presentation.create_from_document"
    ]["input_schema"]
    assert "authenticated app must confirm" in presentation["schema"]["description"]
    assert not {"url", "handler", "tenant", "user"} & set(
        presentation["schema"]["parameters"]["properties"]
    )
    text_presentation = registered["app_presentation_create_from_text"]
    text_schema = text_presentation["schema"]["parameters"]
    assert text_schema == implemented["presentation.create_from_text"]["input_schema"]
    assert text_schema["required"] == ["title", "text_material"]
    assert text_schema["properties"]["intended_use"]["default"] == "management_briefing"
    assert text_schema["properties"]["layout_style"]["default"] == "clean_professional_16_9"
    contract = implemented["presentation.create_from_text"]["workflow_contract"]
    assert contract["clarification"].startswith("Ask only")
    assert contract["artifact"]["extension"] == "pptx"
    assert contract["preview"]["extension"] == "pdf"
    assert bridge._legacy_client_context_enabled(True, False) is False


def test_native_capability_handler_binds_one_id_without_model_supplied_routing(monkeypatch):
    captured = {}

    def fake_invoke(args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return "bound"

    monkeypatch.setattr(bridge, "_app_capability_invoke_tool", fake_invoke)
    handler = bridge._app_capability_native_handler("workflow.status")
    assert handler({"workflow_id": "wf-1"}, trusted=True) == "bound"
    assert captured == {
        "args": {
            "capability_id": "workflow.status",
            "input": {"workflow_id": "wf-1"},
        },
        "kwargs": {"trusted": True},
    }


@pytest.mark.parametrize(
    ("qcp_enabled", "knowledge_enabled", "expected_toolsets"),
    [
        (True, False, {"app_capabilities"}),
        (False, True, {"knowledge_workspace"}),
        (True, True, {"app_capabilities"}),
        (False, False, set()),
    ],
)
def test_request_build_routes_qcp_and_knowledge_toolsets_independently(
    monkeypatch, tmp_path, qcp_enabled, knowledge_enabled, expected_toolsets
):
    registered = {}
    captured = {}

    class Registry:
        def register(self, **kwargs):
            registered[kwargs["name"]] = kwargs

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            captured["agent"] = self

    registry_module = types.SimpleNamespace(registry=Registry())
    run_agent_module = types.SimpleNamespace(AIAgent=FakeAgent)
    model_tools_module = types.SimpleNamespace(get_tool_definitions=lambda **kwargs: [
        {"function": {"name": name}}
        for name, item in registered.items()
        if item["toolset"] in set(kwargs.get("enabled_toolsets") or [])
    ])
    monkeypatch.setitem(sys.modules, "tools.registry", registry_module)
    monkeypatch.setitem(sys.modules, "run_agent", run_agent_module)
    monkeypatch.setitem(sys.modules, "model_tools", model_tools_module)
    monkeypatch.setattr(bridge, "_app_capability_tools_registered", False)
    monkeypatch.setattr(bridge, "_knowledge_workspace_tools_registered", False)
    monkeypatch.setattr(bridge, "_get_cached_config", lambda: {"model": {"default": "test"}})
    monkeypatch.setattr(bridge, "_get_cached_runtime", lambda _cfg: {"provider": "test"})
    monkeypatch.setattr(bridge, "_get_cached_fallback", lambda _cfg: None)
    monkeypatch.setattr(bridge, "_get_cached_tools", lambda _cfg: set())
    monkeypatch.setattr(bridge, "_resolve_dynamic_toolsets", lambda *_args: [])
    monkeypatch.setattr(bridge, "_create_sandbox_session_db", lambda _sandbox: object())
    monkeypatch.setattr(bridge, "_take_cached_agent", lambda *_args: None)
    monkeypatch.setattr(bridge, "persist_agent_snapshot", lambda *_args: None)
    monkeypatch.setattr("agent.runtime_cwd.set_session_cwd", lambda _value: None)

    agent, _, route = bridge._build_in_process_agent(
        "inspect application data",
        f"route-{int(qcp_enabled)}-{int(knowledge_enabled)}",
        None,
        queue.Queue(),
        agent_config={},
        qcp_enabled=qcp_enabled,
        knowledge_action_enabled=knowledge_enabled,
        sandbox=types.SimpleNamespace(
            root=tmp_path, state_db=tmp_path / "state.db", hermes_home=tmp_path
        ),
    )

    actual = set(route["enabled_toolsets"])
    assert actual & {"app_capabilities", "knowledge_workspace"} == expected_toolsets
    app_tools = {
        bridge._app_capability_native_tool_name(item["id"])
        for item in load_catalog()["capabilities"]
        if item["implementation_status"] == "implemented"
    }
    assert (app_tools <= set(registered)) is qcp_enabled
    if qcp_enabled:
        assert app_tools <= {item["function"]["name"] for item in agent.tools}
        assert not {
            "app_capability_search", "app_capability_describe", "app_capability_invoke",
        } & {item["function"]["name"] for item in agent.tools}


def test_bridge_navigation_emits_semantic_event_and_rejects_injected_identity():
    events = []
    bridge._client_context_tool_context.value = {
        "knowledge_action_v1": True, "emit": events.append,
    }
    try:
        result = json.loads(bridge._app_capability_invoke_tool({
            "capability_id": "knowledge.navigation",
            "input": {"destination": "archive"},
        }))
        denied = json.loads(bridge._app_capability_invoke_tool({
            "capability_id": "knowledge.navigation",
            "input": {"destination": "archive", "user_id": "other"},
        }))
    finally:
        bridge._client_context_tool_context.value = None
    assert result["success"] is True
    assert events == [{"type": "knowledge_navigation", "destination": "archive", "note_id": None, "query": None}]
    assert denied["error"] == "contract_invalid"


@pytest.mark.asyncio
async def test_ordinary_archive_is_not_merge_self_target_and_cas_retry_is_safe(tmp_path):
    import backend.api.knowledge_sync as sync

    payload = {"tenant_key": "tenant-a", "user_id": "user-a"}
    original = "# v1"
    revised = "# v2"
    original_hash = hashlib.sha256(original.encode()).hexdigest()
    revised_hash = hashlib.sha256(revised.encode()).hexdigest()
    with patch.object(sync, "_sync_root", return_value=Path(tmp_path)), \
         patch.object(sync, "enqueue_note_contribution", AsyncMock(return_value=None)), \
         patch.object(sync, "_withdraw_note_event", AsyncMock(return_value=set())):
        await sync.sync_note("note-a", sync.NoteSyncRequest(markdown=original, content_hash=original_hash), payload)
        await sync.sync_note("note-a", sync.NoteSyncRequest(markdown=revised, content_hash=revised_hash, base_hash=original_hash), payload)
        retry = await sync.sync_note("note-a", sync.NoteSyncRequest(markdown=revised, content_hash=revised_hash, base_hash=original_hash), payload)
        assert retry["changed"] is False
        archived = await sync.archive_note("note-a", sync.NoteArchiveRequest(expected_content_hash=revised_hash), payload)
    assert archived["archive_status"] == "archived"
    assert archived["merged_into_note_id"] is None


def test_bridge_db_reads_dispatch_consecutively_on_one_stable_loop():
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    seen = []

    def run_loop():
        asyncio.set_event_loop(loop)
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    ready.wait(timeout=2)

    invocation_keys = []

    async def fake_invoke(*_args, **kwargs):
        seen.append(asyncio.get_running_loop())
        invocation_keys.append(kwargs.get("idempotency_key"))
        return {"status": "completed", "events": [], "receipt": None, "error": None}

    bridge._bridge_async_loop = loop
    bridge._client_context_tool_context.value = {
        "identity": {"tenant_key": "tenant-a", "user_id": "user-a"},
        "request_id": "request-123", "emit": lambda _event: None,
    }
    try:
        with patch("backend.services.capability_catalog.invoke_capability", new=fake_invoke):
            for _ in range(2):
                result = json.loads(bridge._app_capability_invoke_tool({
                    "capability_id": "workflow.open", "input": {"workflow_id": "wf-1"},
                }))
                assert result["status"] == "completed"
            consumed = json.loads(bridge._app_capability_invoke_tool({
                "capability_id": "artifact.consume_structured",
                "input": {
                    "execution_id": "execution-1", "artifact_id": "artifact-1",
                    "expected_content_hash": "a" * 64,
                },
            }))
            assert consumed["status"] == "completed"
            consumed_again = json.loads(bridge._app_capability_invoke_tool({
                "capability_id": "artifact.consume_structured",
                "input": {
                    "execution_id": "execution-1", "artifact_id": "artifact-1",
                    "expected_content_hash": "a" * 64,
                },
            }))
            consumed_other = json.loads(bridge._app_capability_invoke_tool({
                "capability_id": "artifact.consume_structured",
                "input": {
                    "execution_id": "execution-1", "artifact_id": "artifact-2",
                    "expected_content_hash": "b" * 64,
                },
            }))
            assert consumed_again["status"] == consumed_other["status"] == "completed"
    finally:
        bridge._client_context_tool_context.value = None
        bridge._bridge_async_loop = None
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        loop.close()
    assert seen == [loop, loop, loop, loop, loop]
    assert invocation_keys[:2] == [None, None]
    first_input = {
        "execution_id": "execution-1", "artifact_id": "artifact-1",
        "expected_content_hash": "a" * 64,
    }
    input_digest = hashlib.sha256(json.dumps(
        first_input, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    assert invocation_keys[2] == invocation_keys[3] == "bridge-" + hashlib.sha256(
        f"artifact.consume_structured:request-123:{input_digest}".encode()
    ).hexdigest()
    assert invocation_keys[4] != invocation_keys[2]


def test_bridge_qcp_read_path_installs_only_trusted_invocation_identity(
    monkeypatch, tmp_path
):
    observed = {}

    class FakeAgent:
        session_id = "hermes-session"

        def run_conversation(self, _goal, **_kwargs):
            observed.update(bridge._client_context_tool_context.value)
            return {"final_response": "done"}

        def close(self):
            return None

    class FakeSessionDB:
        def get_messages(self, _session_id):
            return []

        def close(self):
            return None

    monkeypatch.setattr(
        bridge, "_build_in_process_agent",
        lambda *_args, **kwargs: (
            observed.update(build_kwargs=kwargs)
            or (FakeAgent(), FakeSessionDB(), {"triage": None})
        ),
    )
    monkeypatch.setattr(bridge, "_update_session_mapping", lambda *_args: None)
    gateway_context = types.ModuleType("gateway.session_context")
    gateway_context.declare_stateless_channel = lambda: None
    monkeypatch.setitem(sys.modules, "gateway.session_context", gateway_context)

    bridge._run_agent_sync(
        "consume an artifact", "logical-session", "hermes-session",
        queue.Queue(), [None],
        sandbox=types.SimpleNamespace(
            root=tmp_path, hermes_home=tmp_path, state_db=tmp_path / "state.db"
        ),
        qcp_enabled=True,
        trusted_request_id="trusted-request-123",
        trusted_identity_claims={"tenant_key": "tenant-a", "user_id": "user-a"},
    )

    assert observed["identity"] == {"tenant_key": "tenant-a", "user_id": "user-a"}
    assert observed["request_id"] == "trusted-request-123"
    assert observed["build_kwargs"]["qcp_enabled"] is True
    assert bridge._client_context_tool_context.value is None


@pytest.mark.asyncio
async def test_knowledge_create_idempotency_preserves_first_payload(tmp_path):
    import backend.api.knowledge_sync as sync

    payload = {"tenant_key": "tenant-a", "user_id": "user-a"}
    key = "request-123"
    with patch.object(sync, "_sync_root", return_value=Path(tmp_path)), \
         patch.object(sync, "enqueue_note_contribution", AsyncMock(return_value=None)):
        first = await invoke_capability(
            "knowledge.note.create", {"markdown": "# original"}, payload=payload,
            confirmed=True, idempotency_key=key,
        )
        replay = await invoke_capability(
            "knowledge.note.create", {"markdown": "# original"}, payload=payload,
            confirmed=True, idempotency_key=key,
        )
        conflict = await invoke_capability(
            "knowledge.note.create", {"markdown": "# changed"}, payload=payload,
            confirmed=True, idempotency_key=key,
        )
        notes = await sync.list_synced_notes(False, payload)

    assert first["status"] == replay["status"] == "completed"
    assert first["events"][0]["payload"]["content_hash"] == replay["events"][0]["payload"]["content_hash"]
    assert conflict["status"] == "failed"
    assert conflict["error"]["code"] == "idempotency_conflict"
    assert len(notes["items"]) == 1
    assert notes["items"][0]["markdown"] == "# original"
    assert notes["items"][0]["content_hash"] == hashlib.sha256(b"# original").hexdigest()


def test_workflow_idempotency_identity_includes_exact_capability():
    from backend.capability_handlers import _qcp_workflow_identity

    payload = {"tenant_key": "tenant-a", "user_id": "user-a"}
    data = {"title": "Same", "description": "same request"}
    workflow = _qcp_workflow_identity("workflow.create", payload, "same-key", data)
    presentation = _qcp_workflow_identity(
        "presentation.create_from_document", payload, "same-key", data
    )
    assert workflow[0] != presentation[0]
    assert workflow[1] != presentation[1]


@pytest.mark.asyncio
async def test_knowledge_mutation_receipts_survive_cache_clear_and_are_scoped(tmp_path):
    import backend.api.knowledge_sync as sync

    tenant_a = {"tenant_key": "tenant-a", "user_id": "user-a"}
    tenant_b = {"tenant_key": "tenant-b", "user_id": "user-a"}
    user_b = {"tenant_key": "tenant-a", "user_id": "user-b"}
    original = "# original"
    revised = "# revised"
    original_hash = hashlib.sha256(original.encode()).hexdigest()
    revised_hash = hashlib.sha256(revised.encode()).hexdigest()

    async def create(payload):
        await sync.sync_note(
            "note-a", sync.NoteSyncRequest(markdown=original, content_hash=original_hash),
            payload,
        )

    with patch.object(sync, "_sync_root", return_value=Path(tmp_path)), \
         patch.object(sync, "enqueue_note_contribution", AsyncMock(return_value=None)), \
         patch.object(sync, "_withdraw_note_event", AsyncMock(return_value=[])):
        await create(tenant_a)
        await create(tenant_b)
        await create(user_b)
        update = {"note_id": "note-a", "markdown": revised, "base_hash": original_hash}
        first = await invoke_capability(
            "knowledge.note.update", update, payload=tenant_a,
            confirmed=True, idempotency_key="shared-key",
        )
        load_catalog.cache_clear()
        import backend.capability_handlers as handlers
        importlib.reload(handlers)
        replay = await invoke_capability(
            "knowledge.note.update", update, payload=tenant_a,
            confirmed=True, idempotency_key="shared-key",
        )
        conflict = await invoke_capability(
            "knowledge.note.update", {**update, "markdown": "# conflict"}, payload=tenant_a,
            confirmed=True, idempotency_key="shared-key",
        )
        isolated_tenant = await invoke_capability(
            "knowledge.note.update", update, payload=tenant_b,
            confirmed=True, idempotency_key="shared-key",
        )
        isolated_user = await invoke_capability(
            "knowledge.note.update", update, payload=user_b,
            confirmed=True, idempotency_key="shared-key",
        )
        archived = await invoke_capability(
            "knowledge.note.archive", {"note_id": "note-a", "base_hash": revised_hash},
            payload=tenant_a, confirmed=True, idempotency_key="shared-key",
        )
        archive_replay = await invoke_capability(
            "knowledge.note.archive", {"note_id": "note-a", "base_hash": revised_hash},
            payload=tenant_a, confirmed=True, idempotency_key="shared-key",
        )
        restored = await invoke_capability(
            "knowledge.note.restore", {"note_id": "note-a"}, payload=tenant_a,
            confirmed=True, idempotency_key="shared-key",
        )
        restore_conflict = await invoke_capability(
            "knowledge.note.restore", {"note_id": "other-note"}, payload=tenant_a,
            confirmed=True, idempotency_key="shared-key",
        )

    assert first == replay and first["events"][0]["payload"]["changed"] is True
    assert conflict["error"]["code"] == "idempotency_conflict"
    assert isolated_tenant["status"] == "completed"
    assert isolated_user["status"] == "completed"
    assert archived == archive_replay and archived["status"] == "completed"
    assert restored["status"] == "completed"
    assert restore_conflict["error"]["code"] == "idempotency_conflict"
