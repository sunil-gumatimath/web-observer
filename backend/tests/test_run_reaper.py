"""Unit tests for the fenced stuck-run reaper (no database required)."""

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


class _FakeMonitor:
    def __init__(self, id):
        self.id = id
        self.consecutive_failures = 0
        self.consecutive_unchanged = 0


class _FakeDB:
    """Session double modelling the reaper's actual DB traffic.

    ``execute`` models the fenced conditional UPDATE: it succeeds (rowcount 1)
    and flips the run's status unless persistence has been disabled by the
    test (simulating a concurrent completion winning the race, rowcount 0).
    """

    def __init__(self, rows, *, allow_fence=True):
        self._rows = rows
        self.committed = 0
        self.allow_fence = allow_fence
        self.executed = []

    def scalars(self, stmt):
        return _FakeScalars(self._rows)

    def get(self, model, pk):
        return _FakeMonitor(pk)

    def execute(self, stmt, *_a, **_k):
        self.executed.append(stmt)
        if self.allow_fence:
            # Flip the in-memory status like a real conditional UPDATE would.
            for row in self._rows:
                row.status = RunStatus.FAILED.value
            return SimpleNamespace(rowcount=1)
        return SimpleNamespace(rowcount=0)

    def commit(self):
        self.committed += 1


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
    db = _FakeDB([run])
    db.scalars = lambda stmt: _FakeScalars([run])  # type: ignore[method-assign]

    n = reap_stuck_runs(db)  # type: ignore[arg-type]
    assert n == 1
    assert run.status == RunStatus.FAILED.value
    assert run.error_code == "timeout_reaped"
    assert "running" in (run.error_message or "").lower()
    assert run.finished_at is not None
    assert db.committed == 1


def test_reaps_old_queued_run(monkeypatch):
    old = datetime.now(UTC) - timedelta(minutes=STUCK_QUEUED_MINUTES + 5)
    run = _run(status=RunStatus.QUEUED.value, queued_at=old, started_at=None)
    db = _FakeDB([run])
    db.scalars = lambda stmt: _FakeScalars([run])  # type: ignore[method-assign]

    n = reap_stuck_runs(db)  # type: ignore[arg-type]
    assert n == 1
    assert run.status == RunStatus.FAILED.value
    assert "queued" in (run.error_message or "").lower()
    assert db.committed == 1


def test_fenced_transition_lost_when_concurrent_completion_wins(monkeypatch):
    """A run completing between SELECT and WRITE keeps its terminal state."""
    old = datetime.now(UTC) - timedelta(minutes=STUCK_RUNNING_MINUTES + 5)
    run = _run(status=RunStatus.RUNNING.value, started_at=old)
    db = _FakeDB([run], allow_fence=False)
    db.scalars = lambda stmt: _FakeScalars([run])  # type: ignore[method-assign]

    n = reap_stuck_runs(db)  # type: ignore[arg-type]
    assert n == 0
    # The concurrent completion set this status — the reaper must not
    # overwrite it with FAILED.
    assert run.status != RunStatus.FAILED.value


def test_no_stuck_runs_no_commit():
    db = _FakeDB([])
    db.scalars = lambda stmt: _FakeScalars([])  # type: ignore[method-assign]
    n = reap_stuck_runs(db)  # type: ignore[arg-type]
    assert n == 0
    assert db.committed == 0


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
