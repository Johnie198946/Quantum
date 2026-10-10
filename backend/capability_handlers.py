"""Thin QCP bindings; existing domain handlers remain the authorization truth."""

from __future__ import annotations

import fcntl
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from backend.api.knowledge_sync import (
    NoteArchiveRequest,
    NoteMergeRequest,
    NoteSyncRequest,
    archive_note,
    list_synced_notes,
    merge_notes,
    restore_note,
    trash_note,
    sync_note,
)
from backend.api.workflows import (
    ApprovalRequest,
    ClarificationResponse,
    StageReviewRequest,
    TravelRevisionRequest,
    PlanEdit,
    WorkflowCancelRequest,
    WorkflowCreate,
    _create_workflow,
    approve_plan,
    cancel_workflow,
    edit_plan,
    get_artifact_content,
    get_execution,
    get_clarification,
    get_plan,
    respond_to_clarification,
    review_presentation_stage,
    retry_execution,
    save_travel_revision,
    get_workflow,
    list_artifacts,
    start_workflow,
)


Handler = Callable[[dict[str, Any], dict[str, Any], str | None], Awaitable[dict[str, Any]]]


async def verify_resource_versions(
    capability_id: str,
    data: dict[str, Any],
    payload: dict[str, Any],
    resource_versions: dict[str, Any],
) -> None:
    """Re-read CAS state at the domain boundary immediately before mutation."""
    if capability_id == "knowledge.note.trash" and data.get("note_versions"):
        expected = data["note_versions"]
        if resource_versions != expected:
            raise HTTPException(409, detail={"code": "resource_conflict"})
        snapshot = await list_synced_notes(True, payload, include_trashed=True)
        current = {item["note_id"]: item["content_hash"] for item in snapshot["items"]
                   if not item.get("archived") or item.get("trashed")}
        if any(current.get(key) != value for key, value in expected.items()):
            raise HTTPException(409, detail={"code": "resource_conflict"})
    elif capability_id in {"knowledge.note.update", "knowledge.note.archive", "knowledge.note.trash"}:
        note_id = str(data["note_id"])
        expected = str(resource_versions.get(note_id) or "")
        if expected != str(data.get("base_hash") or ""):
            raise HTTPException(status_code=409, detail={"code": "resource_conflict"})
        snapshot = await list_synced_notes(True, payload)
        current = next((item for item in snapshot["items"] if item["note_id"] == note_id), None)
        if current is None or str(current.get("content_hash") or "") != expected:
            raise HTTPException(status_code=409, detail={"code": "resource_conflict"})
    elif capability_id == "knowledge.note.merge":
        expected = {
            str(data["target_note_id"]): str(data["target_base_hash"]),
            **{str(key): str(value) for key, value in data["source_versions"].items()},
        }
        if any(str(resource_versions.get(key) or "") != value for key, value in expected.items()):
            raise HTTPException(status_code=409, detail={"code": "resource_conflict"})
        snapshot = await list_synced_notes(True, payload)
        current = {str(item["note_id"]): str(item.get("content_hash") or "") for item in snapshot["items"]}
        if any(current.get(key) != value for key, value in expected.items()):
            raise HTTPException(status_code=409, detail={"code": "resource_conflict"})
    elif capability_id == "workflow.start":
        workflow_id = str(data["workflow_id"])
        expected = str(resource_versions.get(workflow_id) or "")
        current = await get_workflow(workflow_id, payload)
        accepted = {str(current.get("updated_at") or ""), str(current.get("active_plan_id") or "")}
        if not expected or expected not in accepted:
            raise HTTPException(status_code=409, detail={"code": "resource_conflict"})


def _qcp_workflow_identity(
    capability_id: str, payload: dict[str, Any], key: str, data: dict[str, Any]
) -> tuple[str, str]:
    owner = (
        f"{payload.get('tenant_key')}:{payload.get('user_id') or payload.get('sub')}:"
        f"{capability_id}:{key}"
    )
    workflow_id = "wf_" + hashlib.sha256(owner.encode()).hexdigest()[:32]
    request_hash = hashlib.sha256(
        json.dumps(
            {"capability_id": capability_id, "input": data},
            sort_keys=True, separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return workflow_id, request_hash


async def _knowledge_mutation(
    capability_id: str,
    data: dict[str, Any],
    payload: dict[str, Any],
    key: str | None,
    operation: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Serialize and durably replay one owner-scoped capability mutation in the existing receipt store."""
    assert key
    from backend.api import knowledge_sync as sync

    tenant_key = str(payload.get("tenant_key") or "")
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    directory = sync.note_directory(tenant_key, user_id, sync._sync_root())
    receipts = directory / ".operations"
    receipts.mkdir(parents=True, exist_ok=True)
    identity = hashlib.sha256(f"{capability_id}:{key}".encode()).hexdigest()
    receipt_path = receipts / f"qcp-{identity}.json"
    lock_path = receipts / f"qcp-{identity}.lock"
    payload_digest = hashlib.sha256(json.dumps(
        {"capability_id": capability_id, "input": data},
        sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    with lock_path.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        prior = sync._read_metadata(receipt_path)
        if receipt_path.exists():
            if receipt_path.is_symlink() or not prior:
                raise HTTPException(
                    status_code=409, detail={"code": "idempotency_receipt_invalid"}
                )
            if prior.get("payload_digest") != payload_digest:
                raise HTTPException(
                    status_code=409, detail={"code": "idempotency_conflict"}
                )
            if isinstance(prior.get("result"), dict):
                return prior["result"]
        else:
            sync._atomic_write(receipt_path, json.dumps({
                "capability_id": capability_id,
                "key_hash": hashlib.sha256(key.encode()).hexdigest(),
                "payload_digest": payload_digest,
                "status": "applying",
            }, sort_keys=True, separators=(",", ":")).encode())
        result = await operation()
        sync._atomic_write(receipt_path, json.dumps({
            "capability_id": capability_id,
            "key_hash": hashlib.sha256(key.encode()).hexdigest(),
            "payload_digest": payload_digest,
            "status": "completed",
            "result": jsonable_encoder(result),
        }, sort_keys=True, separators=(",", ":")).encode())
        return result


def _note_title(markdown: str) -> str:
    from backend.services.user_note_context import _frontmatter_value
    if title := _frontmatter_value(markdown, "title"):
        return title[:200]
    first = next((line.strip() for line in markdown.splitlines() if line.strip()), "无标题")
    return first.lstrip("# ")[:200] or "无标题"


async def _knowledge_search(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    started = time.perf_counter()
    snapshot = await list_synced_notes(bool(data.get("include_archived", False)), payload)
    if data.get("mode") == "organize":
        from backend.services.user_note_context import organize_note_candidates
        from backend.services.knowledge_catalog import run_knowledge_read
        organization = await run_knowledge_read(organize_note_candidates, snapshot["items"], offset=int(data.get("offset", 0)), limit=int(data.get("limit", 20)))
        organization["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return {"items": [], "organization": organization,
                "local_state": "client_managed", "cloud_state": "synced", "index_state": snapshot["compile_status"]}
    terms = data["query"].casefold().split()
    matched = [item for item in snapshot["items"] if data.get("mode") == "catalog" or all(
        term in str(item.get("markdown") or "").casefold() for term in terms
    )]
    offset, limit = max(0, int(data.get("offset", 0))), int(data.get("limit", 5))
    items = []
    content_chars = 0
    for item in matched[offset:offset + limit]:
        markdown = str(item.get("markdown") or "")
        # One oversized note is returned whole; never label a clipped body complete.
        if data.get("include_content") and items and content_chars + len(markdown) > 48_000:
            break
        projected = {
            "note_id": item["note_id"], "title": _note_title(markdown),
            "snippet": markdown[:1000], "content_hash": item["content_hash"],
            "updated_at": item.get("updated_at"), "archived": item["archived"],
        }
        if data.get("include_content"):
            projected.update(markdown=markdown, content_complete=True)
            content_chars += len(markdown)
        items.append(projected)
    return {
        "items": items,
        "total_count": len(matched),
        "next_offset": offset + len(items) if offset + len(items) < len(matched) else None,
        "content_complete": bool(data.get("include_content")),
        "local_state": "client_managed", "cloud_state": "synced",
        "index_state": snapshot["compile_status"],
    }


async def _knowledge_read(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    snapshot = await list_synced_notes(True, payload, include_trashed=True)
    note = next((item for item in snapshot["items"] if item["note_id"] == data["note_id"]), None)
    if note is None:
        raise HTTPException(status_code=404, detail={"code": "note_not_found"})
    return {"note": {**note, "title": _note_title(note["markdown"])}, "local_state": "client_managed", "cloud_state": "synced", "index_state": snapshot["compile_status"]}


async def _knowledge_compare(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    from backend.services.knowledge_action_capability import note_merge_preview

    snapshot = await list_synced_notes(True, payload, include_trashed=True)
    by_id = {item["note_id"]: item for item in snapshot["items"]}
    notes = []
    for note_id in (data["target_note_id"], data["source_note_id"]):
        if note_id not in by_id:
            raise HTTPException(status_code=404, detail={"code": "note_not_found"})
        notes.append({**by_id[note_id], "id": note_id})
    try:
        return note_merge_preview(*notes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _knowledge_create(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    assert key
    owner = f"{payload.get('tenant_key')}:{payload.get('user_id') or payload.get('sub')}:{key}"
    note_id = "qcp-" + hashlib.sha256(owner.encode()).hexdigest()[:32]
    markdown = data["markdown"]
    return await sync_note(note_id, NoteSyncRequest(
        markdown=markdown, content_hash=hashlib.sha256(markdown.encode()).hexdigest(),
        updated_at=datetime.now(timezone.utc), create_only=True,
    ), payload)


async def _knowledge_update(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    markdown = data["markdown"]
    return await _knowledge_mutation(
        "knowledge.note.update", data, payload, key,
        lambda: sync_note(data["note_id"], NoteSyncRequest(
            markdown=markdown, content_hash=hashlib.sha256(markdown.encode()).hexdigest(),
            base_hash=data["base_hash"], updated_at=datetime.now(timezone.utc),
        ), payload),
    )


async def _knowledge_merge(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    assert key
    operation_id = "qcp-" + hashlib.sha256(key.encode()).hexdigest()[:32]
    return await merge_notes(NoteMergeRequest(operation_id=operation_id, **data), payload)


async def _knowledge_archive(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    return await _knowledge_mutation(
        "knowledge.note.archive", data, payload, key,
        lambda: archive_note(data["note_id"], NoteArchiveRequest(
            expected_content_hash=data["base_hash"]
        ), payload),
    )


async def _knowledge_trash(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    if data.get("all_active"):
        raise HTTPException(409, detail={"code": "reviewed_note_scope_required"})
    if data.get("note_versions"):
        results = []
        for note_id, expected in data["note_versions"].items():
            try:
                results.append(await _knowledge_trash({"note_id": note_id, "base_hash": expected}, payload, f"{key}:{note_id}"))
            except HTTPException as error:
                raise HTTPException(error.status_code, detail={"code": "batch_trash_incomplete", "message":
                    f"已完成{len(results)}篇，其余未完成；请重新生成提案重试，仅包含原确认范围。"}) from error
        return {"trash_status": "trashed", "count": len(results), "results": results}
    return await _knowledge_mutation(
        "knowledge.note.trash", data, payload, key,
        lambda: trash_note(data["note_id"], payload, expected_content_hash=data["base_hash"]),
    )


async def _knowledge_restore(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    return await _knowledge_mutation(
        "knowledge.note.restore", data, payload, key,
        lambda: restore_note(data["note_id"], payload),
    )


async def _navigation(data: dict[str, Any], _payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    return dict(data)


async def _workflow_create(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    assert key
    workflow_id, request_hash = _qcp_workflow_identity("workflow.create", payload, key, data)
    workflow_data = dict(data)
    source_client_session_id = workflow_data.pop("source_client_session_id", None)
    travel_fields = {
        label: str(workflow_data.pop(key, "") or "").strip()
        for key, label in (
            ("destination", "目的地"), ("travel_dates", "出行时间"),
            ("travelers", "同行人"), ("travel_preferences", "偏好"),
        )
    }
    if workflow_data.get("output_kind") == "travel":
        workflow_data["clarification_mode"] = "dynamic"
        confirmed = "；".join(f"{label}：{value}" for label, value in travel_fields.items() if value)
        if confirmed:
            workflow_data["description"] = (
                f"已确认旅行信息（与原始需求冲突时以此为准）：{confirmed}。\n"
                f"原始需求：{workflow_data['description']}"
            )
    return await _create_workflow(
        WorkflowCreate(**workflow_data), payload,
        workflow_id=workflow_id, qcp_request_hash=request_hash,
        requirements_snapshot_overrides={
            **({"source_client_session_id": source_client_session_id} if source_client_session_id else {}),
            **({"travel_details": travel_fields} if workflow_data.get("output_kind") == "travel" else {}),
        },
    )


async def _presentation_create(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    assert key
    workflow_id, request_hash = _qcp_workflow_identity(
        "presentation.create_from_document", payload, key, data
    )
    workflow_data = dict(data)
    source_client_session_id = workflow_data.pop("source_client_session_id", None)
    return await _create_workflow(
        WorkflowCreate(
            **workflow_data,
            desired_output="可编辑 PPTX 与渲染预览",
            output_kind="presentation",
        ),
        payload,
        workflow_id=workflow_id,
        qcp_request_hash=request_hash,
        requirements_snapshot_overrides={
            "source_client_session_id": source_client_session_id
        } if source_client_session_id else None,
    )


async def _presentation_create_from_text(
    data: dict[str, Any], payload: dict[str, Any], key: str | None
) -> dict[str, Any]:
    """Create the governed text-to-deck workflow selected by Hermes."""
    assert key
    presentation_review_gates = data.get("presentation_review_gates")
    if presentation_review_gates is None:
        presentation_review_gates = []
    normalized = {
        "audience": data.get("audience") or "general_business_audience",
        "intended_use": data.get("intended_use") or "management_briefing",
        "layout_style": data.get("layout_style") or "clean_professional_16_9",
        "slide_count": int(data.get("slide_count") or 10),
        "clarification_strategy": data.get("clarification_strategy")
        or "use_defaults_unless_blocked",
        "presentation_review_gates": list(presentation_review_gates),
    }
    identity_input = {**data, **normalized}
    workflow_id, request_hash = _qcp_workflow_identity(
        "presentation.create_from_text", payload, key, identity_input
    )
    material = data["text_material"].strip()
    editorial_instruction = str(data.get("editorial_instruction") or "").strip()
    description = (
        f"用户与场景：{normalized['audience']}；用途：{normalized['intended_use']}；"
        f"范围：根据以下文本材料制作 {normalized['slide_count']} 页演示文稿；"
        f"约束：版式必须采用 {normalized['layout_style']}，不得虚构材料中的事实；"
        "数据与知识库：仅使用用户文字和明确授权的检索；"
        "验收：输出可编辑 PPTX、同版本 PDF 渲染预览和鉴权下载入口；"
        f"文本材料已绑定到私有需求快照（{len(material)} 字符）。"
    )
    result = await _create_workflow(
        WorkflowCreate(
            title=data["title"],
            description=description,
            desired_output="可编辑 PPTX、同版本 PDF 渲染预览与鉴权下载",
            clarification_mode="compatibility",
            showroom_session_id=None,
            customer_demand_id=None,
            source_document_id=None,
            output_kind="presentation",
            presentation_review_gates=normalized["presentation_review_gates"],
        ),
        payload,
        workflow_id=workflow_id,
        qcp_request_hash=request_hash,
        requirements_explicit=(
            normalized["clarification_strategy"] == "use_defaults_unless_blocked"
        ),
        requirements_snapshot_overrides={
            "text_material": material,
            "source_text_sha256": hashlib.sha256(material.encode("utf-8")).hexdigest(),
            **(
                {"editorial_instruction": editorial_instruction}
                if editorial_instruction
                else {}
            ),
            "presentation_defaults": normalized,
            **(
                {"source_client_session_id": data["source_client_session_id"]}
                if data.get("source_client_session_id")
                else {}
            ),
            "artifact_contract": {
                "extension": "pptx",
                "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "preview_extension": "pdf",
                "preview_source": "exact_final_pptx_bytes",
                "download": "authenticated",
            },
        },
    )
    return {
        **result,
        "delivery": {
            "artifact_extension": "pptx",
            "artifact_mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "preview_extension": "pdf",
            "preview_source": "exact_final_pptx_bytes",
            "preview_return": "authenticated_artifact_reference",
            "download_return": "authenticated_artifact_download_reference",
        },
    }


async def _document_create_from_text(
    capability_id: str,
    document_kind: str,
    data: dict[str, Any],
    payload: dict[str, Any],
    key: str | None,
) -> dict[str, Any]:
    """Create one governed DOCX workflow from a first-class document contract."""
    assert key
    defaults = {
        "audience": data.get("audience") or "professional_reader",
        "language": data.get("language") or "zh-CN",
        "citation_style": data.get("citation_style") or (
            "none" if document_kind == "word" else "apa7"
        ),
        "evidence_policy": data.get("evidence_policy") or "verified_public_sources",
        "clarification_strategy": data.get("clarification_strategy")
        or "use_defaults_unless_blocked",
    }
    identity_input = {**data, **defaults}
    workflow_id, request_hash = _qcp_workflow_identity(
        capability_id, payload, key, identity_input
    )
    material = data["text_material"].strip()
    focus = str(data.get("research_question") or data.get("thesis") or "").strip()
    label, structure = {
        "word": ("Word 文档", "通用文档结构、标题层级与可编辑格式"),
        "research_report": ("研究报告", "研究问题、方法、证据、分析、结论、局限与建议"),
        "academic_paper": ("学术论文", "摘要、关键词、引言、方法、结果、讨论、结论与参考文献"),
    }[document_kind]
    description = (
        f"用户与场景：{defaults['audience']}；输出：{label}；语言：{defaults['language']}；"
        f"结构：{structure}；引文：{defaults['citation_style']}；"
        f"证据策略：{defaults['evidence_policy']}；不得虚构事实或来源；"
        "验收：大纲和全文分别审阅，输出可编辑 DOCX、鉴权下载、版本与内容哈希。"
        + (f"\n核心问题：{focus}" if focus else "")
        + f"\n文本材料已绑定到私有需求快照（{len(material)} 字符）。"
    )
    result = await _create_workflow(
        WorkflowCreate(
            title=data["title"],
            description=description,
            desired_output=f"可编辑 {label} DOCX、版本、内容哈希与鉴权下载",
            clarification_mode="compatibility",
            showroom_session_id=None,
            customer_demand_id=None,
            source_document_id=None,
            output_kind="document",
        ),
        payload,
        workflow_id=workflow_id,
        qcp_request_hash=request_hash,
        requirements_explicit=(
            defaults["clarification_strategy"] == "use_defaults_unless_blocked"
        ),
        requirements_snapshot_overrides={
            "text_material": material,
            **(
                {"source_client_session_id": data["source_client_session_id"]}
                if data.get("source_client_session_id")
                else {}
            ),
            "document_profile": {
                **defaults,
                "kind": document_kind,
                "focus": focus,
                "required_structure": structure,
                "review_gates": ["outline", "content", "final_output"],
            },
            "artifact_contract": {
                "extension": "docx",
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "download": "authenticated",
                "version": "required",
                "content_hash": "required",
            },
        },
    )
    return {
        **result,
        "delivery": {
            "artifact_extension": "docx",
            "artifact_mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "download_return": "authenticated_artifact_download_reference",
            "version": "required",
            "content_hash": "required",
        },
    }


async def _word_create_from_text(data, payload, key):
    return await _document_create_from_text(
        "document.word.create_from_text", "word", data, payload, key
    )


async def _research_report_create_from_text(data, payload, key):
    return await _document_create_from_text(
        "report.research.create_from_text", "research_report", data, payload, key
    )


async def _academic_paper_create_from_text(data, payload, key):
    return await _document_create_from_text(
        "paper.academic.create_from_text", "academic_paper", data, payload, key
    )


async def _workflow_open(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    return await get_workflow(data["workflow_id"], payload)


async def _workflow_status(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    return await get_execution(data["execution_id"], payload)


async def _workflow_start(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    assert key
    return await start_workflow(data["workflow_id"], ApprovalRequest(
        comment="QCP confirmed start", request_id=key
    ), payload)


async def _workflow_approve(
    data: dict[str, Any], payload: dict[str, Any], key: str | None
) -> dict[str, Any]:
    assert key
    return await approve_plan(data["workflow_id"], ApprovalRequest(
        comment=data.get("comment", ""), request_id=key,
        expected_hash=data["expected_plan_hash"],
        expected_revision=data["expected_plan_revision"],
    ), payload)


async def _workflow_revise(
    data: dict[str, Any], payload: dict[str, Any], key: str | None
) -> dict[str, Any]:
    assert key
    return await edit_plan(data["workflow_id"], PlanEdit(
        dsl=data["dsl"], deliverable=data["deliverable"],
        allow_network=data.get("allow_network", True),
        max_tokens=data.get("max_tokens", 999999),
        knowledge_scope=data.get("knowledge_scope", []),
        expected_hash=data["expected_plan_hash"],
        expected_revision=data["expected_plan_revision"], request_id=key,
    ), payload)


async def _workflow_cancel(
    data: dict[str, Any], payload: dict[str, Any], key: str | None
) -> dict[str, Any]:
    assert key
    return await cancel_workflow(
        data["workflow_id"],
        WorkflowCancelRequest(
            request_id=key,
            expected_updated_at=data["expected_updated_at"],
        ),
        payload,
    )


async def _workflow_clarification_read(data, payload, _key):
    return await get_clarification(data["workflow_id"], payload)


async def _workflow_clarification_respond(data, payload, key):
    async def apply():
        result = await respond_to_clarification(data["workflow_id"], ClarificationResponse(
            **{k: v for k, v in data.items() if k != "workflow_id"}
        ), payload)
        return {"workflow": await get_workflow(data["workflow_id"], payload), "clarification": result}
    return await _knowledge_mutation("workflow.clarification.respond", data, payload, key, apply)


async def _workflow_plan_read(data, payload, _key):
    plan = await get_plan(data["workflow_id"], payload)
    return {"workflow": await get_workflow(data["workflow_id"], payload), "plan": plan}


async def _execution_workflow_result(execution_id, payload, **details):
    execution = await get_execution(execution_id, payload)
    return {"workflow": await get_workflow(execution["workflow_id"], payload),
            "execution": execution, **details}


async def _workflow_artifacts_list(data, payload, _key):
    artifacts = await list_artifacts(data["execution_id"], payload)
    return await _execution_workflow_result(data["execution_id"], payload, artifacts=artifacts)


async def _workflow_review(data, payload, key):
    async def apply():
        result = await review_presentation_stage(data["execution_id"], StageReviewRequest(
            **{k: v for k, v in data.items() if k != "execution_id"}
        ), payload)
        return await _execution_workflow_result(data["execution_id"], payload, review=result)
    return await _knowledge_mutation("workflow.review", data, payload, key, apply)


async def _workflow_retry(data, payload, key):
    async def apply():
        result = await retry_execution(data["execution_id"], payload)
        return await _execution_workflow_result(data["execution_id"], payload, retry=result)
    return await _knowledge_mutation("workflow.retry", data, payload, key, apply)


async def _travel_revise(data, payload, key):
    assert key
    # Domain request digest and artifact CAS remain the authoritative revision fence.
    result = await save_travel_revision(data["execution_id"], TravelRevisionRequest(
        **{k: v for k, v in data.items() if k != "execution_id"}, request_id=key,
    ), payload)
    return await _execution_workflow_result(data["execution_id"], payload, revision=result)


def _travel_note_document(markdown):
    # Match existing raw JSON / fenced JSON notebook formats; unrelated notes stay untouched.
    text = str(markdown or "").strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


async def _travel_notebook_save(data, payload, key):
    from backend.services.travel_plan import validate_travel_document

    async def apply():
        execution = await get_execution(data["execution_id"], payload)
        if execution["status"] != "completed":
            raise HTTPException(409, detail="请先采用最终旅行成果")
        artifacts = await list_artifacts(data["execution_id"], payload)
        candidates = [a for a in artifacts if (a.get("metadata") or {}).get("render_type") == "travel_plan_v2"
                      and not (a.get("metadata") or {}).get("approval_gate")]
        if not candidates:
            raise HTTPException(404, detail="没有已采用的最终旅行手记")
        current = max(candidates, key=lambda a: (int((a.get("metadata") or {}).get("travel_revision", 0)),
                                                str(a.get("created_at") or ""), a["id"]))
        if current["id"] != data["artifact_id"] or current["content_hash"] != data["expected_hash"]:
            raise HTTPException(409, detail={"code": "stale_travel_artifact", "message": "请查看最新旅行成果后再保存"})
        artifact = await get_artifact_content(data["execution_id"], current["id"], payload)
        document = _travel_note_document(artifact["content"])
        if document is None:
            raise HTTPException(422, detail="旅行成果不是结构化文档")
        document = validate_travel_document(document)
        snapshot = await list_synced_notes(True, payload, include_trashed=True)
        linked = [n for n in snapshot["items"] if (_travel_note_document(n.get("markdown")) or {}).get("workflow_execution_id") == data["execution_id"]]
        if linked:
            if len(linked) != 1 or linked[0].get("archived") or linked[0].get("trashed") or (
                _travel_note_document(linked[0]["markdown"]).get("workflow_artifact_hash") != data["expected_hash"]
            ):
                raise HTTPException(409, detail={"code": "linked_note_requires_review", "message": "已有旅行笔记，请读取原笔记并确认合并；不会覆盖日记或创建重复笔记"})
            note = {"note_id": linked[0]["note_id"], "content_hash": linked[0]["content_hash"], "reused": True}
        else:
            document.update(workflow_execution_id=data["execution_id"], workflow_artifact_id=current["id"],
                            workflow_artifact_hash=current["content_hash"])
            # Stable per owned execution across separate confirmation keys; create_only prevents overwrite.
            note = await _knowledge_create({"markdown": json.dumps(document, ensure_ascii=False, indent=2)},
                                           payload, "travel-notebook:" + data["execution_id"])
        return await _execution_workflow_result(data["execution_id"], payload, note=note)
    return await _knowledge_mutation("travel.notebook.save", data, payload, key, apply)


async def _artifact_open(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    return await get_artifact_content(data["execution_id"], data["artifact_id"], payload)


async def _artifact_download(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    artifacts = await list_artifacts(data["execution_id"], payload)
    artifact = next((item for item in artifacts if item["id"] == data["artifact_id"]), None)
    if artifact is None:
        raise HTTPException(status_code=404, detail="工作流素材不存在")
    return {
        "path": f"workflow-executions/{data['execution_id']}/artifacts/{data['artifact_id']}/download",
        "content_hash": artifact["content_hash"], "mime_type": artifact["mime_type"],
        "extension": artifact["extension"],
    }


async def _artifact_consume_structured(
    data: dict[str, Any], payload: dict[str, Any], key: str | None
) -> dict[str, Any]:
    assert key
    from backend.services.artifact_consumption import consume_structured_artifact

    return await consume_structured_artifact(data, payload, key)


async def _bookshelf_search(
    data: dict[str, Any], payload: dict[str, Any], _key: str | None
) -> dict[str, Any]:
    from backend.api.subscriptions import knowledge_bookshelves

    catalog = await knowledge_bookshelves(payload)
    terms = data["query"].casefold().split()
    items = [
        book
        for shelf in catalog["bookshelves"]
        for book in shelf["books"]
        if all(
            term in " ".join(
                str(book.get(field) or "")
                for field in ("title", "author", "summary", "series_title")
            ).casefold()
            for term in terms
        )
    ][: int(data.get("limit", 20))]
    return {"items": items}


async def _bookshelf_subscribe(
    data: dict[str, Any], payload: dict[str, Any], _key: str | None
) -> dict[str, Any]:
    from backend.api.subscriptions import (
        BookSubscriptionWrite,
        subscribe_book,
        unsubscribe_book,
    )

    body = BookSubscriptionWrite(book_id=data["book_id"])
    if data["action"] == "subscribe":
        subscription = await subscribe_book(body, payload)
        return {
            "action": "subscribe",
            "book_id": data["book_id"],
            "subscription": jsonable_encoder(subscription),
        }
    result = await unsubscribe_book(body, payload)
    return {"action": "unsubscribe", "book_id": data["book_id"], **result}


async def _bookshelf_open(
    data: dict[str, Any], payload: dict[str, Any], _key: str | None
) -> dict[str, Any]:
    from backend.api.subscriptions import knowledge_book_body

    return jsonable_encoder(await knowledge_book_body(data["book_id"], payload))


async def _memory_list(
    _data: dict[str, Any], payload: dict[str, Any], _key: str | None
) -> dict[str, Any]:
    from backend.api.hot_memory import get_memory

    return jsonable_encoder(await get_memory(payload))


async def _memory_create(
    data: dict[str, Any], payload: dict[str, Any], _key: str | None
) -> dict[str, Any]:
    from backend.api.hot_memory import MemoryWriteRequest, create_memory

    return jsonable_encoder(await create_memory(MemoryWriteRequest(**data), payload))


async def _memory_update(
    data: dict[str, Any], payload: dict[str, Any], _key: str | None
) -> dict[str, Any]:
    from backend.api.hot_memory import MemoryReplaceRequest, replace_memory

    return jsonable_encoder(await replace_memory(
        data["memory_id"], MemoryReplaceRequest(content=data["content"]), payload
    ))


async def _memory_delete(
    data: dict[str, Any], payload: dict[str, Any], _key: str | None
) -> dict[str, Any]:
    from backend.api.hot_memory import remove_memory

    return jsonable_encoder(await remove_memory(data["memory_id"], payload))


async def _profile_read(
    _data: dict[str, Any], payload: dict[str, Any], _key: str | None
) -> dict[str, Any]:
    from backend.api.me import me

    return jsonable_encoder(await me(payload))


async def _profile_update(
    data: dict[str, Any], payload: dict[str, Any], _key: str | None
) -> dict[str, Any]:
    from backend.api.me import ProfileUpdate, patch_me

    if not data:
        raise HTTPException(status_code=422, detail={"code": "contract_invalid"})
    return jsonable_encoder(await patch_me(ProfileUpdate(**data), payload))


async def _agent_list(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    from backend.api.tenant_agents import list_tenant_agents

    rows = await list_tenant_agents(payload=payload, owned_only=bool(data.get("owned_only", False)))
    return {"agents": jsonable_encoder(rows)}


async def _agent_create(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    from backend.api.tenant_agents import TenantAgentCreate, create_tenant_agent

    return jsonable_encoder(await create_tenant_agent(TenantAgentCreate(**data), payload))


async def _agent_update(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    from backend.api.tenant_agents import TenantAgentCreate, update_tenant_agent

    body = dict(data)
    agent_id = str(body.pop("agent_id"))
    return jsonable_encoder(await update_tenant_agent(agent_id, TenantAgentCreate(**body), payload))


async def _agent_delete(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    from backend.api.tenant_agents import delete_tenant_agent

    await delete_tenant_agent(str(data["agent_id"]), payload)
    return {"status": "deleted"}


async def _agent_evaluate(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    from backend.api.tenant_agents import AgentEvaluationCreate, create_agent_evaluation

    body = AgentEvaluationCreate(request_id=str(data["request_id"]))
    return jsonable_encoder(await create_agent_evaluation(str(data["agent_id"]), body, payload))


async def _agent_evaluation_status(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    from backend.api.tenant_agents import get_agent_evaluation

    return jsonable_encoder(await get_agent_evaluation(str(data["run_id"]), payload))


async def _skill_context(payload: dict[str, Any]):
    from backend.api.chat import _resolve_chat_policy

    policy = await _resolve_chat_policy(payload)
    user_id = str(payload.get("user_id") or payload.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail={"code": "not_authenticated"})
    return policy, user_id


async def _skill_bridge_call(operation: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    try:
        return await operation
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail")
        except (ValueError, AttributeError):
            detail = "skill_bridge_rejected"
        code = detail if isinstance(detail, str) else (detail or {}).get("code")
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": str(code or "skill_bridge_rejected")},
        ) from exc


async def _skill_list(
    data: dict[str, Any], payload: dict[str, Any], _key: str | None
) -> dict[str, Any]:
    from backend.services.hermes_sandbox_catalog import fetch_skill_catalog

    policy, user_id = await _skill_context(payload)
    skills = await _skill_bridge_call(fetch_skill_catalog(policy, user_id=user_id))
    if data.get("owned_only"):
        skills = [item for item in skills if item.get("scope") == "tenant"]
    return {"skills": skills}


async def _skill_create(
    data: dict[str, Any], payload: dict[str, Any], key: str | None
) -> dict[str, Any]:
    from backend.services.hermes_sandbox_catalog import create_tenant_skill

    assert key
    policy, user_id = await _skill_context(payload)
    return await _skill_bridge_call(create_tenant_skill(
        policy, user_id=user_id, name=data["name"], content=data["content"],
        idempotency_key=key,
    ))


async def _skill_update(
    data: dict[str, Any], payload: dict[str, Any], key: str | None
) -> dict[str, Any]:
    from backend.services.hermes_sandbox_catalog import update_tenant_skill

    assert key
    policy, user_id = await _skill_context(payload)
    return await _skill_bridge_call(update_tenant_skill(
        policy, user_id=user_id, name=data["name"], content=data["content"],
        idempotency_key=key,
    ))


async def _skill_delete(
    data: dict[str, Any], payload: dict[str, Any], key: str | None
) -> dict[str, Any]:
    from backend.services.hermes_sandbox_catalog import delete_tenant_skill

    assert key
    policy, user_id = await _skill_context(payload)
    return await _skill_bridge_call(delete_tenant_skill(
        policy, user_id=user_id, name=data["name"], idempotency_key=key
    ))


def _response_payload(value: Any) -> Any:
    """Unwrap direct FastAPI domain calls without changing their semantics."""
    body = getattr(value, "body", None)
    return json.loads(body) if isinstance(body, bytes) else jsonable_encoder(value)


async def _project_list(_data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    from backend.api.quantum_workspace import list_projects

    return {"projects": jsonable_encoder(await list_projects(payload))}


async def _project_create(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    from backend.api.quantum_workspace import InstantiateProjectRequest, instantiate_project

    assert key
    body = InstantiateProjectRequest(request_id=key, **data)
    return _response_payload(await instantiate_project("ipd-product-development", body, payload))


async def _project_open(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    from backend.api.quantum_workspace import get_project

    return {"project": jsonable_encoder(await get_project(data["project_id"], payload))}


async def _project_update(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    from backend.api.quantum_workspace import UpdateProjectRequest, update_project

    assert key
    body = dict(data)
    project_id = str(body.pop("project_id"))
    return _response_payload(await update_project(
        project_id, UpdateProjectRequest(request_id=key, **body), payload
    ))


async def _project_delete(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    from backend.api.quantum_workspace import (
        ProjectArchiveProposalRequest,
        propose_project_archive,
    )

    assert key
    return await propose_project_archive(
        data["project_id"],
        ProjectArchiveProposalRequest(
            expected_revision=data["expected_revision"], request_id=key
        ),
        payload,
    )


async def _task_list(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    from backend.api.quantum_workspace import get_project_process

    process = jsonable_encoder(await get_project_process(data["project_id"], payload))
    result = {
        "project_id": process["project_id"],
        "process_revision": process["process_revision"],
        "tasks": process.get("tasks") or [],
    }
    if data.get("include_cleanup"):
        from backend.services.task_operating_loop import find_duplicate_candidates, create_merge_preview
        active = [{**item, "project_id": data["project_id"]} for item in result["tasks"]
                  if not item.get("archived_at") and item.get("status") not in {"MERGED", "CANCELLED"}]
        # ponytail: bounded quadratic scan; use indexed candidates if projects exceed this window.
        scanned = active[:100]
        candidates, seen = [], set()
        by_id = {str(item["id"]): item for item in scanned}
        for task in scanned:
            for candidate in find_duplicate_candidates(task, scanned, trigger="CLEANUP"):
                pair = tuple(sorted((str(task["id"]), str(candidate["target_task_id"]))))
                if pair in seen:
                    continue
                seen.add(pair)
                preview = create_merge_preview(task, by_id[str(candidate["target_task_id"])], created_by="preview")
                candidates.append({**candidate, "source_task_id": task["id"], "preview": preview})
        result.update(cleanup_candidates=candidates[:50], cleanup_truncated=len(active) > 100 or len(candidates) > 50)
        result["cleanup_merges"] = [
            {key: item[key] for key in ("id", "primary_task_id", "secondary_task_id")}
            for item in process.get("task_merges") or [] if item.get("status") == "APPLIED"
        ]
    return result


async def _task_create(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    from backend.api.quantum_workspace import CreateProjectTaskRequest, create_project_task

    assert key
    body = dict(data)
    project_id = str(body.pop("project_id"))
    return _response_payload(await create_project_task(
        project_id, CreateProjectTaskRequest(request_id=key, **body), payload
    ))


async def _task_update(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    from backend.api.quantum_workspace import EditProjectTaskRequest, edit_project_task

    assert key
    if "operations" in data:
        from backend.api.quantum_workspace import (
            TaskOrganizationRequest, propose_project_task_organization,
            DecideProjectChangeProposalRequest, decide_project_change_proposal,
        )
        if set(data) != {"project_id", "expected_revision", "operations"}:
            raise HTTPException(status_code=422, detail="mixed_task_update_modes")
        proposed = await propose_project_task_organization(
            data["project_id"], TaskOrganizationRequest(
                expected_revision=data["expected_revision"], request_id=key, operations=data["operations"],
            ), payload,
        )
        result = await decide_project_change_proposal(
            data["project_id"], proposed["proposal"]["id"],
            DecideProjectChangeProposalRequest(expected_process_revision=data["expected_revision"], decision="APPROVE"),
            payload,
        )
        if result["proposal"]["status"] != "APPROVED":
            raise HTTPException(status_code=409, detail="task_changes_not_applied")
        return _response_payload({**result, "task_preview": None, "applied": True})
    body = dict(data)
    project_id = str(body.pop("project_id"))
    task_id = str(body.pop("task_id"))
    return _response_payload(await edit_project_task(
        project_id, task_id, EditProjectTaskRequest(request_id=key, **body), payload
    ))


async def _task_status(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    from backend.api.quantum_workspace import get_project_task

    return {"task": jsonable_encoder(await get_project_task(
        data["project_id"], data["task_id"], payload
    ))}


async def _task_delete(data: dict[str, Any], payload: dict[str, Any], key: str | None) -> dict[str, Any]:
    from backend.api.quantum_workspace import (
        TaskArchiveProposalRequest,
        propose_project_task_archive,
    )

    assert key
    return _response_payload(await propose_project_task_archive(
        data["project_id"],
        data["task_id"],
        TaskArchiveProposalRequest(
            expected_revision=data["expected_revision"], request_id=key, action="ARCHIVE"
        ),
        payload,
    ))


async def _schedule_list(
    data: dict[str, Any], payload: dict[str, Any], _key: str | None
) -> dict[str, Any]:
    from backend.api.quantum_workspace import get_project_schedule

    return {"schedule": jsonable_encoder(await get_project_schedule(data["project_id"], payload))}


async def _schedule_mutation(
    operation: str, data: dict[str, Any], payload: dict[str, Any], key: str | None
) -> dict[str, Any]:
    from backend.api.quantum_workspace import (
        ProjectScheduleProposalRequest,
        propose_project_schedule,
    )

    assert key
    entry = {"task_id": data["task_id"]}
    if operation != "DELETE":
        entry.update(start_date=data["start_date"], due_date=data["due_date"])
    else:
        entry.update(start_date=None, due_date=None)
    return _response_payload(await propose_project_schedule(
        data["project_id"],
        ProjectScheduleProposalRequest(
            request_id=key,
            expected_revision=data["expected_revision"],
            entries=[entry],
            operation=operation,
        ),
        payload,
    ))


async def _schedule_create(data, payload, key):
    return await _schedule_mutation("CREATE", data, payload, key)


async def _schedule_update(data, payload, key):
    return await _schedule_mutation("UPDATE", data, payload, key)


async def _schedule_delete(data, payload, key):
    return await _schedule_mutation("DELETE", data, payload, key)


async def _notification_list(
    data: dict[str, Any], payload: dict[str, Any], _key: str | None
) -> dict[str, Any]:
    from backend.api.notifications import list_notifications

    return await list_notifications(
        limit=int(data.get("limit", 50)),
        unread_only=bool(data.get("unread_only", False)),
        payload=payload,
    )


async def _notification_mark_read(
    data: dict[str, Any], payload: dict[str, Any], key: str | None
) -> dict[str, Any]:
    from backend.api.notifications import NotificationReadRequest, mark_read

    assert key
    return await mark_read(
        int(data["notification_id"]),
        NotificationReadRequest(expected_read=bool(data["expected_read"])),
        payload,
    )


async def _notification_preferences_update(
    data: dict[str, Any], payload: dict[str, Any], key: str | None
) -> dict[str, Any]:
    from backend.api.notifications import NotificationPreferenceRequest, update_preferences

    assert key
    return await update_preferences(NotificationPreferenceRequest(**data), payload)


async def _hermes_session_action(
    action: str, data: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from backend.services.hermes_sessions import owner_session_action

    return await owner_session_action(action, data, payload)


async def _hermes_session_list(data, payload, key):
    return await _hermes_session_action("list", data, payload)


async def _hermes_session_open(data, payload, key):
    return await _hermes_session_action("open", data, payload)


async def _hermes_session_resume(data, payload, key):
    return await _hermes_session_action("resume", data, payload)


async def _hermes_session_delete(data, payload, key):
    return await _hermes_session_action("delete", data, payload)


async def _client_action(capability_id, data, payload, key):
    from backend.services.client_actions import issue_client_action

    return await issue_client_action(capability_id, data, payload, key)


async def _file_pick(data, payload, key):
    return await _client_action("file.pick", data, payload, key)


async def _conversation_lifecycle(data, payload, key):
    return await _client_action("conversation.lifecycle", data, payload, key)


async def _photo_capture(data, payload, key):
    return await _client_action("photo.capture", data, payload, key)


async def _photo_import(data, payload, key):
    return await _client_action("photo.import", data, payload, key)


async def _voice_record(data, payload, key):
    return await _client_action("voice.record", data, payload, key)


async def _share_present(data, payload, key):
    return await _client_action("share.present", data, payload, key)


async def _file_upload(data, payload, key):
    return await _client_action("file.upload", data, payload, key)


async def _file_download(data, payload, key):
    return await _client_action("file.download", data, payload, key)


async def _voice_transcribe(data, payload, key):
    return await _client_action("voice.transcribe", data, payload, key)


def _generated_owner(payload: dict[str, Any]) -> tuple[str, str]:
    return (
        str(payload.get("tenant_key") or ""),
        str(payload.get("user_id") or payload.get("sub") or ""),
    )


async def _spreadsheet_create(data, payload, key):
    from backend.services.generated_artifacts import create_spreadsheet

    return create_spreadsheet(*_generated_owner(payload), data)


async def _pdf_create(data, payload, key):
    from backend.services.generated_artifacts import create_pdf

    return create_pdf(*_generated_owner(payload), data)


async def _data_analyze(data, payload, key):
    from backend.services.generated_artifacts import analyze_data

    return analyze_data(*_generated_owner(payload), data)


async def _media_process(data, payload, key):
    from backend.services.image_processing import ImageEdit, validate_studio_assets, workflow_image_source, expected_image_size

    assert key
    edit = ImageEdit.model_validate({k: v for k, v in data.items() if k not in {"source_artifact_id", "source_client_session_id"}})
    validate_studio_assets(*_generated_owner(payload), edit)
    expected_image_size(workflow_image_source(*_generated_owner(payload), data["source_artifact_id"]), edit)
    workflow_id, request_hash = _qcp_workflow_identity("media.process", payload, key, data)
    return await _create_workflow(
        WorkflowCreate(title="图片处理", description="按已确认的图片编辑参数处理原图，交付可下载的真实图片。",
                       desired_output=f"处理后的 {edit.format.upper()} 图片",
                       output_kind="image", source_image_id=data["source_artifact_id"],
                       source_client_session_id=data.get("source_client_session_id")),
        payload, workflow_id=workflow_id, qcp_request_hash=request_hash,
        requirements_explicit=True,
        requirements_snapshot_overrides={"image_edit": edit.model_dump()},
    )


async def _media_save_edit(data, payload, key):
    from backend.services.image_processing import save_processed_image
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(save_processed_image, *_generated_owner(payload), data, key)


async def _media_create(data, payload, key):
    from backend.services.generated_artifacts import create_media

    return create_media(*_generated_owner(payload), data)


async def _task_execute(data, payload, key):
    from backend.api import auth as auth_api
    from backend.api import quantum_workspace as qws
    from backend.services.task_execution import mint_task_execution_token

    token = mint_task_execution_token(
        data,
        payload,
        key,
        secret=auth_api.AUTHEN_JWT_SECRET,
        algorithm=auth_api.AUTHEN_JWT_ALGORITHM,
        issuer=auth_api.AUTHEN_JWT_ISSUER,
        audience=auth_api.AUTHEN_JWT_AUDIENCE,
    )
    body = qws.AutoExecuteTaskRequest(
        instruction=str(data["instruction"]),
        request_id=key,
    )
    return await qws.queue_task_auto_execution(
        str(data["conversation_id"]),
        body,
        payload,
        f"Bearer {token}",
        expected_task_id=str(data["task_id"]),
        expected_intent_hash=str(data["expected_intent_hash"]),
    )



async def _knowledge_illustration_status(data, payload, key):
    from backend.api.knowledge_sync import _illustration_bridge
    return await _illustration_bridge(payload, f"/by-note/{data['note_id']}")


async def _knowledge_illustration_action(data, payload, key):
    # Mutations use the existing signed local-note proposal/executor, just as
    # unsynced note edits do. A server-only caller cannot bypass that receipt.
    raise HTTPException(409, detail={"code": "local_note_executor_required"})


def _learning_chat_snapshot(item):
    # Unrequested hints are withheld from Chat; the exercise screen uses its domain API.
    return {**item, "questions": [
        {**q, "hint": q.get("hint", "") if item["answers"].get(q["id"], {}).get("assisted") else ""}
        for q in item["questions"]
    ]}


async def _learning_resume(data, payload, key):
    from backend.api.subscriptions import learning_resume
    return await learning_resume(payload)


async def _learning_read(data, payload, key):
    from backend.api import learning
    from uuid import UUID
    exercise_id = data.get("exercise_id")
    if not exercise_id:
        query = learning.owner_query(payload)
        if data.get("unfinished_only"):
            query = query.where(learning.LearningExercise.status.in_(["draft", "generating", "grading"]))
        async with learning.SessionLocal() as db:
            row = await db.scalar(query.order_by(
                learning.LearningExercise.updated_at.desc(), learning.LearningExercise.id.desc()
            ).limit(1))
        if row is None:
            raise HTTPException(404, "没有符合条件的练习，请选择阅读章节出题或指定已有题组。")
        exercise_id = row.id
    return _learning_chat_snapshot(await learning.get_exercise(UUID(exercise_id), payload))


async def _learning_create(data, payload, key):
    from backend.api import learning
    from uuid import NAMESPACE_URL, uuid5
    # Same confirmed operation always resumes the same domain request after a lost response.
    identity = f"{payload['tenant_key']}:{payload.get('user_id') or payload.get('sub')}:{key}"
    body = learning.CreateExercise(id=uuid5(NAMESPACE_URL, identity), **data)
    return _learning_chat_snapshot(await learning.create_exercise(body, payload))


async def _learning_change(data, payload, key, *, operation):
    from backend.api import learning
    from uuid import UUID
    exercise_id = UUID(data["exercise_id"])
    row = await learning.owned(exercise_id, payload)
    if row.revision != data["revision"]:
        raise HTTPException(409, "练习已更新，请重新读取后操作；已有答案已保留。")
    answers = {k: dict(v) for k, v in row.drafts.items()}
    if operation == "submit":
        return _learning_chat_snapshot(await learning.submit_exercise(exercise_id,
            learning.SaveAnswers(revision=data["revision"], answers=answers), payload))
    question_id = data["question_id"]
    question = next((q for q in row.questions if q["id"] == question_id), None)
    if question is None:
        raise HTTPException(422, "题号不存在，请重新读取题组。")
    answer = dict(answers.get(question_id) or learning.Answer().model_dump())
    if operation == "hint":
        if not question.get("hint"):
            raise HTTPException(409, "这份旧题组没有提示，可继续独立作答或生成新题组。")
        answer["assisted"] = True
    else:
        if not data.get("selected") and not str(data.get("text") or "").strip():
            raise HTTPException(422, "请先提供这一题的答案。")
        answer.update(selected=data.get("selected", []), text=data.get("text", ""))
    answers[question_id] = answer
    item = await learning.save_draft(exercise_id,
        learning.SaveAnswers(revision=data["revision"], answers=answers), payload)
    result = _learning_chat_snapshot(item)
    if operation == "hint":
        result.update(question_id=question_id, hint=question["hint"])
    return result


async def _learning_hint(data, payload, key):
    return await _learning_change(data, payload, key, operation="hint")


async def _learning_answer(data, payload, key):
    return await _learning_change(data, payload, key, operation="answer")


async def _learning_submit(data, payload, key):
    return await _learning_change(data, payload, key, operation="submit")


HANDLERS: dict[str, Handler] = {
    "knowledge.illustration.action": _knowledge_illustration_action,
    "knowledge.illustration.status": _knowledge_illustration_status,
    "knowledge.compare": _knowledge_compare,
    "learning.resume": _learning_resume,
    "learning.exercise.read": _learning_read,
    "learning.exercise.create": _learning_create,
    "learning.exercise.hint": _learning_hint,
    "learning.exercise.answer": _learning_answer,
    "learning.exercise.submit": _learning_submit,

    "knowledge.search": _knowledge_search,
    "knowledge.read": _knowledge_read,
    "knowledge.create": _knowledge_create,
    "knowledge.update": _knowledge_update,
    "knowledge.merge": _knowledge_merge,
    "knowledge.archive": _knowledge_archive,
    "knowledge.restore": _knowledge_restore,
    "knowledge.trash": _knowledge_trash,
    "client.knowledge.navigation": _navigation,
    "workflow.create": _workflow_create,
    "workflow.clarification.read": _workflow_clarification_read,
    "workflow.clarification.respond": _workflow_clarification_respond,
    "workflow.plan.read": _workflow_plan_read,
    "workflow.artifacts.list": _workflow_artifacts_list,
    "workflow.review": _workflow_review,
    "workflow.retry": _workflow_retry,
    "travel.revise": _travel_revise,
    "travel.notebook.save": _travel_notebook_save,

    "workflow.open": _workflow_open,
    "workflow.status": _workflow_status,
    "workflow.start": _workflow_start,
    "workflow.approve": _workflow_approve,
    "workflow.revise": _workflow_revise,
    "workflow.cancel": _workflow_cancel,
    "presentation.create_from_document": _presentation_create,
    "presentation.create_from_text": _presentation_create_from_text,
    "document.word.create_from_text": _word_create_from_text,
    "report.research.create_from_text": _research_report_create_from_text,
    "paper.academic.create_from_text": _academic_paper_create_from_text,
    "artifact.open": _artifact_open,
    "artifact.download": _artifact_download,
    "artifact.consume_structured": _artifact_consume_structured,
    "bookshelf.search": _bookshelf_search,
    "bookshelf.subscribe": _bookshelf_subscribe,
    "bookshelf.open": _bookshelf_open,
    "memory.list": _memory_list,
    "memory.create": _memory_create,
    "memory.update": _memory_update,
    "memory.delete": _memory_delete,
    "profile.read": _profile_read,
    "profile.update": _profile_update,
    "agent.list": _agent_list,
    "agent.create": _agent_create,
    "agent.update": _agent_update,
    "agent.delete": _agent_delete,
    "agent.evaluate": _agent_evaluate,
    "agent.evaluation_status": _agent_evaluation_status,
    "skill.list": _skill_list,
    "skill.create": _skill_create,
    "skill.update": _skill_update,
    "skill.delete": _skill_delete,
    "project.list": _project_list,
    "project.create": _project_create,
    "project.open": _project_open,
    "project.update": _project_update,
    "project.delete": _project_delete,
    "task.list": _task_list,
    "task.create": _task_create,
    "task.update": _task_update,
    "task.delete": _task_delete,
    "task.status": _task_status,
    "schedule.list": _schedule_list,
    "schedule.create": _schedule_create,
    "schedule.update": _schedule_update,
    "schedule.delete": _schedule_delete,
    "notification.list": _notification_list,
    "notification.mark_read": _notification_mark_read,
    "notification.preferences.update": _notification_preferences_update,
    "hermes.session.list": _hermes_session_list,
    "hermes.session.open": _hermes_session_open,
    "hermes.session.resume": _hermes_session_resume,
    "hermes.session.delete": _hermes_session_delete,
    "file.pick": _file_pick,
    "conversation.lifecycle": _conversation_lifecycle,
    "photo.capture": _photo_capture,
    "photo.import": _photo_import,
    "voice.record": _voice_record,
    "share.present": _share_present,
    "file.upload": _file_upload,
    "file.download": _file_download,
    "voice.transcribe": _voice_transcribe,
    "office.spreadsheet.create": _spreadsheet_create,
    "office.pdf.create": _pdf_create,
    "data.analyze": _data_analyze,
    "media.create": _media_create,
    "media.process": _media_process,
    "media.save_edit": _media_save_edit,
    "task.execute": _task_execute,
}
