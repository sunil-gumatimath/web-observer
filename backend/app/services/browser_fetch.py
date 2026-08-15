"""Playwright-based fetch for JS-rendered pages."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import get_settings
from app.security.ssrf import SSRFError, validate_url_for_fetch
from app.services.fetcher import FetchError, FetchResult, detect_bot_challenge

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}

_LAUNCH_ARGS = [
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-software-rasterizer",
]


def _fetch_url_browser_inline(
    url: str,
    *,
    timeout_seconds: int,
    max_response_bytes: int,
    wait_selector: str | None = None,
) -> FetchResult:
    """In-process Playwright fetch. Prefer fetch_url_browser() (subprocess by default)."""
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
            try:
                browser = p.chromium.launch(headless=True, args=_LAUNCH_ARGS)
            except Exception as launch_exc:  # noqa: BLE001
                msg = str(launch_exc)
                if "Executable doesn't exist" in msg or "playwright install" in msg.lower():
                    raise FetchError(
                        "internal_error",
                        "Playwright browsers missing/outdated. "
                        "Run: python -m playwright install chromium",
                    ) from launch_exc
                raise
            context = None
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
                    try:
                        # Resolve every browser request, not just the initial URL.
                        # This blocks private destinations reached through redirects,
                        # scripts, iframes, and DNS changes.
                        validate_url_for_fetch(request.url, resolve_dns=True)
                    except SSRFError:
                        return route.abort()
                    return route.continue_()

                page.route("**/*", _route_handler)

                response = page.goto(
                    validated.url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                try:
                    page.wait_for_load_state("networkidle", timeout=min(15_000, timeout_ms))
                except PlaywrightTimeout:
                    logger.debug("networkidle_timeout url=%s", validated.url)

                status = response.status if response is not None else 200
                challenge = detect_bot_challenge(
                    status_code=status,
                    headers=dict(response.headers) if response is not None else {},
                    text=page.content(),
                )
                if challenge:
                    raise FetchError(
                        "bot_challenge",
                        f"Blocked while fetching {validated.url}: {challenge}. "
                        "The site requires a real browser session; try a "
                        "non-headless browser with an existing login session.",
                        http_status=status,
                    )

                if wait_selector:
                    page.wait_for_selector(wait_selector, timeout=min(30_000, timeout_ms))

                html = page.content()
                final_url = page.url
                content = html.encode("utf-8", errors="replace")
            finally:
                if context is not None:
                    try:
                        context.close()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    browser.close()
                except Exception:  # noqa: BLE001
                    pass
    except PlaywrightTimeout as exc:
        raise FetchError("read_timeout", f"Browser timeout: {exc}") from exc
    except SSRFError as exc:
        raise FetchError(exc.code, str(exc)) from exc
    except FetchError:
        raise
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        if "Bad file descriptor" in err or "errno 9" in err.lower():
            raise FetchError(
                "internal_error",
                "Browser fetch failed (Playwright process error). "
                "Restart the browser worker with --threads 1.",
            ) from exc
        raise FetchError("internal_error", f"Browser fetch failed: {exc}") from exc

    if len(content) > max_response_bytes:
        raise FetchError(
            "response_too_large",
            f"Rendered content size {len(content)} exceeds limit {max_response_bytes}",
            http_status=status,
        )

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


def _fetch_url_browser_subprocess(
    url: str,
    *,
    timeout_seconds: int,
    max_response_bytes: int,
    wait_selector: str | None = None,
) -> FetchResult:
    validate_url_for_fetch(url, resolve_dns=True)
    started = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="wo-browser-") as tmp:
        out_path = str(Path(tmp) / "body.bin")
        meta_path = str(Path(tmp) / "meta.json")
        cmd = [
            sys.executable,
            "-m",
            "app.services.playwright_job",
            "fetch",
            "--url",
            url,
            "--out",
            out_path,
            "--meta",
            meta_path,
            "--timeout",
            str(timeout_seconds),
            "--max-bytes",
            str(max_response_bytes),
        ]
        if wait_selector:
            cmd.extend(["--wait-selector", wait_selector])

        env = os.environ.copy()
        env["WEB_OBSERVER_PLAYWRIGHT_CHILD"] = "1"
        backend_root = str(Path(__file__).resolve().parents[2])
        prev_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            backend_root if not prev_pp else f"{backend_root}{os.pathsep}{prev_pp}"
        )

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=max(60, timeout_seconds + 30),
                env=env,
                cwd=backend_root,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise FetchError("read_timeout", "Browser fetch subprocess timed out") from exc

        if proc.returncode != 0:
            err_payload: dict = {}
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            stdout = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
            for blob in (stderr, stdout):
                if not blob:
                    continue
                for line in reversed(blob.splitlines()):
                    line = line.strip()
                    if line.startswith("{") and "error" in line:
                        try:
                            err_payload = json.loads(line)
                            break
                        except json.JSONDecodeError:
                            continue
                if err_payload:
                    break
            code = err_payload.get("error_code") or "internal_error"
            msg = err_payload.get("error") or stderr or stdout or f"exit {proc.returncode}"
            raise FetchError(str(code), f"Browser fetch failed: {msg}")

        if not Path(out_path).is_file() or not Path(meta_path).is_file():
            raise FetchError("internal_error", "Browser fetch subprocess produced no output")

        content = Path(out_path).read_bytes()
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        html = content.decode("utf-8", errors="replace")
        latency_ms = int(meta.get("latency_ms") or int((time.perf_counter() - started) * 1000))
        final_url = str(meta.get("final_url") or url)
        try:
            validate_url_for_fetch(final_url, resolve_dns=True)
        except SSRFError as exc:
            raise FetchError(exc.code, f"Final navigation URL blocked: {exc}") from exc
        return FetchResult(
            final_url=final_url,
            status_code=int(meta.get("status_code") or 200),
            content=content,
            text=html,
            content_type=str(meta.get("content_type") or "text/html; charset=utf-8"),
            latency_ms=latency_ms,
        )


def fetch_url_browser(
    url: str,
    *,
    timeout_seconds: int,
    max_response_bytes: int,
    wait_selector: str | None = None,
) -> FetchResult:
    """Fetch page with headless Chromium. Applies SSRF checks on the target URL.

    Defaults to a subprocess so Dramatiq workers do not share Playwright pipes
    (Windows errno 9). Child process / WEB_OBSERVER_PLAYWRIGHT_INLINE runs inline.
    """
    force_inline = os.environ.get("WEB_OBSERVER_PLAYWRIGHT_INLINE", "").strip() in {
        "1",
        "true",
        "yes",
    }
    is_child = os.environ.get("WEB_OBSERVER_PLAYWRIGHT_CHILD", "").strip() in {
        "1",
        "true",
        "yes",
    }
    if force_inline or is_child:
        return _fetch_url_browser_inline(
            url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            wait_selector=wait_selector,
        )
    return _fetch_url_browser_subprocess(
        url,
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
        wait_selector=wait_selector,
    )
