from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.rate_limit import limiter

from app.auth import (
    AuthPrincipal,
    get_current_principal,
    require_workspace_member,
)
from app.db import get_db
from app.models import (
    NotificationChannel,
    Workspace,
)
from app.schemas import (
    NotificationChannelCreate,
    NotificationChannelOut,
    NotificationChannelUpdate,
)

Principal = Annotated[AuthPrincipal, Depends(get_current_principal)]
Db = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/v1", tags=["notifications"])


@router.get(
    "/workspaces/{workspace_id}/notification-channels",
    response_model=list[NotificationChannelOut],
)
def list_notification_channels(
    workspace_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> list[NotificationChannel]:
    return list(
        db.scalars(
            select(NotificationChannel)
            .where(NotificationChannel.workspace_id == workspace_id)
            .order_by(NotificationChannel.created_at)
        ).all()
    )


@router.post(
    "/workspaces/{workspace_id}/notification-channels",
    response_model=NotificationChannelOut,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
def create_notification_channel(
    request: Request,
    workspace_id: UUID,
    body: NotificationChannelCreate,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> NotificationChannel:
    existing = db.scalar(
        select(NotificationChannel).where(
            NotificationChannel.workspace_id == workspace_id,
            NotificationChannel.type == body.type,
            NotificationChannel.address == str(body.address),
        )
    )
    if existing is not None:
        existing.enabled = body.enabled
        db.commit()
        db.refresh(existing)
        return existing

    channel = NotificationChannel(
        workspace_id=workspace_id,
        type=body.type,
        address=str(body.address),
        enabled=body.enabled,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@router.patch(
    "/workspaces/{workspace_id}/notification-channels/{channel_id}",
    response_model=NotificationChannelOut,
)
def update_notification_channel(
    workspace_id: UUID,
    channel_id: UUID,
    body: NotificationChannelUpdate,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> NotificationChannel:
    channel = db.scalar(
        select(NotificationChannel).where(
            NotificationChannel.id == channel_id,
            NotificationChannel.workspace_id == workspace_id,
        )
    )
    if channel is None:
        raise HTTPException(status_code=404, detail="Notification channel not found")

    data = body.model_dump(exclude_unset=True)
    if "address" in data and data["address"] is not None:
        channel.address = str(data["address"])
    if "enabled" in data and data["enabled"] is not None:
        channel.enabled = data["enabled"]
    db.commit()
    db.refresh(channel)
    return channel


@router.delete(
    "/workspaces/{workspace_id}/notification-channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_notification_channel(
    workspace_id: UUID,
    channel_id: UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> None:
    channel = db.scalar(
        select(NotificationChannel).where(
            NotificationChannel.id == channel_id,
            NotificationChannel.workspace_id == workspace_id,
        )
    )
    if channel is None:
        raise HTTPException(status_code=404, detail="Notification channel not found")
    db.delete(channel)
    db.commit()
