from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import delete

from backend.db import SessionLocal, init_db
from backend.models.tenant import (
    KnowledgeCatalog,
    KnowledgeSubscription,
    TenantEntitlementSnapshot,
)
from backend.services.knowledge_policy import (
    KnowledgeScopeDenied,
    mint_capability,
    resolve_policy,
    verify_capability,
)


CATALOG = [
    {"category": "public", "path_prefix": "public/", "title": "Public", "doc_count": 1, "open": True},
    {"category": "premium", "path_prefix": "premium/", "title": "Premium", "doc_count": 1, "open": True},
    {"category": "private-a", "path_prefix": "private-a/", "title": "Private", "doc_count": 1, "open": True},
]


@pytest_asyncio.fixture
async def policy_rows():
    await init_db()
    async with SessionLocal() as db:
        await db.execute(delete(KnowledgeSubscription))
        await db.execute(delete(TenantEntitlementSnapshot))
        await db.execute(delete(KnowledgeCatalog))
        db.add_all([
            KnowledgeCatalog(category="public", path_prefix="public/", title="Public", security_level="green"),
            KnowledgeCatalog(
                category="premium", path_prefix="premium/", title="Premium",
                security_level="yellow", entitlement_key="premium_research",
            ),
            KnowledgeCatalog(
                category="private-a", path_prefix="private-a/", title="Private",
                security_level="red", owner_tenant="tenant-a",
            ),
            KnowledgeSubscription(tenant_key="tenant-b", category="premium"),
            TenantEntitlementSnapshot(
                tenant_key="tenant-a", org_id="org-a", plan_id="pro", status="active",
                knowledge_entitlements=["premium_research"], entitlement_version=7,
                effective_until=datetime.now(timezone.utc) + timedelta(days=1),
                synced_at=datetime.now(timezone.utc),
            ),
        ])
        await db.commit()
    yield


@pytest.mark.asyncio
async def test_all_active_categories_are_readable_without_tenant_or_plan_gates(policy_rows):
    async with SessionLocal() as db:
        tenant_a, _ = await resolve_policy(db, tenant_key="tenant-a", org_id="org-a", catalog=CATALOG)
        tenant_b, _ = await resolve_policy(db, tenant_key="tenant-b", org_id="org-b", catalog=CATALOG)
    assert tenant_a.effective_categories == frozenset({"public", "premium", "private-a"})
    assert tenant_b.wallet == frozenset({"premium"})
    assert tenant_b.effective_categories == frozenset({"public", "premium", "private-a"})


@pytest.mark.asyncio
async def test_effective_knowledge_projection_matches_runtime_policy(policy_rows):
    from backend.api.catalog import _effective_knowledge_items

    async with SessionLocal() as db:
        policy, metadata = await resolve_policy(
            db, tenant_key="tenant-a", org_id="org-a", catalog=CATALOG,
            is_super_admin=True, allow_admin_bypass=False,
        )
    items = _effective_knowledge_items(policy, metadata, CATALOG)
    assert {item["category"] for item in items} == {"public", "premium", "private-a"}
    assert next(item for item in items if item["category"] == "premium")["source"] == "subscription"
    assert next(item for item in items if item["category"] == "private-a")["source"] == "tenant_private"


@pytest.mark.asyncio
async def test_stale_authen_projection_does_not_gate_knowledge_reads(policy_rows):
    async with SessionLocal() as db:
        snapshot = await db.get(TenantEntitlementSnapshot, "tenant-a")
        snapshot.synced_at = datetime.now(timezone.utc) - timedelta(minutes=16)
        await db.commit()
        policy, _ = await resolve_policy(db, tenant_key="tenant-a", org_id="org-a", catalog=CATALOG)
    assert policy.entitlement_stale is True
    assert policy.effective_categories == frozenset({"public", "premium", "private-a"})


@pytest.mark.asyncio
async def test_capability_is_signed_scoped_and_bound_to_policy(policy_rows):
    async with SessionLocal() as db:
        policy, _ = await resolve_policy(db, tenant_key="tenant-a", org_id="org-a", catalog=CATALOG)
    token = mint_capability(
        policy, subject_id="run-1", entry_point="workflow",
        requested_scopes=["premium"], user_id="user-a",
        sources=("tenant_knowledge", "user_notes"),
    )
    claims = verify_capability(token)
    assert claims["tenant_key"] == "tenant-a"
    assert claims["subject_id"] == "run-1"
    assert claims["scopes"] == ["premium"]
    assert claims["user_id"] == "user-a"
    assert claims["sources"] == ["tenant_knowledge", "user_notes"]
    payload, signature = token.split(".", 1)
    tampered = ("A" if payload[0] != "A" else "B") + payload[1:] + "." + signature
    with pytest.raises(KnowledgeScopeDenied):
        verify_capability(tampered)


@pytest.mark.asyncio
async def test_guest_read_policy_is_not_color_or_tenant_gated(policy_rows, monkeypatch):
    monkeypatch.setattr("backend.services.knowledge_policy.GUEST_GREEN_CATEGORIES", frozenset({"public"}))
    async with SessionLocal() as db:
        policy, _ = await resolve_policy(
            db, tenant_key="demo-guest", org_id="", catalog=CATALOG, is_guest=True
        )
    assert policy.effective_categories == frozenset({"public", "premium", "private-a"})
