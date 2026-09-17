from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.capability_catalog import (
    execute_verified_capability,
    invoke_capability,
    load_catalog,
)
from backend.services.capability_gateway import (
    confirm_capability_proposal,
    create_capability_proposal,
)
from backend.services.tenant_hermes_sandbox import (
    ensure_tenant_sandbox,
    list_sandbox_skills,
    read_sandbox_skill,
)


AUTH = {
    "tenant_key": "tenant-skill",
    "user_id": "user-skill",
    "sub": "user-skill",
    "principal_type": "human",
    "amr": ["password"],
}
CONTENT = """---
name: qa-skill
description: Use when the user requests tenant QA checks. Do not use for production deployment.
skill_path: software-development/testing
skill_level: simple
trigger_phrases:
  - run tenant QA
negative_phrases:
  - deploy production
---
# QA Skill
Run the bounded QA check.
"""
UPDATED = CONTENT.replace("bounded QA check", "updated bounded QA check")


def test_skill_contracts_are_registered_and_writes_require_gateway_confirmation():
    catalog = {item["id"]: item for item in load_catalog()["capabilities"]}
    assert {"skill.list", "skill.create", "skill.update", "skill.delete"} <= set(catalog)
    for capability_id in {"skill.create", "skill.update", "skill.delete"}:
        assert catalog[capability_id]["confirmation"] == "required"
        assert catalog[capability_id]["idempotency"] == "required"
        assert catalog[capability_id]["receipt"] == "required"


@pytest.mark.asyncio
async def test_skill_mutation_cannot_use_legacy_direct_invoke():
    result = await invoke_capability(
        "skill.create", {"name": "qa-skill", "content": CONTENT},
        payload=AUTH, idempotency_key="skill-create-unsafe",
    )
    assert result["error"]["code"] == "confirmation_protocol_upgrade_required"


@pytest.mark.asyncio
async def test_skill_create_uses_bound_proposal_confirmation_and_idempotent_receipt():
    payload = {**AUTH, "knowledge_policy_version": "skill-policy-v1"}
    arguments = {"name": "qa-skill", "content": CONTENT}

    async def proposal():
        return await create_capability_proposal(
            "skill.create", arguments, payload=payload,
            session_id="skill-session", request_id="skill-request",
            idempotency_key="skill-create-durable", renderer_version="qcp-ios@1",
        )

    first = await proposal()
    event = first["events"][0]["payload"]
    denied = await confirm_capability_proposal(
        event["proposal_id"], event["confirmation_token"],
        payload={**payload, "tenant_key": "other-tenant"}, session_id="skill-session",
    )
    assert denied["error"]["code"] == "confirmation_invalid"

    verified = {
        "name": "qa-skill", "sha256": "a" * 64,
        "scope": "tenant", "verified": True,
    }
    with (
        patch("backend.api.chat._resolve_chat_policy", new=AsyncMock(return_value=object())),
        patch("backend.services.hermes_sandbox_catalog.create_tenant_skill", new=AsyncMock(return_value=verified)) as create,
    ):
        completed = await confirm_capability_proposal(
            event["proposal_id"], event["confirmation_token"],
            payload=payload, session_id="skill-session",
        )
        second = await proposal()
        second_event = second["events"][0]["payload"]
        replay = await confirm_capability_proposal(
            second_event["proposal_id"], second_event["confirmation_token"],
            payload=payload, session_id="skill-session",
        )
    assert completed["status"] == "completed"
    assert completed["receipt"]["status"] == "completed"
    assert replay == completed
    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_skill_handlers_reuse_signed_sandbox_facade_and_forward_idempotency():
    policy = object()
    created = {"name": "qa-skill", "sha256": "a" * 64, "scope": "tenant", "verified": True}
    updated = {**created, "sha256": "b" * 64}
    deleted = {"name": "qa-skill", "deleted": True, "verified": True}
    with (
        patch("backend.api.chat._resolve_chat_policy", new=AsyncMock(return_value=policy)),
        patch("backend.services.hermes_sandbox_catalog.fetch_skill_catalog", new=AsyncMock(return_value=[{"name": "qa-skill", "scope": "tenant"}])) as listed,
        patch("backend.services.hermes_sandbox_catalog.create_tenant_skill", new=AsyncMock(return_value=created)) as create,
        patch("backend.services.hermes_sandbox_catalog.update_tenant_skill", new=AsyncMock(return_value=updated)) as update,
        patch("backend.services.hermes_sandbox_catalog.delete_tenant_skill", new=AsyncMock(return_value=deleted)) as delete,
    ):
        list_result = await execute_verified_capability(
            "skill.list", {"owned_only": True}, payload=AUTH, idempotency_key=None
        )
        create_result = await execute_verified_capability(
            "skill.create", {"name": "qa-skill", "content": CONTENT},
            payload=AUTH, idempotency_key="skill-create-1",
        )
        update_result = await execute_verified_capability(
            "skill.update", {"name": "qa-skill", "content": UPDATED},
            payload=AUTH, idempotency_key="skill-update-1",
        )
        delete_result = await execute_verified_capability(
            "skill.delete", {"name": "qa-skill"},
            payload=AUTH, idempotency_key="skill-delete-1",
        )
    assert list_result["events"][0]["payload"]["skills"][0]["name"] == "qa-skill"
    assert create_result["events"][0]["payload"] == created
    assert update_result["events"][0]["payload"] == updated
    assert delete_result["events"][0]["payload"] == deleted
    assert listed.await_args.kwargs["user_id"] == "user-skill"
    assert create.await_args.kwargs["idempotency_key"] == "skill-create-1"
    assert update.await_args.kwargs["idempotency_key"] == "skill-update-1"
    assert delete.await_args.kwargs["idempotency_key"] == "skill-delete-1"


@pytest.mark.asyncio
async def test_skill_contract_rejects_invalid_name_before_domain_call():
    result = await execute_verified_capability(
        "skill.create", {"name": "../escape", "content": CONTENT},
        payload=AUTH, idempotency_key="invalid-name",
    )
    assert result["error"]["code"] == "contract_invalid"


def _sandbox(tmp_path: Path, tenant: str):
    template = tmp_path / "template"
    template.mkdir(exist_ok=True)
    return ensure_tenant_sandbox(
        tenant_key=tenant,
        user_id="owner",
        root=tmp_path / "sandboxes",
        template_root=template,
    )


def test_bridge_primitive_create_update_delete_readback_and_tenant_isolation(tmp_path: Path):
    import scripts.hermes_bridge as bridge

    tenant_a = _sandbox(tmp_path, "tenant-a")
    tenant_b = _sandbox(tmp_path, "tenant-b")
    created = bridge._write_skill_and_verify(
        tenant_a, name="qa-skill", content=CONTENT, replace=False
    )
    assert created["verified"] is True
    assert read_sandbox_skill(tenant_a, "qa-skill") == CONTENT
    assert not any(item["name"] == "qa-skill" for item in list_sandbox_skills(tenant_b))

    updated = bridge._write_skill_and_verify(
        tenant_a, name="qa-skill", content=UPDATED, replace=True
    )
    assert updated["sha256"] != created["sha256"]
    assert read_sandbox_skill(tenant_a, "qa-skill") == UPDATED

    assert bridge.delete_sandbox_skill(tenant_a, "qa-skill") is True
    assert read_sandbox_skill(tenant_a, "qa-skill") is None


def test_bridge_skill_facade_requires_signed_skill_entrypoint(monkeypatch):
    from backend.services.knowledge_policy import KnowledgePolicy, mint_capability
    import scripts.hermes_bridge as bridge

    policy = KnowledgePolicy(
        tenant_key="tenant-a", org_id="org-a", plan_id="pro", plan_status="active",
        wallet=frozenset(), entitled_yellow=frozenset(), effective_categories=frozenset(),
        policy_version="policy-v1", entitlement_stale=False,
    )
    sentinel = object()
    monkeypatch.setattr(bridge, "_tenant_sandbox_from_claims", lambda **_: sentinel)
    skill_token = mint_capability(
        policy, subject_id="skills-user-a", entry_point="skills", user_id="user-a"
    )
    assert bridge._skill_sandbox(skill_token) is sentinel
    chat_token = mint_capability(
        policy, subject_id="chat-user-a", entry_point="chat", user_id="user-a"
    )
    with pytest.raises(bridge.HTTPException) as denied:
        bridge._skill_sandbox(chat_token)
    assert denied.value.status_code == 403


def test_ios_registry_declares_skill_event_fallbacks():
    source = Path("ios/AIPlatformApp/Networking/APIClient.swift").read_text(encoding="utf-8")
    for event in ("skill.snapshot", "skill.changed"):
        assert f'"{event}": .init(path: .answer' in source
