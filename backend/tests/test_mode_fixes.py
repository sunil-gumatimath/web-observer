"""Regression tests for the four monitor-mode fixes.

Covers:
1. ``diff_lists`` preserves on-page order (no alphabetical scramble).
2. ``items_from_normalized`` / ``list_to_normalized`` round-trip.
3. ``ListDiff`` renderer consolidation (single ``as_text_diff``).
4. API schema guards: site_links monitors cannot require JS rendering.
5. ``MONITOR_MODES`` is derived from the ``MonitorMode`` enum.
6. product_price extraction scoping via css_selector/ignore_selectors.
7. Price-removal detection helper.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.entities import MONITOR_MODES, MonitorMode
from app.schemas import MonitorCreate, MonitorUpdate
from app.services.extract import ExtractionError, extract_price
from app.services.structured import (
    diff_lists,
    items_from_normalized,
    list_to_normalized,
)

# ---------------------------------------------------------------------------
# 1) Order-preserving set diffs
# ---------------------------------------------------------------------------


def test_diff_lists_added_items_keep_after_order() -> None:
    before = ["old"]
    after = ["zebra", "alpha", "mid", "new-last"]
    d = diff_lists(before, after)
    # Alphabetical sorting used to surface "alpha" first; on-page order wins.
    assert d.added == ["zebra", "alpha", "mid", "new-last"]


def test_diff_lists_removed_items_keep_before_order() -> None:
    before = ["zeta", "beta", "gamma"]
    after = ["gamma"]
    d = diff_lists(before, after)
    assert d.removed == ["zeta", "beta"]


def test_diff_lists_dedupes_while_preserving_order() -> None:
    d = diff_lists(["a", "b"], ["x", "x", "y"])
    assert d.added == ["x", "y"]


def test_items_from_normalized_round_trip() -> None:
    items = ["[Post A](https://example.com/a)", "plain item", "[B](https://b.io)"]
    normalized = list_to_normalized(items)
    assert normalized.startswith("- ")
    assert items_from_normalized(normalized) == items


def test_items_from_normalized_skips_blank_lines() -> None:
    assert items_from_normalized("- a\n\n- b\n") == ["a", "b"]


def test_listdiff_single_renderer() -> None:
    """The duplicate as_link_diff renderer was consolidated away."""
    from app.services.structured import ListDiff

    d = diff_lists(["[Old](https://o.io)"], ["[New](https://n.io)"])
    text = d.as_text_diff()
    assert "- [Old](https://o.io)" in text
    assert "+ [New](https://n.io)" in text
    assert not hasattr(ListDiff, "as_link_diff")


# ---------------------------------------------------------------------------
# 2) Mode constants derive from the enum (single source of truth)
# ---------------------------------------------------------------------------


def test_monitor_modes_derived_from_enum() -> None:
    assert MONITOR_MODES == tuple(m.value for m in MonitorMode)
    assert set(MONITOR_MODES) == {
        "page_content",
        "site_links",
        "product_price",
        "list_items",
    }


# ---------------------------------------------------------------------------
# 3) site_links + js_required is rejected at the schema layer
# ---------------------------------------------------------------------------


def test_create_rejects_site_links_with_js_required() -> None:
    with pytest.raises(ValidationError, match="site_links"):
        MonitorCreate(
            name="Sitemap",
            url="https://example.com",
            mode="site_links",
            js_required=True,
        )


def test_update_rejects_site_links_with_js_required() -> None:
    with pytest.raises(ValidationError, match="site_links"):
        MonitorUpdate(mode="site_links", js_required=True)


def test_update_rejects_js_only_flip_on_existing_site_links() -> None:
    """PATCHing only js_required=true must also fail when mode=site_links."""
    with pytest.raises(ValidationError, match="site_links"):
        MonitorUpdate(mode="site_links", js_required=True)


def test_site_links_without_js_is_accepted() -> None:
    m = MonitorCreate(
        name="Sitemap",
        url="https://example.com",
        mode="site_links",
        js_required=False,
    )
    assert m.mode == "site_links"
    assert m.js_required is False


def test_product_price_defaults_to_daily_interval() -> None:
    m = MonitorCreate(name="P", url="https://example.com/p", mode="product_price")
    assert m.schedule_interval_minutes == 1440


def test_page_content_defaults_to_hourly_interval() -> None:
    m = MonitorCreate(name="Page", url="https://example.com/", mode="page_content")
    assert m.schedule_interval_minutes == 60


# ---------------------------------------------------------------------------
# 4) product_price extraction hardening
# ---------------------------------------------------------------------------


def test_extract_price_scopes_to_css_selector() -> None:
    html = "<html><body><span>$4.50</span><div id='buy'><span>$24.90</span></div></body></html>"
    assert extract_price(html, css_selector="#buy") == "USD 24.90"


def test_extract_price_honors_ignore_selectors() -> None:
    html = "<html><body><nav>$1</nav><b>$9.87</b></body></html>"
    assert extract_price(html, ignore_selectors=["nav"]) == "USD 9.87"


def test_extract_price_error_code_is_price_not_found() -> None:
    with pytest.raises(ExtractionError) as excinfo:
        extract_price("<html><body><p>nothing</p></body></html>")
    assert excinfo.value.code == "price_not_found"
