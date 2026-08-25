"""HTTP check worker."""

from __future__ import annotations

import logging
import time

import dramatiq

from app.config import get_settings
from app.models import Monitor
from app.models.entities import RunStatus
from app.services.fetcher import FetchError, FetchResult, fetch_url
from app.services.sitemap import SitemapError, sitemap_monitor_text
from app.workers.broker import redis_broker  # noqa: F401
from app.workers.run_guard import execute_monitored_run

logger = logging.getLogger(__name__)
settings = get_settings()

MODE_SITE_LINKS = "site_links"


@dramatiq.actor(queue_name="http_checks", max_retries=3, time_limit=120_000)
def run_http_check(run_id: str) -> None:
    """Execute a single HTTP monitor run end-to-end."""

    def _pre_run_hook(monitor, run, db):
        # Misrouted browser job. site_links must stay on THIS worker even when
        # js_required is set: its fetch path is sitemap discovery over plain
        # HTTP, so handing it to Playwright would snapshot the wrong content.
        if monitor.js_required and monitor.mode != MODE_SITE_LINKS:
            from app.workers.browser_checks import run_browser_check

            run.status = RunStatus.QUEUED.value
            db.commit()
            run_browser_check.send(run_id)
            return True
        return False

    def _fetch(monitor: Monitor, db) -> FetchResult:
        if monitor.mode == MODE_SITE_LINKS:
            started = time.perf_counter()
            try:
                text = sitemap_monitor_text(monitor.url, timeout_seconds=monitor.timeout_seconds)
            except SitemapError as exc:
                raise FetchError("sitemap_error", str(exc)) from exc
            content = text.encode("utf-8")
            if len(content) > monitor.max_response_bytes:
                raise FetchError(
                    "response_too_large",
                    f"Sitemap URL list size {len(content)} exceeds limit "
                    f"{monitor.max_response_bytes}",
                )
            return FetchResult(
                final_url=monitor.url,
                status_code=200,
                content=content,
                text=text,
                content_type="text/plain; charset=utf-8",
                # round() returns an int here and avoids a lint-rule trip on
                # unchecked int() conversion of a value that cannot fail.
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
        return fetch_url(
            monitor.url,
            timeout_seconds=monitor.timeout_seconds,
            max_response_bytes=monitor.max_response_bytes,
            respect_robots=True,
        )

    execute_monitored_run(
        run_id,
        _fetch,
        pre_run_hook=_pre_run_hook,
        worker_label="check",
    )
