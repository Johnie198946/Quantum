from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.services.batch6_refactor_guard import (
    BATCH6_KILL_SWITCH_ENV,
    batch6_execution_killed,
    require_batch6_execution_enabled,
)
from backend.services.qws_session_context import (
    context_changes,
    task_from_card_context,
)
from backend.services.workflow_document_contracts import (
    document_source_constraint_issues,
    document_source_constraints,
    ensure_document_page_breaks,
    workflow_minimum_document_pages,
)
from backend.services.workflow_reviews import REVIEW_KEY, validate_review_document


REPO = Path(__file__).resolve().parents[1]


def test_batch6_kill_switch_is_explicit_and_fail_closed(monkeypatch):
    assert batch6_execution_killed({}) is False
    for value in ("1", "true", "TRUE", "yes", "on"):
        assert batch6_execution_killed({BATCH6_KILL_SWITCH_ENV: value}) is True
    monkeypatch.setenv(BATCH6_KILL_SWITCH_ENV, "1")
    with pytest.raises(HTTPException) as caught:
        require_batch6_execution_enabled("golden")
    assert caught.value.status_code == 503
    assert caught.value.detail == {
        "code": "batch6_execution_kill_switch",
        "component": "golden",
        "retryable": True,
    }


def test_batch6_execution_entrypoints_all_enforce_the_same_kill_switch():
    from backend.api import quantum_workspace, workflows
    from scripts import hermes_bridge

    assert 'require_batch6_execution_enabled("qws_auto_execution")' in inspect.getsource(
        quantum_workspace.start_task_auto_execution
    )
    assert 'require_batch6_execution_enabled("workflow_api")' in inspect.getsource(
        workflows.start_workflow
    )
    assert 'require_batch6_execution_enabled("hermes_workflow_run")' in inspect.getsource(
        hermes_bridge.start_workflow_run
    )


def test_document_contract_golden_behavior_survives_extraction():
    run = {
        "goal": "at least three full pages",
        "source_material": {
            "text": (
                "[S1] 10.1234/example.1\n"
                "[S2] 10.5678/example.2\n"
                "Unverified fail-closed: https://invalid.example/source\n"
                "must contain, in this order: Abstract, Methods and References."
            )
        },
        "nodes": {},
        "plan": {"nodes": []},
    }
    assert document_source_constraints(run) == (
        ["10.1234/example.1", "10.5678/example.2"],
        [
            "https://invalid.example/source",
            "invalid.example/source",
            "invalid.example",
            "source",
        ],
    )
    reply = "Abstract [S1] 10.1234/example.1\nMethods\nReferences"
    assert document_source_constraint_issues(run, reply) == [
        "缺少已核验 DOI：10.5678/example.2",
        "缺少指定来源标签：[S2]",
    ]
    assert workflow_minimum_document_pages(run) == 3
    assert ensure_document_page_breaks("A\n\nB\n\nC", 3) == "A\fB\fC"


def test_qws_session_context_golden_mapping_and_delta():
    context = {
        "task": {
            "qws_task_id": "task-1",
            "dashi_task_id": "task-1",
            "title": "Produce report",
            "status": "IN_PROGRESS",
            "descriptions": [{"source": "qws", "content": "Bound summary"}],
            "assignee": {"name": "Analyst"},
            "qws": {
                "canonical_task_id": "canonical-1",
                "stage_id": "stage-1",
                "workflow_id": "wf-1",
                "binding_kind": "project_planning",
                "deliverables": ["report.md"],
            },
        }
    }
    assert task_from_card_context(context, expected_task_id="task-1") == {
        "id": "task-1",
        "canonical_task_id": "canonical-1",
        "title": "Produce report",
        "summary": "Bound summary",
        "status": "IN_PROGRESS",
        "assignee_role": "Analyst",
        "deliverables": ["report.md"],
        "stage_id": "stage-1",
        "workflow_id": "wf-1",
        "binding_kind": "project_planning",
    }
    assert context_changes(
        {"tasks": [{"id": "a", "status": "TODO"}]},
        {"tasks": [{"id": "a", "status": "DONE"}, {"id": "b"}]},
    ) == [
        {
            "path": "tasks[id=a].status",
            "change": "updated",
            "before": "TODO",
            "after": "DONE",
        },
        {"path": "tasks[id=b]", "change": "added", "after": {"id": "b"}},
    ]


def test_workflow_review_contract_golden_validation():
    document = {
        "title": "Review",
        "fields": [
            {"id": "decision", "label": "Decision", "type": "choice", "required": True, "options": ["approve", "revise"]},
            {"id": "notes", "label": "Notes", "type": "textarea", "required": False},
        ],
        "values": {"decision": "approve", "notes": "Ready"},
    }
    assert REVIEW_KEY.fullmatch("final.review")
    assert validate_review_document(document) is document
    invalid = {**document, "values": {"decision": "unknown"}}
    with pytest.raises(HTTPException) as caught:
        validate_review_document(invalid)
    assert caught.value.status_code == 422


def test_batch6_monoliths_no_longer_define_extracted_truths_or_import_backwards():
    expected_absent = {
        "backend/api/quantum_workspace.py": {
            "_project_for_owner",
            "_project_for_access",
            "_normalize_card_context",
            "_context_changes",
            "_compact_qws_business_snapshot",
            "_task_from_card_context",
        },
        "backend/api/workflows.py": {
            "_validate_review_document",
            "_review_etag",
            "_review_out",
        },
        "scripts/hermes_bridge.py": {
            "_apply_explicit_document_replacements",
            "_document_source_constraints",
            "_document_required_source_labels",
            "_document_source_constraint_issues",
            "_document_source_constraint_instruction",
            "_workflow_minimum_document_pages",
            "_ensure_document_page_breaks",
            "_workflow_output_incomplete",
        },
    }
    for relative, names in expected_absent.items():
        tree = ast.parse((REPO / relative).read_text())
        defined = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert not (defined & names)

    forbidden_modules = {
        "backend.api.quantum_workspace",
        "backend.api.workflows",
        "scripts.hermes_bridge",
    }
    for relative in (
        "backend/services/qws_access.py",
        "backend/services/qws_session_context.py",
        "backend/services/workflow_reviews.py",
        "backend/services/workflow_document_contracts.py",
    ):
        tree = ast.parse((REPO / relative).read_text())
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imports.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not (imports & forbidden_modules)
