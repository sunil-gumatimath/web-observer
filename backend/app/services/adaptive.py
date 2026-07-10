"""Adaptive scheduling: stretch interval after quiet success runs."""

from __future__ import annotations

from app.config import get_settings
from app.models import Monitor


def note_check_outcome(monitor: Monitor, *, changed: bool, succeeded: bool) -> None:
    """Mutate monitor interval fields based on outcome."""
    settings = get_settings()
    if monitor.base_interval_minutes is None:
        monitor.base_interval_minutes = monitor.schedule_interval_minutes

    if not succeeded:
        return

    if changed:
        monitor.consecutive_unchanged = 0
        # reset toward base interval
        monitor.schedule_interval_minutes = monitor.base_interval_minutes
        return

    monitor.consecutive_unchanged = int(monitor.consecutive_unchanged or 0) + 1
    # Every 5 quiet successes, stretch interval up to 4x base (capped)
    if monitor.consecutive_unchanged > 0 and monitor.consecutive_unchanged % 5 == 0:
        base = monitor.base_interval_minutes or settings.min_check_interval_minutes
        stretched = min(base * 4, monitor.schedule_interval_minutes + base)
        # never go below plan min (caller may enforce further)
        monitor.schedule_interval_minutes = max(base, stretched)
