"""Conditional alert evaluation for monitors."""

from __future__ import annotations

import difflib
import re
from typing import Any

from app.models.entities import LIST_DIFF_MODES, VALUE_MODES
from app.services.structured import diff_lists, items_from_normalized

# User-supplied regexes run inside check workers against fetched page text.
# Two mitigations keep a pathological pattern from stalling a shared worker:
# the pattern itself is validated/capped at the schema layer, and the text it
# is applied to is hard-capped here. An oversized/invalid pattern yields None;
# callers decide the fail direction per rule (must_match suppresses with a
# reason; must_not_match lets the alert through) — the config author sees the
# "does not match" reason in the change row either way.
_MAX_PATTERN_LEN = 256
_MAX_REGEX_TEXT_CHARS = 200_000

# Cap on the strings compared by difflib when sizing a change. Snapshot text
# can reach ~50k chars; SequenceMatcher is O(n*m) in the worst case.
_MAX_DIFF_COMPARE_CHARS = 50_000


def _bounded_search(pattern: str, text: str) -> bool | None:
    """re.search with caps; None when the pattern is invalid or oversized."""
    if len(pattern) > _MAX_PATTERN_LEN:
        return None
    try:
        # pi-lens-ignore: python-unsafe-regex - length-capped, auth-scoped
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None
    return rx.search(text[:_MAX_REGEX_TEXT_CHARS]) is not None


def _changed_char_count(before: str, after: str) -> int:
    """Number of characters that actually differ between two snapshots.

    A plain length delta (``abs(len(a) - len(b))``) reports 0 for a same-size
    rewrite — including the common price case ``"USD 19.99" -> "USD 24.99"``,
    which would let ``min_diff_chars`` suppress a genuine price move. Counting
    the non-equal opcodes measures the real size of the edit instead.
    """
    if before == after:
        return 0
    a = (before or "")[:_MAX_DIFF_COMPARE_CHARS]
    b = (after or "")[:_MAX_DIFF_COMPARE_CHARS]
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    total = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        total += max(i2 - i1, j2 - j1)
    return total


def _visual_hash(text: str, key: str) -> str | None:
    """Extract a hash line (``phash:`` / ``ahash:``) from a visual snapshot."""
    for line in (text or "").splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return None


def _visual_distance(before: str, after: str) -> int | None:
    """Perceptual (hamming) distance between two visual captures.

    Prefers the DCT pHash — the digest change detection compares — and only
    falls back to the legacy aHash for snapshots taken before pHash existed.
    Comparing on the aHash while detecting on the pHash suppressed real
    changes: an aHash barely moves on a text edit (1-2 bits), so any
    ``min_diff_chars`` above that silenced changes detection had just flagged.

    Returns *None* when neither digest is readable, so the caller can fall back
    to a generic size measure.
    """
    from app.services.visual import hamming_distance_hex

    for key in ("phash", "ahash"):
        pa = _visual_hash(before, key)
        na = _visual_hash(after, key)
        if not pa or not na:
            continue
        try:
            return hamming_distance_hex(pa, na)
        except ValueError:
            # Corrupt digest — try the next one rather than reporting 0.
            continue
    return None


def _parse_price_value(text: str) -> float | None:
    """Extract numeric value from normalized price like 'USD 19.99'."""
    return parse_monitor_value(text, "product_price")


def _parse_json_number(text: str) -> float | None:
    """Numeric value of a json_field snapshot's normalized text."""
    return parse_monitor_value(text, "json_field")


def parse_monitor_value(text: str, mode: str) -> float | None:
    """Numeric value of a snapshot's normalized text for chartable modes.

    ``product_price`` reuses the price-token parser; ``json_field`` parses a
    bare number. Returns *None* for other modes or unparsable text.
    """
    if mode == "json_field":
        try:
            return float((text or "").strip())
        except (ValueError, TypeError):
            return None
    if mode != "product_price":
        return None
    import re as _re

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
      - value_below / value_above (float) for json_field
      - percent_change (float) — minimum % change to alert
      - min_diff_chars (int) — minimum character difference (for visual mode:
        the minimum perceptual distance: pHash, aHash for legacy snapshots)
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
    if mode == "json_field":
        new_val = _parse_json_number(new_text)
        if new_val is not None:
            if "value_below" in cfg:
                try:
                    thresh = float(cfg["value_below"])
                    if new_val >= thresh:
                        return False, f"value {new_val} not below {thresh}"
                except (ValueError, TypeError):
                    pass
            if "value_above" in cfg:
                try:
                    thresh = float(cfg["value_above"])
                    if new_val <= thresh:
                        return False, f"value {new_val} not above {thresh}"
                except (ValueError, TypeError):
                    pass
        if "percent_change" in cfg:
            try:
                pct = float(cfg["percent_change"])
                old_v = _parse_json_number(prev_text)
                new_v = _parse_json_number(new_text)
                if old_v is not None and new_v is not None and old_v != 0:
                    change_pct = abs(new_v - old_v) / abs(old_v) * 100
                    if change_pct < pct:
                        return False, f"value change {change_pct:.1f}% < {pct}%"
            except (ValueError, TypeError, ZeroDivisionError):
                pass

    # List thresholds
    if mode in LIST_DIFF_MODES:
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
            if mode == "visual":
                # Visual snapshots carry hashes, not text — the meaningful
                # "size of the change" is the perceptual distance (same digest
                # change detection used).
                diff_len = _visual_distance(prev_text, new_text)
                if diff_len is None:
                    diff_len = _changed_char_count(prev_text, new_text)
            elif mode in VALUE_MODES:
                # "USD 19.99" -> "USD 24.99" has a length delta of 0 but is a
                # real change — count the characters that actually differ.
                diff_len = _changed_char_count(prev_text, new_text)
            else:
                diff_len = _changed_char_count(prev_text, new_text)
            if diff_len < need:
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
    # Visual snapshots are hash strings, not page text — a content regex can
    # never match them, so applying one would silently suppress every alert.
    if mode != "visual":
        if "regex_must_match" in cfg:
            result = _bounded_search(str(cfg["regex_must_match"]), new_text)
            if result is False or result is None:
                return False, f"new content does not match {cfg['regex_must_match']}"
        if "regex_must_not_match" in cfg:
            result = _bounded_search(str(cfg["regex_must_not_match"]), new_text)
            if result:
                return False, f"new content matches excluded {cfg['regex_must_not_match']}"

    return True, None


def check_rate_limits(
    session: Any, monitor: Any, exclude_change_id: Any = None
) -> tuple[bool, str | None]:
    """Cooldown + flapping guard, driven by ``alert_config``.

    Supported keys (all optional, all opt-in):

    - ``cooldown_minutes`` — after a signal alert, skip notifications for this
      many minutes. The change is still recorded in the inbox; only the
      outbound notify is skipped.
    - ``flap_window_minutes`` + ``flap_max_alerts`` — when at least
      ``flap_max_alerts`` signal changes fired inside the last
      ``flap_window_minutes`` minutes, the monitor is flapping between states;
      skip notifications until it settles.

    Returns ``(allowed, reason_if_suppressed)``. Fails open (allows) on any
    error or missing/invalid config — alerting must never silently die.
    """
    try:
        cfg: dict[str, Any] = getattr(monitor, "alert_config", None) or {}
        cooldown = _positive_float(cfg.get("cooldown_minutes"))
        flap_window = _positive_float(cfg.get("flap_window_minutes"))
        flap_max = _positive_int(cfg.get("flap_max_alerts"))
        if not cooldown and not (flap_window and flap_max):
            return True, None

        from datetime import UTC, datetime, timedelta

        from sqlalchemy import select

        from app.models import ChangeEvent

        now = datetime.now(UTC)
        monitor_id = getattr(monitor, "id", None)

        def _recent_signal_count(since: datetime) -> int:
            q = select(ChangeEvent.id).where(
                ChangeEvent.monitor_id == monitor_id,
                ChangeEvent.is_noise.is_(False),
                ChangeEvent.created_at >= since,
            )
            if exclude_change_id is not None:
                q = q.where(ChangeEvent.id != exclude_change_id)
            return len(list(session.execute(q).all()))

        if cooldown:
            cutoff = now - timedelta(minutes=cooldown)
            if _recent_signal_count(cutoff) > 0:
                return False, f"cooldown active ({cooldown:g} min quiet period)"

        if flap_window and flap_max:
            cutoff = now - timedelta(minutes=flap_window)
            hits = _recent_signal_count(cutoff)
            if hits >= flap_max:
                return (
                    False,
                    f"flapping: {hits} alerts in last {flap_window:g} min "
                    f"(limit {flap_max}); notifications bundled until settled",
                )

        return True, None
    except Exception:
        return True, None


def _positive_float(v: Any) -> float | None:
    try:
        f = float(v)
    except (ValueError, TypeError):
        return None
    return f if f > 0 else None


def _positive_int(v: Any) -> int | None:
    try:
        i = int(v)
    except (ValueError, TypeError):
        return None
    return i if i > 0 else None
