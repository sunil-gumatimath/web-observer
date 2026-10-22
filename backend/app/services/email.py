"""Resend email delivery (official SDK).

Configure via env:
  RESEND_API_KEY=re_...
  EMAIL_FROM=onboarding@resend.dev   # use your domain after Resend verifies it
"""

from __future__ import annotations

import html
import logging
import threading

from app.config import get_settings

logger = logging.getLogger(__name__)

# Serializes the global ``resend.api_key`` swap+send so BYOK sends can never
# leak one workspace's key to (or overwrite) another's in-flight send.
_RESEND_LOCK = threading.Lock()


def send_email(
    *,
    to: str | list[str],
    subject: str,
    text: str,
    html_body: str | None = None,
    api_key: str | None = None,
    from_addr_override: str | None = None,
) -> str:
    """Send an email via Resend. Returns provider message id.

    ``api_key``/``from_addr_override`` allow per-account (bring-your-own)
    credentials to override the server-managed ``RESEND_API_KEY``/``EMAIL_FROM``.

    If no key resolves (fallback is empty), logs to console and returns "console".
    """
    settings = get_settings()
    to_list = [to] if isinstance(to, str) else list(to)
    from_addr = from_addr_override or settings.email_from or "onboarding@resend.dev"
    effective_key = api_key or settings.resend_api_key

    if not effective_key:
        logger.info(
            "email_console from=%s to=%s subject=%s\n%s",
            from_addr,
            to_list,
            subject,
            text,
        )
        return "console"

    import resend

    # The SDK's Emails.send reads the module-global ``resend.api_key``. BYOK
    # sends run concurrently with server-key sends in worker threads/processes;
    # serialize key swap + send under a lock (and restore the previous value)
    # so a BYOK thread can never see (or overwrite with) the server key.
    with _RESEND_LOCK:
        previous = getattr(resend, "api_key", None)
        try:
            resend.api_key = effective_key

            if html_body is None:
                # Simple HTML wrapper from plain text
                escaped = html.escape(text).replace("\n", "<br>\n")
                html_body = f"<div style='font-family:sans-serif;font-size:14px'>{escaped}</div>"

            params: resend.Emails.SendParams = {
                "from": from_addr,
                "to": to_list,
                "subject": subject,
                "html": html_body,
                "text": text,
            }

            result = resend.Emails.send(params)
        finally:
            resend.api_key = previous
    # SDK may return dict or object with id
    if isinstance(result, dict):
        return str(result.get("id") or "resend")
    return str(getattr(result, "id", None) or "resend")
