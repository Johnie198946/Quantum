"""Thin QCP bindings; existing domain handlers remain the authorization truth."""

from __future__ import annotations

import fcntl
import hashlib
import json
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
    sync_note,
)
from backend.api.workflows import (
    ApprovalRequest,
    PlanEdit,
    WorkflowCancelRequest,
    WorkflowCreate,
    _create_workflow,
    approve_plan,
    cancel_workflow,
    edit_plan,
    get_artifact_content,
    get_execution,
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
    if capability_id in {"knowledge.note.update", "knowledge.note.archive"}:
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
    return {
        "project_id": process["project_id"],
        "process_revision": process["process_revision"],
        "tasks": process.get("tasks") or [],
    }


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


async def _photo_capture(data, payload, key):
    return await _client_action("photo.capture", data, payload, key)


async def _photo_import(data, payload, key):
    return await _client_action("photo.import", data, payload, key)


async def _voice_record(data, payload, key):
    return await _client_action("voice.record", data, payload, key)


async def _share_present(data, payload, key):
    return await _client_action("share.present", data, payload, key)


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
    "photo.capture": _photo_capture,
    "photo.import": _photo_import,
    "voice.record": _voice_record,
    "share.present": _share_present,
}
