"""Reap stuck MonitorRuns that exceeded their time limit.

If a Dramatiq worker crashes mid-run, the MonitorRun stays in RUNNING/QUEUED
status forever. The scheduler skips monitors with active runs, so a stuck run
permanently blocks that monitor. This reaper detects and recovers from that.

Notifications are intentionally not sent for reaped runs (minimal recovery).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Monitor, MonitorRun
from app.models.entities import RunStatus
from app.services.failure_notify import record_run_outcome

logger = logging.getLogger(__name__)

# Dramatiq time_limit is 2–3 min for most actors.
# Keep these tight so a dead worker cannot block "first check" for long.
STUCK_RUNNING_MINUTES = 5
# QUEUED with no worker pickup — often a lost Redis message after restart.
STUCK_QUEUED_MINUTES = 2


def reap_stuck_runs(db: Session) -> int:
    """Mark RUNNING/QUEUED runs as FAILED if they've been stuck too long.

    Returns the number of reaped runs. Does not enqueue user notifications.
    """
    now = datetime.now(UTC)
    running_cutoff = now - timedelta(minutes=STUCK_RUNNING_MINUTES)
    queued_cutoff = now - timedelta(minutes=STUCK_QUEUED_MINUTES)

    stuck = db.scalars(
        select(MonitorRun).where(
            or_(
                # Stuck in RUNNING state (must have started_at)
                (MonitorRun.status == RunStatus.RUNNING.value)
                & (MonitorRun.started_at.is_not(None))
                & (MonitorRun.started_at < running_cutoff),
                # Stuck in QUEUED state (never picked up)
                (MonitorRun.status == RunStatus.QUEUED.value)
                & (MonitorRun.queued_at.is_not(None))
                & (MonitorRun.queued_at < queued_cutoff),
            )
        )
    ).all()

    for run in stuck:
        old_status = run.status
        age_ref = run.started_at or run.queued_at or now
        logger.warning(
            "reaping_stuck_run run_id=%s status=%s monitor_id=%s age_minutes=%d",
            run.id,
            old_status,
            run.monitor_id,
            int((now - age_ref).total_seconds() / 60),
        )
        run.status = RunStatus.FAILED.value
        run.error_code = "timeout_reaped"
        run.error_message = (
            f"Run stuck in {old_status} state for too long, reaped by cleanup. "
            f"This usually means the worker crashed or was restarted mid-run."
        )
        run.finished_at = now

        # Route through failure accounting so consecutive_failures, the circuit
        # breaker, and (at threshold) user failure notifications are not skipped
        # for reaped runs.  We avoid reaping runs whose monitor is missing.
        monitor = db.get(Monitor, run.monitor_id)
        if monitor is not None:
            outbox_ids = record_run_outcome(
                db,
                monitor=monitor,
                succeeded=False,
                error_code="timeout_reaped",
                error_message=run.error_message,
            )
            for oid in outbox_ids:
                from app.workers.notifications import deliver_outbox_message

                deliver_outbox_message.send(str(oid))

    if stuck:
        db.commit()

    return len(stuck)
