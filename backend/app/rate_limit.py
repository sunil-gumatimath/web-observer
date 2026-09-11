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
    """Rate-limit key from the VERIFIED principal only, else client IP.

    The principal is stashed on ``request.state.auth_principal`` by the
    verified auth dependency (:func:`app.auth.get_current_principal`).
    This function never parses tokens itself: an unverified JWT ``sub``
    is attacker-controlled input and must not allocate its own bucket
    (spoofed-sub keying would let a caller dodge per-user limits or
    collide with another user's bucket).
    """
    # Verified principal only — set by the auth dependency after checking
    # the signature / API-key hash. Anything else falls through to IP below.
    principal = getattr(request.state, "auth_principal", None)
    if principal is not None:
        # AuthPrincipal.user_id or clerk_user_id
        uid = getattr(principal, "clerk_user_id", None) or getattr(principal, "user_id", None)
        if uid:
            return f"user:{uid}"
        ak_ws = getattr(principal, "api_key_workspace_id", None)
        if ak_ws:
            return f"apikey:{ak_ws}"
        if getattr(principal, "is_internal", False):
            return "internal:local"
        # Authenticated but no stable identity (e.g. first-login Clerk user
        # whose row is still provisioning): share one bucket, never the IP
        # pool and never a caller-supplied claim.
        return "auth:unknown"
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
