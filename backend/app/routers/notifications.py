from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    AuthPrincipal,
    get_current_principal,
    require_role,
    require_workspace_member,
)
from app.db import get_db
from app.models import (
    NotificationChannel,
    Workspace,
)
from app.rate_limit import limiter
from app.schemas import (
    NotificationChannelCreate,
    NotificationChannelOut,
    NotificationChannelUpdate,
)
from app.security.ssrf import SSRFError, validate_url_for_fetch

Principal = Annotated[AuthPrincipal, Depends(get_current_principal)]
Db = Annotated[Session, Depends(get_db)]
MemberWs = Annotated[Workspace, Depends(require_role("member"))]
AnyWs = Annotated[Workspace, Depends(require_workspace_member)]

router = APIRouter(prefix="/api/v1", tags=["notifications"])


@router.get(
    "/workspaces/{workspace_id}/notification-channels",
    response_model=list[NotificationChannelOut],
)
def list_notification_channels(
    workspace_id: UUID,
    db: Db,
    _workspace: AnyWs,
) -> list[NotificationChannel]:
    return list(
        db.scalars(
            select(NotificationChannel)
            .where(NotificationChannel.workspace_id == workspace_id)
            .order_by(NotificationChannel.created_at)
        ).all()
    )


def _validate_channel_address(channel_type: str, address: str) -> None:
    if channel_type not in ("slack", "discord"):
        return
    if not address.startswith("https://"):
        raise HTTPException(status_code=400, detail="Webhook address must be an https URL")
    try:
        validate_url_for_fetch(address, resolve_dns=True)
    except SSRFError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error_code": exc.code, "message": str(exc)},
        ) from exc


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
    _workspace: MemberWs,
) -> NotificationChannel:
    _validate_channel_address(body.type, str(body.address))
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
    _workspace: MemberWs,
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
    channel_type = (channel.type or "email").lower()
    if "address" in data and data["address"] is not None:
        _validate_channel_address(channel_type, str(data["address"]))
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
    _workspace: MemberWs,
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


@router.post("/workspaces/{workspace_id}/notification-channels/{channel_id}/test")
@limiter.limit("5/minute")
def test_notification_channel(
    request: Request,
    workspace_id: UUID,
    channel_id: UUID,
    db: Db,
    _workspace: MemberWs,
) -> dict:
    """Send a one-off test message to verify a channel works.

    Reuses the same delivery helpers as the notification worker so the test
    path matches real delivery. Returns ok/detail rather than raising on a
    delivery failure, so the UI can show the exact error.
    """
    from app.services.email import send_email
    from app.workers.notifications import _send_discord, _send_slack

    channel = db.scalar(
        select(NotificationChannel).where(
            NotificationChannel.id == channel_id,
            NotificationChannel.workspace_id == workspace_id,
        )
    )
    if channel is None:
        raise HTTPException(status_code=404, detail="Notification channel not found")

    title = "[Web Observer] Test notification"
    body = (
        "This is a test message from Web Observer. "
        "If you can read this, your channel is configured correctly."
    )

    try:
        ctype = (channel.type or "email").lower()
        if ctype == "slack":
            _send_slack(channel.address, title, body)
        elif ctype == "discord":
            _send_discord(channel.address, title, body)
        else:
            send_email(to=channel.address, subject=title, text=body)
        return {"ok": True, "detail": f"Test {ctype} message sent to {channel.address}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc)[:500]}
