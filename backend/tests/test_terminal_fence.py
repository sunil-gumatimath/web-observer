"""Unit tests for the fenced terminal SUCCEEDED write in the pipeline.

The terminal commit on both the changed path and the async-AI path used to be
a blind ``run.status = SUCCEEDED`` + commit. That re-introduced a reaper race:
the pre-commit fence re-reads live status in-transaction, but a reaper that
commits RUNNING -> FAILED between that read and the worker's commit was
overwritten last-write-wins, resurrecting a reaped run.

The replacement, ``_commit_terminal_success``, is a conditional UPDATE
(``WHERE status = 'running'``) mirroring the claim fence (run_guard.py) and the
reaper's fenced transitions (run_reaper.py).
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.models.entities import RunStatus
from app.services.pipeline import _commit_terminal_success


class _FakeDB:
    """Session double exposing execute/commit/rollback with a controllable rowcount."""

    def __init__(self, rowcount: int):
        self.rowcount = rowcount
        self.executed = []
        self.commit_count = 0
        self.rollback_count = 0

    def execute(self, stmt, *_a, **_k):
        self.executed.append(stmt)
        return SimpleNamespace(rowcount=self.rowcount)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


def _running_run() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        status=RunStatus.RUNNING.value,
        started_at=None,
        finished_at=None,
        error_code=None,
        error_message=None,
    )


def test_fence_fires_when_still_running():
    run = _running_run()
    db = _FakeDB(rowcount=1)

    assert _commit_terminal_success(db, run) is True

    assert db.commit_count == 1
    # In-memory object synced for PipelineResult reads after commit expiry.
    assert run.status == RunStatus.SUCCEEDED.value
    assert run.error_code is None
    assert run.finished_at is not None


def test_fence_refuses_when_run_no_longer_running():
    """A reaper that won RUNNING -> FAILED inside the read-to-commit window is
    not overwritten: the helper reports False so the caller rolls back and
    returns run_reaped instead of committing results over the reaper."""
    run = _running_run()
    db = _FakeDB(rowcount=0)

    assert _commit_terminal_success(db, run) is False
    assert db.commit_count == 1  # no-op commit; caller rolls back and returns


def test_fence_where_clause_targets_running_status():
    """The conditional UPDATE must be fenced on status = 'running' (the claim
    fence's losing sibling would otherwise re-introduce the blind write)."""
    from app.models import MonitorRun

    run = _running_run()
    db = _FakeDB(rowcount=1)
    _commit_terminal_success(db, run)

    stmt = db.executed[0]
    assert stmt.__class__.__name__ == "Update"
    assert stmt.table.name == MonitorRun.__tablename__
    compiled = stmt.compile()
    where_sql = str(compiled).split("WHERE")[1]
    assert "status" in where_sql
    # The fence value is bound as a parameter — verify it, not the placeholder.
    fence_values = {str(k): v for k, v in compiled.params.items()}
    assert "running" in fence_values.values()
