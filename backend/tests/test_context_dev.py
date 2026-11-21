"""Tests for the optional Context.dev provider (failover + enrichment)."""

from __future__ import annotations

import base64

import httpx
import pytest

from app.models.entities import Monitor
from app.services import context_dev


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _configured(monkeypatch):
    class S:
        context_dev_api_key = "ctxt_secret_test"

    monkeypatch.setattr(context_dev, "get_settings", lambda: S())


def test_scrape_markdown_sends_bearer_key_and_returns_main_content(monkeypatch):
    _configured(monkeypatch)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["path"] = request.url.path
        seen["body"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={
                "markdown": {"requested": True, "success": True, "data": "# Hello\n\nBody text."},
            },
        )

    with _client(handler) as client:
        text = context_dev.scrape_markdown(
            "https://example.com/page", timeout_seconds=12, client=client
        )

    assert text == "# Hello\n\nBody text."
    assert seen["auth"] == f"Bearer {context_dev.configured_key()}"
    assert seen["path"] == "/v1/web/scrape"
    assert seen["body"]["formats"] == {"markdown": True}
    assert seen["body"]["sharedParams"]["mainContentOnly"] is True


def test_scrape_product_price_returns_canonical_price(monkeypatch):
    _configured(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "product": {
                    "requested": True,
                    "success": True,
                    "data": {
                        "isProductPage": True,
                        "product": {"price": 79.5, "currency": "usd"},
                    },
                },
            },
        )

    with _client(handler) as client:
        price = context_dev.scrape_product_price(
            "https://shop.example.com/p", timeout_seconds=8, client=client
        )

    assert price == "USD 79.5"


def test_map_urls_returns_only_public_http_urls(monkeypatch):
    _configured(monkeypatch)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "success": True,
                "domain": "example.com",
                "urls": [
                    {"url": "https://example.com/a"},
                    {"url": "https://example.com/a"},
                    {"url": "ftp://example.com/b"},
                    {"url": "https://sub.example.net/x"},
                ],
            },
        )

    with _client(handler) as client:
        urls = context_dev.map_urls(
            "https://example.com/home", max_links=25, timeout_seconds=7, client=client
        )

    assert urls == ["https://example.com/a", "https://sub.example.net/x"]
    assert seen["params"]["domain"] == "example.com"
    assert seen["params"]["maxLinks"] == "25"


def test_scrape_screenshot_png_decodes_inline_data_url(monkeypatch):
    _configured(monkeypatch)
    png = b"\x89PNG\r\n\x1a\nFAKE"
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = __import__("json").loads(request.content)
        data_url = "data:image/png;base64," + base64.b64encode(png).decode()
        return httpx.Response(
            200,
            json={
                "screenshot": {"requested": True, "success": True, "data": data_url},
            },
        )

    with _client(handler) as client:
        raw = context_dev.scrape_screenshot_png(
            "https://example.com", timeout_seconds=9, client=client
        )

    assert raw == png
    assert seen["body"]["formats"] == {"screenshot": True}
    assert seen["body"]["screenshotParams"] == {"area": "fullPage", "format": "png"}


def test_context_key_is_a_masked_server_setting(monkeypatch):
    from app.config import _OVERRIDE_CHECKED_FIELDS, _SECRET_FIELDS, get_settings

    monkeypatch.setenv("CONTEXT_DEV_API_KEY", "ctxt_secret_from_env")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.context_dev_api_key == "ctxt_secret_from_env"
        assert "CONTEXT_DEV_API_KEY" in _SECRET_FIELDS
        assert "CONTEXT_DEV_API_KEY" in _OVERRIDE_CHECKED_FIELDS
    finally:
        get_settings.cache_clear()


def _price_monitor() -> Monitor:
    from uuid import uuid4

    from app.models.entities import Monitor

    return Monitor(
        id=uuid4(),
        workspace_id=uuid4(),
        name="Price watch",
        url="https://shop.example.com/product",
        mode="product_price",
        js_required=False,
    )


def test_product_price_uses_structured_provider_when_configured(monkeypatch):
    from app.services.fetcher import FetchResult
    from app.services.pipeline import extract_normalized

    monkeypatch.setattr(context_dev, "is_configured", lambda: True)
    monkeypatch.setattr(
        context_dev,
        "scrape_product_price",
        lambda url, **kwargs: "USD 79.5",
    )
    result = FetchResult(
        final_url="https://shop.example.com/product",
        status_code=200,
        content=b"<html>$1.00 cross-sell</html>",
        text="<html>$1.00 cross-sell</html>",
        content_type="text/html",
        latency_ms=1,
    )

    assert extract_normalized(_price_monitor(), result)[0] == "USD 79.5"


def test_product_price_falls_back_to_local_regex_when_provider_fails(monkeypatch):
    from app.services.fetcher import FetchResult
    from app.services.pipeline import extract_normalized

    monkeypatch.setattr(context_dev, "is_configured", lambda: True)

    def boom(*args, **kwargs):
        raise context_dev.ContextDevError("no credits")

    monkeypatch.setattr(context_dev, "scrape_product_price", boom)
    html = "<html><body>Only <b>$12.99</b> today</body></html>"
    result = FetchResult(
        final_url="https://shop.example.com/product",
        status_code=200,
        content=html.encode(),
        text=html,
        content_type="text/html",
        latency_ms=1,
    )

    assert extract_normalized(_price_monitor(), result)[0] == "USD 12.99"


def test_site_links_uses_url_map_when_no_sitemap_exists(monkeypatch):
    from app.services import sitemap

    def fail(*args, **kwargs):
        raise sitemap.SitemapError("no_sitemap", "none found")

    monkeypatch.setattr(sitemap, "discover_sitemap_urls", fail)
    monkeypatch.setattr(context_dev, "is_configured", lambda: True)
    monkeypatch.setattr(
        context_dev,
        "map_urls",
        lambda url, **kwargs: ["https://example.com/a", "https://example.com/b"],
    )

    text = sitemap.sitemap_monitor_text(
        "https://example.com", timeout_seconds=5, max_response_bytes=1000
    )

    assert text.splitlines() == ["https://example.com/a", "https://example.com/b"]


def test_site_links_still_errors_when_no_sitemap_and_no_key(monkeypatch):
    from app.services import sitemap

    def fail(*args, **kwargs):
        raise sitemap.SitemapError("no_sitemap", "none found")

    monkeypatch.setattr(sitemap, "discover_sitemap_urls", fail)
    monkeypatch.setattr(context_dev, "is_configured", lambda: False)

    with pytest.raises(sitemap.SitemapError):
        sitemap.sitemap_monitor_text(
            "https://example.com", timeout_seconds=5, max_response_bytes=1000
        )


def _png_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (4, 4), (120, 30, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _page_monitor() -> Monitor:
    from uuid import uuid4

    from app.models.entities import Monitor

    return Monitor(
        id=uuid4(),
        workspace_id=uuid4(),
        name="Page watch",
        url="https://example.com/page",
        mode="page_content",
        js_required=False,
    )


def test_page_content_falls_back_to_provider_markdown_on_bot_challenge(monkeypatch):
    from app.services import fetcher
    from app.workers import checks

    def blocked(*args, **kwargs):
        raise fetcher.FetchError("bot_challenge", "blocked")

    monkeypatch.setattr(checks, "fetch_url", blocked)
    monkeypatch.setattr(context_dev, "is_configured", lambda: True)
    monkeypatch.setattr(
        context_dev,
        "scrape_markdown",
        lambda url, **kwargs: "# Provider markdown\n\nFresh content.",
    )

    result = checks.fetch_page_with_provider_fallback(
        "https://example.com/page",
        monitor_mode="page_content",
        timeout_seconds=10,
        max_response_bytes=1000,
    )

    assert result.provider_markdown == "# Provider markdown\n\nFresh content."
    assert result.status_code == 200


def test_page_content_fallback_ignores_other_modes(monkeypatch):
    from app.services import fetcher
    from app.workers import checks

    def blocked(*args, **kwargs):
        raise fetcher.FetchError("bot_challenge", "blocked")

    monkeypatch.setattr(checks, "fetch_url", blocked)
    monkeypatch.setattr(context_dev, "is_configured", lambda: True)

    with pytest.raises(fetcher.FetchError):
        checks.fetch_page_with_provider_fallback(
            "https://example.com/feed",
            monitor_mode="rss_feed",
            timeout_seconds=10,
            max_response_bytes=1000,
        )


def test_pipeline_uses_provider_markdown_without_reconverting(monkeypatch):
    from app.services.fetcher import FetchResult
    from app.services.pipeline import extract_normalized

    result = FetchResult(
        final_url="https://example.com/page",
        status_code=200,
        content=b"",
        text="",
        content_type="text/html",
        latency_ms=1,
        provider_markdown="# Provider markdown\n\nFresh content.",
    )

    assert extract_normalized(_page_monitor(), result)[0] == "# Provider markdown\n\nFresh content."


def test_visual_capture_falls_back_to_provider_screenshot(monkeypatch):
    from PIL import Image

    from app.services import visual
    from app.services.fetcher import FetchError

    png = _png_bytes()

    def fail(*args, **kwargs):
        raise FetchError("internal_error", "Playwright unavailable")

    monkeypatch.setattr(visual, "capture_screenshot", fail)
    monkeypatch.setattr(context_dev, "is_configured", lambda: True)
    monkeypatch.setattr(context_dev, "scrape_screenshot_png", lambda url, **kwargs: png)

    capture = visual.capture_with_provider_fallback(
        "https://example.com/page", timeout_seconds=45, clip_selector=None
    )

    assert capture.png_bytes == png
    assert capture.sha256
    assert capture.phash
    with Image.open(__import__("io").BytesIO(capture.png_bytes)) as im:
        assert im.size == (4, 4)
