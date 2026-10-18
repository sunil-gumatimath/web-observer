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
from sqlalchemy import update as sa_update
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

    Every transition is a fenced conditional UPDATE
    (``WHERE id = :id AND status = :old_status``): a run that completes
    legitimately between the SELECT and the WRITE is no longer clobbered
    (SUCCEEDED -> FAILED), and concurrent reapers of the same run can only
    win the transition once (the loser sees rowcount 0). Only successfully
    fenced transitions route through failure accounting, so a monitor's
    ``consecutive_failures`` and failure notifications stay correct.

    Returns the number of reaped runs (only fenced transitions counted).
    """
    now = datetime.now(UTC)
    running_cutoff = now - timedelta(minutes=STUCK_RUNNING_MINUTES)
    queued_cutoff = now - timedelta(minutes=STUCK_QUEUED_MINUTES)

    # FOR UPDATE SKIP LOCKED: two scheduler instances reaping concurrently
    # must not both work the same row (double failure-accounting, outbox
    # idempotency races). The conditional UPDATE below is the real fence;
    # SKIP LOCKED just avoids redundant duplicate work.
    stuck = db.scalars(
        select(MonitorRun)
        .where(
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
        .with_for_update(skip_locked=True)
    ).all()

    reaped = 0
    for run in stuck:
        old_status = run.status
        age_ref = run.started_at or run.queued_at or now
        failure_message = (
            f"Run stuck in {old_status} state for too long, reaped by cleanup. "
            f"This usually means the worker crashed or was restarted mid-run."
        )
        # Fenced transition: only fires if the status is unchanged — a run
        # finishing right now keeps its terminal state untouched.
        # pi-lens-ignore: python-sql-injection - ORM Core stmt, params bound
        claimed = db.execute(
            sa_update(MonitorRun)
            .where(
                MonitorRun.id == run.id,
                MonitorRun.status == old_status,
            )
            .values(
                status=RunStatus.FAILED.value,
                error_code="timeout_reaped",
                error_message=failure_message,
                finished_at=now,
            )
        )
        # rowcount exists on CursorResult; the Result stub omits it.
        if claimed.rowcount != 1:  # type: ignore[attr-defined]
            logger.info("reap_skipped_fenced run_id=%s status_now=%s", run.id, run.status)
            continue
        reaped += 1
        run.status = RunStatus.FAILED.value
        run.error_code = "timeout_reaped"
        run.error_message = failure_message
        run.finished_at = now
        logger.warning(
            "reaping_stuck_run run_id=%s status=%s monitor_id=%s age_minutes=%d",
            run.id,
            old_status,
            run.monitor_id,
            int((now - age_ref).total_seconds() / 60),
        )

        # Route through failure accounting so consecutive_failures, the circuit
        # breaker, and (at threshold) user failure notifications are not skipped
        # for reaped runs.  We avoid reaping runs whose monitor is missing.
        monitor = db.get(Monitor, run.monitor_id)
        outbox_ids: list = []
        if monitor is not None:
            outbox_ids = record_run_outcome(
                db,
                monitor=monitor,
                succeeded=False,
                error_code="timeout_reaped",
                error_message=failure_message,
            )
        # Commit the fenced transition (and any failure-accounting outbox rows)
        # immediately: releases the row lock and makes fencing state durable.
        db.commit()
        for oid in outbox_ids:
            from app.workers.notifications import deliver_outbox_message

            _safe_send(deliver_outbox_message, str(oid))

    return reaped


def _safe_send(actor, outbox_id: str) -> None:
    """Best-effort dramatiq enqueue: a Redis outage must not abort the reaper."""
    try:
        actor.send(outbox_id)
    except Exception:  # noqa: BLE001 - enqueue failure must not blow up recovery
        logger.warning(
            "reaper_enqueue_failed outbox_id=%s (row stays pending; "
            "the periodic reaper will retry)",
            outbox_id,
        )
