"""Authentication and workspace authorization.

Modes:
1. Clerk JWT (`Authorization: Bearer <token>`) when CLERK_JWKS_URL + CLERK_ISSUER set
2. Internal token (`X-Internal-Token`) for local/dev and smoke tests
"""

from __future__ import annotations

import hmac
import logging
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import BackgroundTasks, Depends, Header, HTTPException, Request, status
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User, Workspace, WorkspaceMember

logger = logging.getLogger(__name__)

_jwks_client: PyJWKClient | None = None
_jwks_client_url: str | None = None


@dataclass
class AuthPrincipal:
    """Authenticated caller."""

    user: User | None
    is_internal: bool
    clerk_user_id: str | None = None
    email: str | None = None
    api_key_workspace_id: uuid.UUID | None = None
    role_hint: str | None = None  # from membership when scoped

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.user.id if self.user else None


def clerk_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.clerk_jwks_url and settings.clerk_issuer)


def _get_jwks_client(settings: Settings) -> PyJWKClient:
    global _jwks_client, _jwks_client_url
    assert settings.clerk_jwks_url
    if _jwks_client is None or _jwks_client_url != settings.clerk_jwks_url:
        from app.security.ssl_context import get_ssl_context

        _jwks_client = PyJWKClient(
            settings.clerk_jwks_url,
            ssl_context=get_ssl_context(),
            cache_keys=True,
        )
        _jwks_client_url = settings.clerk_jwks_url
    return _jwks_client


def verify_clerk_token(token: str, settings: Settings) -> dict[str, Any]:
    if not clerk_configured(settings):
        raise HTTPException(status_code=401, detail="Clerk is not configured")
    try:
        client = _get_jwks_client(settings)
        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            options={"verify_aud": False},  # Clerk session tokens often omit aud
            leeway=10,
        )
        return payload
    except jwt.PyJWTError as exc:
        logger.info("clerk_jwt_invalid error=%s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def upsert_clerk_user(db: Session, *, clerk_user_id: str, email: str) -> User:
    user = db.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
    if user is None:
        # Prefer clerk id; if email already exists from seed, attach clerk id —
        # but never hijack an account that is already linked to a different
        # Clerk identity (would be a cross-account merge / takeover).
        by_email = db.scalar(select(User).where(User.email == email))
        if by_email is not None and by_email.clerk_user_id:
            raise HTTPException(
                status_code=401,
                detail="This email is already linked to a different account.",
            )
        if by_email is not None:
            by_email.clerk_user_id = clerk_user_id
            user = by_email
        else:
            user = User(clerk_user_id=clerk_user_id, email=email)
            db.add(user)
        db.flush()
    elif user.email != email and email:
        user.email = email
        db.flush()
    return user


def ensure_default_workspace(db: Session, user: User) -> Workspace:
    membership = db.scalar(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id).limit(1)
    )
    if membership is not None:
        workspace = db.get(Workspace, membership.workspace_id)
        assert workspace is not None
        return workspace

    workspace = Workspace(name=f"{user.email.split('@')[0]}'s workspace")
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
    db.flush()
    return workspace


def _touch_api_key_last_used(key_id: uuid.UUID) -> None:
    """Background write: refresh an API key's ``last_used_at`` in its own session.

    Runs via FastAPI BackgroundTasks after the response is sent, so the
    request-scoped session in :func:`get_current_principal` stays read-only.
    Best-effort: a stale timestamp must never fail a request.
    """
    try:
        from datetime import UTC, datetime

        from app.db import SessionLocal
        from app.models import ApiKey

        session = SessionLocal()
    except Exception as exc:  # noqa: BLE001 - never fail the request path
        logger.debug("api_key_touch_setup_failed error=%s", exc)
        return
    try:
        row = session.get(ApiKey, key_id)
        if row is not None:
            row.last_used_at = datetime.now(UTC)
            session.commit()
    except Exception as exc:  # noqa: BLE001 - best-effort timestamp
        session.rollback()
        logger.debug("api_key_touch_failed error=%s", exc)
    finally:
        session.close()


def sync_clerk_principal(db: Session, *, clerk_user_id: str, email: str) -> User:
    """Explicit provisioning path for Clerk users. COMMITS.

    :func:`get_current_principal` is read-only; first-login provisioning is
    deferred to a background task. Endpoints that need the user row
    immediately (e.g. workspace bootstrap) should call this explicitly
    instead of relying on auth side effects.
    """
    user = upsert_clerk_user(db, clerk_user_id=clerk_user_id, email=email)
    ensure_default_workspace(db, user)
    db.commit()
    db.refresh(user)
    return user


def _sync_clerk_user_background(clerk_user_id: str, email: str) -> None:
    """Background provisioning for first-login Clerk users (own session)."""
    try:
        from app.db import SessionLocal

        session = SessionLocal()
    except Exception as exc:  # noqa: BLE001 - never fail the request path
        logger.debug("clerk_sync_setup_failed error=%s", exc)
        return
    try:
        sync_clerk_principal(session, clerk_user_id=clerk_user_id, email=email)
    except Exception as exc:  # noqa: BLE001 - best-effort provisioning
        session.rollback()
        logger.debug("clerk_sync_failed error=%s", exc)
    finally:
        session.close()


def get_current_principal(
    request: Request,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
    x_internal_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthPrincipal:
    """Resolve the caller. READ-ONLY: never commits or flushes ``db``.

    Writes that used to happen here moved out of the request path:
    API-key ``last_used_at`` touches run in :func:`_touch_api_key_last_used`
    via BackgroundTasks, and Clerk user/workspace provisioning runs in
    :func:`_sync_clerk_user_background` (or explicitly via
    :func:`sync_clerk_principal`). The verified principal is stashed on
    ``request.state.auth_principal`` for the rate limiter — which must only
    ever trust this value, never a self-parsed JWT claim.
    """
    # Prefer Bearer token when present (API key or Clerk JWT)
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Empty bearer token")

        # Workspace API keys: mtw_...
        if token.startswith("mtw_"):
            from app.services.api_keys import lookup_api_key

            found = lookup_api_key(db, token)
            if found is None:
                raise HTTPException(status_code=401, detail="Invalid API key")
            _key, ws, user = found
            # lookup_api_key stages last_used_at on the request session as a
            # side effect; discard it so this dependency performs no write.
            # The touch is deferred to a background task with its own session.
            key_id = _key.id
            try:
                db.rollback()
            except Exception:  # noqa: BLE001 - rollback is best-effort cleanup
                pass
            if background_tasks is not None:
                background_tasks.add_task(_touch_api_key_last_used, key_id)
            principal = AuthPrincipal(
                user=user,
                is_internal=False,
                email=user.email if user else f"apikey@{ws.id}",
                api_key_workspace_id=ws.id,
                role_hint="admin",
            )
            request.state.auth_principal = principal
            return principal

        if not clerk_configured(settings):
            raise HTTPException(
                status_code=401,
                detail="Bearer auth requires Clerk configuration or an mtw_ API key",
            )
        payload = verify_clerk_token(token, settings)
        clerk_user_id = str(payload.get("sub") or "")
        if not clerk_user_id:
            raise HTTPException(status_code=401, detail="Token missing subject")
        email = (
            payload.get("email")
            or payload.get("primary_email")
            or f"{clerk_user_id}@users.clerk.local"
        )
        if isinstance(email, list):
            email = email[0] if email else f"{clerk_user_id}@users.clerk.local"
        email = str(email)
        # Read-only: resolve an existing user without writing. First-login
        # provisioning (upsert + default workspace) is deferred to a
        # background task with its own session, or to an explicit
        # sync_clerk_principal() call where the row is needed immediately.
        user = db.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
        if user is None:
            if background_tasks is not None:
                background_tasks.add_task(_sync_clerk_user_background, clerk_user_id, email)
            principal = AuthPrincipal(
                user=None, is_internal=False, clerk_user_id=clerk_user_id, email=email
            )
            request.state.auth_principal = principal
            return principal
        if email and user.email != email and background_tasks is not None:
            background_tasks.add_task(_sync_clerk_user_background, clerk_user_id, email)
        principal = AuthPrincipal(
            user=user, is_internal=False, clerk_user_id=clerk_user_id, email=user.email
        )
        request.state.auth_principal = principal
        return principal

    # Dev / smoke internal token
    if hmac.compare_digest(x_internal_token or "", settings.internal_api_token):
        principal = AuthPrincipal(
            user=None, is_internal=True, email="internal@local", role_hint="owner"
        )
        request.state.auth_principal = principal
        return principal

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication (Bearer token, API key, or X-Internal-Token)",
    )


ROLE_RANK = {"viewer": 1, "member": 2, "admin": 3, "owner": 4}


def require_workspace_member(
    workspace_id: uuid.UUID,
    principal: AuthPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if principal.is_internal:
        principal.role_hint = "owner"
        return workspace

    # API key scoped to one workspace
    if principal.api_key_workspace_id is not None:
        if principal.api_key_workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Workspace not found")
        principal.role_hint = principal.role_hint or "admin"
        return workspace

    if principal.user is None:
        raise HTTPException(status_code=401, detail="Unauthenticated")

    membership = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == principal.user.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    principal.role_hint = membership.role
    return workspace


def require_role(min_role: str):
    """Dependency factory: require membership role >= min_role on workspace path param."""

    def _dep(
        workspace_id: uuid.UUID,
        principal: AuthPrincipal = Depends(get_current_principal),
        db: Session = Depends(get_db),
    ) -> Workspace:
        workspace = require_workspace_member(workspace_id, principal, db)
        role = principal.role_hint or "viewer"
        if ROLE_RANK.get(role, 0) < ROLE_RANK.get(min_role, 99):
            raise HTTPException(status_code=403, detail=f"Requires role {min_role} or higher")
        return workspace

    return _dep


def list_user_workspaces(db: Session, principal: AuthPrincipal) -> list[Workspace]:
    if principal.is_internal:
        return list(db.scalars(select(Workspace).order_by(Workspace.created_at)).all())
    if principal.user is None:
        return []
    return list(
        db.scalars(
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == principal.user.id)
            .order_by(Workspace.created_at)
        ).all()
    )


def fetch_clerk_user_email(clerk_user_id: str, settings: Settings) -> str | None:
    """Optional: resolve email via Clerk Backend API when JWT lacks email claim."""
    if not settings.clerk_secret_key:
        return None
    try:
        from app.security.ssl_context import get_ssl_context

        resp = httpx.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
            timeout=10.0,
            verify=get_ssl_context(),
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        addresses = data.get("email_addresses") or []
        primary_id = data.get("primary_email_address_id")
        for addr in addresses:
            if addr.get("id") == primary_id:
                return addr.get("email_address")
        if addresses:
            return addresses[0].get("email_address")
    except Exception as exc:  # noqa: BLE001
        logger.debug("clerk_user_lookup_failed error=%s", exc)
    return None
