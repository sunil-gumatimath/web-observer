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


# Default: 60 requests/minute per IP for decorated endpoints that rely on defaults.
# Individual endpoints can override with @limiter.limit("10/minute").
limiter = Limiter(
    key_func=get_remote_address,
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
