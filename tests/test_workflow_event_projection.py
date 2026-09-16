import pytest

from backend.models.workflow import WorkflowDefinition, WorkflowExecution
from backend.services.workflow_executor import (
    artifact_identity_metadata,
    contiguous_bridge_events,
)


def test_bridge_events_are_sorted_deduplicated_and_contiguous():
    events = [
        {"seq": 3, "event_id": "run:3"},
        {"seq": 2, "event_id": "run:2"},
        {"seq": 2, "event_id": "run:2"},
        {"seq": 1, "event_id": "run:1"},
    ]
    assert [event["seq"] for event in contiguous_bridge_events(events, 0)] == [1, 2, 3]
    assert [event["seq"] for event in contiguous_bridge_events(events, 1)] == [2, 3]


def test_bridge_event_gap_is_not_projected():
    with pytest.raises(RuntimeError, match="event gap"):
        contiguous_bridge_events(
            [{"seq": 4, "event_id": "run:4"}],
            2,
        )


def test_artifact_identity_uses_server_owned_workflow_scope():
    metadata = artifact_identity_metadata(
        WorkflowExecution(tenant_key="tenant-a"),
        WorkflowDefinition(
            created_by="signed-owner",
            source_client_session_id="session-a",
        ),
        2,
    )
    assert metadata == {
        "tenant_key": "tenant-a",
        "owner_id": "signed-owner",
        "source_client_session_id": "session-a",
        "generation": 2,
    }
