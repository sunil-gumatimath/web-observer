"""Notify users after consecutive monitor failures."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Monitor, NotificationChannel, NotificationOutbox, Workspace
from app.models.entities import OutboxStatus

logger = logging.getLogger(__name__)


def record_run_outcome(
    db: Session,
    *,
    monitor: Monitor,
    succeeded: bool,
    error_code: str | None = None,
    error_message: str | None = None,
) -> list[uuid.UUID]:
    """Update consecutive_failures; enqueue failure notifications when threshold hit.

    Returns outbox IDs to deliver.
    """
    settings = get_settings()
    outbox_ids: list[uuid.UUID] = []

    if succeeded:
        monitor.consecutive_failures = 0
        return outbox_ids

    monitor.consecutive_failures = int(monitor.consecutive_failures or 0) + 1
    threshold = settings.consecutive_failure_notify_threshold
    if monitor.consecutive_failures < threshold:
        # Not yet at the threshold.  Use >= (not exact ==) so a count that jumps
        # past the threshold — e.g. when the reaper marks several stuck runs
        # failed — still fires instead of being silently skipped.  Since
        # record_run_outcome is called exactly once per failed run, the count
        # increments by one per call and the per-count idempotency_key below
        # prevents duplicate notifications for any given count.
        return outbox_ids

    cooldown_minutes = int(getattr(settings, "failure_notify_cooldown_minutes", 0) or 0)
    if cooldown_minutes > 0 and _sent_within(db, monitor, minutes=cooldown_minutes):
        # The failure count still advances; only the outbound notice is
        # suppressed so a flapping monitor doesn't flood every channel.
        logger.info(
            "failure_notification_cooled_down monitor_id=%s failures=%s",
            monitor.id,
            monitor.consecutive_failures,
        )
        return outbox_ids

    from app.services.usage import QuotaExceeded, assert_can_use_notifications

    try:
        workspace = db.get(Workspace, monitor.workspace_id)
        assert_can_use_notifications(db, workspace)
    except QuotaExceeded as exc:
        logger.warning(
            "failure_notification_quota_exceeded monitor_id=%s error=%s", monitor.id, exc
        )
        return outbox_ids

    channels = db.scalars(
        select(NotificationChannel).where(
            NotificationChannel.workspace_id == monitor.workspace_id,
            NotificationChannel.enabled.is_(True),
        )
    ).all()

    for channel in channels:
        idem = f"failure:{monitor.id}:count:{monitor.consecutive_failures}:channel:{channel.id}"
        existing = db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.idempotency_key == idem)
        )
        if existing is not None:
            continue
        outbox = NotificationOutbox(
            workspace_id=monitor.workspace_id,
            change_event_id=None,
            channel_id=channel.id,
            payload={
                "kind": "monitor_failure",
                "monitor_id": str(monitor.id),
                "monitor_name": monitor.name,
                "url": monitor.url,
                "summary": (
                    f"Monitor failed {monitor.consecutive_failures} times in a row"
                    + (f" ({error_code})" if error_code else "")
                ),
                "diff": error_message or "",
                "to": channel.address,
            },
            status=OutboxStatus.PENDING.value,
            idempotency_key=idem,
        )
        db.add(outbox)
        db.flush()
        outbox_ids.append(outbox.id)
        logger.info(
            "failure_notification_enqueued monitor_id=%s channel=%s",
            monitor.id,
            channel.id,
        )

    return outbox_ids


def _sent_within(db: Session, monitor: Monitor, *, minutes: int) -> bool:
    """True when a monitor_failure notice went out for this monitor recently.

    The idempotency-key prefix scopes the lookup to this monitor without a
    JSONB-specific query (works on SQLite in unit tests too); the payload kind
    is checked in Python so an unrelated outbox row can never trigger the
    cooldown.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
    rows = db.scalars(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.workspace_id == monitor.workspace_id,
            NotificationOutbox.idempotency_key.startswith(
                f"failure:{monitor.id}:count:"
            ),
        )
        .order_by(NotificationOutbox.created_at.desc())
        .limit(200)
    ).all()
    for row in rows:
        payload = row.payload or {}
        if payload.get("kind") != "monitor_failure":
            continue
        created = row.created_at
        if created is None:
            continue
        # SQLite stores naive timestamps; normalize both sides to UTC.
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created.astimezone(UTC) >= cutoff:
            return True
    return False
