"""API key generation and verification."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ApiKey, User, Workspace, WorkspaceMember


def _hash_key(raw: str) -> str:
    settings = get_settings()
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_api_key(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    name: str,
    created_by: uuid.UUID | None,
) -> tuple[ApiKey, str]:
    raw = f"mtw_{secrets.token_urlsafe(32)}"
    prefix = raw[:12]
    row = ApiKey(
        workspace_id=workspace_id,
        name=name,
        key_prefix=prefix,
        key_hash=_hash_key(raw),
        created_by_user_id=created_by,
    )
    db.add(row)
    db.flush()
    return row, raw


def lookup_api_key(db: Session, raw: str) -> tuple[ApiKey, Workspace, User | None] | None:
    if not raw.startswith("mtw_"):
        return None
    key_hash = _hash_key(raw)
    row = db.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None)))
    if row is None:
        return None
    ws = db.get(Workspace, row.workspace_id)
    if ws is None:
        return None
    user = db.get(User, row.created_by_user_id) if row.created_by_user_id else None
    row.last_used_at = datetime.now(UTC)
    return row, ws, user


def revoke_api_key(db: Session, key: ApiKey) -> None:
    key.revoked_at = datetime.now(UTC)
