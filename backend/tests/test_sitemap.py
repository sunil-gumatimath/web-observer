"""Tests for sitemap discovery and sitemap-driven monitor creation."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Monitor, Workspace
from app.services.bulk_import import import_monitors
from app.services.sitemap import (
    SitemapError,
    discover_sitemap_urls,
    name_from_url,
    parse_sitemap_xml,
)
from app.models.entities import RunStatus


SAMPLE_URLSET = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/</loc></url>
  <url><loc>https://example.com/about</loc></url>
  <url><loc>https://example.com/pricing</loc></url>
</urlset>"""

SAMPLE_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-products.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-blog.xml</loc></sitemap>
</sitemapindex>"""

SAMPLE_URLSET_PRODUCTS = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/product/a</loc></url>
  <url><loc>https://example.com/product/b</loc></url>
</urlset>"""

SAMPLE_URLSET_BLOG = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/blog/a</loc></url>
  <url><loc>https://example.com/blog/b</loc></url>
  <url><loc>https://example.com/blog/c</loc></url>
</urlset>"""


def test_parse_urlset() -> None:
    urls = parse_sitemap_xml(SAMPLE_URLSET)
    assert urls == [
        "https://example.com/",
        "https://example.com/about",
        "https://example.com/pricing",
    ]


def test_parse_sitemapindex_returns_child_locs() -> None:
    urls = parse_sitemap_xml(SAMPLE_INDEX)
    assert urls == [
        "https://example.com/sitemap-products.xml",
        "https://example.com/sitemap-blog.xml",
    ]


def test_parse_invalid_xml_raises() -> None:
    with pytest.raises(SitemapError):
        parse_sitemap_xml("<not-xml")


def test_parse_empty_sitemap_returns_empty() -> None:
    assert parse_sitemap_xml("<urlset></urlset>") == []


def test_name_from_url() -> None:
    assert name_from_url("https://example.com/") == "example.com"
    assert name_from_url("https://example.com/pricing") == "example.com · pricing"
    assert name_from_url("https://example.com/blog/my-post") == "example.com · my-post"


def test_discover_recurses_sitemapindex(monkeypatch: pytest.MonkeyPatch) -> None:
    # Map of URL -> XML body returned by the fetcher.
    sitemaps = {
        "https://example.com/sitemap.xml": SAMPLE_INDEX,
        "https://example.com/sitemap-products.xml": SAMPLE_URLSET_PRODUCTS,
        "https://example.com/sitemap-blog.xml": SAMPLE_URLSET_BLOG,
    }

    def fake_fetch_text(url, *, timeout_seconds, max_bytes):  # type: ignore[no-untyped-def]
        if url in sitemaps:
            return sitemaps[url]
        raise SitemapError("fetch_failed", f"no fixture for {url}")

    monkeypatch.setattr("app.services.sitemap._fetch_text", fake_fetch_text)

    urls = discover_sitemap_urls(
        "https://example.com/",
        timeout_seconds=5,
        max_urls=500,
    )
    # The two child sitemaps contribute 2 + 3 distinct page URLs.
    assert len(urls) == 5
    assert "https://example.com/product/a" in urls
    assert "https://example.com/blog/c" in urls
    assert all(u.startswith("https://example.com/") for u in urls)


def test_discover_no_sitemap_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch_text(url, *, timeout_seconds, max_bytes):  # type: ignore[no-untyped-def]
        raise SitemapError("fetch_failed", "blocked")

    monkeypatch.setattr("app.services.sitemap._fetch_text", fake_fetch_text)

    with pytest.raises(SitemapError) as exc:
        discover_sitemap_urls("https://example.com/", timeout_seconds=5)
    assert exc.value.code == "no_sitemap"


def test_import_from_sitemap_creates_monitors(db_session) -> None:  # noqa: ANN001
    ws = Workspace(name="sitemap-test", plan="free")
    db_session.add(ws)
    db_session.commit()

    urls = [
        "https://example.com/",
        "https://example.com/about",
        "https://example.com/pricing",
    ]
    rows = [
        {"name": name_from_url(u), "url": u, "mode": "whole_page",
         "schedule_interval_minutes": 60, "js_required": False}
        for u in urls
    ]
    result = import_monitors(db_session, ws, rows)
    db_session.commit()

    assert len(result.created) == 3

    monitors = db_session.scalars(select(Monitor).where(Monitor.workspace_id == ws.id)).all()
    assert len(monitors) == 3
    # New monitors must be scheduled (next_run_at set, enabled) so the
    # scheduler picks them up automatically.
    for m in monitors:
        assert m.enabled is True
        assert m.next_run_at is not None


def test_import_from_sitemap_dedupes(db_session) -> None:  # noqa: ANN001
    ws = Workspace(name="sitemap-dedup", plan="free")
    db_session.add(ws)
    db_session.commit()

    rows = [
        {"name": "A", "url": "https://example.com/x", "mode": "whole_page",
         "schedule_interval_minutes": 60, "js_required": False},
        {"name": "A2", "url": "https://example.com/x", "mode": "whole_page",
         "schedule_interval_minutes": 60, "js_required": False},
    ]
    result = import_monitors(db_session, ws, rows)
    db_session.commit()
    # Second row is a duplicate URL and should be skipped, not created.
    assert len(result.created) == 1
    assert len(result.skipped) == 1
