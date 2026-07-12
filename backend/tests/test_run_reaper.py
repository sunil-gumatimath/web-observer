"""Unit tests for stuck-run reaper (no database required)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.models.entities import RunStatus
from app.services.run_reaper import (
    STUCK_QUEUED_MINUTES,
    STUCK_RUNNING_MINUTES,
    reap_stuck_runs,
)


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows
        self.committed = False
        self.last_where = None

    def scalars(self, stmt):
        # Filter in-process the same way the reaper SQL would for our fixtures
        return _FakeScalars(self._rows)

    def commit(self):
        self.committed = True


def _run(
    *,
    status: str,
    started_at: datetime | None = None,
    queued_at: datetime | None = None,
):
    return SimpleNamespace(
        id=uuid4(),
        monitor_id=uuid4(),
        status=status,
        started_at=started_at,
        queued_at=queued_at,
        error_code=None,
        error_message=None,
        finished_at=None,
    )


def test_reaps_old_running_run(monkeypatch):
    old = datetime.now(UTC) - timedelta(minutes=STUCK_RUNNING_MINUTES + 5)
    run = _run(status=RunStatus.RUNNING.value, started_at=old, queued_at=old)
    # Patch select path: reaper loads via db.scalars(...).all() — we feed rows directly
    db = _FakeDB([run])

    # Force reaper query result by replacing the select execution path
    def fake_scalars(stmt):
        return _FakeScalars([run])

    db.scalars = fake_scalars  # type: ignore[method-assign]

    n = reap_stuck_runs(db)  # type: ignore[arg-type]
    assert n == 1
    assert run.status == RunStatus.FAILED.value
    assert run.error_code == "timeout_reaped"
    assert "running" in (run.error_message or "").lower()
    assert run.finished_at is not None
    assert db.committed is True


def test_reaps_old_queued_run():
    old = datetime.now(UTC) - timedelta(minutes=STUCK_QUEUED_MINUTES + 5)
    run = _run(status=RunStatus.QUEUED.value, queued_at=old, started_at=None)
    db = _FakeDB([run])
    db.scalars = lambda stmt: _FakeScalars([run])  # type: ignore[method-assign]

    n = reap_stuck_runs(db)  # type: ignore[arg-type]
    assert n == 1
    assert run.status == RunStatus.FAILED.value
    assert "queued" in (run.error_message or "").lower()
    assert db.committed is True


def test_no_stuck_runs_no_commit():
    db = _FakeDB([])
    db.scalars = lambda stmt: _FakeScalars([])  # type: ignore[method-assign]
    n = reap_stuck_runs(db)  # type: ignore[arg-type]
    assert n == 0
    assert db.committed is False


def test_error_message_uses_previous_status_not_failed():
    """Regression: message must say running/queued, never the post-update status."""
    old = datetime.now(UTC) - timedelta(minutes=STUCK_RUNNING_MINUTES + 1)
    run = _run(status=RunStatus.RUNNING.value, started_at=old)
    db = _FakeDB([run])
    db.scalars = lambda stmt: _FakeScalars([run])  # type: ignore[method-assign]

    reap_stuck_runs(db)  # type: ignore[arg-type]
    assert run.status == RunStatus.FAILED.value
    assert "running" in run.error_message.lower()
    assert "stuck in failed" not in run.error_message.lower()
