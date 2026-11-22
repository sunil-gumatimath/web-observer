"""Route monitor runs to HTTP or browser queues."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import update as sa_update

from app.db import SessionLocal
from app.models import MonitorRun
from app.models.entities import RunStatus
from app.workers.browser_checks import run_browser_check
from app.workers.checks import run_http_check

logger = logging.getLogger(__name__)


def _refresh_queued_at(run_id: str) -> None:
    """Restart the reaper's 2-minute QUEUED clock for a re-enqueued run."""
    try:
        with SessionLocal() as db:
            # Fenced: only a run still QUEUED gets a fresh attempt clock. A
            # run already RUNNING or terminal keeps its original timestamps.
            db.execute(
                sa_update(MonitorRun)
                .where(
                    MonitorRun.id == run_id,
                    MonitorRun.status == RunStatus.QUEUED.value,
                )
                .values(queued_at=datetime.now(UTC))
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 - enqueue must never fail on bookkeeping
        logger.warning("enqueue_queued_at_refresh_failed run_id=%s error=%s", run_id, exc)


def enqueue_check(run_id: str, *, needs_browser: bool = False) -> None:
    """Route a run to the appropriate Dramatiq queue.

    A re-enqueue of a still-QUEUED run (misrouted job, redelivery, manual
    re-run) refreshes ``queued_at`` so the reaper's 2-minute lost-message
    cutoff measures from the new attempt instead of the original enqueue.
    """
    _refresh_queued_at(run_id)
    if needs_browser:
        run_browser_check.send(str(run_id))
    else:
        run_http_check.send(str(run_id))
