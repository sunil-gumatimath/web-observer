"""Public share links, team invite links, and public brand assets.

webdog.ai-parity features:
  * Public read-only share links per monitor (unguessable token, no login).
  * Expiring multi-use team invite links.
  * Brand asset images served to the dashboard and public pages.

Only hashed tokens are stored; the plaintext token is shown once at creation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete as sa_delete
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
    ChangeEvent,
    Monitor,
    ShareLink,
    Workspace,
    WorkspaceInvite,
    WorkspaceMember,
)
from app.schemas import (
    PublicShareAlertOut,
    PublicShareMonitorOut,
    PublicShareOut,
    ShareLinkCreate,
    ShareLinkOut,
    WorkspaceInviteCreate,
    WorkspaceInviteOut,
    WorkspaceInviteRedeemOut,
)
from app.services.audit import write_audit
from app.services.branding import brand_asset_allowed
from app.services.storage import get_bytes
from app.services.tokens import hash_token, new_token

Principal = Annotated[AuthPrincipal, Depends(get_current_principal)]
Db = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/v1", tags=["sharing"])


def _new_share_url(token: str) -> str:
    return f"/share/{token}"


def _new_invite_url(token: str) -> str:
    return f"/invite/{token}"


# ---------------------------------------------------------------------------
# Public read-only share links
# ---------------------------------------------------------------------------


@router.post(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/share-links",
    response_model=ShareLinkOut,
    status_code=status.HTTP_201_CREATED,
)
def create_share_link(
    workspace_id: uuid.UUID,
    monitor_id: uuid.UUID,
    body: ShareLinkCreate,
    db: Db,
    principal: Principal,
    workspace: Workspace = Depends(require_role("member")),
) -> ShareLinkOut:
    monitor = db.scalar(
        select(Monitor).where(Monitor.id == monitor_id, Monitor.workspace_id == workspace_id)
    )
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    token, token_hash, prefix = new_token()
    row = ShareLink(
        workspace_id=workspace_id,
        monitor_id=monitor_id,
        token_hash=token_hash,
        token_prefix=prefix,
        created_by_user_id=principal.user_id,
        enabled=True,
        expires_at=(
            datetime.now(UTC) + timedelta(days=body.expires_days) if body.expires_days else None
        ),
    )
    db.add(row)
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="share_link.created",
        resource_type="monitor",
        resource_id=str(monitor_id),
    )
    db.commit()
    db.refresh(row)
    return ShareLinkOut(
        id=row.id,
        monitor_id=row.monitor_id,
        token=token,
        url=_new_share_url(token),
        enabled=row.enabled,
        expires_at=row.expires_at,
        created_at=row.created_at,
        note=body.note,
    )


@router.get(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/share-links",
    response_model=list[dict],
)
def list_share_links(
    workspace_id: uuid.UUID,
    monitor_id: uuid.UUID,
    db: Db,
    _workspace: Workspace = Depends(require_workspace_member),
) -> list[dict]:
    rows = db.scalars(
        select(ShareLink)
        .where(ShareLink.monitor_id == monitor_id, ShareLink.workspace_id == workspace_id)
        .order_by(ShareLink.created_at.desc())
    ).all()
    return [
        {
            "id": str(r.id),
            "monitor_id": str(r.monitor_id),
            "token_prefix": r.token_prefix,
            "enabled": r.enabled,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.delete(
    "/workspaces/{workspace_id}/monitors/{monitor_id}/share-links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_share_link(
    workspace_id: uuid.UUID,
    monitor_id: uuid.UUID,
    link_id: uuid.UUID,
    db: Db,
    principal: Principal,
    _workspace: Workspace = Depends(require_role("admin")),
) -> None:
    row = db.scalar(
        select(ShareLink).where(
            ShareLink.id == link_id,
            ShareLink.monitor_id == monitor_id,
            ShareLink.workspace_id == workspace_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    db.execute(sa_delete(ShareLink).where(ShareLink.id == link_id))
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="share_link.revoked",
        resource_type="monitor",
        resource_id=str(monitor_id),
    )
    db.commit()
@router.get("/public/share/{token}", response_model=PublicShareOut)
def get_public_share(token: str, db: Db) -> PublicShareOut:
    row = db.scalar(select(ShareLink).where(ShareLink.token_hash == hash_token(token)))
    now = datetime.now(UTC)
    if row is None or not row.enabled or (row.expires_at and row.expires_at < now):
        raise HTTPException(status_code=404, detail="Share link not found")

    monitor = db.get(Monitor, row.monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")

    events = db.scalars(
        select(ChangeEvent)
        .where(
            ChangeEvent.monitor_id == monitor.id,
            ChangeEvent.workspace_id == row.workspace_id,
        )
        .order_by(ChangeEvent.created_at.desc())
        .limit(50)
    ).all()

    alerts: list[PublicShareAlertOut] = []
    for ev in events:
        alerts.append(
            PublicShareAlertOut(
                id=ev.id,
                change_category=ev.change_category,
                ai_summary=ev.ai_summary,
                diff_summary=ev.diff_summary,
                diff=None,
                new_hash=ev.new_hash,
                previous_hash=ev.previous_hash,
                created_at=ev.created_at,
            )
        )

    return PublicShareOut(
        monitor=PublicShareMonitorOut(
            monitor_id=monitor.id,
            name=monitor.name,
            url=monitor.url,
            mode=monitor.mode,
            watch_note=monitor.watch_note,
            brand=monitor.brand,
        ),
        alerts=alerts,
        total=len(alerts),
    )
# ---------------------------------------------------------------------------
# Team invite links
# ---------------------------------------------------------------------------


@router.post(
    "/workspaces/{workspace_id}/invites",
    response_model=WorkspaceInviteOut,
    status_code=status.HTTP_201_CREATED,
)
def create_invite(
    workspace_id: uuid.UUID,
    body: WorkspaceInviteCreate,
    db: Db,
    principal: Principal,
    workspace: Workspace = Depends(require_role("admin")),
) -> WorkspaceInviteOut:
    if body.role not in ("owner", "admin", "member", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    token, token_hash, prefix = new_token()
    row = WorkspaceInvite(
        workspace_id=workspace_id,
        token_hash=token_hash,
        token_prefix=prefix,
        created_by_user_id=principal.user_id,
        role=body.role,
        max_uses=body.max_uses,
        expires_at=(
            datetime.now(UTC) + timedelta(days=body.expires_days) if body.expires_days else None
        ),
    )
    db.add(row)
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="invite.created",
        resource_type="workspace",
        resource_id=str(workspace_id),
        meta={"role": body.role},
    )
    db.commit()
    db.refresh(row)
    return WorkspaceInviteOut(
        id=row.id,
        token=token,
        url=_new_invite_url(token),
        role=row.role,
        max_uses=row.max_uses,
        use_count=row.use_count,
        expires_at=row.expires_at,
        created_at=row.created_at,
    )


@router.get("/workspaces/{workspace_id}/invites", response_model=list[dict])
def list_invites(
    workspace_id: uuid.UUID,
    db: Db,
    _workspace: Workspace = Depends(require_role("admin")),
) -> list[dict]:
    rows = db.scalars(
        select(WorkspaceInvite)
        .where(WorkspaceInvite.workspace_id == workspace_id)
        .order_by(WorkspaceInvite.created_at.desc())
    ).all()
    return [
        {
            "id": str(r.id),
            "token_prefix": r.token_prefix,
            "role": r.role,
            "max_uses": r.max_uses,
            "use_count": r.use_count,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.delete(
    "/workspaces/{workspace_id}/invites/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_invite(
    workspace_id: uuid.UUID,
    invite_id: uuid.UUID,
    db: Db,
    principal: Principal,
    _workspace: Workspace = Depends(require_role("admin")),
) -> None:
    row = db.scalar(
        select(WorkspaceInvite).where(
            WorkspaceInvite.id == invite_id, WorkspaceInvite.workspace_id == workspace_id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    db.execute(sa_delete(WorkspaceInvite).where(WorkspaceInvite.id == invite_id))
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="invite.revoked",
        resource_type="workspace",
        resource_id=str(workspace_id),
    )
    db.commit()
@router.get("/invites/{token}/preview")
def preview_invite(token: str, db: Db) -> dict:
    row = db.scalar(select(WorkspaceInvite).where(WorkspaceInvite.token_hash == hash_token(token)))
    now = datetime.now(UTC)
    if row is None or (row.expires_at and row.expires_at < now):
        raise HTTPException(status_code=404, detail="Invite link not found")
    if row.use_count >= row.max_uses:
        raise HTTPException(status_code=410, detail="Invite link has expired")
    workspace = db.get(Workspace, row.workspace_id)
    return {
        "invite_id": str(row.id),
        "workspace_id": str(row.workspace_id),
        "workspace_name": workspace.name if workspace else "a team workspace",
        "role": row.role,
    }


@router.post("/invites/{token}/redeem", response_model=WorkspaceInviteRedeemOut)
def redeem_invite(
    token: str,
    db: Db,
    principal: Principal,
) -> WorkspaceInviteRedeemOut:
    if principal.user is None:
        raise HTTPException(status_code=401, detail="Sign in to accept this invite")
    row = db.scalar(select(WorkspaceInvite).where(WorkspaceInvite.token_hash == hash_token(token)))
    now = datetime.now(UTC)
    if row is None or (row.expires_at and row.expires_at < now):
        raise HTTPException(status_code=404, detail="Invite link not found")
    if row.use_count >= row.max_uses:
        raise HTTPException(status_code=410, detail="Invite link has expired")

    existing = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == row.workspace_id,
            WorkspaceMember.user_id == principal.user.id,
        )
    )
    if existing is None:
        db.add(
            WorkspaceMember(
                workspace_id=row.workspace_id,
                user_id=principal.user.id,
                role=row.role,
            )
        )
        row.use_count += 1
        db.commit()
    workspace = db.get(Workspace, row.workspace_id)
    return WorkspaceInviteRedeemOut(
        workspace_id=row.workspace_id,
        workspace_name=workspace.name if workspace else "the workspace",
        role=row.role,
        message="You've joined the workspace.",
    )


# ---------------------------------------------------------------------------
# Public brand assets (served to the dashboard and public share pages)
# ---------------------------------------------------------------------------


@router.get("/public/assets/{object_key:path}")
def get_public_brand_asset(object_key: str) -> Response:
    if not brand_asset_allowed(object_key):
        return Response(status_code=404)
    data = get_bytes(object_key)
    if not data:
        return Response(status_code=404)
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )