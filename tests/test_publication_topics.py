"""Config-only topics and multiple occurrences use the existing publication store."""
from __future__ import annotations

import copy
from datetime import datetime
import json

import pytest

from backend.services import knowledge_publication_store as publications
from scripts.publication_daily_completion import evaluate
from scripts import publication_release_remote as release
from scripts.publication_release_remote import _status, _summary
from test_daily_publication import add_daily_media, bundle, ready


def topic(monkeypatch):
    value = {
        "id": "new-reader-topic", "title": "随时可以添加的新专题", "kind": "daily",
        "enabled": True, "cover_theme": "history", "genre": "feature",
        "release_times": ["08:00", "13:00", "20:00"], "execution_enabled": False,
    }
    monkeypatch.setattr(publications, "SERIES", {value["id"]: value})
    return value


def test_config_added_topic_has_three_independent_idempotent_publications(tmp_path, monkeypatch):
    value = topic(monkeypatch)
    day = "2026-09-26"
    store = publications.PublicationStore(tmp_path / "publications")
    editions = []
    for slot in value["release_times"]:
        occurrence = publications.publication_slot(value["id"], day, slot)
        draft = bundle(series=value["id"], day=day, issue_slot=slot,
                       release_at=occurrence["release_at"])
        draft = add_daily_media(store, draft)
        prepared = ready(store, draft)
        edition = store.stage(prepared)
        assert edition["state"] == "scheduled"
        assert store.stage(prepared)["edition_id"] == edition["edition_id"]
        editions.append(edition)
    assert len({item["issue_id"] for item in editions}) == 3
    noon = datetime.fromisoformat(day + "T12:00:00+08:00")
    first = store.release_due(now=noon)
    assert first["released"] == [editions[0]["edition_id"]]
    assert store.release_due(now=noon)["released"] == []
    assert store.missing(noon) == []  # Future scheduled occurrences are not overdue.
    monkeypatch.setattr(release, "_today", lambda: day)
    partial = _summary(store.status_report(now=noon))
    assert partial["today"]["expected"] == 3
    assert partial["today"]["published"] == 1
    assert evaluate(partial)[1] == 2
    final_time = datetime.fromisoformat(day + "T21:00:00+08:00")
    assert len(store.release_due(now=final_time)["released"]) == 2
    report = store.status_report(now=final_time)
    parsed = _status(json.dumps({"ok": True, "result": report}), 0)
    monkeypatch.setattr(release, "_today", lambda: day)
    summary = _summary(parsed)
    assert summary["today"]["expected"] == 3
    assert summary["today"]["published"] == 3
    assert evaluate(summary)[1] == 0
    for edition in editions:
        assert store.get_published(edition["publication_id"], now=final_time)["content_hash"] == edition["content_hash"]
        for role in publications.PUBLICATION_MEDIA:
            assert store.get_published_media(edition["publication_id"], role, now=final_time)


def test_disable_topic_preserves_history_and_stops_new_writes_and_due_release(tmp_path, monkeypatch):
    value = topic(monkeypatch)
    day = "2026-09-26"
    store = publications.PublicationStore(tmp_path / "publications")
    staged = []
    for slot in ("08:00", "13:00"):
        draft = bundle(series=value["id"], day=day, issue_slot=slot,
                       release_at=publications.publication_slot(value["id"], day, slot)["release_at"])
        staged.append(store.stage(ready(store, add_daily_media(store, draft))))
    store.release_due(now=datetime.fromisoformat(day + "T09:00:00+08:00"))
    value["enabled"] = False
    later = datetime.fromisoformat(day + "T21:00:00+08:00")
    assert store.expected_issues(later) == []
    assert store.get_published(staged[0]["publication_id"], now=later)
    assert store.release_due(now=later)["released"] == []
    with pytest.raises(publications.PublicationError, match="disabled"):
        publications.validate_bundle(bundle(series=value["id"], day=day))


def test_legacy_noon_identity_survives_new_slots(monkeypatch, tmp_path):
    legacy = copy.deepcopy(publications.SERIES["ai-history"])
    legacy["release_times"] = ["08:00", "12:00", "20:00"]
    monkeypatch.setitem(publications.SERIES, "ai-history", legacy)
    slot = publications.publication_slot("ai-history", "2026-09-26", "12:00")
    assert slot["issue_key"] == "2026-09-26"
    normalized, _ = publications.validate_bundle(ready(publications.PublicationStore(tmp_path), bundle(series="ai-history", day="2026-09-26"), editorial=False))
    assert normalized["issue_key"] == "2026-09-26"
    assert publications.PublicationStore.ids("ai-history", slot["issue_key"], 1) == publications.PublicationStore.ids("ai-history", "2026-09-26", 1)
    with pytest.raises(publications.PublicationError, match="explicit"):
        publications.publication_slot("ai-history", "2026-09-26")


@pytest.mark.parametrize("mutation", ["duplicate", "bad_slot", "duplicate_schedule", "profile"])
def test_topic_configuration_fails_closed(tmp_path, mutation):
    first = {"id": "new-topic", "title": "新主题", "kind": "daily", "release_times": ["08:00"],
             "workflow_schedule_id": "schedule-one"}
    second = {**first, "id": "other-topic", "workflow_schedule_id": "schedule-two"}
    if mutation == "duplicate":
        second["id"] = first["id"]
    elif mutation == "bad_slot":
        first["release_times"] = ["25:00"]
    elif mutation == "duplicate_schedule":
        second["workflow_schedule_id"] = first["workflow_schedule_id"]
    else:
        first["author_profile"] = "story"
    path = tmp_path / "topics.json"
    path.write_text(json.dumps({"series": [first, second]}))
    with pytest.raises(ValueError):
        publications.load_publication_series(path)


def test_completion_requires_every_slot_and_does_not_assume_four_topics():
    roles = list(publications.PUBLICATION_MEDIA)
    slot = {"issue_key": "2026-09-26T08:00", "published": 1,
            "body_available": True, "media_roles": roles}
    summary = {"today": {"expected": 2, "published": 1, "by_series": {
        "arbitrary-topic": {"expected": 2, "published": 1, "body_available": True,
                            "media_roles": roles, "slots": [slot]},
    }}, "issues": {"missing": []}}
    assert evaluate(summary)[1] == 2
    summary["today"]["published"] = 2
    summary["today"]["by_series"]["arbitrary-topic"]["published"] = 2
    summary["today"]["by_series"]["arbitrary-topic"]["slots"].append(dict(slot))
    assert evaluate(summary)[1] == 2  # A duplicate occurrence cannot fill another slot.


def test_series_review_policy_enforced_without_cli_flag(tmp_path, monkeypatch):
    from test_publication_editorial import synthetic_brief
    value = topic(monkeypatch)
    value.update(review_policy="story-supervision-v2", author_profile="story")
    store = publications.PublicationStore(tmp_path / "publication")
    draft = bundle(series=value["id"], issue_slot="08:00", release_at="2026-09-08T08:00:00+08:00")
    draft = ready(store, add_daily_media(store, draft), editorial=False)
    draft["quality_contract"] = {"format": "chapter", "writer_sessions": ["hermes:story-writer"], "learning_objectives": ["验证栏目审核策略不能被恢复流程绕过"], "editorial_brief": synthetic_brief(), "research_gaps": []}
    prepared = store.prepare_editorial(draft)
    assert prepared["quality_contract"]["review_policy"] == "story-supervision-v2"
