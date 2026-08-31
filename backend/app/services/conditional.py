"""Conditional alert evaluation for monitors."""

from __future__ import annotations

import re
from typing import Any

from app.services.structured import diff_lists, items_from_normalized


def _parse_price_value(text: str) -> float | None:
    """Extract numeric value from normalized price like 'USD 19.99'."""
    import re as _re

    m = _re.search(r"([0-9][0-9,]*\.?[0-9]*)", text.replace(",", ""))
    # Better: find last number
    nums = _re.findall(r"[0-9]+\.?[0-9]*", text.replace(",", ""))
    if not nums:
        return None
    try:
        return float(nums[-1].replace(",", ""))
    except ValueError:
        return None


def should_alert(
    monitor: Any,
    prev_text: str,
    new_text: str,
    items_before: list[str] | None = None,
    items_after: list[str] | None = None,
) -> tuple[bool, str | None]:
    """Evaluate alert_config thresholds. Returns (should_alert, reason_if_suppressed).

    If no alert_config is set, always returns (True, None) — any hash difference alerts.
    Supports:
      - price_below / price_above (float) for product_price
      - percent_change (float) — minimum % change to alert
      - min_diff_chars (int) — minimum character difference
      - regex_must_match (str) — new_text must match regex to alert
      - regex_must_not_match (str) — suppress if matches
      - list_min_added / list_min_removed (int) for list modes
    """
    cfg: dict[str, Any] = getattr(monitor, "alert_config", None) or {}
    if not cfg:
        return True, None

    mode = getattr(monitor, "mode", "page_content")

    # Price thresholds
    if mode == "product_price":
        new_price = _parse_price_value(new_text)
        if new_price is not None:
            if "price_below" in cfg:
                try:
                    thresh = float(cfg["price_below"])
                    if new_price >= thresh:
                        return False, f"price {new_price} not below {thresh}"
                except (ValueError, TypeError):
                    pass
            if "price_above" in cfg:
                try:
                    thresh = float(cfg["price_above"])
                    if new_price <= thresh:
                        return False, f"price {new_price} not above {thresh}"
                except (ValueError, TypeError):
                    pass
            if "percent_change" in cfg and prev_text:
                try:
                    pct = float(cfg["percent_change"])
                    old_price = _parse_price_value(prev_text)
                    if old_price and old_price != 0:
                        change_pct = abs(new_price - old_price) / abs(old_price) * 100
                        if change_pct < pct:
                            return False, f"price change {change_pct:.1f}% < {pct}%"
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

    # JSON field numeric thresholds (reusing price logic)
    if mode == "json_field" and "percent_change" in cfg:
        try:
            pct = float(cfg["percent_change"])
            old_v = float(prev_text.strip()) if prev_text.strip() else None
            new_v = float(new_text.strip()) if new_text.strip() else None
            if old_v is not None and new_v is not None and old_v != 0:
                change_pct = abs(new_v - old_v) / abs(old_v) * 100
                if change_pct < pct:
                    return False, f"value change {change_pct:.1f}% < {pct}%"
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    # List thresholds
    if mode in ("list_items", "site_links", "rss_feed"):
        try:
            before = items_before if items_before is not None else items_from_normalized(prev_text)
            after = items_after if items_after is not None else items_from_normalized(new_text)
            ld = diff_lists(before, after)
            if "list_min_added" in cfg:
                need = int(cfg["list_min_added"])
                if len(ld.added) < need:
                    return False, f"only {len(ld.added)} added < {need}"
            if "list_min_removed" in cfg:
                need = int(cfg["list_min_removed"])
                if len(ld.removed) < need:
                    return False, f"only {len(ld.removed)} removed < {need}"
        except Exception:
            pass

    # Generic diff size threshold
    if "min_diff_chars" in cfg:
        try:
            need = int(cfg["min_diff_chars"])
            # Count diff chars as absolute length delta + changed chars estimate
            diff_len = abs(len(new_text) - len(prev_text))
            if diff_len < need:
                # Also check unified diff-like: require at least need differing chars
                # Simple heuristic: suppress if change is too small
                return False, f"diff {diff_len} chars < {need}"
        except (ValueError, TypeError):
            pass

    if "percent_change" in cfg and mode == "page_content":
        try:
            pct = float(cfg["percent_change"])
            # Percentage of content that changed (based on length delta)
            max_len = max(len(prev_text), len(new_text), 1)
            change_pct = abs(len(new_text) - len(prev_text)) / max_len * 100
            # Rough; if below threshold suppress
            if change_pct < pct:
                return False, f"content change {change_pct:.1f}% < {pct}%"
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    # Regex filters
    if "regex_must_match" in cfg:
        pat = str(cfg["regex_must_match"])
        try:
            if not re.search(pat, new_text, re.IGNORECASE):
                return False, f"new content does not match {pat}"
        except re.error:
            pass
    if "regex_must_not_match" in cfg:
        pat = str(cfg["regex_must_not_match"])
        try:
            if re.search(pat, new_text, re.IGNORECASE):
                return False, f"new content matches excluded {pat}"
        except re.error:
            pass

    return True, None
