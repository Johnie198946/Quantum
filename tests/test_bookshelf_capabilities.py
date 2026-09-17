from unittest.mock import AsyncMock, patch

import pytest

from backend.services.capability_catalog import execute_verified_capability, load_catalog


AUTH = {"tenant_key": "tenant-bookshelf", "user_id": "reader-bookshelf"}
BOOK = {
    "id": "book-1",
    "title": "AI Product",
    "author": "Author",
    "summary": "Product strategy",
}
BODY = {
    "book_id": "book-1",
    "title": "AI Product",
    "author": "Author",
    "content_version": "a" * 64,
    "edition": 1,
    "citation": "knowledge:wiki/book.md",
    "sections": [{"id": "s1", "title": "Intro", "level": 1, "markdown": "Body"}],
}


def test_bookshelf_contracts_are_registered_on_the_shared_gateway():
    catalog = {item["id"]: item for item in load_catalog()["capabilities"]}
    assert set(catalog) >= {"bookshelf.search", "bookshelf.subscribe", "bookshelf.open"}
    assert catalog["bookshelf.subscribe"]["confirmation"] == "required"
    assert catalog["bookshelf.subscribe"]["idempotency"] == "required"
    assert catalog["bookshelf.subscribe"]["receipt"] == "required"


@pytest.mark.asyncio
async def test_bookshelf_search_filters_only_the_authorized_catalog():
    authorized = {
        "bookshelves": [{"id": "owned", "books": [BOOK, {**BOOK, "id": "book-2", "title": "Cooking"}]}],
        "public_collections": [],
        "owner_private_collections": [],
    }
    with patch(
        "backend.api.subscriptions.knowledge_bookshelves",
        new=AsyncMock(return_value=authorized),
    ):
        result = await execute_verified_capability(
            "bookshelf.search", {"query": "AI product"},
            payload=AUTH, idempotency_key=None,
        )
    assert result["status"] == "completed"
    assert [item["id"] for item in result["events"][0]["payload"]["items"]] == ["book-1"]


@pytest.mark.asyncio
async def test_bookshelf_open_and_subscribe_reuse_existing_domain_functions():
    with patch(
        "backend.api.subscriptions.knowledge_book_body",
        new=AsyncMock(return_value=BODY),
    ), patch(
        "backend.api.subscriptions.subscribe_book",
        new=AsyncMock(return_value={"book": BOOK, "content_version": "a" * 64}),
    ):
        opened = await execute_verified_capability(
            "bookshelf.open", {"book_id": "book-1"},
            payload=AUTH, idempotency_key=None,
        )
        subscribed = await execute_verified_capability(
            "bookshelf.subscribe", {"book_id": "book-1", "action": "subscribe"},
            payload=AUTH, idempotency_key="bookshelf-subscribe-1",
        )
    assert opened["status"] == subscribed["status"] == "completed"
    assert opened["receipt"]["event_type"] == "bookshelf.opened"
    assert subscribed["receipt"]["event_type"] == "bookshelf.subscription_changed"
    assert subscribed["events"][0]["payload"]["book_id"] == "book-1"


@pytest.mark.asyncio
async def test_bookshelf_subscribe_rejects_unknown_action_before_handler():
    result = await execute_verified_capability(
        "bookshelf.subscribe", {"book_id": "book-1", "action": "steal"},
        payload=AUTH, idempotency_key="bookshelf-invalid-1",
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "contract_invalid"
