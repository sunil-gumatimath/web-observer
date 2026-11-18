"""``min_diff_chars`` must tighten visual similarity, not be ignored."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.pipeline import _visual_thresholds


def _settings(ahash: int = 5, phash: int = 8):
    return SimpleNamespace(visual_ahash_threshold=ahash, visual_phash_threshold=phash)


def test_visual_thresholds_tightened_by_min_diff_chars() -> None:
    monitor = SimpleNamespace(alert_config={"min_diff_chars": 3})
    assert _visual_thresholds(monitor, _settings()) == (3, 3)


def test_visual_thresholds_fall_back_to_configured_defaults() -> None:
    monitor = SimpleNamespace(alert_config={})
    assert _visual_thresholds(monitor, _settings()) == (5, 8)


def test_visual_min_diff_chars_cannot_make_detection_less_sensitive() -> None:
    monitor = SimpleNamespace(alert_config={"min_diff_chars": 50})
    assert _visual_thresholds(monitor, _settings()) == (5, 8)
