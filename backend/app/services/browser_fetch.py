"""Playwright-based fetch for JS-rendered pages."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from app.config import get_settings
from app.security.ssrf import SSRFError, validate_url_for_fetch
from app.services.fetcher import FetchError, FetchResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}


def fetch_url_browser(
    url: str,
    *,
    timeout_seconds: int,
    max_response_bytes: int,
    wait_selector: str | None = None,
) -> FetchResult:
    """Fetch page with headless Chromium. Applies SSRF checks on the target URL."""
    settings = get_settings()
    validated = validate_url_for_fetch(url, resolve_dns=True)

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FetchError(
            "internal_error",
            "Playwright is not installed. Install playwright and browser binaries.",
        ) from exc

    timeout_ms = max(5_000, timeout_seconds * 1000)
    started = time.perf_counter()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
            try:
                context = browser.new_context(
                    user_agent=settings.http_user_agent,
                    java_script_enabled=True,
                    ignore_https_errors=False,
                )
                page = context.new_page()

                def _route_handler(route, request):  # type: ignore[no-untyped-def]
                    if request.resource_type in _BLOCKED_RESOURCE_TYPES:
                        return route.abort()
                    # Soft SSRF: block clearly private hosts on subresources
                    try:
                        validate_url_for_fetch(request.url, resolve_dns=False)
                    except SSRFError:
                        return route.abort()
                    return route.continue_()

                page.route("**/*", _route_handler)

                response = page.goto(
                    validated.url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                # Prefer networkidle when possible for SPA hydration
                try:
                    page.wait_for_load_state("networkidle", timeout=min(15_000, timeout_ms))
                except PlaywrightTimeout:
                    logger.debug("networkidle_timeout url=%s", validated.url)

                if wait_selector:
                    page.wait_for_selector(wait_selector, timeout=min(30_000, timeout_ms))

                html = page.content()
                final_url = page.url
                status = response.status if response is not None else 200
                content = html.encode("utf-8", errors="replace")
            finally:
                browser.close()
    except PlaywrightTimeout as exc:
        raise FetchError("read_timeout", f"Browser timeout: {exc}") from exc
    except SSRFError as exc:
        raise FetchError(exc.code, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise FetchError("internal_error", f"Browser fetch failed: {exc}") from exc

    if len(content) > max_response_bytes:
        raise FetchError(
            "response_too_large",
            f"Rendered content size {len(content)} exceeds limit {max_response_bytes}",
            http_status=status,
        )

    # Re-validate final URL after navigations
    try:
        validate_url_for_fetch(final_url, resolve_dns=True)
    except SSRFError as exc:
        raise FetchError(exc.code, f"Final navigation URL blocked: {exc}") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    return FetchResult(
        final_url=final_url,
        status_code=status,
        content=content,
        text=html,
        content_type="text/html; charset=utf-8",
        latency_ms=latency_ms,
    )
