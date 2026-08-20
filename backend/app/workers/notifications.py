"""Notification outbox delivery worker (email, Slack, Discord)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import dramatiq
import httpx

from app.config import get_settings
from app.db import SessionLocal
from app.models import NotificationChannel, NotificationDelivery, NotificationOutbox, Workspace
from app.models.entities import OutboxStatus
from app.services.email import send_email
from app.services.usage import increment_notifications
from app.workers.broker import redis_broker  # noqa: F401

logger = logging.getLogger(__name__)
settings = get_settings()


@dramatiq.actor(queue_name="notifications", max_retries=5, time_limit=60_000)
def deliver_outbox_message(outbox_id: str) -> None:
    with SessionLocal() as db:
        outbox = db.get(NotificationOutbox, UUID(outbox_id))
        if outbox is None:
            return
        if outbox.status == OutboxStatus.SENT.value:
            return

        channel = db.get(NotificationChannel, outbox.channel_id)
        if channel is None or not channel.enabled:
            outbox.status = OutboxStatus.FAILED.value
            outbox.last_error = "Channel missing or disabled"
            outbox.attempts += 1
            db.commit()
            return

        outbox.status = OutboxStatus.PROCESSING.value
        outbox.attempts += 1
        db.commit()

        payload = outbox.payload or {}
        channel_type = (payload.get("channel_type") or channel.type or "email").lower()
        kind = payload.get("kind") or "change"
        label = {
            "monitor_failure": "Failure",
            "digest": "Digest",
        }.get(kind, "Change")

        title = f"[Web Observer] {label}: {payload.get('monitor_name', 'workspace')}"
        body_lines = [
            f"*Monitor:* {payload.get('monitor_name')}",
            f"*URL:* {payload.get('url')}",
            f"*Category:* {payload.get('category') or 'n/a'}",
        ]
        if payload.get("watch_note"):
            body_lines.append(f"*Watching:* {payload.get('watch_note')}")
        body_lines.append(f"*Summary:* {payload.get('ai_summary') or payload.get('summary') or 'Content changed'}")
        # list_items diffs are link-rich ("+ [title](url)") — render them as
        # plain mrkdwn so Slack/Discord turn them into clickable links, mirroring
        # webdog's readable added/removed list. Code-fenced diffs are kept for
        # the text/visual modes where raw +/- lines are more useful.
        mode = payload.get("mode")
        diff = payload.get("diff")
        if diff:
            if mode == "list_items":
                body_lines.append("")
                body_lines.append("*Changes:*")
                body_lines.append(str(diff))
            else:
                body_lines.append("")
                body_lines.append("*Diff (truncated):*")
                body_lines.append(f"```{str(diff)[:2500]}```")
        if payload.get("body"):
            body_lines.append(str(payload.get("body"))[:8000])
        body = "\n".join(line for line in body_lines if line is not None)
        # Plain-text variant for email (strip simple markdown markers)
        plain_body = (
            body.replace("*", "")
            .replace("```", "")
        )
        to_addr = payload.get("to") or channel.address

        try:
            if channel_type == "slack":
                provider_id = _send_slack(to_addr, title, body)
            elif channel_type == "discord":
                provider_id = _send_discord(to_addr, title, plain_body)
            else:
                # Per-account (bring-your-own) Resend credentials override the
                # server-managed defaults when present.
                workspace = db.get(Workspace, outbox.workspace_id)
                from app.services.crypto import decrypt_secret as _decrypt

                ws_api_key = _decrypt(workspace.resend_api_key) if workspace else None
                ws_from = workspace.email_from if workspace else None
                provider_id = send_email(
                    to=to_addr,
                    subject=title,
                    text=plain_body,
                    api_key=ws_api_key,
                    from_addr_override=ws_from,
                )

            outbox.status = OutboxStatus.SENT.value
            outbox.last_error = None
            outbox.updated_at = datetime.now(UTC)
            db.add(
                NotificationDelivery(
                    outbox_id=outbox.id,
                    channel_id=channel.id,
                    provider_message_id=provider_id,
                    status="sent",
                )
            )
            increment_notifications(db, outbox.workspace_id)
            db.commit()
            logger.info(
                "notification_sent outbox_id=%s type=%s to=%s",
                outbox_id,
                channel_type,
                to_addr[:80],
            )
        except Exception as exc:  # noqa: BLE001
            outbox.status = OutboxStatus.PENDING.value
            outbox.last_error = str(exc)[:2000]
            outbox.updated_at = datetime.now(UTC)
            db.commit()
            logger.exception("notification_failed outbox_id=%s", outbox_id)
            raise


def reap_stuck_outbox_messages(db, *, older_than_seconds: int = 600) -> int:
    """Re-enqueue outbox rows stuck in PROCESSING/PENDING after a worker death.

    ``deliver_outbox_message`` sets status to PROCESSING and commits before
    delivering; if the worker dies mid-delivery the row is stuck in PROCESSING
    forever (it never re-enters the queue, and the error path only runs on an
    actual exception).  This reaper finds such rows — or PENDING rows that were
    never picked up — older than ``older_than_seconds`` and flips them back to
    PENDING so they are re-delivered.  ``updated_at`` is used when present,
    otherwise ``created_at``.

    Returns the number of rows re-enqueued.
    """
    from sqlalchemy import select

    cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
    stuck = db.scalars(
        select(NotificationOutbox).where(
            NotificationOutbox.status.in_(
                [OutboxStatus.PROCESSING.value, OutboxStatus.PENDING.value]
            ),
            NotificationOutbox.available_at <= cutoff,
        )
    ).all()

    reaped = 0
    for outbox in stuck:
        stamp = outbox.updated_at or outbox.created_at or cutoff
        if stamp > cutoff:
            continue
        outbox.status = OutboxStatus.PENDING.value
        outbox.updated_at = datetime.now(UTC)
        db.add(outbox)
        db.flush()
        deliver_outbox_message.send(str(outbox.id))
        reaped += 1
        logger.warning(
            "reaped_stuck_outbox outbox_id=%s old_status=%s",
            outbox.id,
            outbox.status,
        )

    if reaped:
        db.commit()
    return reaped


def _pinned_post(url: str, payload: dict, *, timeout: float = 30.0) -> httpx.Response:
    """POST a JSON payload to a validated, IP-pinned URL (SSRF-safe delivery).

    Validates the target against private/internal IPs and pins the resolved IP
    into the transport so the DNS record cannot be re-pointed between validation
    and connection.  Redirects are not followed — a notification webhook URL
    should resolve directly.
    """
    from app.security.ssrf import PinnedIPTransport, SSRFError, validate_url_for_fetch

    if not url.startswith("https://"):
        raise ValueError("Webhook URL must be https")
    try:
        validated = validate_url_for_fetch(url, resolve_dns=True)
    except SSRFError as exc:
        raise ValueError(f"Blocked webhook address: {exc}") from exc
    hostname = httpx.URL(url).host
    transport = PinnedIPTransport(
        pinned_ip=validated.resolved_ips[0],
        server_hostname=hostname,
    )
    with httpx.Client(
        transport=transport, timeout=timeout, follow_redirects=False
    ) as client:
        return client.post(url, json=payload)


def _send_slack(webhook_url: str, title: str, body: str) -> str:
    """Post a Block Kit message to a Slack incoming webhook."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": title[:150], "emoji": True},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": body[:2900]},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Web Observer · open the app Alerts inbox for full detail",
                }
            ],
        },
    ]
    payload = {
        "text": f"{title}\n{body[:500]}",  # notification fallback
        "blocks": blocks,
    }
    resp = _pinned_post(webhook_url, payload)
    resp.raise_for_status()
    return "slack"


def _send_discord(webhook_url: str, title: str, body: str) -> str:
    content = f"**{title}**\n```\n{body[:1800]}\n```"
    resp = _pinned_post(webhook_url, {"content": content})
    resp.raise_for_status()
    return "discord"
