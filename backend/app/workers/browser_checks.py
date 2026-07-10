"""Browser (Playwright) check worker — separate queue and capacity."""

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
from app.services.browser_fetch import fetch_url_browser
from app.services.domain_guard import (
    DomainBlocked,
    _redis,
    acquire_domain_slot,
    assert_domain_allowed,
    record_domain_failure,
    record_domain_success,
    release_domain_slot,
)
from app.services.failure_notify import record_run_outcome
from app.services.fetcher import FetchError
from app.services.pipeline import apply_fetch_result
from app.services.visual import capture_screenshot, visual_to_fetch_result
from app.workers.broker import redis_broker  # noqa: F401
from app.workers.notifications import deliver_outbox_message

logger = logging.getLogger(__name__)
settings = get_settings()


@dramatiq.actor(queue_name="browser_checks", max_retries=2, time_limit=180_000)
def run_browser_check(run_id: str) -> None:
    """Execute a JS-required or visual monitor run with Playwright."""
    domain: str | None = None
    with SessionLocal() as db:
        run = db.get(MonitorRun, UUID(run_id))
        if run is None:
            logger.warning("run_not_found run_id=%s", run_id)
            return
        if run.status in (RunStatus.SUCCEEDED.value, RunStatus.CANCELLED.value):
            return

        monitor = db.get(Monitor, run.monitor_id)
        if monitor is None:
            run.status = RunStatus.FAILED.value
            run.error_code = "internal_error"
            run.error_message = "Monitor missing"
            run.finished_at = datetime.now(UTC)
            db.commit()
            return

        day = datetime.now(UTC).strftime("%Y%m%d")
        bkey = f"browser_quota:{monitor.workspace_id}:{day}"
        r = _redis()
        bcount = int(r.get(bkey) or 0)
        if bcount >= settings.max_browser_checks_per_day:
            run.status = RunStatus.FAILED.value
            run.error_code = "internal_error"
            run.error_message = "Browser check daily quota exceeded"
            run.finished_at = datetime.now(UTC)
            db.commit()
            return

        run.status = RunStatus.RUNNING.value
        run.started_at = datetime.now(UTC)
        db.commit()

        try:
            domain = assert_domain_allowed(monitor.url)
            acquire_domain_slot(domain)

            if monitor.mode == "visual":
                capture = capture_screenshot(
                    monitor.url,
                    timeout_seconds=max(monitor.timeout_seconds, 45),
                    full_page=True,
                    clip_selector=monitor.css_selector or None,
                )
                result = visual_to_fetch_result(capture, url=monitor.url)
            else:
                result = fetch_url_browser(
                    monitor.url,
                    timeout_seconds=max(monitor.timeout_seconds, 45),
                    max_response_bytes=monitor.max_response_bytes,
                    wait_selector=monitor.css_selector if monitor.mode == "css_selector" else None,
                )

            r.incr(bkey)
            r.expire(bkey, 86_400)

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

            for oid in list(pipeline.outbox_ids or []) + outbox_extra:
                deliver_outbox_message.send(str(oid))

            logger.info(
                "browser_check_done monitor_id=%s run_id=%s mode=%s status=%s",
                monitor.id,
                run.id,
                monitor.mode,
                pipeline.status,
            )

        except DomainBlocked as exc:
            _fail(db, run, "blocked_address", str(exc))
            record_run_outcome(
                db, monitor=monitor, succeeded=False, error_code="blocked_address", error_message=str(exc)
            )
            db.commit()
        except SSRFError as exc:
            _fail(db, run, exc.code, str(exc))
            record_run_outcome(
                db, monitor=monitor, succeeded=False, error_code=exc.code, error_message=str(exc)
            )
            db.commit()
        except FetchError as exc:
            if domain:
                record_domain_failure(domain)
            _fail(db, run, exc.code, str(exc), http_status=exc.http_status)
            outbox_extra = record_run_outcome(
                db, monitor=monitor, succeeded=False, error_code=exc.code, error_message=str(exc)
            )
            db.commit()
            for oid in outbox_extra:
                deliver_outbox_message.send(str(oid))
            if exc.code in ("read_timeout", "connection_timeout"):
                raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("browser_check_failed run_id=%s", run_id)
            if domain:
                record_domain_failure(domain)
            _fail(db, run, "internal_error", str(exc)[:2000])
            raise
        finally:
            if domain:
                release_domain_slot(domain)


def _fail(
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
