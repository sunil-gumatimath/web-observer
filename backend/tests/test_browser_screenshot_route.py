"""Misrouted plain-HTTP jobs must not trigger a browser screenshot."""

from __future__ import annotations

from types import SimpleNamespace

import app.workers.browser_checks as bc
import app.workers.checks as checks


def test_browser_worker_skips_screenshot_for_rerouted_plain_http_mode(monkeypatch):
    sent: list[str] = []
    monitor = SimpleNamespace(mode="site_links", workspace_id="ws")
    run = SimpleNamespace(status="queued")

    monkeypatch.setattr(
        checks,
        "run_http_check",
        SimpleNamespace(send=lambda run_id: sent.append(f"http:{run_id}")),
    )
    monkeypatch.setattr(
        bc,
        "capture_run_screenshot",
        SimpleNamespace(send=lambda run_id: sent.append(f"shot:{run_id}")),
    )

    def fake_execute(run_id, fetch_fn, *, pre_run_hook=None, worker_label=""):
        assert pre_run_hook is not None
        pre_run_hook(monitor, run, SimpleNamespace(commit=lambda: None))

    monkeypatch.setattr(bc, "execute_monitored_run", fake_execute)

    bc.run_browser_check.fn("run-1")

    assert sent == ["http:run-1"]
