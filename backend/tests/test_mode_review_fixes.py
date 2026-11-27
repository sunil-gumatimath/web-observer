"""Regression tests for the monitor-mode review findings.

Covers:
1. A configured sitemap path (``/blog/sitemap.xml``) is probed before the
   well-known root locations instead of being silently dropped.
2. An emptied sitemap reports ``sitemap_empty``; unreachable sitemaps (or an
   index whose children all fail) stay ``no_sitemap``. The Context.dev map
   fallback never hides an emptied sitemap.
3. An RSS/Atom feed that parses but publishes no entries raises ``no_items``
   and counts as a list removal once a baseline exists.
4. A visual clip region that disappears is reported as a change, not a
   permanently failing run.
5. ``js_required`` is rejected for every ``PLAIN_HTTP_MODES`` entry at the
   schema layer (driven by the shared set, not a hand-written list).
6. ``html_meta`` reserves room for the JSON-LD and script groups, so a busy
   head cannot evict them from the total cap.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.models import Monitor
from app.models.entities import EMPTY_LIST_IS_CHANGE_MODES, PLAIN_HTTP_MODES, MonitorMode
from app.schemas import MonitorCreate, MonitorUpdate
from app.services import html_meta, pipeline, sitemap
from app.services.extract import ExtractionError
from app.services.rss import extract_rss_items
from app.services.sitemap import SitemapError, discover_sitemap_urls
from app.services.visual import REGION_MISSING_MARKER

MARK = REGION_MISSING_MARKER

BLOG_URLSET = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/blog/a</loc></url>
  <url><loc>https://example.com/blog/b</loc></url>
</urlset>"""

EMPTY_URLSET = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-blog.xml</loc></sitemap>
</sitemapindex>"""

VISUAL_HASHES = "ahash:0123456789abcdef\nphash:00\nsha256:abc\nsize:1280x720"


class _Baseline:
    """Session double whose run lookups always find a succeeded run."""

    def scalar(self, _query):  # noqa: ANN001, ANN202
        return uuid.uuid4()


class _NoBaseline:
    """Session double whose run lookups find nothing."""

    def scalar(self, _query):  # noqa: ANN001, ANN202
        return None


def _monitor(mode: str, **kw) -> Monitor:  # noqa: ANN003
    return Monitor(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="m",
        url="https://example.com/",
        mode=mode,
        **kw,
    )


# ---------------------------------------------------------------------------
# 1) Configured sitemap path
# ---------------------------------------------------------------------------


def test_local_urls_tries_the_configured_path_first() -> None:
    assert sitemap._local_urls("https://example.com/blog/sitemap.xml") == [
        "https://example.com/blog/sitemap.xml",
        "https://example.com/sitemap.xml",
        "https://example.com/sitemap_index.xml",
    ]


def test_local_urls_keeps_root_urls_for_a_site_url() -> None:
    assert sitemap._local_urls("https://example.com/") == [
        "https://example.com/sitemap.xml",
        "https://example.com/sitemap_index.xml",
    ]


def test_local_urls_does_not_duplicate_the_configured_root_sitemap() -> None:
    assert sitemap._local_urls("https://example.com/sitemap.xml") == [
        "https://example.com/sitemap.xml",
        "https://example.com/sitemap_index.xml",
    ]


def test_discover_probes_the_configured_sitemap_path_first(monkeypatch) -> None:  # noqa: ANN001
    fetched: list[str] = []

    def fake_fetch(url, *, timeout_seconds, max_bytes):  # noqa: ANN001, ANN202
        fetched.append(url)
        if url == "https://example.com/blog/sitemap.xml":
            return BLOG_URLSET
        raise SitemapError("http_error", "HTTP 404")

    monkeypatch.setattr(sitemap, "_fetch_text", fake_fetch)

    urls = discover_sitemap_urls(
        "https://example.com/blog/sitemap.xml",
        timeout_seconds=5,
    )

    assert fetched[0] == "https://example.com/blog/sitemap.xml"
    assert urls == ["https://example.com/blog/a", "https://example.com/blog/b"]


# ---------------------------------------------------------------------------
# 2) Emptied vs unreachable sitemap
# ---------------------------------------------------------------------------


def test_discover_reports_an_emptied_sitemap(monkeypatch) -> None:  # noqa: ANN001
    def fake_fetch(url, *, timeout_seconds, max_bytes):  # noqa: ANN001, ANN202
        if url == "https://example.com/sitemap.xml":
            return EMPTY_URLSET
        raise SitemapError("http_error", "HTTP 404")

    monkeypatch.setattr(sitemap, "_fetch_text", fake_fetch)

    with pytest.raises(SitemapError) as exc:
        discover_sitemap_urls("https://example.com/", timeout_seconds=5)
    assert exc.value.code == "sitemap_empty"


def test_unreachable_child_sitemaps_are_not_reported_as_empty(monkeypatch) -> None:  # noqa: ANN001
    def fake_fetch(url, *, timeout_seconds, max_bytes):  # noqa: ANN001, ANN202
        if url == "https://example.com/sitemap.xml":
            return SITEMAP_INDEX
        raise SitemapError("http_error", "HTTP 404")

    monkeypatch.setattr(sitemap, "_fetch_text", fake_fetch)

    with pytest.raises(SitemapError) as exc:
        discover_sitemap_urls("https://example.com/", timeout_seconds=5)
    assert exc.value.code == "no_sitemap"


def test_sitemap_monitor_urls_does_not_map_an_emptied_sitemap(monkeypatch) -> None:  # noqa: ANN001
    """The provider fallback would hide "all URLs removed"."""

    def fake_discover(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        raise SitemapError("sitemap_empty", "no pages")

    def fail_map(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("provider map must not be used for an emptied sitemap")

    monkeypatch.setattr(sitemap, "discover_sitemap_urls", fake_discover)
    monkeypatch.setattr(sitemap.context_dev, "is_configured", lambda: True)
    monkeypatch.setattr(sitemap.context_dev, "map_urls", fail_map)

    with pytest.raises(SitemapError) as exc:
        sitemap.sitemap_monitor_urls("https://example.com/")
    assert exc.value.code == "sitemap_empty"


# ---------------------------------------------------------------------------
# 3) Emptied feed / list after a baseline
# ---------------------------------------------------------------------------


def test_empty_feed_raises_no_items_code() -> None:
    with pytest.raises(ExtractionError) as exc:
        extract_rss_items("<rss><channel><title>Empty</title></channel></rss>")
    assert exc.value.code == "no_items"


def test_invalid_feed_xml_still_fails_as_extraction() -> None:
    with pytest.raises(ExtractionError) as exc:
        extract_rss_items("<not-xml")
    assert exc.value.code == "extraction_failed"


def test_empty_list_modes_are_the_readable_ones() -> None:
    assert EMPTY_LIST_IS_CHANGE_MODES == {"list_items", "site_links", "rss_feed"}


@pytest.mark.parametrize("mode", sorted(EMPTY_LIST_IS_CHANGE_MODES))
def test_empty_list_counts_as_removal_after_a_baseline(mode: str) -> None:
    code = "no_items" if mode == MonitorMode.RSS_FEED.value else "selector_not_found"
    assert pipeline._is_list_removal(_Baseline(), _monitor(mode), code) is True


@pytest.mark.parametrize("mode", sorted(EMPTY_LIST_IS_CHANGE_MODES))
def test_empty_list_without_a_baseline_stays_a_failure(mode: str) -> None:
    code = "no_items" if mode == MonitorMode.RSS_FEED.value else "selector_not_found"
    assert pipeline._is_list_removal(_NoBaseline(), _monitor(mode), code) is False


def test_empty_html_meta_is_not_a_removal() -> None:
    assert pipeline._is_list_removal(_Baseline(), _monitor("html_meta"), "no_items") is False


def test_unrelated_error_code_is_not_a_removal() -> None:
    assert pipeline._is_list_removal(_Baseline(), _monitor("rss_feed"), "http_error") is False


# ---------------------------------------------------------------------------
# 4) Visual clip region gone
# ---------------------------------------------------------------------------


def test_visual_region_missing_is_a_change() -> None:
    result = pipeline._visual_region_change(VISUAL_HASHES, MARK, "#hero")
    assert result is not None
    summary, diff = result
    assert "watched region missing" in summary
    assert "#hero" in diff


def test_visual_region_restored_is_a_change() -> None:
    result = pipeline._visual_region_change(MARK, VISUAL_HASHES, "#hero")
    assert result is not None
    summary, diff = result
    assert "watched region restored" in summary
    assert "ahash:0123456789abcdef" in diff


def test_visual_region_change_returns_none_for_regular_captures() -> None:
    assert pipeline._visual_region_change("ahash:aa", "ahash:bb", "#hero") is None


def test_repeated_missing_region_is_unchanged() -> None:
    """The marker digest is stable, so a still-missing region settles."""
    assert pipeline._visual_region_change(MARK, MARK, "#hero") is None


# ---------------------------------------------------------------------------
# 5) js_required rejection is driven by PLAIN_HTTP_MODES
# ---------------------------------------------------------------------------


def _url_for_mode(mode: str) -> str:
    if mode == MonitorMode.README.value:
        return "vercel/next.js"
    return "https://example.com/"


@pytest.mark.parametrize("mode", sorted(PLAIN_HTTP_MODES))
def test_create_rejects_js_for_every_plain_http_mode(mode: str) -> None:
    with pytest.raises(ValidationError, match=mode):
        MonitorCreate(name="M", url=_url_for_mode(mode), mode=mode, js_required=True)


@pytest.mark.parametrize("mode", sorted(PLAIN_HTTP_MODES))
def test_update_rejects_js_for_every_plain_http_mode(mode: str) -> None:
    with pytest.raises(ValidationError, match=mode):
        MonitorUpdate(mode=mode, js_required=True)


def test_browser_modes_still_accept_js_required() -> None:
    m = MonitorCreate(
        name="Page",
        url="https://example.com/",
        mode="page_content",
        js_required=True,
    )
    assert m.js_required is True


# ---------------------------------------------------------------------------
# 6) html_meta total cap cannot evict script facts
# ---------------------------------------------------------------------------


def _busy_page(script_count: int = 5) -> str:
    parts = ["<html lang='en'><head><title>Busy</title>"]
    for i in range(html_meta.MAX_ALTERNATE_LINKS):
        parts.append(f'<link rel="alternate" hreflang="l{i}" href="https://example.com/l{i}">')
    for i in range(html_meta.MAX_CANONICAL_LINKS):
        parts.append(f'<link rel="canonical" href="https://example.com/c{i}">')
    parts.append('<script type="application/ld+json">{"@type": "Article"}</script>')
    for i in range(script_count):
        parts.append(f'<script src="https://cdn.example.com/{i}.js"></script>')
    parts.append("</head><body></body></html>")
    return "".join(parts)


def test_busy_head_does_not_evict_script_or_jsonld_facts() -> None:
    items = html_meta.extract_html_meta_items(_busy_page(), "https://example.com/")

    assert any(item.startswith("script src: ") for item in items)
    assert any(item.startswith("jsonld type: ") for item in items)
    assert any(item.startswith("title: ") for item in items)
    assert len(items) <= html_meta.MAX_TOTAL_ITEMS
