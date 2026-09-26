from __future__ import annotations

import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import time
import types


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "agency/hermes-plugins/ai-lab-capabilities/jev_selector.py"
SPEC = importlib.util.spec_from_file_location("jev_selector_test_module", PATH)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def capability(identifier: str, kind: str) -> dict:
    return {
        "id": identifier,
        "kind": kind,
        "version": "1.0.0",
        "use_when": ["matching task"],
        "do_not_use_when": ["unrelated task"],
        "requires": {"permissions": ["tenant:read"], "tools": [], "platforms": ["ios", "feishu"]},
        "risk": "read",
        "status": "active",
        "description": "This full-text-looking field must never reach JEV.",
        "_search_text": "private specialist prompt must never reach JEV",
    }


def test_jev_input_is_bounded_pcm_projection_and_selects_zero_or_one_each():
    captured = {}

    def provider(payload, timeout):
        captured.update(payload)
        assert timeout == 0.2
        return {
            "skill_id": "skill:research",
            "agent_id": "agency:reviewer",
            "skill_confidence": 0.91,
            "agent_confidence": 0.87,
            "reason_code": "MATCHED",
        }

    decision = module.select_route(
        "请研究并独立复核",
        task_state={"turn_id": "turn-unique-1"},
        policy_version="policy-7",
        skill_candidates=[capability("skill:research", "skill")],
        agent_candidates=[capability("agency:reviewer", "agency_agent")],
        tenant_scope="tenant-a",
        principal_scope="user-a",
        provider=provider,
        timeout_seconds=0.2,
    )

    assert decision.skill_id == "skill:research"
    assert decision.agent_id == "agency:reviewer"
    assert decision.validated is True
    assert set(captured) == {
        "request", "task_state", "policy_version", "catalog_version",
        "skill_candidates", "agent_candidates",
    }
    encoded = json.dumps(captured, ensure_ascii=False)
    assert "private specialist prompt" not in encoded
    assert "full-text-looking" not in encoded
    assert set(captured["skill_candidates"][0]) == module._REQUIRED_CARD_FIELDS


def test_hallucinated_or_unauthorized_id_fails_closed_to_direct_hermes():
    decision = module.select_route(
        "unique hallucination test",
        task_state={"turn_id": "turn-unique-2"},
        policy_version="policy-7",
        skill_candidates=[capability("skill:allowed", "skill")],
        agent_candidates=[],
        provider=lambda _payload, _timeout: {
            "skill_id": "skill:not-authorized",
            "agent_id": None,
            "skill_confidence": 0.99,
            "agent_confidence": 0.0,
            "reason_code": "MATCHED",
        },
    )
    assert decision.skill_id is None
    assert decision.agent_id is None
    assert decision.reason_code == "INVALID_OUTPUT"
    assert decision.validated is False


def test_low_confidence_timeout_and_provider_failure_all_degrade_without_legacy_router():
    low = module.select_route(
        "unique low confidence test",
        task_state={"turn_id": "turn-unique-3"},
        policy_version="policy-7",
        skill_candidates=[capability("skill:allowed", "skill")],
        agent_candidates=[],
        provider=lambda _payload, _timeout: {
            "skill_id": "skill:allowed", "agent_id": None,
            "skill_confidence": 0.2, "agent_confidence": 0.0,
            "reason_code": "MATCHED",
        },
        confidence_threshold=0.55,
    )
    assert low.skill_id is None and low.reason_code == "LOW_CONFIDENCE"

    def timeout(_payload, _seconds):
        raise TimeoutError

    timed_out = module.select_route(
        "unique timeout test", task_state={"turn_id": "turn-unique-4"},
        policy_version="policy-7", skill_candidates=[], agent_candidates=[], provider=timeout,
    )
    assert timed_out.skill_id is None and timed_out.agent_id is None
    assert timed_out.reason_code == "TIMEOUT"
    assert timed_out.validated is False

    failed = module.select_route(
        "unique provider failure test", task_state={"turn_id": "turn-unique-5"},
        policy_version="policy-7", skill_candidates=[], agent_candidates=[],
        provider=lambda _payload, _timeout: (_ for _ in ()).throw(RuntimeError("down")),
    )
    assert failed.reason_code == "PROVIDER_UNAVAILABLE"


def test_cache_key_isolated_by_tenant_principal_policy_catalog_and_request():
    calls = []

    def provider(_payload, _timeout):
        calls.append(1)
        return {"skill_id": None, "agent_id": None, "skill_confidence": 0,
                "agent_confidence": 0, "reason_code": "NO_MATCH"}

    common = dict(
        request_text="unique cache request",
        task_state={"turn_id": "cache-turn"},
        policy_version="policy-7",
        skill_candidates=[], agent_candidates=[], provider=provider,
    )
    first = module.select_route(**common, tenant_scope="a", principal_scope="u1")
    cached = module.select_route(
        **dict(common, task_state={"turn_id": "cache-turn-2"}),
        tenant_scope="a", principal_scope="u1",
    )
    module.select_route(**common, tenant_scope="b", principal_scope="u1")
    module.select_route(**common, tenant_scope="a", principal_scope="u2")
    module.select_route(
        **dict(common, task_state={"turn_id": "cache-turn-3", "phase": "review"}),
        tenant_scope="a", principal_scope="u1",
    )
    assert len(calls) == 4
    assert cached.cache_hit is True
    assert cached.decision_id != first.decision_id


def test_cache_reuses_decision_across_opaque_session_ids_but_not_platforms():
    calls = []

    def provider(_payload, _timeout):
        calls.append(1)
        return {"skill_id": None, "agent_id": None, "skill_confidence": 0,
                "agent_confidence": 0, "reason_code": "NO_MATCH"}

    common = dict(
        request_text="same authorized request",
        policy_version="policy-session-cache",
        skill_candidates=[], agent_candidates=[], provider=provider,
        tenant_scope="tenant-a", principal_scope="user-a",
    )
    first = module.select_route(
        **common,
        task_state={"session_id": "session-1", "turn_id": "turn-1", "platform": "ios"},
    )
    cached = module.select_route(
        **common,
        task_state={"session_id": "session-2", "turn_id": "turn-2", "platform": "ios"},
    )
    other_platform = module.select_route(
        **common,
        task_state={"session_id": "session-3", "turn_id": "turn-3", "platform": "qws"},
    )

    assert first.cache_hit is False
    assert cached.cache_hit is True
    assert other_platform.cache_hit is False
    assert len(calls) == 2


def test_transient_failure_is_not_reused_across_sessions():
    calls = []

    def provider(_payload, _timeout):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("temporary outage")
        return {"skill_id": None, "agent_id": None, "skill_confidence": 0,
                "agent_confidence": 0, "reason_code": "NO_MATCH"}

    common = dict(
        request_text="retry after outage", policy_version="policy-retry",
        skill_candidates=[], agent_candidates=[], provider=provider,
        tenant_scope="tenant-a", principal_scope="user-a",
    )
    failed = module.select_route(
        **common, task_state={"session_id": "session-1", "platform": "ios"}
    )
    retried = module.select_route(
        **common, task_state={"session_id": "session-2", "platform": "ios"}
    )

    assert failed.reason_code == "PROVIDER_UNAVAILABLE"
    assert retried.validated is True
    assert retried.cache_hit is False
    assert len(calls) == 2


def test_catalog_version_changes_when_semantic_boundaries_change():
    original = module.compact_card(capability("skill:research", "skill"))
    changed = dict(original, use_when=["a materially different trigger"])

    assert module.catalog_version([original]) != module.catalog_version([changed])


def test_incomplete_output_and_duplicate_catalog_fail_closed():
    incomplete = module.select_route(
        "strict output",
        task_state={"turn_id": "strict-output-turn"},
        policy_version="policy-7",
        skill_candidates=[capability("skill:allowed", "skill")],
        agent_candidates=[],
        provider=lambda _payload, _timeout: {
            "skill_id": None,
            "agent_id": None,
            "reason_code": "NO_MATCH",
        },
    )
    assert incomplete.reason_code == "INVALID_OUTPUT"

    duplicate = capability("skill:duplicate", "skill")
    duplicated = module.select_route(
        "duplicate catalog",
        task_state={"turn_id": "duplicate-catalog-turn"},
        policy_version="policy-7",
        skill_candidates=[duplicate, duplicate],
        agent_candidates=[],
        provider=lambda _payload, _timeout: {
            "skill_id": None,
            "agent_id": None,
            "skill_confidence": 0.0,
            "agent_confidence": 0.0,
            "reason_code": "NO_MATCH",
        },
    )
    assert duplicated.reason_code == "INVALID_OUTPUT"
    assert duplicated.catalog_version == "invalid-catalog"


def test_non_finite_boolean_and_inconsistent_null_confidence_fail_closed():
    bad_outputs = (
        {"skill_id": None, "agent_id": None, "skill_confidence": True,
         "agent_confidence": 0.0, "reason_code": "NO_MATCH"},
        {"skill_id": None, "agent_id": None, "skill_confidence": float("nan"),
         "agent_confidence": 0.0, "reason_code": "NO_MATCH"},
        {"skill_id": None, "agent_id": None, "skill_confidence": 0.2,
         "agent_confidence": 0.0, "reason_code": "NO_MATCH"},
    )
    for index, output in enumerate(bad_outputs):
        decision = module.select_route(
            f"strict numeric output {index}",
            task_state={"turn_id": f"strict-numeric-{index}"},
            policy_version="policy-7",
            skill_candidates=[],
            agent_candidates=[],
            provider=lambda _payload, _timeout, value=output: value,
        )
        assert decision.reason_code == "INVALID_OUTPUT"


def test_default_provider_round_trips_over_real_http(monkeypatch):
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - stdlib callback name
            size = int(self.headers["Content-Length"])
            captured.update(json.loads(self.rfile.read(size)))
            body = json.dumps({
                "skill_id": "skill:research",
                "agent_id": None,
                "skill_confidence": 0.95,
                "agent_confidence": 0.0,
                "reason_code": "MATCHED",
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(
        "JEV_SELECTOR_URL", f"http://127.0.0.1:{server.server_port}/select"
    )
    try:
        decision = module.select_route(
            "HTTP contract test",
            task_state={"turn_id": "http-contract-turn"},
            policy_version="policy-http",
            skill_candidates=[capability("skill:research", "skill")],
            agent_candidates=[],
            timeout_seconds=1.0,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert decision.skill_id == "skill:research"
    assert decision.validated is True
    assert captured["catalog_version"] == decision.catalog_version


def test_resident_provider_is_used_without_http_or_request_cold_start(monkeypatch):
    calls = []

    class Resident:
        @staticmethod
        def enabled():
            return True

        @staticmethod
        def select(payload, timeout):
            calls.append((payload, timeout))
            return {
                "skill_id": "skill:research",
                "agent_id": None,
                "skill_confidence": 0.97,
                "agent_confidence": 0.0,
                "reason_code": "MATCHED",
            }

        @staticmethod
        def status():
            return {"enabled": True, "ready": True}

    monkeypatch.delenv("JEV_SELECTOR_URL", raising=False)
    monkeypatch.setattr(module, "_RESIDENT_MODULE", Resident)
    decision = module.select_route(
        "resident route",
        task_state={"turn_id": "resident-route-turn"},
        policy_version="policy-resident",
        skill_candidates=[capability("skill:research", "skill")],
        agent_candidates=[],
        timeout_seconds=0.8,
    )

    assert decision.skill_id == "skill:research"
    assert decision.validated is True
    assert len(calls) == 1
    assert calls[0][1] == 0.8


def test_resident_catalog_warmup_is_explicit_and_bounded(monkeypatch):
    warmed = []

    class Resident:
        @staticmethod
        def enabled():
            return True

        @staticmethod
        def start_warmup(cards):
            warmed.extend(cards)

    monkeypatch.setattr(module, "_RESIDENT_MODULE", Resident)
    module.start_resident_warmup(
        [capability("skill:research", "skill")],
        [capability("agency:reviewer", "agency_agent")],
    )

    assert [card["id"] for card in warmed] == ["skill:research", "agency:reviewer"]
    assert [card["kind"] for card in warmed] == ["skill", "agent"]


def test_resident_provider_uses_structured_selection_tool(monkeypatch):
    resident = module._resident_module()
    captured = {}

    def call_llm(**kwargs):
        captured.update(kwargs)
        function = types.SimpleNamespace(
            name="select_route",
            arguments=json.dumps({
                "skill_id": "skill:research",
                "agent_id": None,
                "skill_confidence": 0.97,
                "agent_confidence": 0.0,
                "reason_code": "MATCHED",
            }),
        )
        message = types.SimpleNamespace(
            content=None,
            tool_calls=[types.SimpleNamespace(function=function)],
        )
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=message)]
        )

    agent_module = types.ModuleType("agent")
    auxiliary_client = types.ModuleType("agent.auxiliary_client")
    setattr(auxiliary_client, "call_llm", call_llm)
    setattr(agent_module, "auxiliary_client", auxiliary_client)
    monkeypatch.setitem(sys.modules, "agent", agent_module)
    monkeypatch.setitem(sys.modules, "agent.auxiliary_client", auxiliary_client)
    output = resident._provider_select({
        "request": "research",
        "task_state": {},
        "skill_candidates": [module.compact_card(capability("skill:research", "skill"))],
        "agent_candidates": [],
    })

    assert output["skill_id"] == "skill:research"
    provider_payload = json.loads(captured["messages"][1]["content"])
    assert provider_payload["skill_candidates"][0][:3] == [
        "skill:research", "skill", "1.0.0",
    ]
    assert "Evaluate them independently" in captured["messages"][0]["content"]
    assert captured["max_tokens"] == 80
    assert captured["tools"][0]["function"]["name"] == "select_route"
    assert set(captured["tools"][0]["function"]["parameters"]["required"]) == {
        "skill_id", "agent_id", "skill_confidence",
        "agent_confidence", "reason_code",
    }


def test_resident_shortlist_fails_closed_when_catalog_is_stale(monkeypatch):
    resident = module._resident_module()
    monkeypatch.setattr(resident, "_READY", True)
    monkeypatch.setattr(resident, "_CARD_IDS", ["skill:known"])
    monkeypatch.setattr(resident, "_CARD_EMBEDDINGS", object())

    try:
        resident._shortlist({
            "request": "new capability",
            "skill_candidates": [module.compact_card(capability("skill:new", "skill"))],
            "agent_candidates": [],
        })
    except RuntimeError as exc:
        assert str(exc) == "resident_catalog_stale"
    else:
        raise AssertionError("stale resident catalog must not silently abstain")


def test_resident_provider_warm_failure_keeps_local_abstain_and_can_retry(monkeypatch):
    resident = module._resident_module()
    cards = [{"id": "skill:research", "kind": "skill", "version": "1"}]

    monkeypatch.setattr(resident, "enabled", lambda: True)
    monkeypatch.setattr(resident, "request_timeout_seconds", lambda: 1.0)
    monkeypatch.setattr(resident, "_READY", False)
    monkeypatch.setattr(resident, "_PROVIDER_READY", False)
    monkeypatch.setattr(resident, "_NEXT_RETRY_AT", 0.0)
    monkeypatch.setattr(resident, "_WARM_THREAD", None)
    monkeypatch.setattr(resident, "_WARM_CARDS", [])
    monkeypatch.setattr(resident, "_CARD_FINGERPRINT", "")
    monkeypatch.setattr(resident, "_CARD_IDS", [])
    monkeypatch.setattr(resident, "_CARD_EMBEDDINGS", None)

    def load_embeddings(items):
        resident._CARD_FINGERPRINT = resident._fingerprint(items)
        resident._CARD_IDS = ["skill:research"]
        resident._CARD_EMBEDDINGS = object()

    monkeypatch.setattr(resident, "_load_embeddings", load_embeddings)
    monkeypatch.setattr(
        resident, "_provider_warmup",
        lambda: (_ for _ in ()).throw(RuntimeError("down")),
    )
    resident.start_warmup(cards)
    resident._WARM_THREAD.join(timeout=2)
    assert resident.status()["ready"] is True
    assert resident.status()["provider_ready"] is False

    monkeypatch.setattr(resident, "_shortlist", lambda _payload: ([], [], -1.0, -1.0))
    assert resident.select({"request": "hello"}, 0.1)["reason_code"] == "NO_MATCH"

    monkeypatch.setattr(resident, "_NEXT_RETRY_AT", 0.0)
    monkeypatch.setattr(resident, "_provider_warmup", lambda: None)
    resident.start_warmup(cards)
    resident._WARM_THREAD.join(timeout=2)
    assert resident.status()["provider_ready"] is True


def test_resident_provider_call_has_a_hard_request_deadline(monkeypatch):
    resident = module._resident_module()
    release = threading.Event()
    monkeypatch.setattr(resident, "_PROVIDER_READY", True)
    monkeypatch.setattr(
        resident,
        "_shortlist",
        lambda _payload: ([{"id": "skill:research"}], [], 0.9, -1.0),
    )

    def blocked(_payload):
        release.wait(timeout=1)
        return {}

    monkeypatch.setattr(resident, "_provider_select", blocked)
    started = time.perf_counter()
    try:
        resident.select({"request": "research"}, 0.02)
    except TimeoutError as exc:
        assert str(exc) == "resident_jev_timeout"
    else:
        raise AssertionError("resident provider must honor the hard deadline")
    finally:
        release.set()
    assert time.perf_counter() - started < 0.2


def test_resident_rejects_immediately_when_provider_workers_are_saturated(monkeypatch):
    resident = module._resident_module()

    class BusySlots:
        @staticmethod
        def acquire(*, blocking):
            assert blocking is False
            return False

    monkeypatch.setattr(resident, "_PROVIDER_READY", True)
    monkeypatch.setattr(resident, "_PROVIDER_SLOTS", BusySlots())
    monkeypatch.setattr(
        resident,
        "_shortlist",
        lambda _payload: ([{"id": "skill:research"}], [], 0.9, -1.0),
    )
    monkeypatch.setattr(
        resident,
        "_provider_select",
        lambda _payload: (_ for _ in ()).throw(AssertionError("must not queue")),
    )

    started = time.perf_counter()
    try:
        resident.select({"request": "research"}, 1.0)
    except RuntimeError as exc:
        assert str(exc) == "resident_provider_busy"
    else:
        raise AssertionError("saturated provider must fail fast")
    assert time.perf_counter() - started < 0.05


def test_resident_omits_each_low_affinity_kind_before_remote_selection(monkeypatch):
    resident = module._resident_module()
    captured = []
    monkeypatch.setattr(resident, "_PROVIDER_READY", True)
    monkeypatch.setattr(resident, "_number", lambda _name, default: default)
    monkeypatch.setattr(
        resident,
        "_shortlist",
        lambda _payload: (
            [{"id": "skill:research"}],
            [{"id": "agency:reviewer"}],
            0.9,
            0.2,
        ),
    )

    def provider(payload):
        captured.append(payload)
        return {
            "skill_id": "skill:research",
            "agent_id": None,
            "skill_confidence": 0.9,
            "agent_confidence": 0.0,
            "reason_code": "MATCHED",
        }

    monkeypatch.setattr(resident, "_provider_select", provider)
    output = resident.select({"request": "research"}, 0.2)

    assert output["skill_id"] == "skill:research"
    assert captured[0]["skill_candidates"] == [{"id": "skill:research"}]
    assert captured[0]["agent_candidates"] == []


def test_resident_rejects_an_id_omitted_by_per_kind_abstention(monkeypatch):
    resident = module._resident_module()
    monkeypatch.setattr(resident, "_PROVIDER_READY", True)
    monkeypatch.setattr(resident, "_number", lambda _name, default: default)
    monkeypatch.setattr(
        resident,
        "_shortlist",
        lambda _payload: (
            [{"id": "skill:research"}],
            [{"id": "agency:reviewer"}],
            0.9,
            0.2,
        ),
    )
    monkeypatch.setattr(
        resident,
        "_provider_select",
        lambda _payload: {
            "skill_id": None,
            "agent_id": "agency:reviewer",
            "skill_confidence": 0.0,
            "agent_confidence": 0.99,
            "reason_code": "MATCHED",
        },
    )

    try:
        resident.select({"request": "research"}, 0.2)
    except ValueError as exc:
        assert str(exc) == "resident_jev_candidate_escape"
    else:
        raise AssertionError("an omitted candidate must fail closed")


def test_resident_rejects_non_string_provider_ids(monkeypatch):
    resident = module._resident_module()
    monkeypatch.setattr(resident, "_PROVIDER_READY", True)
    monkeypatch.setattr(resident, "_number", lambda _name, default: default)
    monkeypatch.setattr(
        resident,
        "_shortlist",
        lambda _payload: ([{"id": "skill:research"}], [], 0.9, 0.0),
    )
    monkeypatch.setattr(
        resident,
        "_provider_select",
        lambda _payload: {
            "skill_id": [],
            "agent_id": None,
            "skill_confidence": 0.99,
            "agent_confidence": 0.0,
            "reason_code": "MATCHED",
        },
    )

    try:
        resident.select({"request": "research"}, 0.2)
    except ValueError as exc:
        assert str(exc) == "resident_jev_candidate_escape"
    else:
        raise AssertionError("a non-string candidate id must fail closed")
