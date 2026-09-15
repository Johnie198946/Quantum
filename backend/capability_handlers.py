"""Thin QCP bindings; existing domain handlers remain the authorization truth."""

from __future__ import annotations

import hashlib
import fcntl
import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

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
    sync_note,
)
from backend.api.workflows import (
    ApprovalRequest,
    WorkflowCreate,
    _create_workflow,
    get_artifact_content,
    get_execution,
    get_workflow,
    list_artifacts,
    start_workflow,
)


Handler = Callable[[dict[str, Any], dict[str, Any], str | None], Awaitable[dict[str, Any]]]


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
    """Serialize and durably replay one private-note capability mutation."""
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
    first = next((line.strip() for line in markdown.splitlines() if line.strip()), "无标题")
    return first.lstrip("# ")[:200] or "无标题"


async def _knowledge_search(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    snapshot = await list_synced_notes(bool(data.get("include_archived", False)), payload)
    terms = data["query"].casefold().split()
    items = [item for item in snapshot["items"] if all(
        term in str(item.get("markdown") or "").casefold() for term in terms
    )][:int(data.get("limit", 5))]
    return {
        "items": [{
            "note_id": item["note_id"], "title": _note_title(item["markdown"]),
            "snippet": item["markdown"][:1000], "content_hash": item["content_hash"],
            "updated_at": item.get("updated_at"), "archived": item["archived"],
        } for item in items],
        "local_state": "client_managed", "cloud_state": "synced",
        "index_state": snapshot["compile_status"],
    }


async def _knowledge_read(data: dict[str, Any], payload: dict[str, Any], _key: str | None) -> dict[str, Any]:
    snapshot = await list_synced_notes(True, payload)
    note = next((item for item in snapshot["items"] if item["note_id"] == data["note_id"]), None)
    if note is None:
        raise HTTPException(status_code=404, detail={"code": "note_not_found"})
    return {"note": note, "local_state": "client_managed", "cloud_state": "synced", "index_state": snapshot["compile_status"]}


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
    return await _create_workflow(
        WorkflowCreate(**workflow_data), payload,
        workflow_id=workflow_id, qcp_request_hash=request_hash,
        requirements_snapshot_overrides={
            "source_client_session_id": source_client_session_id
        } if source_client_session_id else None,
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
    normalized = {
        "audience": data.get("audience") or "general_business_audience",
        "intended_use": data.get("intended_use") or "management_briefing",
        "layout_style": data.get("layout_style") or "clean_professional_16_9",
        "slide_count": int(data.get("slide_count") or 10),
        "clarification_strategy": data.get("clarification_strategy")
        or "use_defaults_unless_blocked",
    }
    identity_input = {**data, **normalized}
    workflow_id, request_hash = _qcp_workflow_identity(
        "presentation.create_from_text", payload, key, identity_input
    )
    material = data["text_material"].strip()
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
        ),
        payload,
        workflow_id=workflow_id,
        qcp_request_hash=request_hash,
        requirements_explicit=(
            normalized["clarification_strategy"] == "use_defaults_unless_blocked"
        ),
        requirements_snapshot_overrides={
            "text_material": material,
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


HANDLERS: dict[str, Handler] = {
    "knowledge.search": _knowledge_search,
    "knowledge.read": _knowledge_read,
    "knowledge.create": _knowledge_create,
    "knowledge.update": _knowledge_update,
    "knowledge.merge": _knowledge_merge,
    "knowledge.archive": _knowledge_archive,
    "knowledge.restore": _knowledge_restore,
    "client.knowledge.navigation": _navigation,
    "workflow.create": _workflow_create,
    "workflow.open": _workflow_open,
    "workflow.status": _workflow_status,
    "workflow.start": _workflow_start,
    "presentation.create_from_document": _presentation_create,
    "presentation.create_from_text": _presentation_create_from_text,
    "document.word.create_from_text": _word_create_from_text,
    "report.research.create_from_text": _research_report_create_from_text,
    "paper.academic.create_from_text": _academic_paper_create_from_text,
    "artifact.open": _artifact_open,
    "artifact.download": _artifact_download,
    "artifact.consume_structured": _artifact_consume_structured,
}
