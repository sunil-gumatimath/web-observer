"""Integration-gap regressions: notification quota covers every outbox path."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.services import digest, failure_notify, usage


def test_failure_notice_respects_notification_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    settings.consecutive_failure_notify_threshold = 3
    monkeypatch.setattr(failure_notify, "get_settings", lambda: settings)

    def quota_exceeded(db, workspace):
        raise usage.QuotaExceeded("quota")

    monkeypatch.setattr(usage, "assert_can_use_notifications", quota_exceeded)

    class FakeDB:
        def get(self, cls, key):
            return SimpleNamespace(id=key)

        def scalars(self, stmt):
            return SimpleNamespace(all=lambda: [])

    monitor = SimpleNamespace(
        id="monitor-1",
        workspace_id="workspace-1",
        consecutive_failures=2,
        name="Docs",
        url="https://example.com",
    )
    outbox_ids = failure_notify.record_run_outcome(
        FakeDB(),  # type: ignore[arg-type]
        monitor=monitor,  # type: ignore[arg-type]
        succeeded=False,
    )
    assert outbox_ids == []


def test_digest_respects_notification_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(digest, "build_digest_body", lambda db, workspace, since: ("body", 1))

    def quota_exceeded(db, workspace):
        raise usage.QuotaExceeded("quota")

    monkeypatch.setattr(usage, "assert_can_use_notifications", quota_exceeded)
    workspace = SimpleNamespace(id="workspace-1")  # type: ignore[arg-type]
    assert digest.enqueue_workspace_digest(object(), workspace, since=None, period_key="p") == []  # type: ignore[arg-type]
