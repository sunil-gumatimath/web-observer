"""Route monitor runs to HTTP or browser queues."""

from __future__ import annotations

from app.models import Monitor
from app.workers.browser_checks import run_browser_check
from app.workers.checks import run_http_check


def enqueue_check(run_id: str, monitor: Monitor) -> None:
    # Visual always uses browser; js_required also uses browser
    needs_browser = bool(getattr(monitor, "js_required", False)) or getattr(
        monitor, "mode", None
    ) == "visual"
    if needs_browser:
        run_browser_check.send(str(run_id))
    else:
        run_http_check.send(str(run_id))
