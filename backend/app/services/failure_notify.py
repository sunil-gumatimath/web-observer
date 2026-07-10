"""Notify users after consecutive monitor failures."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Monitor, NotificationChannel, NotificationOutbox
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
    if monitor.consecutive_failures != threshold:
        # Only notify once when crossing the threshold
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
