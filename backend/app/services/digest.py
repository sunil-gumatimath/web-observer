"""Daily/weekly digest generation for workspaces."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, Monitor, NotificationChannel, NotificationOutbox, Workspace
from app.models.entities import OutboxStatus

logger = logging.getLogger(__name__)


def build_digest_body(db: Session, workspace: Workspace, *, since: datetime) -> tuple[str, int]:
    events = list(
        db.scalars(
            select(ChangeEvent)
            .where(
                ChangeEvent.workspace_id == workspace.id,
                ChangeEvent.created_at >= since,
                ChangeEvent.is_noise.is_(False),
            )
            .order_by(ChangeEvent.created_at.desc())
            .limit(100)
        ).all()
    )
    if not events:
        return "", 0

    lines = [f"Digest for {workspace.name}", f"Period since {since.isoformat()}", ""]
    for ev in events:
        mon = db.get(Monitor, ev.monitor_id)
        name = mon.name if mon else str(ev.monitor_id)
        cat = ev.change_category or "other"
        summary = ev.ai_summary or ev.diff_summary or "change"
        lines.append(f"- [{cat}] {name}: {summary}")
    return "\n".join(lines), len(events)


def enqueue_workspace_digest(
    db: Session,
    workspace: Workspace,
    *,
    since: datetime,
    period_key: str,
) -> list[uuid.UUID]:
    body, count = build_digest_body(db, workspace, since=since)
    if count == 0:
        return []

    channels = db.scalars(
        select(NotificationChannel).where(
            NotificationChannel.workspace_id == workspace.id,
            NotificationChannel.enabled.is_(True),
        )
    ).all()
    outbox_ids: list[uuid.UUID] = []
    for channel in channels:
        idem = f"digest:{workspace.id}:{period_key}:channel:{channel.id}"
        existing = db.scalar(select(NotificationOutbox).where(NotificationOutbox.idempotency_key == idem))
        if existing is not None:
            continue
        outbox = NotificationOutbox(
            workspace_id=workspace.id,
            change_event_id=None,
            channel_id=channel.id,
            payload={
                "kind": "digest",
                "monitor_name": workspace.name,
                "url": "",
                "summary": f"{count} change(s) in digest window",
                "body": body,
                "channel_type": channel.type,
                "to": channel.address,
            },
            status=OutboxStatus.PENDING.value,
            idempotency_key=idem,
        )
        db.add(outbox)
        db.flush()
        outbox_ids.append(outbox.id)
    return outbox_ids


def due_digest_workspaces(db: Session, *, now: datetime | None = None) -> list[tuple[Workspace, str, datetime]]:
    """Return workspaces that should receive a digest now: (workspace, period_key, since)."""
    now = now or datetime.now(UTC)
    results: list[tuple[Workspace, str, datetime]] = []
    workspaces = db.scalars(
        select(Workspace).where(Workspace.digest_cadence.in_(["daily", "weekly"]))
    ).all()
    for ws in workspaces:
        hour = int(ws.digest_hour_utc or 14)
        if now.hour != hour:
            continue
        if ws.digest_cadence == "daily":
            period_key = f"daily:{now.strftime('%Y%m%d')}"
            since = now - timedelta(days=1)
            results.append((ws, period_key, since))
        elif ws.digest_cadence == "weekly" and now.weekday() == 0:  # Monday
            period_key = f"weekly:{now.strftime('%Y-W%W')}"
            since = now - timedelta(days=7)
            results.append((ws, period_key, since))
    return results
