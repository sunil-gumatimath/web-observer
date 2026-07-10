"""Resend email delivery (official SDK).

Configure via env:
  RESEND_API_KEY=re_...
  EMAIL_FROM=onboarding@resend.dev   # use your domain after Resend verifies it
"""

from __future__ import annotations

import html
import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


def send_email(
    *,
    to: str | list[str],
    subject: str,
    text: str,
    html_body: str | None = None,
) -> str:
    """Send an email via Resend. Returns provider message id.

    If RESEND_API_KEY is empty, logs to console and returns "console".
    """
    settings = get_settings()
    to_list = [to] if isinstance(to, str) else list(to)
    from_addr = settings.email_from or "onboarding@resend.dev"

    if not settings.resend_api_key:
        logger.info(
            "email_console from=%s to=%s subject=%s\n%s",
            from_addr,
            to_list,
            subject,
            text,
        )
        return "console"

    import resend

    resend.api_key = settings.resend_api_key

    if html_body is None:
        # Simple HTML wrapper from plain text
        escaped = html.escape(text).replace("\n", "<br>\n")
        html_body = f"<div style='font-family:sans-serif;font-size:14px'>{escaped}</div>"

    params: dict[str, Any] = {
        "from": from_addr,
        "to": to_list,
        "subject": subject,
        "html": html_body,
        "text": text,
    }

    result = resend.Emails.send(params)
    # SDK may return dict or object with id
    if isinstance(result, dict):
        return str(result.get("id") or "resend")
    return str(getattr(result, "id", None) or "resend")
