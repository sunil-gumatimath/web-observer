"""Tests for the html_meta monitor mode."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.models.entities import (
    LIST_DIFF_MODES,
    MONITOR_MODES,
    PLAIN_HTTP_MODES,
    Monitor,
    MonitorMode,
)
from app.schemas import MonitorCreate, MonitorUpdate
from app.services.fetcher import FetchResult
from app.services.html_meta import extract_html_meta_items
from app.services.pipeline import extract_normalized
from app.services.structured import diff_lists, items_from_normalized

HTML = """<!doctype html>
<html lang="en">
<head>
  <title>Example Store</title>
  <meta charset="utf-8">
  <meta name="description" content="An example store for tests">
  <meta name="robots" content="index, follow">
  <meta property="og:title" content="Example Store">
  <meta property="og:image" content="/og.png?v=123">
  <link rel="canonical" href="https://shop.example.com/store?utm=newsletter">
  <link rel="alternate" hreflang="fr" href="/fr">
  <script type="application/ld+json">{"@type": "Organization", "name": "Example"}</script>
  <script src="/static/app.js?v=42"></script>
  <script src="https://analytics.example.com/track.js?token=abc"></script>
</head>
<body>Visible content that page_content would track.</body>
</html>
"""


def _fetch(html: str = HTML) -> FetchResult:
    return FetchResult(
        final_url="https://shop.example.com/store",
        status_code=200,
        content=html.encode(),
        text=html,
        content_type="text/html; charset=utf-8",
        latency_ms=5,
    )


def _monitor() -> Monitor:
    return Monitor(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="Example",
        url="https://shop.example.com/store",
        mode=MonitorMode.HTML_META.value,
        js_required=False,
    )


def test_html_meta_is_registered_as_plain_http_list_mode() -> None:
    assert "html_meta" in MONITOR_MODES
    assert "html_meta" in PLAIN_HTTP_MODES
    assert "html_meta" in LIST_DIFF_MODES


def test_extract_html_meta_items_collects_stable_facts() -> None:
    items = extract_html_meta_items(HTML, "https://shop.example.com/store")
    assert "document: https://shop.example.com/store" in items
    assert "title: Example Store" in items
    assert "html lang: en" in items
    assert "meta description: An example store for tests" in items
    assert "meta robots: index, follow" in items
    assert "meta og:title: Example Store" in items
    assert "canonical: https://shop.example.com/store" in items
    assert "alternate fr: https://shop.example.com/fr" in items
    assert "jsonld type: Organization" in items
    assert "script src: https://shop.example.com/static/app.js" in items
    assert "script src: https://analytics.example.com/track.js" in items
    # Volatile query strings are stripped so ad/analytics tokens do not fire alerts.
    assert "?token=" not in " ".join(items)
    # Visible body text belongs to page_content, not to this mode.
    assert not any("Visible content" in item for item in items)


def test_preview_image_meta_keeps_meaningful_query_but_nav_urls_strip_it() -> None:
    """A preview-image swap that only differs by query is a real change.

    ``og:image``/``twitter:image`` point at CDN URLs whose query carries the
    image's identity (resize/format params, signed-URL tokens), so the query
    survives normalization. Navigation URLs (``og:url``, ``canonical``) and
    script src keep stripping it — there the query is genuine cache-busting
    noise (utm/token/version) that must never fire an alert.
    """
    items = extract_html_meta_items(HTML, "https://shop.example.com/store")
    # og:image keeps its resize/version query…
    assert "meta og:image: https://shop.example.com/og.png?v=123" in items
    # …while og:url / canonical / script src still drop theirs.
    assert "canonical: https://shop.example.com/store" in items
    assert "script src: https://shop.example.com/static/app.js" in items
    assert "script src: https://analytics.example.com/track.js" in items

    twitter = HTML.replace(
        '<meta property="og:image" content="/og.png?v=123">',
        '<meta name="twitter:image" content="https://cdn.example.com/hero.jpg?w=640&token=abc">',
    )
    t_items = extract_html_meta_items(twitter, "https://shop.example.com/store")
    assert "meta twitter:image: https://cdn.example.com/hero.jpg?w=640&token=abc" in t_items
    # The token on a *navigation* URL would still be stripped:
    assert "?token=" not in " ".join(items)


def test_extract_html_meta_items_ignores_unlisted_meta_tags() -> None:
    html = '<html><head><title>T</title><meta name="csrf-token" content="abc123"></head></html>'
    items = extract_html_meta_items(html, "https://example.com/")
    assert not any("csrf-token" in item for item in items)


def test_pipeline_extract_normalized_returns_item_list() -> None:
    text, items = extract_normalized(_monitor(), _fetch())
    assert items is not None
    assert "title: Example Store" in items
    assert "title: Example Store" in text
    assert text.startswith("- ")


def test_changed_meta_is_an_item_level_diff() -> None:
    before = extract_html_meta_items(HTML, "https://shop.example.com/store")
    changed = HTML.replace(
        '<meta name="description" content="An example store for tests">',
        '<meta name="description" content="A newer description">',
    )
    after = extract_html_meta_items(changed, "https://shop.example.com/store")
    diff = diff_lists(before, after).as_text_diff()
    assert "+ meta description: A newer description" in diff
    assert "- meta description: An example store for tests" in diff
    # Item diffs never render the double-prefixed "- +" of a text diff.
    assert "- + " not in diff
    assert items_from_normalized("\n".join(after)) == after


@pytest.mark.parametrize("model", [MonitorCreate, MonitorUpdate])
def test_html_meta_rejects_js_required(model) -> None:
    with pytest.raises(ValidationError, match="html_meta"):
        model(
            name="Example",
            url="https://example.com/",
            mode="html_meta",
            js_required=True,
        )


def test_extract_html_meta_items_reads_standard_charset_attribute() -> None:
    html = '<html><head><meta charset="utf-8"><title>T</title></head></html>'
    items = extract_html_meta_items(html, "https://example.com/")
    assert "meta charset: utf-8" in items
    named = '<html><head><meta name="charset" content="utf-8"></head></html>'
    assert "meta charset: utf-8" in extract_html_meta_items(named, "https://example.com/")


def test_extract_html_meta_items_caps_alternates_and_keeps_key_facts() -> None:
    alternates = "".join(
        f'<link rel="alternate" hreflang="x{i}" href="/page{i}">' for i in range(130)
    )
    scripts = "".join(f'<script src="/static/s{i}.js"></script>' for i in range(50))
    html = f"<html><head><title>T</title>{alternates}{scripts}</head></html>"
    items = extract_html_meta_items(html, "https://example.com/")
    assert "document: https://example.com/" in items
    assert "title: T" in items
    assert any(item.startswith("script src:") for item in items)
    assert sum(item.startswith("alternate ") for item in items) <= 40
    assert len(items) <= 120


def test_extract_html_meta_items_survives_deeply_nested_jsonld() -> None:
    blob = '{"@type":"X","a":' * 2000 + "1" + "}" * 2000
    html = f'<html><head><script type="application/ld+json">{blob}</script></head></html>'
    items = extract_html_meta_items(html, "https://example.com/")
    assert "document: https://example.com/" in items
