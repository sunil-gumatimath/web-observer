"""HTTP check worker."""

from __future__ import annotations

import logging
import time

import dramatiq

from app.config import get_settings
from app.models import Monitor
from app.models.entities import PLAIN_HTTP_MODES, RunStatus
from app.services import context_dev
from app.services.fetcher import FetchError, FetchResult, fetch_url
from app.services.sitemap import SitemapError, sitemap_monitor_text
from app.workers.broker import redis_broker  # noqa: F401
from app.workers.run_guard import execute_monitored_run

logger = logging.getLogger(__name__)
settings = get_settings()

MODE_SITE_LINKS = "site_links"
MODE_README = "readme"
MODE_SECURITY_SCAN = "security_scan"

# Only retry through the paid provider when the local fetch was plausibly
# blocked or timed out. A 404 is a real result, never a reason to spend credits.
_PROVIDER_FAILOVER_CODES = frozenset({"bot_challenge", "http_error", "read_timeout"})
_PROVIDER_HTTP_STATUSES = frozenset({401, 403, 429})


def fetch_page_with_provider_fallback(
    url: str,
    *,
    monitor_mode: str,
    timeout_seconds: int,
    max_response_bytes: int,
    respect_robots: bool = True,
    primary=None,
    primary_kwargs: dict | None = None,
) -> FetchResult:
    """Fetch a page locally; retry via Context.dev only when it looks blocked."""
    fetch = primary or fetch_url
    kwargs: dict = {
        "timeout_seconds": timeout_seconds,
        "max_response_bytes": max_response_bytes,
        "mode": monitor_mode,
    }
    if respect_robots:
        kwargs["respect_robots"] = True
    if primary_kwargs:
        kwargs.update(primary_kwargs)
    try:
        return fetch(url, **kwargs)
    except FetchError as exc:
        if monitor_mode != "page_content" or not context_dev.is_configured():
            raise
        if exc.code not in _PROVIDER_FAILOVER_CODES:
            raise
        if exc.code == "http_error" and exc.http_status not in _PROVIDER_HTTP_STATUSES:
            raise
        # Clock the provider call itself: starting after it made latency_ms
        # measure only logging / response construction.
        started = time.perf_counter()
        try:
            markdown = context_dev.scrape_markdown(url, timeout_seconds=timeout_seconds)
        except Exception as provider_exc:  # noqa: BLE001 - never mask the original
            logger.warning("page_provider_fallback_failed url=%s error=%s", url, provider_exc)
            raise exc from provider_exc
        logger.info("page_provider_fallback_used url=%s chars=%s", url, len(markdown))
        return FetchResult(
            final_url=url,
            status_code=200,
            content=markdown.encode("utf-8"),
            text=markdown,
            content_type="text/markdown; charset=utf-8",
            latency_ms=round((time.perf_counter() - started) * 1000),
            provider_markdown=markdown,
        )


@dramatiq.actor(queue_name="http_checks", max_retries=3, time_limit=120_000)
def run_http_check(run_id: str) -> None:
    """Execute a single HTTP monitor run end-to-end."""

    def _pre_run_hook(monitor, run, db):
        # Misrouted browser job. site_links/rss_feed/readme must stay on THIS
        # worker even when js_required is set: their fetch paths are plain
        # HTTP, so handing them to Playwright would snapshot the wrong content.
        if (monitor.js_required or monitor.mode == "visual") and monitor.mode not in (
            PLAIN_HTTP_MODES
        ):
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
                text = sitemap_monitor_text(
                    monitor.url,
                    timeout_seconds=monitor.timeout_seconds,
                    max_response_bytes=monitor.max_response_bytes,
                )
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
        if monitor.mode == MODE_README:
            started = time.perf_counter()
            from app.services.readme import fetch_readme_text

            try:
                text, final_url = fetch_readme_text(
                    monitor.url,
                    timeout_seconds=monitor.timeout_seconds,
                    max_response_bytes=monitor.max_response_bytes,
                )
            except Exception as exc:  # noqa: BLE001
                # Preserve ExtractionError code when possible
                code = getattr(exc, "code", "readme_not_found")
                raise FetchError(code, str(exc)) from exc
            content = text.encode("utf-8")
            if len(content) > monitor.max_response_bytes:
                raise FetchError(
                    "response_too_large",
                    f"README size {len(content)} exceeds limit {monitor.max_response_bytes}",
                )
            return FetchResult(
                final_url=final_url,
                status_code=200,
                content=content,
                text=text,
                content_type="text/markdown; charset=utf-8",
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
        if monitor.mode == MODE_SECURITY_SCAN:
            started = time.perf_counter()
            from app.services.security_scan import scan_url

            try:
                return scan_url(
                    monitor.url,
                    timeout_seconds=monitor.timeout_seconds,
                    max_response_bytes=monitor.max_response_bytes,
                )
            except FetchError:  # noqa: TRY203 - re-raise unchanged, latency fresh
                started_delta = time.perf_counter() - started
                logger.debug("security_scan_fetch_failed latency=%.2fs", started_delta)
                raise
        if monitor.mode == "page_content":
            return fetch_page_with_provider_fallback(
                monitor.url,
                monitor_mode=monitor.mode,
                timeout_seconds=monitor.timeout_seconds,
                max_response_bytes=monitor.max_response_bytes,
            )
        return fetch_url(
            monitor.url,
            timeout_seconds=monitor.timeout_seconds,
            max_response_bytes=monitor.max_response_bytes,
            respect_robots=True,
            mode=monitor.mode,
        )

    execute_monitored_run(
        run_id,
        _fetch,
        pre_run_hook=_pre_run_hook,
        worker_label="check",
    )
