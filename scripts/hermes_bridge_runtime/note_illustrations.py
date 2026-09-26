"""Private API into the existing durable worker for note illustration jobs."""
import json
import re
from fastapi import Header, HTTPException
from fastapi.responses import FileResponse

from backend.services.note_illustrations import NoteIllustrationRequest, media_directory
from . import persistence, session_runtime, contracts


def owner(token, tenant, user):
    persistence._require_internal_strict(token)
    if not tenant or not user:
        raise HTTPException(403, "owner_context_required")
    store = session_runtime._chat_run_store
    if store is None:
        raise HTTPException(503, "illustration_worker_unavailable")
    return store, store.tenant_user_hash(tenant, user)


def owned_run(store, owner_hash, run_id):
    try:
        run = store.get(run_id, tenant_user_hash=owner_hash)
    except (KeyError, PermissionError):
        raise HTTPException(404, "illustration_not_found") from None
    if json.loads(run["execution_payload_json"]).get("run_type") != "note_illustration":
        raise HTTPException(404, "illustration_not_found")
    return run


def snapshot(store, run):
    value = json.loads(run["final_answer"]) if run["status"] == "completed" else {}
    events = store.events_after(run["run_id"], 0, tenant_user_hash=run["tenant_user_hash"])
    messages = [e.get("message") for e in events if e.get("type") == "status" and e.get("message")]
    return {"run_id": run["run_id"], "status": run["status"],
            "message": messages[-1] if messages else "正在挑选配图位置",
            "assets": value.get("assets", []), "failed_indices": value.get("failed_indices", []),
            "error_code": run.get("error_code", "")}


async def start(body: NoteIllustrationRequest, x_hermes_internal_token: str | None = Header(None),
                x_tenant_id: str | None = Header(None), x_user_id: str | None = Header(None)):
    store, owner_hash = owner(x_hermes_internal_token, x_tenant_id, x_user_id)
    contracts._require_durable_worker()
    if body.retry_run_id:
        owned_run(store, owner_hash, body.retry_run_id)
    run, created = store.create_or_get(
        tenant_user_hash=owner_hash, tenant_id=x_tenant_id, user_id=x_user_id,
        session_id=f"note-illustration-{body.note_id}", request_id=body.request_id,
        execution_payload={"run_type": "note_illustration", "illustration": body.model_dump(), "agent_config": {}},
    )
    if not created and json.loads(run["execution_payload_json"])["illustration"] != body.model_dump():
        raise HTTPException(409, "illustration_request_conflict")
    return snapshot(store, run)


async def status(run_id: str, x_hermes_internal_token: str | None = Header(None),
                 x_tenant_id: str | None = Header(None), x_user_id: str | None = Header(None)):
    store, owner_hash = owner(x_hermes_internal_token, x_tenant_id, x_user_id)
    return snapshot(store, owned_run(store, owner_hash, run_id))


async def cancel(run_id: str, x_hermes_internal_token: str | None = Header(None),
                 x_tenant_id: str | None = Header(None), x_user_id: str | None = Header(None)):
    store, owner_hash = owner(x_hermes_internal_token, x_tenant_id, x_user_id)
    owned_run(store, owner_hash, run_id)
    store.terminal(run_id, status="cancelled", error_code="user_cancelled")
    return snapshot(store, store.get(run_id, tenant_user_hash=owner_hash))


async def asset(run_id: str, index: int, x_hermes_internal_token: str | None = Header(None),
                x_tenant_id: str | None = Header(None), x_user_id: str | None = Header(None)):
    store, owner_hash = owner(x_hermes_internal_token, x_tenant_id, x_user_id)
    owned_run(store, owner_hash, run_id)
    if index not in range(3) or not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise HTTPException(404, "illustration_asset_not_found")
    path = media_directory(store, run_id) / f"{index}.jpg"
    if not path.is_file():
        raise HTTPException(404, "illustration_asset_not_found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


async def latest(note_id: str, x_hermes_internal_token: str | None = Header(None),
                 x_tenant_id: str | None = Header(None), x_user_id: str | None = Header(None)):
    store, owner_hash = owner(x_hermes_internal_token, x_tenant_id, x_user_id)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", note_id):
        raise HTTPException(404, "illustration_not_found")
    run, _, _ = store.status_snapshot(tenant_user_hash=owner_hash, session_id=f"note-illustration-{note_id}")
    if run is None:
        return {"note_id": note_id, "status": "not_started", "assets": [], "insertion_status": "device_owned"}
    return {**snapshot(store, owned_run(store, owner_hash, run["run_id"])),
            "note_id": note_id, "insertion_status": "device_owned"}
