"""Planned media binds quantity and paragraph positions to reviewed source bytes."""
import copy
import hashlib
import json

import pytest

from backend.services.knowledge_publication_store import (
    PublicationError, PublicationStore, reader_sections, receipt_set_hash,
    required_publication_media, validate_bundle, validate_illustration_plan,
)
from publication_editorial_fixture import approve_fixture
from test_daily_publication import add_daily_media, at, bundle, ready


def plan_for(body, count):
    return {"body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "reason": "测试插图按阅读需要安排；零图表示纯文字足够。",
            "illustrations": [{"role": f"illustration_{i:02d}", "after_paragraph": f"独立测试段落{i}。",
                               "caption": f"图{i}，艺术示意", "alt": "图像描述", "purpose": "帮助理解位置关系"}
                              for i in range(1, count + 1)]}


@pytest.mark.parametrize("count", [0, 1, 3, 5])
def test_planned_media_survives_review_release_and_readback(tmp_path, count, monkeypatch):
    store = PublicationStore(tmp_path)
    value = bundle()
    value["body"] += "\n\n" + "\n\n".join(f"独立测试段落{i}。" for i in range(1, 6))
    value = ready(store, value, editorial=False)
    value = add_daily_media(store, value, illustrations=count)
    plan = value["illustration_plan"] = plan_for(value["body"], count)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    value["source_receipts"].append(store.ingest_file(path, "publication_illustration_plan"))
    value["source_snapshot_hash"] = receipt_set_hash(value["source_receipts"])
    value = approve_fixture(store, value)
    assert not validate_bundle(value)[1]
    store.stage(value, now=at(10))
    store.release_due(now=at(12))
    published = store.published(now=at(12))
    assert len(published) == 1
    item = published[0]
    import asyncio
    from backend.api import subscriptions
    from backend.services.knowledge_publication_store import PUBLICATION_CATEGORY
    monkeypatch.setenv("KNOWLEDGE_PUBLICATION_DIR", str(tmp_path))
    # A section that mentions an anchor as a substring must not receive its image.
    monkeypatch.setattr(subscriptions, "reader_sections", lambda body, **kwargs:
        reader_sections(body, **kwargs) + [{"id": "mention-only", "title": "提及", "level": 2,
            "markdown": "前文提到独立测试段落1。这里并非插图锚点。"}])
    _, projected = asyncio.run(subscriptions._available_book_body(
        {"tenant_key": "fixture", "visible_categories": frozenset({PUBLICATION_CATEGORY})}, item["publication_id"]))
    assert len(projected["illustrations"]) == count
    assert all(image["section_id"] != "mention-only" for image in projected["illustrations"])
    assert all(image["content_version"] == projected["content_version"] for image in projected["illustrations"])
    status = store.status_report(now=at(12))["items"][0]
    assert set(status["media_roles"]) == required_publication_media(value)
    assert status["expected_media_roles"] == status["media_roles"]
    for image in plan["illustrations"]:
        assert sum(image["after_paragraph"] in s["markdown"] for s in reader_sections(item["body"])) == 1
        data = store.get_published_media(item["publication_id"], image["role"], now=at(12))
        assert data is not None
        response = asyncio.run(subscriptions.knowledge_publication_media(
            item["publication_id"], image["role"], {"visible_categories": frozenset({PUBLICATION_CATEGORY})}))
        assert response.body == data[0]
    changed = copy.deepcopy(value)
    changed["illustration_plan"]["reason"] = "tampered after review"
    assert "illustration_plan_not_bound_to_review" in validate_bundle(changed)[1]
    if count:
        changed = copy.deepcopy(value)
        changed["assets"].pop()
        assert "required_publication_media_missing" in validate_bundle(changed)[1]


def test_plan_rejects_stale_ambiguous_and_unbounded_placements():
    body = "独立测试段落1。"
    plan = plan_for(body, 1)
    assert validate_illustration_plan(plan, body) == plan
    for invalid in [dict(plan, body_sha256="0" * 64), dict(plan, illustrations=plan["illustrations"] * 2),
                    dict(plan, illustrations=plan["illustrations"] * 13)]:
        with pytest.raises(PublicationError):
            validate_illustration_plan(invalid, body)
    duplicate_body = body + "\n\n" + body
    with pytest.raises(PublicationError, match="exactly once"):
        validate_illustration_plan(plan_for(duplicate_body, 1), duplicate_body)


@pytest.mark.parametrize("count", [0, 5])
def test_initial_builder_carries_dynamic_plan_and_bound_source(tmp_path, count):
    from PIL import Image
    from scripts import publication_editorial_remote as relay
    from test_publication_editorial_remote import initial_submission
    base, submission = initial_submission(tmp_path)
    body = (base / "body.md").read_text() + "\n\n" + "\n\n".join(f"独立测试段落{i}。" for i in range(1, 6))
    (base / "body.md").write_text(body)
    plan = plan_for(body, count)
    images = []
    roles = required_publication_media({"illustration_plan": plan})
    for role in sorted(roles):
        path = base / f"{role}.jpg"
        if not path.exists():
            Image.new("RGB", (1600, 900), "#445566").save(path)
        images.append({"role": role, "prompt": "synthetic fixture", "final_file": path.name,
                       "sha256": relay.sha(path.read_bytes())})
    relay.save(base / "image-manifest.json", {"illustration_plan": plan, "images": images})
    path = relay.build_initial(submission, base, series_id="ai-toolkit", issue_date="2026-09-24",
                               issue_slot="12:00", format="chapter", owner_policy_id="fixture-policy",
                               writer_session="synthetic-plan-writer")
    _, manifest = relay.load_manifest(path)
    item = manifest["items"][0]
    candidate = json.loads((base / item["bundle_file"]).read_text())
    assert candidate["illustration_plan"] == plan
    assert {role for role in relay.ALL_MEDIA_ROLES if item.get(f"{role}_file")} == roles
    receipt = next(r for r in item["source_files"] if r["kind"] == "publication_illustration_plan")
    assert receipt["sha256"] == relay.sha(relay.encoded(plan))
    from scripts.publication_scheduler_watchdog import _material_hash
    assert len(_material_hash(item)) == 64
    if count:
        invalid = copy.deepcopy(item)
        invalid.pop("illustration_05_sha256")
        with pytest.raises(ValueError, match="material hash input missing"):
            _material_hash(invalid)
