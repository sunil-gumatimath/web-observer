"""Phase 6–7 routes: import, API keys, webhooks, billing, audit, export, members."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import AuthPrincipal, get_current_principal, require_role, require_workspace_member
from app.config import get_settings
from app.db import get_db
from app.models import (
    ApiKey,
    AuditLog,
    ChangeEvent,
    Monitor,
    User,
    WebhookDelivery,
    WebhookEndpoint,
    Workspace,
    WorkspaceMember,
)
from app.security.ssrf import SSRFError, validate_url_for_fetch
from app.services.api_keys import create_api_key, revoke_api_key
from app.services.audit import write_audit
from app.services.bulk_import import import_monitors, parse_csv
from app.services.plans import PLANS, get_plan, plans_public
from app.services.webhooks import new_webhook_secret

router = APIRouter(prefix="/api/v1", tags=["enterprise"])
Db = Annotated[Session, Depends(get_db)]
Principal = Annotated[AuthPrincipal, Depends(get_current_principal)]


class BulkImportBody(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    csv_text: str | None = None


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class ApiKeyCreated(ApiKeyOut):
    raw_key: str


class WebhookCreate(BaseModel):
    url: str


class WebhookOut(BaseModel):
    id: uuid.UUID
    url: str
    enabled: bool
    created_at: datetime
    secret: str | None = None

    model_config = {"from_attributes": True}


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str | None
    role: str


class MemberRoleUpdate(BaseModel):
    role: str


class PlanCheckoutBody(BaseModel):
    plan: str
    success_url: str = "http://localhost:3000/settings?billing=success"
    cancel_url: str = "http://localhost:3000/settings?billing=cancel"


@router.get("/billing/plans")
def list_plans() -> list[dict]:
    return plans_public()


@router.post("/workspaces/{workspace_id}/billing/checkout")
def create_checkout(
    workspace_id: UUID,
    body: PlanCheckoutBody,
    db: Db,
    principal: Principal,
    workspace: Workspace = Depends(require_role("owner")),
) -> dict:
    if body.plan not in PLANS or body.plan == "free":
        raise HTTPException(status_code=400, detail="Invalid plan")
    settings = get_settings()
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="billing.checkout_started",
        resource_type="workspace",
        resource_id=str(workspace_id),
        meta={"plan": body.plan},
    )
    if not getattr(settings, "stripe_secret_key", None):
        # Simulated upgrade for local/dev only (solo users skip real billing).
        if not settings.is_development:
            raise HTTPException(status_code=501, detail="Stripe is not configured")
        workspace.plan = body.plan
        workspace.plan_status = "active"
        db.commit()
        return {
            "mode": "simulated",
            "message": f"Plan set to {body.plan} (no STRIPE_SECRET_KEY configured)",
            "checkout_url": body.success_url,
        }
    # Stripe key is present but checkout is not implemented — be honest instead
    # of returning a misleading success-shaped placeholder.
    raise HTTPException(
        status_code=501,
        detail="Stripe checkout not implemented — billing is not wired up yet",
    )


@router.post("/workspaces/{workspace_id}/monitors/import")
def bulk_import_monitors(
    workspace_id: UUID,
    body: BulkImportBody,
    db: Db,
    principal: Principal,
    workspace: Workspace = Depends(require_role("member")),
) -> dict:
    rows = list(body.items)
    if body.csv_text:
        rows.extend(parse_csv(body.csv_text))
    if not rows:
        raise HTTPException(status_code=400, detail="No items or csv_text provided")
    result = import_monitors(db, workspace, rows)
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="monitors.import",
        resource_type="monitor",
        meta={"created": len(result.created), "errors": len(result.errors)},
    )
    db.commit()
    return {
        "created": result.created,
        "skipped": result.skipped,
        "errors": result.errors,
        "created_count": len(result.created),
    }


@router.get("/workspaces/{workspace_id}/export/monitors")
def export_monitors(
    workspace_id: UUID,
    db: Db,
    workspace: Workspace = Depends(require_workspace_member),
    format: str = Query(default="json"),
) -> Response:
    monitors = db.scalars(
        select(Monitor).where(Monitor.workspace_id == workspace_id).order_by(Monitor.created_at)
    ).all()
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "name", "url", "mode", "css_selector", "schedule_interval_minutes", "enabled", "js_required"])
        for m in monitors:
            w.writerow(
                [m.id, m.name, m.url, m.mode, m.css_selector or "", m.schedule_interval_minutes, m.enabled, m.js_required]
            )
        return Response(content=buf.getvalue(), media_type="text/csv")
    data = [
        {
            "id": str(m.id),
            "name": m.name,
            "url": m.url,
            "mode": m.mode,
            "css_selector": m.css_selector,
            "schedule_interval_minutes": m.schedule_interval_minutes,
            "enabled": m.enabled,
            "js_required": m.js_required,
        }
        for m in monitors
    ]
    import json

    return Response(content=json.dumps(data), media_type="application/json")


@router.get("/workspaces/{workspace_id}/export/changes")
def export_changes(
    workspace_id: UUID,
    db: Db,
    workspace: Workspace = Depends(require_workspace_member),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[dict]:
    events = db.scalars(
        select(ChangeEvent)
        .where(ChangeEvent.workspace_id == workspace_id)
        .order_by(ChangeEvent.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": str(e.id),
            "monitor_id": str(e.monitor_id),
            "diff_summary": e.diff_summary,
            "ai_summary": e.ai_summary,
            "category": e.change_category,
            "is_noise": e.is_noise,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


@router.get("/workspaces/{workspace_id}/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(
    workspace_id: UUID,
    db: Db,
    workspace: Workspace = Depends(require_role("admin")),
) -> list[ApiKey]:
    return list(
        db.scalars(
            select(ApiKey)
            .where(ApiKey.workspace_id == workspace_id)
            .order_by(ApiKey.created_at.desc())
        ).all()
    )


@router.post("/workspaces/{workspace_id}/api-keys", response_model=ApiKeyCreated)
def create_key(
    workspace_id: UUID,
    body: ApiKeyCreate,
    db: Db,
    principal: Principal,
    workspace: Workspace = Depends(require_role("admin")),
) -> ApiKeyCreated:
    plan = get_plan(workspace)
    if not plan.api_keys:
        raise HTTPException(status_code=403, detail=f"Plan {plan.name} does not include API keys")
    row, raw = create_api_key(
        db,
        workspace_id=workspace_id,
        name=body.name,
        created_by=principal.user_id,
    )
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="api_key.created",
        resource_type="api_key",
        resource_id=str(row.id),
    )
    db.commit()
    db.refresh(row)
    return ApiKeyCreated(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        raw_key=raw,
    )


@router.delete("/workspaces/{workspace_id}/api-keys/{key_id}", status_code=204)
def delete_key(
    workspace_id: UUID,
    key_id: UUID,
    db: Db,
    principal: Principal,
    workspace: Workspace = Depends(require_role("admin")),
) -> None:
    key = db.scalar(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.workspace_id == workspace_id)
    )
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    revoke_api_key(db, key)
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="api_key.revoked",
        resource_type="api_key",
        resource_id=str(key_id),
    )
    db.commit()


@router.get("/workspaces/{workspace_id}/webhooks", response_model=list[WebhookOut])
def list_webhooks(
    workspace_id: UUID,
    db: Db,
    workspace: Workspace = Depends(require_role("admin")),
) -> list[WebhookOut]:
    rows = db.scalars(
        select(WebhookEndpoint).where(WebhookEndpoint.workspace_id == workspace_id)
    ).all()
    return [
        WebhookOut(id=r.id, url=r.url, enabled=r.enabled, created_at=r.created_at, secret=None)
        for r in rows
    ]


@router.post("/workspaces/{workspace_id}/webhooks", response_model=WebhookOut)
def create_webhook(
    workspace_id: UUID,
    body: WebhookCreate,
    db: Db,
    principal: Principal,
    workspace: Workspace = Depends(require_role("admin")),
) -> WebhookOut:
    plan = get_plan(workspace)
    if not plan.webhooks:
        raise HTTPException(status_code=403, detail=f"Plan {plan.name} does not include webhooks")
    if not body.url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Webhook URL must be https")
    try:
        validate_url_for_fetch(body.url, resolve_dns=True)
    except SSRFError as exc:
        raise HTTPException(
            status_code=400, detail={"error_code": exc.code, "message": str(exc)}
        ) from exc
    secret = new_webhook_secret()
    row = WebhookEndpoint(workspace_id=workspace_id, url=body.url, secret=secret, enabled=True)
    db.add(row)
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="webhook.created",
        resource_type="webhook",
        resource_id=None,
        meta={"url": body.url},
    )
    db.commit()
    db.refresh(row)
    return WebhookOut(
        id=row.id, url=row.url, enabled=row.enabled, created_at=row.created_at, secret=secret
    )


@router.delete("/workspaces/{workspace_id}/webhooks/{endpoint_id}", status_code=204)
def delete_webhook(
    workspace_id: UUID,
    endpoint_id: UUID,
    db: Db,
    principal: Principal,
    workspace: Workspace = Depends(require_role("admin")),
) -> None:
    row = db.scalar(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == endpoint_id, WebhookEndpoint.workspace_id == workspace_id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(row)
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="webhook.deleted",
        resource_type="webhook",
        resource_id=str(endpoint_id),
    )
    db.commit()


@router.get("/workspaces/{workspace_id}/webhook-deliveries")
def list_webhook_deliveries(
    workspace_id: UUID,
    db: Db,
    workspace: Workspace = Depends(require_role("admin")),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    rows = db.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.workspace_id == workspace_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": str(r.id),
            "event_type": r.event_type,
            "status": r.status,
            "response_code": r.response_code,
            "attempts": r.attempts,
            "last_error": r.last_error,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/workspaces/{workspace_id}/audit-logs")
def list_audit_logs(
    workspace_id: UUID,
    db: Db,
    workspace: Workspace = Depends(require_role("admin")),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.workspace_id == workspace_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": str(r.id),
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "actor_email": r.actor_email,
            "meta": r.meta,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/workspaces/{workspace_id}/members", response_model=list[MemberOut])
def list_members(
    workspace_id: UUID,
    db: Db,
    workspace: Workspace = Depends(require_workspace_member),
) -> list[MemberOut]:
    members = db.scalars(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
    ).all()
    out: list[MemberOut] = []
    for m in members:
        user = db.get(User, m.user_id)
        out.append(MemberOut(user_id=m.user_id, email=user.email if user else None, role=m.role))
    return out


@router.patch("/workspaces/{workspace_id}/members/{user_id}")
def update_member_role(
    workspace_id: UUID,
    user_id: UUID,
    body: MemberRoleUpdate,
    db: Db,
    principal: Principal,
    workspace: Workspace = Depends(require_role("owner")),
) -> MemberOut:
    if body.role not in ("owner", "admin", "member", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    membership = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if membership.role == "owner" and body.role != "owner":
        owner_count = db.scalar(
            select(func.count())
            .select_from(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role == "owner",
            )
        ) or 0
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last owner")
    membership.role = body.role
    write_audit(
        db,
        workspace_id=workspace_id,
        principal=principal,
        action="member.role_updated",
        resource_type="user",
        resource_id=str(user_id),
        meta={"role": body.role},
    )
    db.commit()
    user = db.get(User, user_id)
    return MemberOut(user_id=user_id, email=user.email if user else None, role=body.role)
