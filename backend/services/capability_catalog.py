"""Deterministic PCM catalog loading and QCP contract validation."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1] / "contracts" / "product-capabilities"
REQUIRED_CAPABILITY_FIELDS = {
    "id", "version", "domain", "description", "positive_examples",
    "negative_examples", "input_schema", "output_schema", "effect", "risk",
    "confirmation", "preconditions", "policy_ref", "handler_binding",
    "idempotency", "result_event", "renderer", "renderer_version", "tests",
    "implementation_status", "receipt",
}
IMPLEMENTED_HANDLERS = {
    "knowledge.search", "knowledge.read", "knowledge.create", "knowledge.update",
    "knowledge.merge", "knowledge.archive", "knowledge.restore",
    "client.knowledge.navigation", "workflow.open", "workflow.status",
    "workflow.create", "workflow.start", "presentation.create_from_document",
    "presentation.create_from_text",
    "document.word.create_from_text", "report.research.create_from_text",
    "paper.academic.create_from_text",
    "artifact.open", "artifact.download",
    "artifact.consume_structured",
    "bookshelf.search", "bookshelf.subscribe", "bookshelf.open",
    "memory.list", "memory.create", "memory.update", "memory.delete",
    "profile.read", "profile.update",
    "agent.list", "agent.create", "agent.update", "agent.delete",
    "agent.evaluate", "agent.evaluation_status",
}


class CapabilityContractError(ValueError):
    pass


def _yaml(name: str) -> dict[str, Any]:
    value = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CapabilityContractError(f"{name}: root must be an object")
    return value


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    manifest = _yaml("manifest.yaml")
    capability_files = manifest["capabilities"]
    if isinstance(capability_files, str):
        capability_files = [capability_files]
    capability_documents = [_yaml(str(name)) for name in capability_files]
    catalog = {
        "protocol": manifest.get("protocol"),
        "version": manifest.get("version"),
        "capabilities": [
            capability
            for document in capability_documents
            for capability in document["capabilities"]
        ],
        "agent_descriptions": next(
            (
                document["agent_descriptions"]
                for document in capability_documents
                if document.get("agent_descriptions")
            ),
            {},
        ),
        "events": _yaml(str(manifest["events"]))["events"],
        "renderers": _yaml(str(manifest["renderers"]))["renderers"],
        "bindings": _yaml(str(manifest["bindings"]))["bindings"],
        "policies": _yaml(str(manifest["policies"]))["policies"],
        "consumptions": _yaml(str(manifest["consumptions"]))["consumptions"],
    }
    validate_catalog(catalog)
    return catalog


def _unique(items: list[dict[str, Any]], key: str, label: str) -> set[Any]:
    values = [item.get(key) for item in items]
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise CapabilityContractError(f"duplicate {label}: {duplicates}")
    return set(values)


def validate_catalog(catalog: dict[str, Any]) -> None:
    capabilities = catalog.get("capabilities") or []
    events = catalog.get("events") or []
    renderers = catalog.get("renderers") or []
    bindings = catalog.get("bindings") or []
    policies = catalog.get("policies") or []
    consumptions = catalog.get("consumptions") or []
    agent_descriptions = catalog.get("agent_descriptions") or {}
    required_description_parts = {"function", "suitable", "boundary"}
    if not isinstance(agent_descriptions, dict) or not agent_descriptions:
        raise CapabilityContractError("agent descriptions required")
    rendered_descriptions: set[str] = set()
    rendered_parts: set[tuple[str, str, str]] = set()
    for agent_id, description in agent_descriptions.items():
        if not isinstance(description, dict) or set(description) != required_description_parts:
            raise CapabilityContractError(f"{agent_id}: invalid agent description fields")
        parts = (
            str(description["function"]).strip(),
            str(description["suitable"]).strip(),
            str(description["boundary"]).strip(),
        )
        if any(not part for part in parts) or len(set(parts)) != 3:
            raise CapabilityContractError(f"{agent_id}: agent description parts must be distinct")
        rendered = f"功能：{parts[0]}。适合：{parts[1]}。边界：{parts[2]}。"
        if len(rendered) > 100:
            raise CapabilityContractError(f"{agent_id}: agent description exceeds 100 characters")
        if rendered in rendered_descriptions or parts in rendered_parts:
            raise CapabilityContractError(f"{agent_id}: duplicate agent description")
        rendered_descriptions.add(rendered)
        rendered_parts.add(parts)
    capability_ids = _unique(capabilities, "id", "capability ids")
    if len(capability_ids) != len(capabilities):
        raise CapabilityContractError("capability id missing")
    event_ids = _unique(events, "id", "event ids")
    _unique(renderers, "id", "renderer ids")
    binding_ids = _unique(bindings, "id", "binding ids")
    handler_names = _unique(bindings, "handler", "handler bindings")
    policy_ids = _unique(policies, "id", "policy ids")
    _unique(consumptions, "id", "consumption ids")
    renderer_versions = {(item["id"], item["version"]) for item in renderers}
    for renderer in renderers:
        if (renderer.get("fallback"), renderer.get("fallback_version")) not in renderer_versions:
            raise CapabilityContractError(f"invalid renderer fallback: {renderer.get('id')}")
    for capability in capabilities:
        missing = sorted(REQUIRED_CAPABILITY_FIELDS - capability.keys())
        if missing:
            raise CapabilityContractError(f"{capability.get('id')}: missing {missing}")
        if capability["handler_binding"] not in binding_ids:
            raise CapabilityContractError(f"{capability['id']}: invalid binding")
        binding = next(item for item in bindings if item["id"] == capability["handler_binding"])
        if capability["implementation_status"] == "implemented" and binding["handler"] not in IMPLEMENTED_HANDLERS:
            raise CapabilityContractError(f"{capability['id']}: implemented handler unavailable")
        if capability["policy_ref"] not in policy_ids:
            raise CapabilityContractError(f"{capability['id']}: invalid policy")
        if capability["result_event"] not in event_ids:
            raise CapabilityContractError(f"{capability['id']}: invalid event")
        if (capability["renderer"], capability["renderer_version"]) not in renderer_versions:
            raise CapabilityContractError(f"{capability['id']}: invalid renderer")
        if capability["effect"] != "read" and capability["effect"] != "client":
            if (
                capability["confirmation"] != "required"
                or capability["idempotency"] != "required"
                or capability["receipt"] != "required"
            ):
                raise CapabilityContractError(f"{capability['id']}: unsafe mutation contract")
        if not capability["tests"]:
            raise CapabilityContractError(f"{capability['id']}: tests required")
    if len(handler_names) != len(bindings):
        raise CapabilityContractError("handler binding missing")
    for consumption in consumptions:
        if consumption.get("status") not in {"implemented", "partial", "unverified"}:
            raise CapabilityContractError(f"{consumption.get('id')}: invalid consumption status")
        refs = consumption.get("implementation_refs") or []
        gates = consumption.get("gates") or []
        if not refs or len(refs) != len(set(refs)) or len(gates) != len(set(gates)):
            raise CapabilityContractError(f"{consumption.get('id')}: invalid consumption references")


def agent_description_for(agent_id: str) -> dict[str, str]:
    """Return structured PCM UI copy, never a private-prompt excerpt."""
    descriptions = load_catalog()["agent_descriptions"]
    value = descriptions.get(agent_id) or descriptions["main_agent"]
    return {key: str(value[key]) for key in ("function", "suitable", "boundary")}


def search_capabilities(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    terms = [term for term in re.split(r"\s+", query.casefold().strip()) if term]
    ranked = []
    for capability in load_catalog()["capabilities"]:
        haystack = " ".join([
            capability["id"], capability["domain"], capability["description"],
            *capability["positive_examples"],
        ]).casefold()
        score = sum(term in haystack for term in terms)
        if not terms or score:
            ranked.append((score, capability["id"], capability))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [{
        key: capability[key]
        for key in ("id", "version", "domain", "description", "effect", "risk", "implementation_status")
    } for _, _, capability in ranked[:max(1, min(limit, 10))]]


def describe_capability(capability_id: str) -> dict[str, Any] | None:
    return next(
        (dict(item) for item in load_catalog()["capabilities"] if item["id"] == capability_id),
        None,
    )


def validate_instance(value: Any, schema: dict[str, Any], path: str = "input") -> None:
    """Validate the small JSON Schema subset used by PCM without a new dependency."""
    expected = schema.get("type")
    valid = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }.get(expected, True)
    if not valid:
        raise CapabilityContractError(f"{path}: expected {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise CapabilityContractError(f"{path}: unsupported value")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise CapabilityContractError(f"{path}: too short")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise CapabilityContractError(f"{path}: too long")
        if schema.get("pattern") and not re.fullmatch(str(schema["pattern"]), value):
            raise CapabilityContractError(f"{path}: invalid format")
    if isinstance(value, int) and not isinstance(value, bool):
        if value < int(schema.get("minimum", value)) or value > int(schema.get("maximum", value)):
            raise CapabilityContractError(f"{path}: outside bounds")
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        missing = [key for key in schema.get("required") or [] if key not in value]
        if missing:
            raise CapabilityContractError(f"{path}: missing {missing}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise CapabilityContractError(f"{path}: unsupported fields {unknown}")
        for key, item in value.items():
            if key in properties:
                validate_instance(item, properties[key], f"{path}.{key}")
    if isinstance(value, list) and schema.get("items"):
        for index, item in enumerate(value):
            validate_instance(item, schema["items"], f"{path}[{index}]")


def catalog_digest() -> str:
    import hashlib
    return hashlib.sha256(json.dumps(load_catalog(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def invoke_capability(
    capability_id: str,
    data: dict[str, Any],
    *,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Execute read/client effects only; mutations require the durable Gateway flow.

    Mutation attempts receive a stable upgrade error; no boolean grants authority.
    """
    capability = describe_capability(capability_id)
    if capability is not None and capability["confirmation"] == "required":
        return _failure(
            capability_id,
            "confirmation_protocol_upgrade_required",
            "Create a durable proposal and confirm it with a one-time token",
        )
    return await execute_verified_capability(
        capability_id, data, payload=payload, idempotency_key=idempotency_key
    )


async def execute_verified_capability(
    capability_id: str,
    data: dict[str, Any],
    *,
    payload: dict[str, Any],
    idempotency_key: str | None,
    invocation_id: str | None = None,
    resource_versions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal dispatcher called only after Gateway confirmation or for reads."""
    from fastapi import HTTPException
    from backend.capability_handlers import HANDLERS, verify_resource_versions

    capability = describe_capability(capability_id)
    if capability is None:
        return _failure(capability_id, "capability_not_found", "Capability is not allowlisted")
    if capability["implementation_status"] != "implemented":
        return _failure(capability_id, "capability_not_executable", "Capability is discovery-only in this version")
    try:
        validate_instance(data, capability["input_schema"])
        if capability["idempotency"] == "required" and not idempotency_key:
            raise CapabilityContractError("idempotency_key required")
        binding = next(
            item for item in load_catalog()["bindings"]
            if item["id"] == capability["handler_binding"]
        )["handler"]
        handler = HANDLERS.get(binding)
        if handler is None:
            return _failure(capability_id, "handler_unavailable", "Capability handler is unavailable")
        if resource_versions is not None:
            await verify_resource_versions(
                capability_id, data, payload, dict(resource_versions)
            )
        result = await handler(data, payload, idempotency_key)
        validate_instance(result, capability["output_schema"], "output")
    except CapabilityContractError as exc:
        return _failure(capability_id, "contract_invalid", str(exc))
    except ValidationError:
        return _failure(
            capability_id, "contract_invalid", "Domain input validation failed"
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return _failure(capability_id, str(detail.get("code") or "domain_rejected"), str(detail.get("message") or exc.detail))
    if invocation_id is None:
        invocation_seed = json.dumps(
            {
                "capability_id": capability_id,
                "input": data,
                "idempotency_key": idempotency_key,
                "tenant_key": payload.get("tenant_key"),
                "user_id": payload.get("user_id") or payload.get("sub"),
            },
            sort_keys=True, separators=(",", ":"),
        )
        import hashlib
        invocation_id = "qcp-" + hashlib.sha256(invocation_seed.encode()).hexdigest()[:32]
    event_version = next(
        int(item["version"]) for item in load_catalog()["events"]
        if item["id"] == capability["result_event"]
    )
    event = {"type": capability["result_event"], "version": event_version, "payload": result}
    return {
        "status": "completed",
        "capability_id": capability_id,
        "events": [event],
        "receipt": {
            "version": 1,
            "invocation_id": invocation_id,
            "capability_version": capability["version"],
            "status": "completed",
            "event_type": capability["result_event"],
            "event_version": event_version,
            "resource_versions": dict(resource_versions or {}),
        },
        "error": None,
    }


def _failure(capability_id: str, code: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed", "capability_id": capability_id, "events": [],
        "receipt": None, "error": {"code": code, "message": message[:300]},
    }
