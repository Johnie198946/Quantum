from __future__ import annotations

import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading


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
    cached = module.select_route(**common, tenant_scope="a", principal_scope="u1")
    module.select_route(**common, tenant_scope="b", principal_scope="u1")
    module.select_route(**common, tenant_scope="a", principal_scope="u2")
    assert len(calls) == 3
    assert cached.cache_hit is True
    assert cached.decision_id != first.decision_id


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
