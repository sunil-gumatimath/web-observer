from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import (
    User,
    Workspace,
    WorkspaceMember,
)
from app.schemas import SeedResponse
from app.services.retention import purge_expired_snapshots

settings = get_settings()

router = APIRouter(prefix="/api/v1", tags=["internal"])


def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    if x_internal_token != settings.internal_api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token")


@router.post("/internal/seed", response_model=SeedResponse, dependencies=[Depends(require_internal_token)])
def seed_dev_workspace(
    email: str = "dev@example.com",
    workspace_name: str = "Dev Workspace",
    db: Session = Depends(get_db),
) -> SeedResponse:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email)
        db.add(user)
        db.flush()

    membership = db.scalar(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id).limit(1)
    )
    if membership is None:
        workspace = Workspace(name=workspace_name)
        db.add(workspace)
        db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
        db.commit()
        workspace_id = workspace.id
    else:
        workspace_id = membership.workspace_id
        db.commit()

    return SeedResponse(user_id=user.id, workspace_id=workspace_id, email=user.email)


@router.post(
    "/internal/retention/purge",
    dependencies=[Depends(require_internal_token)],
)
def internal_retention_purge(
    workspace_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> dict:
    result = purge_expired_snapshots(db, workspace_id=workspace_id)
    return {
        "snapshots_deleted": result.snapshots_deleted,
        "runs_deleted": result.runs_deleted,
        "objects_deleted": result.objects_deleted,
    }
