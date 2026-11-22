"""``min_diff_chars`` is the visual perceptual threshold.

For ``visual`` the documented meaning of ``min_diff_chars`` is the minimum
perceptual (hamming) distance that counts as a change, so when configured it
*is* the comparison threshold — a larger value means a coarser comparison
(fewer alerts), the opposite direction to the other modes where it is a minimum
edit size. This supersedes an earlier "tighten-only" clamp that capped the
value at the global defaults and made any ``min_diff_chars`` above 8 a no-op.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.pipeline import _visual_thresholds


def _settings(ahash: int = 5, phash: int = 8):
    return SimpleNamespace(visual_ahash_threshold=ahash, visual_phash_threshold=phash)


def test_visual_thresholds_use_min_diff_chars_when_below_defaults() -> None:
    monitor = SimpleNamespace(alert_config={"min_diff_chars": 3})
    assert _visual_thresholds(monitor, _settings()) == (3, 3)


def test_visual_thresholds_fall_back_to_configured_defaults() -> None:
    monitor = SimpleNamespace(alert_config={})
    assert _visual_thresholds(monitor, _settings()) == (5, 8)


def test_visual_min_diff_chars_above_defaults_coarsens_detection() -> None:
    """A configured value above the global defaults widens the 'similar' band.

    The old clamp returned the global defaults here, so ``min_diff_chars`` of
    e.g. 20 could never make the comparison coarser than the built-in pHash
    threshold of 8 — silently ignoring the user's intent to alert on larger
    visual shifts only.
    """
    monitor = SimpleNamespace(alert_config={"min_diff_chars": 20})
    assert _visual_thresholds(monitor, _settings()) == (20, 20)
