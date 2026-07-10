"""Snapshot and run retention cleanup."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ChangeEvent, MonitorRun, Snapshot
from app.services.storage import delete_object

logger = logging.getLogger(__name__)


@dataclass
class RetentionResult:
    snapshots_deleted: int
    runs_deleted: int
    objects_deleted: int


def purge_expired_snapshots(
    db: Session,
    *,
    now: datetime | None = None,
    workspace_id: uuid.UUID | None = None,
) -> RetentionResult:
    """Delete snapshots older than retention window (and raw objects).

    Change events referencing deleted snapshots are left with SET NULL / CASCADE
    per FK rules. Runs older than run retention are removed when no longer needed.
    """
    settings = get_settings()
    now = now or datetime.now(UTC)
    snapshot_cutoff = now - timedelta(days=settings.snapshot_retention_days)
    run_cutoff = now - timedelta(days=settings.run_retention_days)

    snap_q = select(Snapshot).where(Snapshot.created_at < snapshot_cutoff)
    if workspace_id is not None:
        snap_q = snap_q.where(Snapshot.workspace_id == workspace_id)

    snapshots = list(db.scalars(snap_q).all())
    objects_deleted = 0
    for snap in snapshots:
        if snap.raw_object_key:
            delete_object(snap.raw_object_key)
            objects_deleted += 1
        # Clear run FK to snapshot before delete if needed
        runs = db.scalars(select(MonitorRun).where(MonitorRun.snapshot_id == snap.id)).all()
        for run in runs:
            run.snapshot_id = None
        # Null out change event snapshot refs where SET NULL applies
        for ce in db.scalars(
            select(ChangeEvent).where(ChangeEvent.previous_snapshot_id == snap.id)
        ).all():
            ce.previous_snapshot_id = None
        # new_snapshot_id is NOT NULL CASCADE — delete change events that only point at this snap
        for ce in db.scalars(
            select(ChangeEvent).where(ChangeEvent.new_snapshot_id == snap.id)
        ).all():
            db.delete(ce)
        db.delete(snap)

    # Old runs (keep recent history)
    run_q = select(MonitorRun).where(
        MonitorRun.created_at < run_cutoff,
        MonitorRun.status.in_(["succeeded", "failed", "cancelled", "skipped"]),
    )
    if workspace_id is not None:
        run_q = run_q.where(MonitorRun.workspace_id == workspace_id)
    old_runs = list(db.scalars(run_q).all())
    for run in old_runs:
        db.delete(run)

    db.commit()
    result = RetentionResult(
        snapshots_deleted=len(snapshots),
        runs_deleted=len(old_runs),
        objects_deleted=objects_deleted,
    )
    logger.info(
        "retention_purge snapshots=%s runs=%s objects=%s",
        result.snapshots_deleted,
        result.runs_deleted,
        result.objects_deleted,
    )
    return result
