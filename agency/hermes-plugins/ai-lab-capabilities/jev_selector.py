"""JEV selector adapter embedded in the existing capability router.

The adapter is deliberately selection-only: it receives tenant-authorized compact
PCM projections, returns at most one Skill and one independent Agent, and never
executes or grants a capability. Invalid, low-confidence, unavailable, or timed-out
responses deterministically degrade to Hermes direct execution.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, replace
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Callable, Iterable
from urllib import error, request
import uuid


_ALLOWED_REASONS = {
    "MATCHED",
    "NO_MATCH",
    "LOW_CONFIDENCE",
    "INVALID_OUTPUT",
    "PROVIDER_UNAVAILABLE",
    "TIMEOUT",
}
_REQUIRED_CARD_FIELDS = {
    "id", "kind", "version", "use_when", "do_not_use_when",
    "requires", "risk", "status",
}
_VALID_KINDS = {"skill", "agent", "capability"}
_VALID_RISKS = {"read", "write", "external_write", "privileged"}
_CACHE_LOCK = threading.Lock()
_CACHE: "OrderedDict[str, tuple[float, RouteDecision]]" = OrderedDict()
_RESIDENT_MODULE: Any = None
_VOLATILE_TASK_STATE_KEYS = {
    "session_id", "turn_id", "request_id", "trace_id", "decision_id",
    "timestamp", "created_at", "updated_at",
}


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _cache_task_state(task_state: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in task_state.items()
        if key not in _VOLATILE_TASK_STATE_KEYS
    }


@dataclass(frozen=True)
class RouteDecision:
    decision_id: str
    skill_id: str | None
    agent_id: str | None
    skill_confidence: float
    agent_confidence: float
    reason_code: str
    policy_version: str
    catalog_version: str
    latency_ms: float
    validated: bool
    cache_hit: bool = False
    capability_id: str | None = None
    capability_confidence: float = 0.0
    shortlisted_skill_ids: tuple[str, ...] = ()
    shortlisted_agent_ids: tuple[str, ...] = ()
    shortlisted_capability_ids: tuple[str, ...] = ()
    architecture_reserved_agent_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compact_card(capability: dict[str, Any]) -> dict[str, Any]:
    """Project runtime/PCM metadata without Skill bodies or Agent prompts."""
    kind = str(capability.get("kind") or "skill")
    if kind == "agency_agent":
        kind = "agent"
    use_when = capability.get("use_when") or capability.get("trigger_phrases") or capability.get("description") or []
    do_not_use = capability.get("do_not_use_when") or capability.get("negative_phrases") or []
    if isinstance(use_when, str):
        use_when = [use_when]
    if isinstance(do_not_use, str):
        do_not_use = [do_not_use]
    requires = capability.get("requires") or {}
    if not isinstance(requires, dict):
        requires = {}
    card = {
        "id": str(capability.get("id") or "").strip(),
        "kind": kind,
        "version": str(capability.get("version") or "1.0.0").strip(),
        "use_when": [str(item).strip()[:180] for item in use_when if str(item).strip()][:8],
        "do_not_use_when": [str(item).strip()[:180] for item in do_not_use if str(item).strip()][:8],
        "requires": {
            "permissions": sorted({str(item) for item in requires.get("permissions", [])}),
            "tools": sorted({str(item) for item in requires.get("tools", [])}),
            "platforms": sorted({str(item) for item in requires.get("platforms", [])}),
        },
        "risk": str(capability.get("risk") or "read"),
        "status": str(capability.get("status") or "active"),
    }
    validate_card(card)
    return card


def validate_card(card: dict[str, Any]) -> None:
    if set(card) != _REQUIRED_CARD_FIELDS:
        raise ValueError("invalid_candidate_card_fields")
    if not card["id"] or card["kind"] not in _VALID_KINDS:
        raise ValueError("invalid_candidate_identity")
    if card["risk"] not in _VALID_RISKS or card["status"] != "active":
        raise ValueError("inactive_or_invalid_candidate")
    if not isinstance(card["use_when"], list) or not isinstance(card["do_not_use_when"], list):
        raise ValueError("invalid_candidate_boundaries")


def catalog_version(cards: Iterable[dict[str, Any]]) -> str:
    stable = sorted(cards, key=lambda card: str(card["id"]))
    raw = json.dumps(stable, ensure_ascii=False, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _null_decision(
    *, reason: str, policy_version: str, catalog_version_value: str,
    latency_ms: float = 0.0, decision_id: str | None = None,
) -> RouteDecision:
    return RouteDecision(
        decision_id=decision_id or "route_" + uuid.uuid4().hex,
        skill_id=None,
        agent_id=None,
        skill_confidence=0.0,
        agent_confidence=0.0,
        reason_code=reason if reason in _ALLOWED_REASONS else "INVALID_OUTPUT",
        policy_version=policy_version,
        catalog_version=catalog_version_value,
        latency_ms=round(max(0.0, latency_ms), 3),
        validated=False,
    )


def _resident_module() -> Any:
    global _RESIDENT_MODULE
    if _RESIDENT_MODULE is not None:
        return _RESIDENT_MODULE
    try:
        from . import jev_resident as module
    except ImportError:
        name = "ai_lab_capabilities_jev_resident"
        spec = importlib.util.spec_from_file_location(
            name, Path(__file__).with_name("jev_resident.py")
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("resident_jev_module_unavailable")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    _RESIDENT_MODULE = module
    return module


def start_resident_warmup(
    skill_candidates: Iterable[dict[str, Any]],
    agent_candidates: Iterable[dict[str, Any]],
    capability_candidates: Iterable[dict[str, Any]] = (),
) -> None:
    """Preload the optional in-process selector during gateway startup."""
    module = _resident_module()
    if not module.enabled():
        return
    cards = [compact_card(item) for item in skill_candidates]
    cards.extend(compact_card(item) for item in agent_candidates)
    cards.extend(compact_card(item) for item in capability_candidates)
    module.start_warmup(cards)


def resident_status() -> dict[str, Any]:
    return dict(_resident_module().status())


def _default_timeout_seconds() -> float:
    module = _resident_module()
    if module.enabled():
        return float(module.request_timeout_seconds())
    return _env_float("JEV_SELECTOR_TIMEOUT_SECONDS", 2.5)


class _TrustedProviderOutput(dict[str, Any]):
    """Internal-only envelope for resident trace metadata.

    External/custom providers remain plain mappings and cannot assert shortlist
    provenance. The trace is observational only and never expands selection.
    """

    def __init__(self, output: dict[str, Any], routing_trace: dict[str, Any] | None = None):
        super().__init__(output)
        self.routing_trace = routing_trace if isinstance(routing_trace, dict) else {}


def _provider(payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    endpoint = os.environ.get("JEV_SELECTOR_URL", "").strip()
    if not endpoint:
        module = _resident_module()
        if module.enabled():
            output = module.select(payload, timeout_seconds)
            if not isinstance(output, dict):
                raise ValueError("jev_output_not_object")
            validated_output = dict(output)
            routing_trace = validated_output.pop("_routing_trace", None)
            return _TrustedProviderOutput(validated_output, routing_trace)
        raise RuntimeError("JEV selector is not configured")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    api_key = os.environ.get("JEV_SELECTOR_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        body = json.loads(response.read().decode("utf-8"))
    if isinstance(body, dict) and isinstance(body.get("output"), dict):
        body = body["output"]
    if not isinstance(body, dict):
        raise ValueError("jev_output_not_object")
    return body


def _validate_output(
    output: dict[str, Any], *, skill_ids: set[str], agent_ids: set[str],
    threshold: float, policy_version: str, catalog_version_value: str,
    latency_ms: float, decision_id: str,
    forbid_agent_with_skills: set[str] | None = None,
    capability_ids: set[str] | None = None,
    routing_trace: dict[str, Any] | None = None,
) -> RouteDecision:
    allowed = {"skill_id", "agent_id", "skill_confidence", "agent_confidence", "reason_code"}
    if capability_ids:
        allowed |= {"capability_id", "capability_confidence"}
    if set(output) != allowed:
        return _null_decision(reason="INVALID_OUTPUT", policy_version=policy_version,
                              catalog_version_value=catalog_version_value,
                              latency_ms=latency_ms, decision_id=decision_id)
    capability_id = output.get("capability_id")
    capability_confidence = output.get("capability_confidence", 0.0)
    if (capability_id is not None and (not isinstance(capability_id, str) or capability_id not in (capability_ids or set()))
        or isinstance(capability_confidence, bool) or not isinstance(capability_confidence, (int, float))
        or not math.isfinite(capability_confidence) or not 0 <= capability_confidence <= 1
        or (capability_id is None and capability_confidence != 0)):
        return _null_decision(reason="INVALID_OUTPUT", policy_version=policy_version,
                              catalog_version_value=catalog_version_value,
                              latency_ms=latency_ms, decision_id=decision_id)
    if capability_confidence < threshold:
        capability_id, capability_confidence = None, 0.0
    skill_id = output.get("skill_id")
    agent_id = output.get("agent_id")
    if skill_id is not None and (not isinstance(skill_id, str) or skill_id not in skill_ids):
        return _null_decision(reason="INVALID_OUTPUT", policy_version=policy_version,
                              catalog_version_value=catalog_version_value,
                              latency_ms=latency_ms, decision_id=decision_id)
    if agent_id is not None and (not isinstance(agent_id, str) or agent_id not in agent_ids):
        return _null_decision(reason="INVALID_OUTPUT", policy_version=policy_version,
                              catalog_version_value=catalog_version_value,
                              latency_ms=latency_ms, decision_id=decision_id)
    if agent_id is not None and skill_id in (forbid_agent_with_skills or set()):
        return _null_decision(reason="INVALID_OUTPUT", policy_version=policy_version,
                              catalog_version_value=catalog_version_value,
                              latency_ms=latency_ms, decision_id=decision_id)
    raw_skill_confidence = output.get("skill_confidence")
    raw_agent_confidence = output.get("agent_confidence")
    if (
        isinstance(raw_skill_confidence, bool)
        or isinstance(raw_agent_confidence, bool)
        or not isinstance(raw_skill_confidence, (int, float))
        or not isinstance(raw_agent_confidence, (int, float))
    ):
        return _null_decision(reason="INVALID_OUTPUT", policy_version=policy_version,
                              catalog_version_value=catalog_version_value,
                              latency_ms=latency_ms, decision_id=decision_id)
    try:
        skill_confidence = float(raw_skill_confidence)
        agent_confidence = float(raw_agent_confidence)
    except (TypeError, ValueError):
        return _null_decision(reason="INVALID_OUTPUT", policy_version=policy_version,
                              catalog_version_value=catalog_version_value,
                              latency_ms=latency_ms, decision_id=decision_id)
    if (
        not math.isfinite(skill_confidence)
        or not math.isfinite(agent_confidence)
        or not (0.0 <= skill_confidence <= 1.0 and 0.0 <= agent_confidence <= 1.0)
    ):
        return _null_decision(reason="INVALID_OUTPUT", policy_version=policy_version,
                              catalog_version_value=catalog_version_value,
                              latency_ms=latency_ms, decision_id=decision_id)
    if (skill_id is None and skill_confidence != 0.0) or (
        agent_id is None and agent_confidence != 0.0
    ):
        return _null_decision(reason="INVALID_OUTPUT", policy_version=policy_version,
                              catalog_version_value=catalog_version_value,
                              latency_ms=latency_ms, decision_id=decision_id)
    if skill_id is not None and skill_confidence < threshold:
        skill_id, skill_confidence = None, 0.0
    if agent_id is not None and agent_confidence < threshold:
        agent_id, agent_confidence = None, 0.0
    if skill_id is None:
        skill_confidence = 0.0
    if agent_id is None:
        agent_confidence = 0.0
    reason = str(output.get("reason_code") or "")
    if reason not in _ALLOWED_REASONS:
        return _null_decision(reason="INVALID_OUTPUT", policy_version=policy_version,
                              catalog_version_value=catalog_version_value,
                              latency_ms=latency_ms, decision_id=decision_id)
    if (skill_id or agent_id or capability_id) and reason != "MATCHED":
        return _null_decision(reason="INVALID_OUTPUT", policy_version=policy_version,
                              catalog_version_value=catalog_version_value,
                              latency_ms=latency_ms, decision_id=decision_id)
    if not skill_id and not agent_id and not capability_id and reason == "MATCHED":
        reason = "LOW_CONFIDENCE"

    trace = routing_trace if isinstance(routing_trace, dict) else {}

    def traced_ids(field: str, allowed_ids: set[str]) -> tuple[str, ...]:
        values = trace.get(field) or []
        if not isinstance(values, (list, tuple)):
            return ()
        return tuple(dict.fromkeys(
            value for value in values
            if isinstance(value, str) and value in allowed_ids
        ))[:5]

    shortlisted_skills = traced_ids("skill_ids", skill_ids)
    shortlisted_agents = traced_ids("agent_ids", agent_ids)
    shortlisted_capabilities = traced_ids("capability_ids", capability_ids or set())
    architecture_reserved = tuple(
        identifier for identifier in traced_ids("architecture_reserved_agent_ids", agent_ids)
        if identifier in shortlisted_agents
    )
    return RouteDecision(
        decision_id=decision_id,
        skill_id=skill_id,
        agent_id=agent_id,
        capability_id=capability_id,
        capability_confidence=round(capability_confidence, 6),
        skill_confidence=round(skill_confidence, 6),
        agent_confidence=round(agent_confidence, 6),
        reason_code=reason,
        policy_version=policy_version,
        catalog_version=catalog_version_value,
        latency_ms=round(latency_ms, 3),
        validated=True,
        shortlisted_skill_ids=shortlisted_skills,
        shortlisted_agent_ids=shortlisted_agents,
        shortlisted_capability_ids=shortlisted_capabilities,
        architecture_reserved_agent_ids=architecture_reserved,
    )


def select_route(
    request_text: str,
    *,
    task_state: dict[str, Any] | None,
    policy_version: str,
    skill_candidates: Iterable[dict[str, Any]],
    agent_candidates: Iterable[dict[str, Any]],
    capability_candidates: Iterable[dict[str, Any]] = (),
    tenant_scope: str = "",
    principal_scope: str = "",
    provider: Callable[[dict[str, Any], float], dict[str, Any]] | None = None,
    timeout_seconds: float | None = None,
    confidence_threshold: float | None = None,
) -> RouteDecision:
    decision_id = "route_" + uuid.uuid4().hex
    try:
        skills = [compact_card(item) for item in skill_candidates]
        agents = [compact_card(item) for item in agent_candidates]
        capabilities = [compact_card(item) for item in capability_candidates]
        if any(c["kind"] != kind for kind, group in (("skill", skills), ("agent", agents), ("capability", capabilities)) for c in group):
            raise ValueError("candidate_kind_mismatch")
        ids = [card["id"] for card in skills + agents + capabilities]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_candidate_id")
    except (TypeError, ValueError):
        return _null_decision(
            reason="INVALID_OUTPUT",
            policy_version=policy_version,
            catalog_version_value="invalid-catalog",
            decision_id=decision_id,
        )
    cards = skills + agents + capabilities
    version = catalog_version(cards)
    payload = {
        "request": str(request_text or "")[:12000],
        "task_state": task_state or {},
        "policy_version": policy_version,
        "catalog_version": version,
        "skill_candidates": skills,
        "agent_candidates": agents,
    }
    if capabilities:
        payload["capability_candidates"] = capabilities
    digest = hashlib.sha256(json.dumps({
        "tenant": tenant_scope,
        "principal": principal_scope,
        "policy_version": policy_version,
        "catalog_version": version,
        "request": payload["request"],
        "task_state": _cache_task_state(payload["task_state"]),
    }, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    ttl = max(0.0, _env_float("JEV_SELECTOR_CACHE_TTL_SECONDS", 60.0))
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(digest)
        if cached and now - cached[0] <= ttl:
            _CACHE.move_to_end(digest)
            return replace(
                cached[1],
                decision_id=decision_id,
                latency_ms=0.0,
                cache_hit=True,
            )
        if cached:
            _CACHE.pop(digest, None)
    timeout_value = max(
        0.01,
        timeout_seconds
        if timeout_seconds is not None
        else _default_timeout_seconds(),
    )
    threshold = (
        confidence_threshold
        if confidence_threshold is not None
        else _env_float("JEV_SELECTOR_CONFIDENCE_THRESHOLD", 0.55)
    )
    if not math.isfinite(threshold):
        threshold = 0.55
    started = time.perf_counter()
    try:
        output = (provider or _provider)(payload, timeout_value)
        elapsed = (time.perf_counter() - started) * 1000
        if not isinstance(output, dict):
            raise ValueError("jev_output_not_object")
        routing_trace = (
            output.routing_trace if isinstance(output, _TrustedProviderOutput) else None
        )
        validated_output = dict(output)
        decision = _validate_output(
            validated_output,
            skill_ids={card["id"] for card in skills},
            agent_ids={card["id"] for card in agents},
            capability_ids={card["id"] for card in capabilities},
            threshold=min(1.0, max(0.0, threshold)),
            policy_version=policy_version,
            catalog_version_value=version,
            latency_ms=elapsed,
            decision_id=decision_id,
            forbid_agent_with_skills={
                card["id"]
                for card in skills
                if str((card.get("requires") or {}).get("agent") or "")
                == "forbidden"
            },
            routing_trace=routing_trace,
        )
    except TimeoutError:
        decision = _null_decision(reason="TIMEOUT", policy_version=policy_version,
                                  catalog_version_value=version,
                                  latency_ms=(time.perf_counter() - started) * 1000,
                                  decision_id=decision_id)
    except (error.URLError, OSError, RuntimeError, ValueError, json.JSONDecodeError):
        decision = _null_decision(reason="PROVIDER_UNAVAILABLE", policy_version=policy_version,
                                  catalog_version_value=version,
                                  latency_ms=(time.perf_counter() - started) * 1000,
                                  decision_id=decision_id)
    if decision.validated:
        with _CACHE_LOCK:
            _CACHE[digest] = (now, decision)
            while len(_CACHE) > 512:
                _CACHE.popitem(last=False)
    return decision
