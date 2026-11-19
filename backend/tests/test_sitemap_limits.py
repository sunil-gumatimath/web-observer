"""site_links must honour the monitor's max_response_bytes on every fetch."""

from __future__ import annotations

from app.services import sitemap

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a</loc></url>
</urlset>
"""


def test_sitemap_monitor_text_uses_per_monitor_byte_limit(monkeypatch):
    seen: list[int] = []

    def fake_fetch(url, *, timeout_seconds, max_bytes):
        seen.append(max_bytes)
        return SITEMAP

    monkeypatch.setattr(sitemap, "_fetch_text", fake_fetch)
    out = sitemap.sitemap_monitor_text(
        "https://example.com/", timeout_seconds=7, max_response_bytes=9_000_000
    )

    assert out == "https://example.com/a"
    assert seen and all(limit == 9_000_000 for limit in seen)
