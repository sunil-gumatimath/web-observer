"""Route monitor runs to HTTP or browser queues."""

from __future__ import annotations

from app.workers.browser_checks import run_browser_check
from app.workers.checks import run_http_check


def enqueue_check(run_id: str, *, needs_browser: bool = False) -> None:
    """Route a run to the appropriate Dramatiq queue.

    Args:
        run_id: The MonitorRun UUID as a string.
        needs_browser: True for visual mode or js_required monitors.
    """
    if needs_browser:
        run_browser_check.send(str(run_id))
    else:
        run_http_check.send(str(run_id))
