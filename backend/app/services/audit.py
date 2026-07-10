"""Audit logging for enterprise accountability."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.auth import AuthPrincipal
from app.models import AuditLog


def write_audit(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    principal: AuthPrincipal | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id if principal else None,
        actor_email=principal.email if principal else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        meta=meta or {},
    )
    db.add(row)
    db.flush()
    return row
