from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import (
    AuthPrincipal,
    get_current_principal,
    list_user_workspaces,
    require_role,
    require_workspace_member,
)
from app.db import get_db
from app.models import (
    Workspace,
    WorkspaceMember,
)
from app.schemas import (
    MeOut,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceUpdate,
)

Principal = Annotated[AuthPrincipal, Depends(get_current_principal)]
Db = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/v1", tags=["workspaces"])


@router.get("/me", response_model=MeOut)
def me(principal: Principal, db: Db) -> MeOut:
    workspaces = list_user_workspaces(db, principal)
    return MeOut(
        id=principal.user_id,
        email=principal.email or (principal.user.email if principal.user else None),
        clerk_user_id=principal.clerk_user_id
        or (principal.user.clerk_user_id if principal.user else None),
        is_internal=principal.is_internal,
        workspaces=[WorkspaceOut.model_validate(w) for w in workspaces],
    )


@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(principal: Principal, db: Db) -> list[Workspace]:
    return list_user_workspaces(db, principal)


@router.post("/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(body: WorkspaceCreate, principal: Principal, db: Db) -> Workspace:
    if principal.is_internal and principal.user is None:
        # Internal callers may create orphan workspaces (seed/tools)
        workspace = Workspace(name=body.name)
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        return workspace

    if principal.user is None:
        raise HTTPException(status_code=401, detail="Unauthenticated")

    workspace = Workspace(name=body.name)
    db.add(workspace)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=principal.user.id,
            role="owner",
        )
    )
    db.commit()
    db.refresh(workspace)
    return workspace


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(
    workspace_id: UUID,
    workspace: Workspace = Depends(require_workspace_member),
) -> Workspace:
    return workspace


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: UUID,
    body: WorkspaceUpdate,
    db: Db,
    workspace: Workspace = Depends(require_role("admin")),
) -> Workspace:
    allowed = {"name", "digest_cadence", "digest_hour_utc", "ai_summaries_enabled"}
    for key, value in body.model_dump(exclude_unset=True).items():
        if key in allowed:
            setattr(workspace, key, value)
    db.commit()
    db.refresh(workspace)
    return workspace
