"""URL Scanner polling must finish inside the HTTP actor's 120s time limit."""

from __future__ import annotations

from app.services.security_scan import _poll_deadline_seconds


def test_poll_deadline_preserves_short_monitor_timeouts() -> None:
    assert _poll_deadline_seconds(45) == 45.0


def test_poll_deadline_is_capped_for_long_monitor_timeouts() -> None:
    # Submit (20s) + poll (75s) + one in-flight result GET (20s) = 115s,
    # under the run_http_check actor's 120s time_limit.
    assert _poll_deadline_seconds(120) == 75.0
