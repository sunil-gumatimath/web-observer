"""Shared execution guard for monitor-run workers.

Both the HTTP and browser-check actors follow the same lifecycle:
load run → validate → domain guard → fetch → pipeline → outcome → notify.
Only the *fetch* step differs.  This module captures the shared skeleton
so each actor file becomes a thin wrapper around ``execute_monitored_run``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Monitor, MonitorRun
from app.models.entities import RunStatus
from app.security.ssrf import SSRFError
from app.services.domain_guard import (
    DomainBlocked,
    acquire_domain_slot,
    assert_domain_allowed,
    record_domain_failure,
    record_domain_success,
    release_domain_slot,
)
from app.services.failure_notify import record_run_outcome
from app.services.fetcher import FetchError, FetchResult
from app.services.pipeline import apply_fetch_result
from app.workers.notifications import deliver_outbox_message

logger = logging.getLogger(__name__)

# Type alias for the fetch callback each actor supplies.
# Signature: (monitor, db) -> FetchResult
FetchFn = Callable[[Monitor, Session], FetchResult]

# Type alias for an optional pre-fetch hook that runs *before* the run is set
# to RUNNING.  It receives (monitor, run, db) and may return early (truthy)
# to abort execution (e.g. misrouted job, quota exceeded).
PreRunHook = Callable[[Monitor, MonitorRun, Session], bool]


def fail_run(
    db: Session,
    run: MonitorRun,
    code: str,
    message: str,
    *,
    http_status: int | None = None,
) -> None:
    """Mark a run as FAILED and persist immediately.

    The write is a fenced conditional UPDATE (``WHERE status = 'running'``),
    mirroring the claim fence and the reaper's transitions:

    * a run still RUNNING is transitioned to FAILED and the in-memory object
      is synced for callers that read ``run.*`` afterwards;
    * a run whose terminal state was already committed (e.g. the pipeline
      committed SUCCEEDED and ``record_run_outcome`` then raised) is **not**
      downgraded — a blind ``run.status = FAILED`` here would overwrite the
      committed result while its change event / outbox rows stay live.

    Any pending uncommitted state from the failing path is rolled back first,
    so the fence reads truth and nothing half-applied is flushed alongside.
    """
    db.rollback()
    now = datetime.now(UTC)
    values: dict = {"error_code": code, "error_message": message, "finished_at": now}
    if http_status is not None:
        values["http_status"] = http_status
    # pi-lens-ignore: python-sql-injection - ORM Core stmt, params bound
    fenced = db.execute(
        sa_update(MonitorRun)
        .where(
            MonitorRun.id == run.id,
            MonitorRun.status == RunStatus.RUNNING.value,
        )
        .values(status=RunStatus.FAILED.value, **values)
    )
    db.commit()
    # rowcount exists on CursorResult; the Result stub omits it.
    if fenced.rowcount != 1:  # type: ignore[attr-defined]
        logger.info(
            "fail_run_fenced_off run_id=%s (terminal state already committed; not downgraded)",
            run.id,
        )
        return
    run.status = RunStatus.FAILED.value
    run.error_code = code
    run.error_message = message
    if http_status is not None:
        run.http_status = http_status
    run.finished_at = now


def enqueue_outbox(outbox_ids) -> None:
    """Best-effort dramatiq enqueue for outbox rows.

    A Redis outage during enqueue must not re-raise out of the worker
    (that would trigger dramatiq retries whose claim fails rowcount-0 and
    ends in pointless retry cycles). Re-enqueued rows sit PENDING until the
    periodic outbox reaper re-dispatches them.
    """
    for oid in outbox_ids:
        try:
            deliver_outbox_message.send(str(oid))
        except Exception:  # noqa: BLE001 - delivery reaper recovers later
            logger.warning(
                "outbox_enqueue_failed outbox_id=%s (row stays pending; reaper will retry)",
                oid,
            )


def execute_monitored_run(
    run_id: str,
    fetch_fn: FetchFn,
    *,
    pre_run_hook: PreRunHook | None = None,
    worker_label: str = "check",
) -> None:
    """Execute the full lifecycle of a single monitor run.

    Parameters
    ----------
    run_id:
        Primary-key of the :class:`MonitorRun` row.
    fetch_fn:
        Callback that performs the actual content retrieval.
        Signature: ``(monitor, db) -> FetchResult``.
    pre_run_hook:
        Optional callback invoked *after* the monitor is loaded but *before*
        the run is set to ``RUNNING``.  Return ``True`` to abort the run
        (the hook is responsible for any DB mutations / re-routing).
    worker_label:
        Short label used in log messages (e.g. ``"check"`` or
        ``"browser_check"``).
    """
    domain: str | None = None
    with SessionLocal() as db:
        run = db.get(MonitorRun, UUID(run_id))
        if run is None:
            logger.warning("run_not_found run_id=%s", run_id)
            return
        monitor = db.get(Monitor, run.monitor_id)
        if monitor is None:
            run.status = RunStatus.FAILED.value
            run.error_code = "internal_error"
            run.error_message = "Monitor missing"
            run.finished_at = datetime.now(UTC)
            db.commit()
            return

        # Fencing gate: a pre-run hook may bounce a run to another queue by
        # flipping its status, so it must only ever run while the run hasn't
        # started. Without this gate, a redelivered message arriving after
        # the bounce-target worker already finished the run could flip a
        # terminal SUCCEEDED/FAILED run back to QUEUED and re-execute the
        # whole pipeline (duplicate snapshot, change event, notifications
        # and usage increments). The conditional claim below is the actual
        # fence for execution; this gate is the fence for hooks.
        if run.status not in (RunStatus.SCHEDULED.value, RunStatus.QUEUED.value):
            logger.info("run_not_started_allowed run_id=%s status=%s", run_id, run.status)
            return

        # --- optional pre-run hook (misrouted-job check, quota, etc.) ---
        if pre_run_hook is not None and pre_run_hook(monitor, run, db):
            return

        # Idempotency guard: claim the run atomically.  Dramatiq at-least-once
        # redelivery can hand the same run_id to two workers, and a read-then-set
        # terminal check lets both through (duplicate snapshots, change events,
        # notifications, usage counts).  A conditional UPDATE is race-safe: only
        # one worker transitions QUEUED/SCHEDULED -> RUNNING; the loser sees
        # rowcount 0 and exits.  Terminal runs are simply not claimable, so a
        # redelivered finished run can never be re-processed.
        # pi-lens-ignore: python-sql-injection - ORM Core stmt, params bound
        claimed = db.execute(
            sa_update(MonitorRun)
            .where(
                MonitorRun.id == run.id,
                MonitorRun.status.in_((RunStatus.SCHEDULED.value, RunStatus.QUEUED.value)),
            )
            .values(
                status=RunStatus.RUNNING.value,
                started_at=datetime.now(UTC),
            )
        )
        db.commit()
        # rowcount exists on CursorResult; the Result stub omits it.
        if claimed.rowcount != 1:  # type: ignore[attr-defined]
            logger.info("run_not_claimable run_id=%s", run_id)
            return

        slot_acquired = False
        try:
            domain = assert_domain_allowed(monitor.url)
            acquire_domain_slot(domain)
            slot_acquired = True

            result = fetch_fn(monitor, db)

            pipeline = apply_fetch_result(
                db, monitor=monitor, run=run, result=result, store_raw=True
            )

            if pipeline.status == RunStatus.SUCCEEDED.value:
                record_domain_success(domain)
                outbox_extra = record_run_outcome(db, monitor=monitor, succeeded=True)
                db.commit()
            else:
                record_domain_failure(domain)
                outbox_extra = record_run_outcome(
                    db,
                    monitor=monitor,
                    succeeded=False,
                    error_code=pipeline.error_code,
                    error_message=pipeline.error_message,
                )
                db.commit()

            outbox_ids = list(pipeline.outbox_ids or []) + [str(x) for x in outbox_extra]
            enqueue_outbox(outbox_ids)

            if pipeline.is_baseline:
                logger.info("baseline_set monitor_id=%s run_id=%s", monitor.id, run.id)
            elif pipeline.unchanged:
                logger.info("unchanged monitor_id=%s run_id=%s", monitor.id, run.id)
            elif pipeline.change_event_id:
                logger.info("change_detected monitor_id=%s run_id=%s", monitor.id, run.id)

        except DomainBlocked as exc:
            fail_run(db, run, "blocked_address", str(exc))
            record_run_outcome(
                db,
                monitor=monitor,
                succeeded=False,
                error_code="blocked_address",
                error_message=str(exc),
            )
            db.commit()
        except SSRFError as exc:
            fail_run(db, run, exc.code, str(exc))
            record_run_outcome(
                db,
                monitor=monitor,
                succeeded=False,
                error_code=exc.code,
                error_message=str(exc),
            )
            db.commit()
        except FetchError as exc:
            if domain:
                record_domain_failure(domain)
            fail_run(db, run, exc.code, str(exc), http_status=exc.http_status)
            outbox_extra = record_run_outcome(
                db,
                monitor=monitor,
                succeeded=False,
                error_code=exc.code,
                error_message=str(exc),
            )
            db.commit()
            enqueue_outbox(outbox_extra)
        except Exception as exc:  # noqa: BLE001
            logger.exception("%s_failed run_id=%s", worker_label, run_id)
            if domain:
                record_domain_failure(domain)
            fail_run(db, run, "internal_error", str(exc)[:2000])
            outbox_extra = record_run_outcome(
                db,
                monitor=monitor,
                succeeded=False,
                error_code="internal_error",
                error_message=str(exc)[:2000],
            )
            db.commit()
            enqueue_outbox(outbox_extra)
        finally:
            # Only release a slot we actually acquired.  If assert_domain_allowed
            # or acquire_domain_slot raised (e.g. DomainBlocked), slot_acquired
            # stays False and we must NOT decrement the counter — otherwise the
            # per-domain concurrency counter leaks negative.
            if slot_acquired and domain:
                release_domain_slot(domain)
