"""API rate limiting using slowapi.

Import `limiter` in any router to apply per-endpoint rate limits.
The limiter and exception handler are registered on the FastAPI app in main.py.
"""

from __future__ import annotations

import logging

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from app.config import get_settings

logger = logging.getLogger(__name__)


def _storage_uri() -> str | None:
    """Use Redis so multi-process / multi-instance API workers share counters.

    Falls back to in-memory when redis_url is empty (tests / single-process).
    """
    settings = get_settings()
    uri = (settings.redis_url or "").strip()
    return uri or None


def _key_func(request: Request) -> str:
    """Rate-limit key: authenticated principal when available, else IP.

    Prefers a verified principal if the request has already been authenticated
    (via app.auth). Falls back to best-effort JWT sub parsing for unauthenticated
    endpoints that still want per-user limiting, else IP.
    """
    # Prefer verified principal stash set by auth middleware if present
    principal = getattr(request.state, "auth_principal", None)
    if principal is not None:
        # AuthPrincipal.user_id or clerk_user_id
        uid = getattr(principal, "clerk_user_id", None) or getattr(principal, "user_id", None)
        if uid:
            return f"user:{uid}"
        ak_ws = getattr(principal, "api_key_workspace_id", None)
        if ak_ws:
            return f"apikey:{ak_ws}"
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        tok = auth.split(" ", 1)[1].strip()
        if tok.startswith("mtw_"):
            return f"apikey:{tok[:24]}"
        # Clerk JWT: take sub claim without verifying (cheap, best-effort fallback)
        try:
            import base64
            import json

            part = tok.split(".")[1]
            part += "=" * (-len(part) % 4)
            payload = json.loads(base64.urlsafe_b64decode(part))
            sub = payload.get("sub")
            if sub:
                # Prefix to distinguish unverified fallback
                return f"user_unverified:{sub}"
        except Exception:
            pass
    return f"ip:{get_remote_address(request)}"


# Default: 60 requests/minute per authenticated principal (or per IP when
# unauthenticated) for decorated endpoints that rely on defaults.
# Individual endpoints can override with @limiter.limit("10/minute").
limiter = Limiter(
    key_func=_key_func,
    default_limits=["60/minute"],
    storage_uri=_storage_uri(),
)


def rate_limit_exceeded_handler(_request: Request, exc: RateLimitExceeded) -> Response:
    """Return a JSON 429 response when rate limit is hit."""
    logger.warning("rate_limit_exceeded ip=%s detail=%s", get_remote_address(_request), str(exc))
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )
