"""Notification outbox delivery worker (email, Slack, Discord)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import dramatiq
import httpx

from app.config import get_settings
from app.db import SessionLocal
from app.models import NotificationChannel, NotificationDelivery, NotificationOutbox
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

        title = f"[Monitor-the-Web] {label}: {payload.get('monitor_name', 'workspace')}"
        body_lines = [
            f"*Monitor:* {payload.get('monitor_name')}",
            f"*URL:* {payload.get('url')}",
            f"*Category:* {payload.get('category') or 'n/a'}",
        ]
        if payload.get("watch_note"):
            body_lines.append(f"*Watching:* {payload.get('watch_note')}")
        body_lines.append(f"*Summary:* {payload.get('ai_summary') or payload.get('summary') or 'Content changed'}")
        if payload.get("diff"):
            body_lines.append("")
            body_lines.append("*Diff (truncated):*")
            body_lines.append(f"```{str(payload.get('diff'))[:2500]}```")
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
                provider_id = send_email(to=to_addr, subject=title, text=plain_body)

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


def _send_slack(webhook_url: str, title: str, body: str) -> str:
    """Post a Block Kit message to a Slack incoming webhook."""
    if not webhook_url.startswith("https://"):
        raise ValueError("Slack webhook must be https URL")
    # Prefer structured blocks; fall back fields live in the plain text body.
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
                    "text": "Monitor-the-Web · open the app Alerts inbox for full detail",
                }
            ],
        },
    ]
    payload = {
        "text": f"{title}\n{body[:500]}",  # notification fallback
        "blocks": blocks,
    }
    resp = httpx.post(webhook_url, json=payload, timeout=30.0)
    resp.raise_for_status()
    return "slack"


def _send_discord(webhook_url: str, title: str, body: str) -> str:
    content = f"**{title}**\n```\n{body[:1800]}\n```"
    if not webhook_url.startswith("https://"):
        raise ValueError("Discord webhook must be https URL")
    resp = httpx.post(webhook_url, json={"content": content}, timeout=30.0)
    resp.raise_for_status()
    return "discord"
