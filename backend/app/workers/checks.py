"""HTTP check worker."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import dramatiq

from app.config import get_settings
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
from app.services.fetcher import FetchError, fetch_url
from app.services.pipeline import apply_fetch_result
from app.workers.broker import redis_broker  # noqa: F401
from app.workers.notifications import deliver_outbox_message

logger = logging.getLogger(__name__)
settings = get_settings()


@dramatiq.actor(queue_name="http_checks", max_retries=3, time_limit=120_000)
def run_http_check(run_id: str) -> None:
    """Execute a single HTTP monitor run end-to-end."""
    domain: str | None = None
    with SessionLocal() as db:
        run = db.get(MonitorRun, UUID(run_id))
        if run is None:
            logger.warning("run_not_found run_id=%s", run_id)
            return
        if run.status in (RunStatus.SUCCEEDED.value, RunStatus.CANCELLED.value):
            logger.info("run_already_terminal run_id=%s status=%s", run_id, run.status)
            return

        monitor = db.get(Monitor, run.monitor_id)
        if monitor is None:
            run.status = RunStatus.FAILED.value
            run.error_code = "internal_error"
            run.error_message = "Monitor missing"
            run.finished_at = datetime.now(UTC)
            db.commit()
            return

        # Misrouted browser job
        if monitor.js_required:
            from app.workers.browser_checks import run_browser_check

            run.status = RunStatus.QUEUED.value
            db.commit()
            run_browser_check.send(run_id)
            return

        run.status = RunStatus.RUNNING.value
        run.started_at = datetime.now(UTC)
        db.commit()

        try:
            domain = assert_domain_allowed(monitor.url)
            acquire_domain_slot(domain)

            result = fetch_url(
                monitor.url,
                timeout_seconds=monitor.timeout_seconds,
                max_response_bytes=monitor.max_response_bytes,
                respect_robots=True,
            )
            pipeline = apply_fetch_result(db, monitor=monitor, run=run, result=result, store_raw=True)

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
            for oid in outbox_ids:
                deliver_outbox_message.send(str(oid))

            if pipeline.is_baseline:
                logger.info("baseline_set monitor_id=%s run_id=%s", monitor.id, run.id)
            elif pipeline.unchanged:
                logger.info("unchanged monitor_id=%s run_id=%s", monitor.id, run.id)
            elif pipeline.change_event_id:
                logger.info("change_detected monitor_id=%s run_id=%s", monitor.id, run.id)

        except DomainBlocked as exc:
            _fail_run(db, run, "blocked_address", str(exc))
            record_run_outcome(
                db, monitor=monitor, succeeded=False, error_code="blocked_address", error_message=str(exc)
            )
            db.commit()
        except SSRFError as exc:
            _fail_run(db, run, exc.code, str(exc))
            record_run_outcome(
                db, monitor=monitor, succeeded=False, error_code=exc.code, error_message=str(exc)
            )
            db.commit()
        except FetchError as exc:
            if domain:
                record_domain_failure(domain)
            _fail_run(db, run, exc.code, str(exc), http_status=exc.http_status)
            outbox_extra = record_run_outcome(
                db,
                monitor=monitor,
                succeeded=False,
                error_code=exc.code,
                error_message=str(exc),
            )
            db.commit()
            for oid in outbox_extra:
                deliver_outbox_message.send(str(oid))
            if exc.code in ("read_timeout", "connection_timeout"):
                raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("check_failed run_id=%s", run_id)
            if domain:
                record_domain_failure(domain)
            _fail_run(db, run, "internal_error", str(exc)[:2000])
            raise
        finally:
            if domain:
                release_domain_slot(domain)


def _fail_run(
    db,
    run: MonitorRun,
    code: str,
    message: str,
    *,
    http_status: int | None = None,
) -> None:
    run.status = RunStatus.FAILED.value
    run.error_code = code
    run.error_message = message
    if http_status is not None:
        run.http_status = http_status
    run.finished_at = datetime.now(UTC)
    db.commit()
