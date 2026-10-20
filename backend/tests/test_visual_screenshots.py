"""Screenshot lifecycle for visual monitors (capture reuse, storage existence)."""

import types
from pathlib import Path
from unittest.mock import Mock

import app.workers.browser_checks as browser_checks
from app.services import pipeline, storage


def test_visual_change_does_not_recapture_the_compared_screenshot(monkeypatch) -> None:
    """The check already stored the exact capture the hash was computed from.

    A delayed alert recapture would overwrite it with a later page state, so
    the monitor's Visual diff could show two identical images for a change
    that really happened.
    """
    send = Mock()
    monkeypatch.setattr(browser_checks.capture_alert_screenshot, "send", send)

    monitor = types.SimpleNamespace(id="monitor-id", mode="visual")
    pipeline._enqueue_alert_screenshot("change-id", monitor)

    assert send.call_count == 0


def test_other_modes_still_enqueue_the_alert_screenshot(monkeypatch) -> None:
    send = Mock()
    monkeypatch.setattr(browser_checks.capture_alert_screenshot, "send", send)

    monitor = types.SimpleNamespace(id="monitor-id", mode="page_content")
    pipeline._enqueue_alert_screenshot("change-id", monitor)

    send.assert_called_once_with("change-id")


def _local_storage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage, "_use_local", lambda: True)
    monkeypatch.setattr(storage, "_local_root", lambda: tmp_path)


def test_object_exists_reports_stored_and_missing_keys(tmp_path, monkeypatch) -> None:
    _local_storage(tmp_path, monkeypatch)
    key = "screenshots/monitor/run.png"
    storage.put_bytes(key=key, data=b"png-bytes", content_type="image/png")

    assert storage.object_exists(key) is True
    assert storage.object_exists("screenshots/monitor/other.png") is False


def test_object_exists_rejects_traversal(tmp_path, monkeypatch) -> None:
    _local_storage(tmp_path, monkeypatch)
    assert storage.object_exists("../outside.png") is False
