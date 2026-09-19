"""Tenant/owner/member access boundary for Quantum Workspace projects.

Kept outside API routers so workflow APIs can enforce project scope without an
API-to-API import cycle.
"""

from __future__ import annotations

from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select

from backend.models.workspace import WorkspaceProject, WorkspaceProjectMember


async def project_for_owner(
    db, project_id: str, tenant_key: str, owner_user_id: str
) -> WorkspaceProject:
    project = await db.scalar(
        select(WorkspaceProject).where(
            WorkspaceProject.id == project_id,
            WorkspaceProject.tenant_key == tenant_key,
            WorkspaceProject.owner_user_id == owner_user_id,
            WorkspaceProject.status != "deleted",
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


async def project_for_access(
    db,
    project_id: str,
    tenant_key: str,
    user_id: str,
    required_scope: Literal["project:read", "project:write"],
    *,
    allow_closed_write: bool = False,
) -> WorkspaceProject:
    project = await db.scalar(
        select(WorkspaceProject).where(
            WorkspaceProject.id == project_id,
            WorkspaceProject.tenant_key == tenant_key,
            WorkspaceProject.status != "deleted",
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    if (
        project.status == "closed"
        and required_scope == "project:write"
        and not allow_closed_write
    ):
        raise HTTPException(status_code=409, detail="project_closed_read_only")
    if project.owner_user_id == user_id:
        return project
    member = await db.scalar(
        select(WorkspaceProjectMember).where(
            WorkspaceProjectMember.project_id == project.id,
            WorkspaceProjectMember.tenant_key == tenant_key,
            WorkspaceProjectMember.user_id == user_id,
            WorkspaceProjectMember.status == "ACTIVE",
        )
    )
    if member is None:
        member_exists = await db.scalar(
            select(WorkspaceProjectMember.id).where(
                WorkspaceProjectMember.project_id == project.id,
                WorkspaceProjectMember.tenant_key == tenant_key,
                WorkspaceProjectMember.user_id == user_id,
            )
        )
        if member_exists is not None:
            raise HTTPException(
                status_code=403, detail="active project membership required"
            )
        raise HTTPException(status_code=404, detail="project not found")
    scopes = set(member.scopes or [])
    allowed = required_scope in scopes or (
        required_scope == "project:read" and "project:write" in scopes
    )
    if not allowed:
        raise HTTPException(
            status_code=403, detail=f"{required_scope} scope required"
        )
    return project
