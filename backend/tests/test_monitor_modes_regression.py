"""Regression tests for the monitor-mode fixes.

Covers the defects found while reviewing the eight monitor modes
(``page_content``, ``site_links``, ``product_price``, ``list_items``,
``json_field``, ``rss_feed``, ``readme``, ``visual``) end to end:

1. ``rss_feed`` is a list-diff mode — its diff is item-level, not a
   double-prefixed unified diff.
2. ``rss_feed`` extraction produces item lists (RSS and Atom).
3. ``readme`` URLs are canonicalized and non-GitHub hosts are rejected.
4. ``visual`` on PATCH forces the browser worker + alert screenshots.
5. ``min_diff_chars`` no longer suppresses a same-length price/value change.
6. ``min_diff_chars`` for ``visual`` measures the perceptual aHash distance.
7. Content regex thresholds are not applied to ``visual`` snapshots.
8. ``json_field`` gains absolute value bounds.
9. The plain-HTTP mode set covers every mode that must never use Playwright.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.models.entities import (
    LIST_DIFF_MODES,
    MONITOR_MODES,
    PLAIN_HTTP_MODES,
    VALUE_MODES,
    Monitor,
    MonitorMode,
)
from app.schemas import MonitorCreate, MonitorUpdate
from app.services.conditional import should_alert
from app.services.extract import ExtractionError
from app.services.fetcher import FetchResult
from app.services.pipeline import extract_normalized
from app.services.readme import normalize_readme_url
from app.services.rss import extract_rss_items
from app.services.structured import diff_lists, items_from_normalized, list_to_normalized

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example feed</title>
    <item>
      <title>First post</title>
      <link>https://example.com/1</link>
      <guid>https://example.com/1</guid>
    </item>
    <item>
      <title>Second post</title>
      <link>https://example.com/2</link>
      <guid>https://example.com/2</guid>
    </item>
  </channel>
</rss>
"""

ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom one</title>
    <link href="https://example.com/a1"/>
    <id>tag:example.com,2026:1</id>
  </entry>
  <entry>
    <title>Atom two</title>
    <link href="https://example.com/a2"/>
    <id>tag:example.com,2026:2</id>
  </entry>
</feed>
"""


def _fetch(text: str, content_type: str = "application/rss+xml") -> FetchResult:
    return FetchResult(
        final_url="https://example.com/feed.xml",
        status_code=200,
        content=text.encode(),
        text=text,
        content_type=content_type,
        latency_ms=7,
    )


def _monitor(mode: str, **kw) -> Monitor:
    return Monitor(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="m",
        url="https://example.com/",
        mode=mode,
        **kw,
    )


# ---------------------------------------------------------------------------
# 1) rss_feed is a list-diff mode
# ---------------------------------------------------------------------------


def test_rss_feed_is_a_list_diff_mode() -> None:
    assert MonitorMode.RSS_FEED.value in LIST_DIFF_MODES
    # Every list-diff mode must also be a threshold-aware list mode, otherwise
    # the same mode would get item-level thresholds but a text diff.
    assert LIST_DIFF_MODES <= {"site_links", "list_items", "rss_feed", "security_scan"}


def test_rss_feed_diff_is_item_level_not_double_prefixed() -> None:
    before = list_to_normalized(["[Old post](https://example.com/1)"])
    after = list_to_normalized(
        ["[Old post](https://example.com/1)", "[New post](https://example.com/2)"]
    )
    diff = diff_lists(items_from_normalized(before), items_from_normalized(after)).as_text_diff()
    assert "+ [New post](https://example.com/2)" in diff
    # A unified diff over the stored "- item" lines would render "- + [New …]".
    assert "- + " not in diff
    assert "- - " not in diff


# ---------------------------------------------------------------------------
# 2) rss_feed extraction
# ---------------------------------------------------------------------------


def test_extract_rss_items_from_rss_feed() -> None:
    items = extract_rss_items(RSS_XML)
    assert items == [
        "[First post](https://example.com/1)",
        "[Second post](https://example.com/2)",
    ]


def test_extract_rss_items_from_atom_feed() -> None:
    items = extract_rss_items(ATOM_XML)
    assert items == [
        "[Atom one](https://example.com/a1)",
        "[Atom two](https://example.com/a2)",
    ]


def test_extract_rss_items_rejects_invalid_xml() -> None:
    with pytest.raises(ExtractionError):
        extract_rss_items("<not xml")


def test_rss_feed_pipeline_returns_item_list() -> None:
    normalized, items = extract_normalized(_monitor("rss_feed"), _fetch(RSS_XML))
    assert items == [
        "[First post](https://example.com/1)",
        "[Second post](https://example.com/2)",
    ]
    assert normalized == list_to_normalized(items)
    assert items_from_normalized(normalized) == items


# ---------------------------------------------------------------------------
# 3) readme URL canonicalization
# ---------------------------------------------------------------------------


def test_normalize_readme_url_from_shorthand() -> None:
    assert normalize_readme_url("vercel/next.js") == "https://github.com/vercel/next.js"


def test_normalize_readme_url_from_github_url() -> None:
    assert (
        normalize_readme_url("https://github.com/vercel/next.js")
        == "https://github.com/vercel/next.js"
    )
    assert (
        normalize_readme_url("https://www.github.com/vercel/next.js")
        == "https://github.com/vercel/next.js"
    )
    assert normalize_readme_url("github.com/vercel/next.js") == "https://github.com/vercel/next.js"


def test_normalize_readme_url_keeps_branch_hint() -> None:
    assert (
        normalize_readme_url("https://github.com/vercel/next.js/tree/canary")
        == "https://github.com/vercel/next.js/tree/canary"
    )


def test_normalize_readme_url_rejects_non_github_host() -> None:
    with pytest.raises(ExtractionError):
        normalize_readme_url("https://example.com/foo/bar")


def test_readme_monitor_requires_a_github_repo() -> None:
    with pytest.raises(ValidationError):
        MonitorCreate(name="Docs", url="https://example.com/foo/bar", mode="readme")
    m = MonitorCreate(name="Docs", url="vercel/next.js", mode="readme")
    assert m.mode == "readme"


# ---------------------------------------------------------------------------
# 4) visual on PATCH forces the browser worker + screenshots
# ---------------------------------------------------------------------------


def test_visual_update_forces_js_and_screenshots() -> None:
    u = MonitorUpdate(mode="visual")
    assert u.js_required is True
    assert u.screenshots_enabled is True


def test_visual_update_cannot_disable_js_or_screenshots() -> None:
    u = MonitorUpdate(mode="visual", js_required=False, screenshots_enabled=False)
    assert u.js_required is True
    assert u.screenshots_enabled is True


def test_visual_create_forces_js_and_screenshots() -> None:
    m = MonitorCreate(name="V", url="https://example.com/", mode="visual")
    assert m.js_required is True
    assert m.screenshots_enabled is True


# ---------------------------------------------------------------------------
# 5) min_diff_chars must not suppress a same-length value change
# ---------------------------------------------------------------------------


def _price_monitor(**cfg) -> Monitor:
    return _monitor("product_price", alert_config=cfg or None)


def test_min_diff_chars_does_not_suppress_same_length_price_change() -> None:
    """'USD 19.99' -> 'USD 24.99' has a zero length delta but is a real change."""
    ok, reason = should_alert(_price_monitor(min_diff_chars=1), "USD 19.99", "USD 24.99")
    assert ok is True, reason


def test_min_diff_chars_suppresses_a_tiny_text_change() -> None:
    ok, reason = should_alert(
        _monitor("page_content", alert_config={"min_diff_chars": 50}),
        "hello world",
        "hello there",
    )
    assert ok is False
    assert "chars" in (reason or "")


def test_min_diff_chars_suppresses_a_tiny_json_value_change() -> None:
    ok, _reason = should_alert(
        _monitor("json_field", alert_config={"min_diff_chars": 10}), "42.5", "43.5"
    )
    assert ok is False


# ---------------------------------------------------------------------------
# 6) visual min_diff_chars measures the perceptual distance
# ---------------------------------------------------------------------------


def _visual_text(ahash: str) -> str:
    return f"ahash:{ahash}\nsha256:deadbeef\nsize:1280x720"


def _visual_text_phash(phash: str, ahash: str = "0000000000000000") -> str:
    return f"ahash:{ahash}\nphash:{phash}\nsha256:deadbeef\nsize:1280x720"


def test_visual_min_diff_chars_uses_phash_distance_when_present() -> None:
    """Detection compares pHash; suppression must use the same digest.

    A real text edit moves the aHash by 0-2 bits, so a `min_diff_chars`
    threshold above that used to suppress every change the pHash had just
    flagged.
    """
    before = _visual_text_phash("00" * 32)
    after = _visual_text_phash("ff" * 8 + "00" * 24)
    ok, reason = should_alert(
        _monitor("visual", alert_config={"min_diff_chars": 16}), before, after
    )
    assert ok is True, reason

    # A genuine pHash match stays suppressed even if the aHashes differ.
    ok, _reason = should_alert(
        _monitor("visual", alert_config={"min_diff_chars": 16}),
        _visual_text_phash("00" * 32, ahash="ffffffffffffffff"),
        _visual_text_phash("00" * 32, ahash="0000000000000000"),
    )
    assert ok is False


def test_visual_min_diff_chars_uses_ahash_distance() -> None:
    # Two nearly identical hashes (distance 1) must not trip a threshold of 5.
    ok, reason = should_alert(
        _monitor("visual", alert_config={"min_diff_chars": 5}),
        _visual_text("0000000000000000"),
        _visual_text("0000000000000001"),
    )
    assert ok is False
    assert "chars" in (reason or "")

    # A large perceptual change must alert.
    ok, _reason = should_alert(
        _monitor("visual", alert_config={"min_diff_chars": 5}),
        _visual_text("0000000000000000"),
        _visual_text("ffffffffffffffff"),
    )
    assert ok is True


def test_visual_ignores_content_regex_thresholds() -> None:
    """A regex can never match a hash string — applying it would silence alerts."""
    ok, reason = should_alert(
        _monitor("visual", alert_config={"regex_must_match": "price"}),
        _visual_text("0000000000000000"),
        _visual_text("ffffffffffffffff"),
    )
    assert ok is True, reason


# ---------------------------------------------------------------------------
# 7) json_field absolute bounds
# ---------------------------------------------------------------------------


def test_json_field_value_bounds() -> None:
    # value_above: alert only when the new value is strictly above the bound.
    m = _monitor("json_field", alert_config={"value_above": 100})
    ok, reason = should_alert(m, "50", "80")
    assert ok is False
    assert "not above" in (reason or "")

    ok, _reason = should_alert(m, "50", "150")
    assert ok is True

    # value_below: alert only when the new value is strictly below the bound.
    m = _monitor("json_field", alert_config={"value_below": 10})
    ok, _reason = should_alert(m, "50", "50")
    assert ok is False
    ok, _reason = should_alert(m, "50", "5")
    assert ok is True


# ---------------------------------------------------------------------------
# 8) mode-set wiring
# ---------------------------------------------------------------------------


def test_plain_http_modes_cover_every_http_only_mode() -> None:
    assert PLAIN_HTTP_MODES == {"site_links", "rss_feed", "readme", "security_scan"}


def test_value_modes_cover_the_chartable_modes() -> None:
    assert VALUE_MODES == {"product_price", "json_field"}


def test_monitor_modes_unchanged() -> None:
    assert set(MONITOR_MODES) == {
        "page_content",
        "site_links",
        "product_price",
        "list_items",
        "json_field",
        "rss_feed",
        "readme",
        "visual",
        "security_scan",
    }


def test_extract_normalized_covers_all_nine_modes() -> None:
    # 1. page_content
    res, _ = extract_normalized(
        _monitor("page_content"),
        _fetch("<main><p>Page article text</p></main>", "text/html"),
    )
    assert "Page article text" in res

    # 2. site_links
    res, items = extract_normalized(
        _monitor("site_links"),
        _fetch("https://example.com/\nhttps://example.com/about", "text/plain"),
    )
    assert items == ["https://example.com/", "https://example.com/about"]
    assert "- https://example.com/" in res

    # 3. product_price
    res, _ = extract_normalized(
        _monitor("product_price", css_selector=".price"),
        _fetch("<div class='price'>$29.99</div>", "text/html"),
    )
    assert res == "USD 29.99"

    # 4. list_items
    res, items = extract_normalized(
        _monitor("list_items", css_selector="li"),
        _fetch(
            "<ul><li><a href='/p1'>Item 1</a></li><li><a href='/p2'>Item 2</a></li></ul>",
            "text/html",
        ),
    )
    assert items == ["[Item 1](/p1)", "[Item 2](/p2)"]
    assert "- [Item 1](/p1)" in res

    # 5. json_field
    res, _ = extract_normalized(
        _monitor("json_field", css_selector="$.data.rate"),
        _fetch('{"data": {"rate": 99.5}}', "application/json"),
    )
    assert res == "99.5"

    # 6. rss_feed
    res, items = extract_normalized(_monitor("rss_feed"), _fetch(RSS_XML))
    assert items is not None and len(items) == 2
    assert any("First post" in item for item in items)

    # 7. readme
    res, _ = extract_normalized(
        _monitor("readme"),
        _fetch("# Project Title\n\n- Feature 1\n- Feature 2", "text/markdown"),
    )
    assert "# Project Title" in res

    # 8. visual
    res, _ = extract_normalized(
        _monitor("visual"),
        _fetch("ahash:0123456789abcdef\nsha256:abc\nsize:1920x1080", "text/plain"),
    )
    assert "ahash:0123456789abcdef" in res

    # 9. security_scan
    res, items = extract_normalized(
        _monitor("security_scan"),
        _fetch("malicious=false\ncategories=\ntags=\ntech=nginx", "text/plain"),
    )
    assert items == ["malicious=false", "categories=", "tags=", "tech=nginx"]
    assert "- malicious=false" in res
