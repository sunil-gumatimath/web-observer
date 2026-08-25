"""Browser (Playwright) check worker — separate queue and capacity."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import dramatiq

from app.config import get_settings
from app.models import Monitor
from app.models.entities import RunStatus
from app.services.browser_fetch import fetch_url_browser
from app.services.domain_guard import _redis
from app.workers.broker import redis_broker  # noqa: F401
from app.workers.run_guard import execute_monitored_run

logger = logging.getLogger(__name__)
settings = get_settings()

MODE_SITE_LINKS = "site_links"


@dramatiq.actor(queue_name="browser_checks", max_retries=2, time_limit=180_000)
def run_browser_check(run_id: str) -> None:
    """Execute a JS-required or visual monitor run with Playwright."""

    def _pre_run_hook(monitor, run, db):
        # Defense-in-depth: a site_links monitor must never run through
        # Playwright — a rendered page is not a sitemap, so snapshotting it
        # would produce garbage. Route back to the sitemap-aware HTTP worker.
        if monitor.mode == MODE_SITE_LINKS:
            from app.workers.checks import run_http_check

            run.status = RunStatus.QUEUED.value
            db.commit()
            run_http_check.send(run_id)
            return True

        # Daily browser-check quota per workspace — atomic incr with check.
        day = datetime.now(UTC).strftime("%Y%m%d")
        bkey = f"browser_quota:{monitor.workspace_id}:{day}"
        r = _redis()
        lua = """
        local cur = redis.call('INCR', KEYS[1])
        if cur == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
        return cur
        """
        try:
            cur = int(str(r.eval(lua, 1, bkey, "86400")))
        except Exception:
            # NOTE: keep boolean operators out of this handler — the
            # no-boolean-in-except lint scans the entire except subtree.
            fallback = r.incr(bkey)
            cur = int(str(fallback)) if fallback else 1
            if cur == 1:
                r.expire(bkey, 86_400)
        if cur > settings.max_browser_checks_per_day:
            # Rollback overshoot
            try:
                r.decr(bkey)
            except Exception as decr_exc:  # noqa: BLE001
                logger.debug("browser_quota_rollback_failed error=%s", decr_exc)
            run.status = RunStatus.FAILED.value
            run.error_code = "internal_error"
            run.error_message = "Browser check daily quota exceeded"
            run.finished_at = datetime.now(UTC)
            db.commit()
            return True
        # We already reserved quota; avoid double-increment in _fetch
        run._quota_reserved = True  # type: ignore[attr-defined]
        return False

    def _fetch(monitor: Monitor, db):
        result = fetch_url_browser(
            monitor.url,
            timeout_seconds=max(monitor.timeout_seconds, 45),
            max_response_bytes=monitor.max_response_bytes,
        )
        # Quota already reserved atomically in _pre_run_hook; just refresh expiry.
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
