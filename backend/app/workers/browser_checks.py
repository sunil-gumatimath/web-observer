"""Browser (Playwright) check worker — separate queue and capacity."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import dramatiq

from app.config import get_settings
from app.db import SessionLocal
from app.models import ChangeEvent, Monitor, NotificationOutbox, Workspace
from app.models.entities import PLAIN_HTTP_MODES, OutboxStatus, RunStatus
from app.services.browser_fetch import fetch_url_browser
from app.services.domain_guard import _redis
from app.services.failure_notify import record_run_outcome
from app.workers.broker import redis_broker  # noqa: F401
from app.workers.run_guard import execute_monitored_run

logger = logging.getLogger(__name__)
settings = get_settings()


@dramatiq.actor(queue_name="browser_checks", max_retries=2, time_limit=180_000)
def run_browser_check(run_id: str) -> None:
    """Execute a JS-required or visual monitor run with Playwright."""

    def _pre_run_hook(monitor, run, db):
        # Defense-in-depth: site_links/rss_feed/readme monitors must never run
        # through Playwright — they fetch sitemap/feed/README over plain HTTP.
        if monitor.mode in PLAIN_HTTP_MODES:
            from app.workers.checks import run_http_check

            run.status = RunStatus.QUEUED.value
            db.commit()
            run_http_check.send(run_id)
            return True

        # Daily browser-check quota per workspace, charged ONCE per run — not
        # once per message execution. Dramatiq is at-least-once, so a plain
        # INCR would burn quota for every retry of the same run; a per-run
        # receipt key makes the reservation idempotent.
        from app.services.plans import get_plan

        workspace = db.get(Workspace, monitor.workspace_id)
        if workspace is not None:
            limit = get_plan(workspace).max_browser_checks_per_day
        else:
            limit = settings.max_browser_checks_per_day
        day = datetime.now(UTC).strftime("%Y%m%d")
        bkey = f"browser_quota:{monitor.workspace_id}:{day}"
        rkey = f"browser_quota_run:{run.id}"
        r = _redis()
        # KEYS[1] = quota counter, KEYS[2] = per-run reservation receipt,
        # ARGV[1] = TTL seconds. Returns the quota counter after a *new*
        # reservation, or 0 when this run already reserved a slot.
        lua = """
        local already = redis.call('EXISTS', KEYS[2])
        if already == 1 then return 0 end
        redis.call('SET', KEYS[2], '1', 'EX', ARGV[1])
        local cur = redis.call('INCR', KEYS[1])
        if cur == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
        return cur
        """
        try:
            cur = int(str(r.eval(lua, 2, bkey, rkey, "86400")))
        except Exception:
            # NOTE: keep boolean operators out of this handler — the
            # no-boolean-in-except lint scans the entire except subtree.
            already = r.exists(rkey)
            if already:
                return False
            fallback = r.incr(bkey)
            cur = int(str(fallback)) if fallback else 1
            if cur == 1:
                r.expire(bkey, 86_400)
            r.set(rkey, "1", ex=86_400)
        if cur and cur > limit:
            # Rollback overshoot and release this run's receipt.
            try:
                r.decr(bkey)
                r.delete(rkey)
            except Exception as decr_exc:  # noqa: BLE001
                logger.debug("browser_quota_rollback_failed error=%s", decr_exc)
            run.status = RunStatus.FAILED.value
            run.error_code = "quota_exceeded"
            run.error_message = (
                f"Browser check daily quota exceeded (plan limit: {limit} browser checks/day)"
            )
            run.finished_at = datetime.now(UTC)
            outbox_ids = record_run_outcome(
                db,
                monitor=monitor,
                succeeded=False,
                error_code="quota_exceeded",
                error_message=run.error_message,
            )
            db.commit()
            from app.workers.run_guard import enqueue_outbox

            enqueue_outbox(outbox_ids)
            return True
        return False

    def _fetch(monitor: Monitor, db):
        if monitor.mode == "visual":
            from app.services.visual import capture_screenshot, visual_to_fetch_result

            capture = capture_screenshot(
                monitor.url,
                timeout_seconds=max(monitor.timeout_seconds, 45),
                full_page=True,
                clip_selector=monitor.css_selector,
            )
            try:
                from app.services.storage import put_bytes

                put_bytes(
                    key=f"screenshots/{monitor.id}/{run_id}.png",
                    data=capture.png_bytes,
                    content_type="image/png",
                )
            except Exception as s_exc:
                logger.debug("visual_screenshot_path_save_failed error=%s", s_exc)

            result = visual_to_fetch_result(capture, url=monitor.url)
        else:
            result = fetch_url_browser(
                monitor.url,
                timeout_seconds=max(monitor.timeout_seconds, 45),
                max_response_bytes=monitor.max_response_bytes,
            )
        # Quota was reserved once for this run in _pre_run_hook (receipt key);
        # just refresh expiry — advisory housekeeping only.
        try:
            day = datetime.now(UTC).strftime("%Y%m%d")
            bkey = f"browser_quota:{monitor.workspace_id}:{day}"
            _redis().expire(bkey, 86_400)
        except Exception as exp_exc:  # noqa: BLE001 - TTL refresh is advisory
            logger.debug("browser_quota_ttl_refresh_failed error=%s", exp_exc)
        return result

    execute_monitored_run(
        run_id,
        _fetch,
        pre_run_hook=_pre_run_hook,
        worker_label="browser_check",
    )

    # Best-effort preview screenshot for the finished run (see
    # capture_run_screenshot). No-ops for visual mode (the check stored
    # its own capture), failed runs, and monitors with screenshots off.
    try:
        capture_run_screenshot.send(run_id)
    except Exception as e_exc:  # noqa: BLE001 - hero preview is advisory
        logger.debug("run_screenshot_enqueue_failed run_id=%s error=%s", run_id, e_exc)


def _attach_screenshot_to_pending(db, change: ChangeEvent, screenshot_path: str) -> int:
    """Point still-pending outbox payloads at a screenshot. Returns rows updated."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    pending = db.scalars(
        select(NotificationOutbox).where(
            NotificationOutbox.change_event_id == change.id,
            NotificationOutbox.status == OutboxStatus.PENDING.value,
        )
    ).all()
    for outbox in pending:
        payload = dict(outbox.payload or {})
        payload["screenshot_path"] = screenshot_path
        outbox.payload = payload
        flag_modified(outbox, "payload")
    db.commit()
    return len(pending)


@dramatiq.actor(queue_name="browser_checks", max_retries=2, time_limit=120_000)
def capture_alert_screenshot(change_event_id: str) -> None:
    """Capture a change-alert screenshot off the critical check path.

    Enqueued post-commit by the pipeline when ``screenshots_enabled`` is on,
    so a slow (~30s) Playwright capture never blocks HTTP check workers or
    notification queuing. Best-effort: failures are logged, never raised —
    the change notification was already queued without the attachment.
    """
    from uuid import UUID

    from app.services.storage import object_exists, put_bytes

    try:
        change_uuid = UUID(str(change_event_id))
    except ValueError:
        logger.warning("screenshot_bad_change_id change_id=%s", change_event_id)
        return

    with SessionLocal() as db:
        change = db.get(ChangeEvent, change_uuid)
        if change is None:
            logger.warning("screenshot_change_missing change_id=%s", change_event_id)
            return
        monitor = db.get(Monitor, change.monitor_id)
        if monitor is None:
            logger.warning("screenshot_monitor_missing change_id=%s", change_event_id)
            return
        screenshot_path = f"screenshots/{monitor.id}/{change.run_id}.png"
        if monitor.mode == "visual" and object_exists(screenshot_path):
            # The check stored the capture that was hashed and compared. A
            # recapture seconds later would overwrite it with the page's
            # *current* state — the comparison could then show two identical
            # images for a change that was genuinely detected.
            updated = _attach_screenshot_to_pending(db, change, screenshot_path)
            logger.info(
                "screenshot_reused change_id=%s outbox_updated=%s",
                change_event_id,
                updated,
            )
            return
        try:
            from app.services.visual import capture_screenshot

            # For visual monitors css_selector IS the clip region — honour it
            # so the attached screenshot matches the compared region. For other
            # modes css_selector means something else (a list selector or a
            # JSON path), so the full page is captured instead.
            clip = monitor.css_selector if monitor.mode == "visual" else None
            cap = capture_screenshot(
                monitor.url,
                timeout_seconds=30,
                full_page=True,
                clip_selector=clip,
            )
            put_bytes(
                key=screenshot_path,
                data=cap.png_bytes,
                content_type="image/png",
            )
        except Exception as exc:  # noqa: BLE001 - screenshot is advisory
            logger.warning(
                "screenshot_capture_failed monitor_id=%s change_id=%s error=%s",
                monitor.id,
                change_event_id,
                exc,
            )
            return
        # Stitch the attachment into still-pending outbox payloads so the
        # delivered notification carries the screenshot when it made it in
        # time; already-sent messages keep their original payload.
        updated = _attach_screenshot_to_pending(db, change, screenshot_path)
        logger.info(
            "screenshot_captured change_id=%s outbox_updated=%s",
            change_event_id,
            updated,
        )


@dramatiq.actor(queue_name="browser_checks", max_retries=2, time_limit=120_000)
def capture_run_screenshot(run_id: str) -> None:
    """Store a hero-preview screenshot for a finished non-visual browser run.

    The monitor page header shows ``screenshots/{monitor_id}/{run_id}.png``
    for the latest successful run when no brand hero exists — but nothing
    stored a run-keyed screenshot for ``page_content`` monitors (only visual
    runs and change-alert captures did). Enqueued after a browser-fetched run
    completes; runs off the critical path like :func:`capture_alert_screenshot`
    and is best-effort: failures are logged, never raised.
    """
    from uuid import UUID

    from app.models import MonitorRun
    from app.services.storage import object_exists, put_bytes

    try:
        run_uuid = UUID(str(run_id))
    except ValueError:
        logger.warning("screenshot_bad_run_id run_id=%s", run_id)
        return

    with SessionLocal() as db:
        run = db.get(MonitorRun, run_uuid)
        if run is None:
            logger.warning("screenshot_run_missing run_id=%s", run_id)
            return
        if run.status != RunStatus.SUCCEEDED.value:
            return
        monitor = db.get(Monitor, run.monitor_id)
        if monitor is None:
            logger.warning("screenshot_monitor_missing run_id=%s", run_id)
            return
        if not monitor.screenshots_enabled:
            return
        screenshot_path = f"screenshots/{monitor.id}/{run.id}.png"
        if object_exists(screenshot_path):
            return
        try:
            from app.services.visual import capture_screenshot

            cap = capture_screenshot(
                monitor.url,
                timeout_seconds=30,
                full_page=True,
                clip_selector=None,
            )
            put_bytes(
                key=screenshot_path,
                data=cap.png_bytes,
                content_type="image/png",
            )
            logger.info(
                "run_screenshot_captured monitor_id=%s run_id=%s",
                monitor.id,
                run.id,
            )
        except Exception as exc:  # noqa: BLE001 - screenshot is advisory
            logger.warning(
                "run_screenshot_capture_failed monitor_id=%s run_id=%s error=%s",
                monitor.id,
                run.id,
                exc,
            )
