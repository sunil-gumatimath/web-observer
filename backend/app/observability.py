"""Optional error tracking (Sentry) for the API process.

``SENTRY_DSN`` has been a documented setting for a while but nothing read it,
so a production deploy shipped with no error tracking at all. This wires it up
without making the SDK a hard requirement: with no DSN (the default) or no
installed package, the function is a no-op.
"""

from __future__ import annotations

import logging

from app.config import Settings

logger = logging.getLogger(__name__)

# Headers that carry credentials. They are scrubbed before an event leaves the
# process so a captured request cannot leak an API key, JWT or internal token.
_SENSITIVE_HEADERS = frozenset(
    {"authorization", "x-internal-token", "cookie", "set-cookie", "x-api-key"}
)


def scrub_event(event: dict, _hint: object = None) -> dict:
    """Sentry ``before_send`` hook: drop credential headers and cookies."""
    request = event.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                key: ("[Filtered]" if key.lower() in _SENSITIVE_HEADERS else value)
                for key, value in headers.items()
            }
        request.pop("cookies", None)
    return event


def init_error_tracking(settings: Settings) -> bool:
    """Initialise Sentry when ``SENTRY_DSN`` is set. Returns True when enabled."""
    dsn = (settings.sentry_dsn or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed; error tracking is off")
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=settings.app_env,
        send_default_pii=False,
        before_send=scrub_event,
    )
    logger.info("sentry_enabled environment=%s", settings.app_env)
    return True
