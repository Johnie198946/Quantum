#!/usr/bin/env python3
"""Run the live Gate C two-owner/four-session isolation matrix."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path

import jwt
import requests


def token(secret: str, *, owner: str, tenant: str, issuer: str, audience: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": owner,
            "username": owner,
            "tenant_id": tenant,
            "iss": issuer,
            "aud": audience,
            "token_use": "access",
            "principal_type": "human",
            "amr": ["gate_c_live_acceptance"],
            "iat": now,
            "exp": now + 3600,
        },
        secret,
        algorithm="HS256",
    )


def headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Client-Contract": "ios-unified-agreement-v1",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--db", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()

    secret = os.environ["GATE_C_JWT_SECRET"]
    issuer = os.environ.get("GATE_C_JWT_ISSUER", "quantumn")
    audience = os.environ.get("GATE_C_JWT_AUDIENCE", "quantumn-ios")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tenant = f"gate-c-tenant-{stamp}"
    owners = (f"gate-c-account-a-{stamp}", f"gate-c-account-b-{stamp}")
    sessions = {
        owners[0]: (f"gate-c-a1-{stamp}", f"gate-c-a2-{stamp}"),
        owners[1]: (f"gate-c-b1-{stamp}", f"gate-c-b2-{stamp}"),
    }
    tokens = {
        owner: token(secret, owner=owner, tenant=tenant, issuer=issuer, audience=audience)
        for owner in owners
    }
    agreement = requests.get(f"{args.base_url}/api/v1/legal/agreement", timeout=30)
    agreement.raise_for_status()
    agreement_version = agreement.json()["version"]
    for owner in owners:
        accepted = requests.put(
            f"{args.base_url}/api/v1/me/agreement-acceptance",
            headers=headers(tokens[owner]),
            json={
                "agreement_version": agreement_version,
                "idempotency_key": str(uuid.uuid4()),
                "source": "ios",
            },
            timeout=60,
        )
        assert accepted.status_code == 200, accepted.text
    markers = {
        session: f"GATE-C-{session.upper()}"
        for owner in owners
        for session in sessions[owner]
    }

    def chat(owner_session: tuple[str, str]) -> dict[str, object]:
        owner, session = owner_session
        marker = markers[session]
        response = requests.post(
            f"{args.base_url}/api/chat/stream",
            headers=headers(tokens[owner]),
            json={
                "question": (
                    f"请生成一份完整报告方案，并通过 document.word.create_from_text 产品能力创建多页可编辑 Word 文档。标题必须原样使用 {marker}。"
                    "材料：季度经营计划；收入目标 USD 2.0 million；"
                    "Milestone Alpha = 15 October；财务与交付共同签字。"
                    "先大纲后全文审核；用户修改后归档最终 DOCX。"
                ),
                "session_id": session,
                "request_id": str(uuid.uuid4()),
                "agent_id": "main_agent",
                "regenerate": False,
                "context_scope": {"mode": "auto", "local_notes": []},
                "client_capabilities": [
                    "qcp_v1", "knowledge_action_v1", "answer_blocks_v1"
                ],
            },
            timeout=360,
        )
        response.raise_for_status()
        body = response.text
        foreign = [value for key, value in markers.items() if key != session and value in body]
        ids = re.findall(r'"run_id"\s*:\s*"([^"]+)"', body)
        return {
            "owner": owner,
            "session": session,
            "marker": marker,
            "run_id": ids[-1] if ids else "",
            "own_marker": marker in body,
            "foreign_markers": foreign,
            "body_tail": body[-1200:],
        }

    matrix = [(owner, session) for owner in owners for session in sessions[owner]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        chat_receipts = list(executor.map(chat, matrix))
    chat_failures = [
        item for item in chat_receipts
        if not item["own_marker"] or item["foreign_markers"]
    ]
    if chat_failures:
        failure_path = Path(args.receipt).with_name(Path(args.receipt).stem + "-failure.json")
        failure_path.write_text(
            json.dumps({"chat_runs": chat_receipts}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        raise AssertionError(f"chat isolation failures recorded at {failure_path}")

    def create_workflow(owner_session: tuple[str, str]) -> dict[str, str]:
        owner, session = owner_session
        response = requests.post(
            f"{args.base_url}/api/v1/workflows",
            headers=headers(tokens[owner]),
            json={
                "title": f"Gate C {session}",
                "description": "Two-owner four-session live isolation acceptance",
                "desired_output": "Session-scoped editable DOCX",
                "output_kind": "document",
                "source_client_session_id": session,
            },
            timeout=60,
        )
        assert response.status_code == 201, response.text
        workflow = response.json()["workflow"]
        return {"owner": owner, "session": session, "workflow_id": workflow["id"]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        workflow_receipts = list(executor.map(create_workflow, matrix))

    def activate_workflow(item: dict[str, str]) -> None:
        owner = item["owner"]
        workflow_id = item["workflow_id"]
        for _ in range(8):
            state = requests.get(
                f"{args.base_url}/api/v1/workflows/{workflow_id}/clarification",
                headers=headers(tokens[owner]),
                timeout=60,
            )
            state.raise_for_status()
            phase = state.json()["session"]["phase"]
            if phase == "planning":
                return
            payload = (
                {"response": "内容准确", "intent": "confirm"}
                if phase == "awaiting_requirement_confirmation"
                else {"response": "按默认建议"}
            )
            advanced = requests.post(
                f"{args.base_url}/api/v1/workflows/{workflow_id}/clarification/respond",
                headers=headers(tokens[owner]),
                json=payload,
                timeout=120,
            )
            assert advanced.status_code == 200, advanced.text
        raise AssertionError(f"workflow did not reach planning: {workflow_id}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(activate_workflow, workflow_receipts))

    expected = {(item["owner"], item["session"]): item["workflow_id"] for item in workflow_receipts}
    for owner, session in matrix:
        response = requests.get(
            f"{args.base_url}/api/v1/workflow-activities/active",
            headers=headers(tokens[owner]),
            params={"source_client_session_id": session},
            timeout=60,
        )
        response.raise_for_status()
        visible = {item["workflow"]["id"] for item in response.json()}
        assert expected[(owner, session)] in visible
        assert not (visible & (set(expected.values()) - {expected[(owner, session)]})), (owner, session, visible)
        other = owners[1] if owner == owners[0] else owners[0]
        denied = requests.get(
            f"{args.base_url}/api/v1/workflows/{expected[(owner, session)]}",
            headers=headers(tokens[other]),
            timeout=60,
        )
        assert denied.status_code == 404, denied.text

    legacy_response = requests.post(
        f"{args.base_url}/api/v1/workflows",
        headers=headers(tokens[owners[0]]),
        json={
            "title": f"Gate C legacy {stamp}",
            "description": "Owner-scoped legacy workflow without session provenance",
            "source_client_session_id": sessions[owners[0]][0],
        },
        timeout=60,
    )
    assert legacy_response.status_code == 201, legacy_response.text
    legacy_id = legacy_response.json()["workflow"]["id"]
    with sqlite3.connect(args.db) as connection:
        connection.execute(
            "UPDATE workflows SET clarification_session_id=NULL, source_client_session_binding_id=NULL, "
            "source_client_session_id=NULL WHERE id=?",
            (legacy_id,),
        )
        connection.commit()
    denied = requests.get(
        f"{args.base_url}/api/v1/workflows/{legacy_id}",
        headers=headers(tokens[owners[1]]),
        timeout=60,
    )
    assert denied.status_code == 404, denied.text
    active = requests.get(
        f"{args.base_url}/api/v1/workflow-activities/active",
        headers=headers(tokens[owners[0]]),
        params={"source_client_session_id": sessions[owners[0]][0]},
        timeout=60,
    )
    active.raise_for_status()
    assert legacy_id not in {item["workflow"]["id"] for item in active.json()}

    receipt = {
        "gate": "C",
        "status": "passed",
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tenant": tenant,
        "owners": list(owners),
        "chat_runs": chat_receipts,
        "workflows": workflow_receipts,
        "legacy_workflow": {"workflow_id": legacy_id, "foreign_owner_status": denied.status_code},
        "assertions": {
            "four_concurrent_backend_hermes_sessions": True,
            "no_foreign_chat_marker": True,
            "four_session_scoped_active_workflows": True,
            "cross_owner_workflow_reads_return_404": True,
            "legacy_workflow_owner_scoped_and_not_session_active": True,
        },
    }
    Path(args.receipt).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "chat_runs": 4, "workflows": 4, "receipt": args.receipt}))


if __name__ == "__main__":
    main()
