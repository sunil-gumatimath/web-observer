"""PostgreSQL-driven scheduler.

Polls due monitors, claims with lease, creates idempotent runs, enqueues Dramatiq jobs.
"""

from __future__ import annotations

import logging
import random
import signal
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update

from app.config import get_settings
from app.db import SessionLocal
from app.models import Monitor, MonitorRun
from app.models.entities import RunStatus
from app.services.run_reaper import reap_stuck_runs
from app.services.usage import QuotaExceeded, assert_can_run_check
from app.services.webhooks import reap_stuck_webhook_deliveries
from app.workers.broker import redis_broker  # noqa: F401
from app.workers.enqueue import enqueue_check
from app.workers.notifications import reap_stuck_outbox_messages

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scheduler")
settings = get_settings()

_running = True
_INSTANCE_ID = f"scheduler-{uuid.uuid4().hex[:10]}"


def _handle_signal(signum: int, _frame: object) -> None:
    global _running
    logger.info("shutdown_signal signum=%s", signum)
    _running = False


def claim_due_monitors(limit: int) -> list[tuple[uuid.UUID, bool]]:
    """Return list of (run_id, js_required)."""
    now = datetime.now(UTC)
    lease_until = now + timedelta(seconds=60)

    with SessionLocal() as db:
        due = db.scalars(
            select(Monitor)
            .where(
                Monitor.enabled.is_(True),
                Monitor.next_run_at <= now,
                or_(
                    Monitor.lease_expires_at.is_(None),
                    Monitor.lease_expires_at < now,
                    Monitor.lease_owner == _INSTANCE_ID,
                ),
            )
            .order_by(Monitor.next_run_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()

        claimed: list[tuple[uuid.UUID, bool]] = []
        for monitor in due:
            # Skip if an active run already exists
            active = db.scalar(
                select(MonitorRun.id)
                .where(
                    MonitorRun.monitor_id == monitor.id,
                    MonitorRun.status.in_(
                        [
                            RunStatus.SCHEDULED.value,
                            RunStatus.QUEUED.value,
                            RunStatus.RUNNING.value,
                        ]
                    ),
                )
                .limit(1)
            )
            if active is not None:
                # Push next_run slightly to avoid tight loop and release lease immediately
                monitor.next_run_at = now + timedelta(seconds=30)
                monitor.lease_owner = None
                monitor.lease_expires_at = None
                continue

            try:
                assert_can_run_check(db, monitor.workspace_id)
            except QuotaExceeded:
                logger.warning(
                    "quota_exceeded workspace_id=%s monitor_id=%s", monitor.workspace_id, monitor.id
                )
                monitor.next_run_at = now + timedelta(hours=1)
                continue

            jitter = random.randint(0, settings.scheduler_jitter_seconds)
            interval = timedelta(minutes=monitor.schedule_interval_minutes)
            monitor.lease_owner = _INSTANCE_ID
            monitor.lease_expires_at = lease_until
            monitor.next_run_at = now + interval + timedelta(seconds=jitter)

            idempotency_key = f"{monitor.id}:{int(now.timestamp())}:{uuid.uuid4().hex[:8]}"
            run = MonitorRun(
                monitor_id=monitor.id,
                workspace_id=monitor.workspace_id,
                config_version=monitor.config_version,
                idempotency_key=idempotency_key,
                scheduled_at=now,
                queued_at=now,
                status=RunStatus.QUEUED.value,
                attempt=1,
            )
            db.add(run)
            db.flush()
            needs_browser = bool(monitor.js_required or monitor.mode == "visual")
            claimed.append((run.id, needs_browser))
            logger.info(
                "enqueued monitor_id=%s run_id=%s browser=%s next_run_at=%s",
                monitor.id,
                run.id,
                needs_browser,
                monitor.next_run_at.isoformat(),
            )

        db.commit()
        return claimed


def release_expired_logic() -> None:
    """Clear stale leases (recovery aid)."""
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.execute(
            update(Monitor)
            .where(
                and_(
                    Monitor.lease_expires_at.is_not(None),
                    Monitor.lease_expires_at < now,
                )
            )
            .values(lease_owner=None, lease_expires_at=None)
        )
        db.commit()


def run_once() -> int:
    """Single pass: release leases, reap stuck, claim due, enqueue. Returns jobs claimed."""
    release_expired_logic()
    with SessionLocal() as db:
        reaped = reap_stuck_runs(db)
        if reaped:
            logger.warning("reaped_stuck_runs count=%d", reaped)
        reaped_outbox = reap_stuck_outbox_messages(db)
        if reaped_outbox:
            logger.warning("reaped_stuck_outbox count=%d", reaped_outbox)
        reaped_webhooks = reap_stuck_webhook_deliveries(db)
        if reaped_webhooks:
            logger.warning("reaped_stuck_webhooks count=%d", reaped_webhooks)
    jobs = claim_due_monitors(settings.scheduler_batch_size)
    for run_id, needs_browser in jobs:
        enqueue_check(str(run_id), needs_browser=needs_browser)
    return len(jobs)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="single pass then exit (for Cloud Run Jobs)")
    args = parser.parse_args()

    if args.once:
        n = run_once()
        logger.info("scheduler_once done jobs=%s", n)
        return

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    logger.info("scheduler_started instance=%s", _INSTANCE_ID)

    while _running:
        try:
            release_expired_logic()

            # Recover stuck runs, outbox messages, and webhooks before scheduling new ones
            with SessionLocal() as db:
                reaped = reap_stuck_runs(db)
                if reaped:
                    logger.warning("reaped_stuck_runs count=%d", reaped)
                reaped_outbox = reap_stuck_outbox_messages(db)
                if reaped_outbox:
                    logger.warning("reaped_stuck_outbox count=%d", reaped_outbox)
                reaped_webhooks = reap_stuck_webhook_deliveries(db)
                if reaped_webhooks:
                    logger.warning("reaped_stuck_webhooks count=%d", reaped_webhooks)

            jobs = claim_due_monitors(settings.scheduler_batch_size)
            for run_id, needs_browser in jobs:
                enqueue_check(str(run_id), needs_browser=needs_browser)
        except Exception:  # noqa: BLE001
            logger.exception("scheduler_loop_error")
        time.sleep(settings.scheduler_poll_seconds)

    logger.info("scheduler_stopped")


if __name__ == "__main__":
    main()
