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
from app.services.storage import delete_object, object_exists

logger = logging.getLogger(__name__)


@dataclass
class RetentionResult:
    snapshots_deleted: int
    runs_deleted: int
    objects_deleted: int


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _delete_snapshot_objects(snap: Snapshot) -> int:
    """Delete storage objects associated with *snap* and return count deleted."""
    deleted = 0
    for key in (snap.raw_object_key, snap.text_object_key):
        if key:
            delete_object(key)
            deleted += 1
    if snap.run_id:
        screenshot_key = f"screenshots/{snap.monitor_id}/{snap.run_id}.png"
        if object_exists(screenshot_key):
            delete_object(screenshot_key)
            deleted += 1
    return deleted


def purge_expired_snapshots(
    db: Session,
    *,
    now: datetime | None = None,
    workspace_id: uuid.UUID | None = None,
) -> RetentionResult:
    """Delete snapshots older than retention window (and raw objects).

    Change events are inbox history: ``ChangeEvent.new_snapshot_id`` is
    NOT NULL with ON DELETE CASCADE, so deleting a snapshot it points at
    would destroy the event. Snapshots still referenced as ``new_snapshot``
    are therefore *kept* (event and DB preview survive intact); once past
    ``snapshot_object_retention_days`` their large storage objects are still
    reclaimed so storage does not grow unboundedly.
    """
    settings = get_settings()
    now = now or datetime.now(UTC)
    snapshot_cutoff = now - timedelta(days=settings.snapshot_retention_days)
    object_retention_days = int(
        getattr(
            settings,
            "snapshot_object_retention_days",
            max(settings.snapshot_retention_days, 90),
        )
    )
    object_cutoff = now - timedelta(days=object_retention_days)
    run_cutoff = now - timedelta(days=settings.run_retention_days)

    snap_q = select(Snapshot).where(Snapshot.created_at < snapshot_cutoff)
    if workspace_id is not None:
        snap_q = snap_q.where(Snapshot.workspace_id == workspace_id)

    snapshots = list(db.scalars(snap_q).all())
    # Snapshots referenced by a change event must survive: the event's
    # new_snapshot_id cannot be nulled (NOT NULL) and the FK cascades, so
    # purging them would silently delete inbox history.
    referenced: set = set()
    if snapshots:
        snap_ids = [snap.id for snap in snapshots]
        referenced = set(
            db.scalars(
                select(ChangeEvent.new_snapshot_id).where(ChangeEvent.new_snapshot_id.in_(snap_ids))
            ).all()
        )
    skipped_referenced = 0
    objects_deleted = 0
    purged: list = []
    for snap in snapshots:
        if snap.id in referenced:
            skipped_referenced += 1
            created_at = _as_utc(getattr(snap, "created_at", None))
            if (
                created_at is not None
                and created_at < object_cutoff
                and (snap.raw_object_key or snap.text_object_key)
            ):
                objects_deleted += _delete_snapshot_objects(snap)
                snap.raw_object_key = None
                snap.text_object_key = None
            else:
                logger.info("retention_keep_referenced_snapshot snapshot_id=%s", snap.id)
            continue
        purged.append(snap)
    for snap in purged:
        # Raw HTML snapshot, normalized-text object, and (when present) the
        # screenshot for this run all live in object storage under different
        # keys — purge all of them so retention actually frees space.
        objects_deleted += _delete_snapshot_objects(snap)
        # Clear run FK to snapshot before delete if needed
        runs = db.scalars(select(MonitorRun).where(MonitorRun.snapshot_id == snap.id)).all()
        for run in runs:
            run.snapshot_id = None
        # Null out change event previous-snapshot refs (SET NULL, nullable).
        # new_snapshot refs can no longer dangle here: referenced snapshots
        # are skipped above, so events are never deleted by retention.
        for ce in db.scalars(
            select(ChangeEvent).where(ChangeEvent.previous_snapshot_id == snap.id)
        ).all():
            ce.previous_snapshot_id = None
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
        snapshots_deleted=len(purged),
        runs_deleted=len(old_runs),
        objects_deleted=objects_deleted,
    )
    logger.info(
        "retention_purge snapshots=%s runs=%s objects=%s kept_referenced=%s",
        result.snapshots_deleted,
        result.runs_deleted,
        result.objects_deleted,
        skipped_referenced,
    )
    return result
