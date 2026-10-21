"""Unit tests for the Phase 7 Cloudflare Browser Rendering failover ladder."""

import httpx
import pytest

import app.services.browser_fetch as bf
from app.config import Settings
from app.services.fetcher import FetchError, FetchResult


def _fake_settings(cf_url: str | None) -> Settings:
    return Settings(
        app_env="test",
        cloudflare_browser_url=cf_url or "",
        cloudflare_browser_token="tok",
    )


def _local_result() -> FetchResult:
    return FetchResult(
        final_url="https://example.com/",
        status_code=200,
        content=b"<html>from-local</html>",
        text="<html>from-local</html>",
        content_type="text/html; charset=utf-8",
        latency_ms=9,
    )


def _cf_result() -> FetchResult:
    return FetchResult(
        final_url="https://example.com/",
        status_code=200,
        content=b"<html>from-cf</html>",
        text="<html>from-cf</html>",
        content_type="text/html; charset=utf-8",
        latency_ms=900,
    )


def test_not_configured_short_circuits(monkeypatch) -> None:
    """No CLOUDFLARE_BROWSER_URL -> local path only, no failover attempt."""
    monkeypatch.delenv("WEB_OBSERVER_PLAYWRIGHT_INLINE", raising=False)
    monkeypatch.delenv("WEB_OBSERVER_PLAYWRIGHT_CHILD", raising=False)
    monkeypatch.setattr(bf, "get_settings", lambda: _fake_settings(""))
    called = []

    def _boom(url, **kwargs):  # pragma: no cover - should never run the CF path
        called.append("cf")
        raise AssertionError("failover attempted without configuration")

    monkeypatch.setattr(bf, "_fetch_url_cf_browser", _boom)
    monkeypatch.setattr(bf, "_fetch_url_browser_subprocess", lambda url, **k: _local_result())

    result = bf.fetch_url_browser(
        "https://example.com", timeout_seconds=30, max_response_bytes=1000
    )
    assert result.text == "<html>from-local</html>"
    assert called == []


def test_success_local_no_cf_call(monkeypatch) -> None:
    """When the local fetch succeeds, the CF Worker is never called."""
    monkeypatch.setattr(bf, "get_settings", lambda: _fake_settings("https://worker.example"))
    cf_calls = []

    def _cf(url, **kwargs):
        cf_calls.append(url)
        raise AssertionError("failover attempted despite local success")

    monkeypatch.setattr(bf, "_fetch_url_cf_browser", _cf)
    monkeypatch.setattr(bf, "_fetch_url_browser_subprocess", lambda url, **k: _local_result())

    result = bf.fetch_url_browser(
        "https://example.com", timeout_seconds=30, max_response_bytes=1000
    )
    assert result.text == "<html>from-local</html>"
    assert not cf_calls


def test_local_failure_falls_back_to_cf(monkeypatch) -> None:
    """Local Playwright fails -> CF Worker result is returned instead."""
    monkeypatch.setattr(bf, "get_settings", lambda: _fake_settings("https://worker.example"))

    def _local_boom(url, **kwargs):
        raise FetchError("read_timeout", "Browser fetch subprocess timed out")

    monkeypatch.setattr(bf, "_fetch_url_browser_subprocess", _local_boom)
    monkeypatch.setattr(bf, "_fetch_url_cf_browser", lambda url, **k: _cf_result())

    result = bf.fetch_url_browser(
        "https://example.com", timeout_seconds=30, max_response_bytes=1000
    )
    assert result.text == "<html>from-cf</html>"


def test_bot_challenge_skips_failover(monkeypatch) -> None:
    """Bot challenges are endpoint-independent; do not retry on the edge."""
    monkeypatch.setattr(bf, "get_settings", lambda: _fake_settings("https://worker.example"))

    def _cf(url, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("failover attempted on bot challenge")

    monkeypatch.setattr(bf, "_fetch_url_cf_browser", _cf)

    def _local_boom(url, **kwargs):
        raise FetchError("bot_challenge", "Blocked", http_status=403)

    monkeypatch.setattr(bf, "_fetch_url_browser_subprocess", _local_boom)

    with pytest.raises(FetchError) as exc:
        bf.fetch_url_browser("https://example.com", timeout_seconds=30, max_response_bytes=1000)
    assert exc.value.code == "bot_challenge"


def test_cf_failure_annotates_local_error(monkeypatch) -> None:
    """If the failover is also down, the *local* error is still the surfaced one."""
    monkeypatch.setattr(bf, "get_settings", lambda: _fake_settings("https://worker.example"))

    def _local_boom(url, **kwargs):
        raise FetchError("read_timeout", "Browser fetch subprocess timed out")

    monkeypatch.setattr(bf, "_fetch_url_browser_subprocess", _local_boom)

    def _cf_boom(url, **kwargs):
        raise FetchError("internal_error", "worker unreachable")

    monkeypatch.setattr(bf, "_fetch_url_cf_browser", _cf_boom)

    with pytest.raises(FetchError) as exc:
        bf.fetch_url_browser("https://example.com", timeout_seconds=30, max_response_bytes=1000)
    assert exc.value.code == "read_timeout"


def test_cf_fetch_maps_worker_payload(monkeypatch) -> None:
    """A 200 Worker response maps onto FetchResult (size caps + SSRF rechecked)."""
    monkeypatch.setattr(bf, "get_settings", lambda: _fake_settings("https://worker.example"))

    def _worker_success(url, **kwargs):
        body = {
            "status_code": 200,
            "final_url": "https://example.com/redirected",
            "html": "<html>edge</html>",
        }
        return type("R", (), {"status_code": 200, "json": lambda self: body, "text": ""})()

    monkeypatch.setattr(bf.httpx, "post", _worker_success)
    result = bf._fetch_url_cf_browser(
        "https://example.com", timeout_seconds=30, max_response_bytes=10**6
    )
    assert result.status_code == 200
    assert result.final_url == "https://example.com/redirected"
    assert result.content == b"<html>edge</html>"


def test_cf_fetch_rejects_private_final_url(monkeypatch) -> None:
    """A Worker answer pointing at a private address is refused, not stored."""
    monkeypatch.setattr(bf, "get_settings", lambda: _fake_settings("https://worker.example"))

    def _worker_redirect(url, **kwargs):
        body = {
            "status_code": 200,
            "final_url": "http://10.0.0.5/admin",
            "html": "<html>evil</html>",
        }
        return type("R", (), {"status_code": 200, "json": lambda self: body, "text": ""})()

    monkeypatch.setattr(bf.httpx, "post", _worker_redirect)

    with pytest.raises(FetchError) as exc:
        bf._fetch_url_cf_browser(
            "https://example.com", timeout_seconds=30, max_response_bytes=10**6
        )
    assert exc.value.code == "blocked_address"


def test_cf_fetch_wraps_transport_errors(monkeypatch) -> None:
    """Transport errors surface as FetchError, never as raw httpx exceptions."""
    monkeypatch.setattr(bf, "get_settings", lambda: _fake_settings("https://worker.example"))

    def _unreachable(url, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(bf.httpx, "post", _unreachable)

    with pytest.raises(FetchError) as exc:
        bf._fetch_url_cf_browser(
            "https://example.com", timeout_seconds=30, max_response_bytes=10**6
        )
    assert exc.value.code == "internal_error"
