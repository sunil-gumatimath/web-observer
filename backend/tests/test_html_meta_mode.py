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
from app.services.fetcher import FetchResult, bot_challenge_message
from app.services.ai_summary import _system_prompt
from app.services.html_meta import extract_html_meta_items
from app.services.pipeline import extract_normalized
from app.services.structured import (
    PREVIEW_TRUNCATION_MARKER,
    diff_lists,
    items_from_normalized,
    strip_preview_marker,
)

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
    assert len(items) <= 150


def test_extract_html_meta_items_survives_deeply_nested_jsonld() -> None:
    blob = '{"@type":"X","a":' * 2000 + "1" + "}" * 2000
    html = f'<html><head><script type="application/ld+json">{blob}</script></head></html>'
    items = extract_html_meta_items(html, "https://example.com/")
    assert "document: https://example.com/" in items


def test_duplicate_meta_prefers_spec_correct_source_in_either_order() -> None:
    url = "https://example.com/p"
    fallback_first = (
        '<meta name="og:title" content="Fallback">'
        '<meta property="og:title" content="Real A">'
    )
    spec_first = (
        '<meta property="og:title" content="Real A">'
        '<meta name="og:title" content="Fallback">'
    )
    for html in (fallback_first, spec_first):
        before = extract_html_meta_items(html, url)
        after = extract_html_meta_items(html.replace("Real A", "Real B"), url)
        assert "meta og:title: Real A" in before
        assert "meta og:title: Real B" in after
        assert not any("Fallback" in item for item in before + after)


def test_charset_is_case_normalized_and_attribute_wins() -> None:
    url = "https://example.com/p"
    assert "meta charset: utf-8" in extract_html_meta_items('<meta charset="UTF-8">', url)
    assert "meta charset: utf-8" in extract_html_meta_items(
        '<meta charset="utf-8" content="text/html; charset=ISO-8859-1">', url
    )
    assert "meta charset: utf-8" in extract_html_meta_items(
        '<meta name="charset" content="utf-8">', url
    )


def test_url_facts_are_length_capped() -> None:
    html = '<script src="data:text/javascript;base64,' + "A" * 100000 + '"></script>'
    items = extract_html_meta_items(html, "https://example.com/p")
    # The URL value is capped at MAX_VALUE_CHARS; the "script src: " label
    # adds its own prefix on top of that.
    assert max(len(item.split(": ", 1)[1]) for item in items if ": " in item) <= 300


def test_preview_marker_is_not_parsed_as_a_watched_item() -> None:
    text = "- meta robots: index\n" + PREVIEW_TRUNCATION_MARKER
    assert items_from_normalized(strip_preview_marker(text)) == ["meta robots: index"]


def test_ai_summary_has_html_meta_mode_hint() -> None:
    assert "Mode=html_meta" in _system_prompt(mode="html_meta", has_watch=False)


def test_html_meta_diff_uses_full_fact_identity() -> None:
    """A meta value ending in a markdown link must not collide with another fact."""
    before = [
        "meta description: [A](https://x/d)",
        "meta og:description: [B](https://x/d)",
    ]
    after = [
        "meta description: [Z](https://x/d)",
        "meta og:description: [B](https://x/d)",
    ]
    diff = diff_lists(before, after, mode="html_meta")
    assert diff.added == ["meta description: [Z](https://x/d)"]
    assert diff.removed == ["meta description: [A](https://x/d)"]
    assert diff.modified == []


def test_fact_caps_do_not_evict_script_or_meta_facts() -> None:
    metas = "".join(
        f'<meta name="{key}" content="v{i}">'
        for i, key in enumerate(
            [
                "author", "application-name", "color-scheme", "description",
                "generator", "keywords", "robots", "theme-color", "viewport",
            ]
        )
    )
    alternates = "".join(
        f'<link rel="alternate" hreflang="x{i}" href="/a{i}">' for i in range(130)
    )
    canonicals = "".join(
        f'<link rel="canonical" href="https://example.com/c{i}">' for i in range(10)
    )
    jsonld = (
        '<script type="application/ld+json">{"@graph":['
        + ",".join(f'{{"@type":"T{i}"}}' for i in range(30))
        + ']}</script>'
    )
    scripts = "".join(f'<script src="/s{i}.js"></script>' for i in range(50))
    items = extract_html_meta_items(
        f"<html><head><title>T</title>{metas}{alternates}{canonicals}{jsonld}{scripts}</head></html>",
        "https://example.com/",
    )
    assert len(items) <= 150
    assert "title: T" in items
    assert sum(item.startswith("script src:") for item in items) == 50
    assert sum(item.startswith("alternate ") for item in items) <= 40
    assert sum(item.startswith("canonical:") for item in items) <= 5
    assert sum(item.startswith("jsonld type:") for item in items) == 20
    assert any(item.startswith("meta description:") for item in items)


def test_bot_challenge_message_is_mode_aware() -> None:
    plain = bot_challenge_message("https://example.com", "Cloudflare challenge", "html_meta")
    assert "plain HTTP" in plain
    assert "JavaScript rendering" not in plain
    browser = bot_challenge_message("https://example.com", "Cloudflare challenge", "page_content")
    assert "JavaScript rendering" in browser
