"""Scheduler idempotency: a retry/double-claim of one slot yields ONE run.

Regression test: ``claim_due_monitors`` used to mint
``monitor:timestamp:random`` keys, unique per claim, so two claims for the
same scheduled slot created two ``QUEUED`` runs. Keys are now deterministic
per (monitor_id, slot truncated to the schedule interval), and the claim
reuses the existing row (in-transaction check + unique-constraint savepoint).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


_ACTIVE = {"scheduled", "queued", "running"}


class _FakeDB:
    def __init__(self, monitor):
        self.monitor = monitor
        self.runs: list = []

    def scalars(self, stmt):
        assert "FROM monitors" in str(stmt)
        return _Scalars([self.monitor])

    def scalar(self, stmt):
        raise AssertionError("patched per-test via db.scalar = fake_scalar")

    def add(self, run):
        self.runs.append(run)

    def flush(self):
        if self.runs and self.runs[-1].id is None:
            self.runs[-1].id = uuid4()

    def commit(self):
        return None

    @contextmanager
    def begin_nested(self):
        yield self


class _SessionCtx:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *args):
        return False


def _make_monitor():
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        enabled=True,
        next_run_at=datetime.now(UTC) - timedelta(minutes=5),
        lease_owner=None,
        lease_expires_at=None,
        schedule_interval_minutes=60,
        config_version=1,
        js_required=False,
        mode="page_content",
    )


def test_claim_slot_truncates_to_interval():
    from app.scheduler import _claim_slot

    now = datetime(2026, 9, 11, 10, 37, 12, tzinfo=UTC)
    slot = _claim_slot(now, 60)
    assert slot == datetime(2026, 9, 11, 10, 0, 0, tzinfo=UTC)
    # A retry minutes later lands on the same slot.
    assert _claim_slot(now + timedelta(minutes=5), 60) == slot
    # Next hour is a different slot.
    assert _claim_slot(now + timedelta(minutes=30), 60) != slot


def test_double_claim_same_slot_creates_one_run(monkeypatch):
    from app import scheduler
    from app.models.entities import RunStatus

    monitor = _make_monitor()
    db = _FakeDB(monitor)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: _SessionCtx(db))
    monkeypatch.setattr(scheduler, "assert_can_run_check", lambda *a, **k: None)

    # Pre-compute the deterministic key for this slot and make the fake's
    # idempotency lookup answer from the stored runs.
    def fake_scalar(stmt):
        s = str(stmt)
        if "idempotency_key" in s:
            now = datetime.now(UTC)
            slot = scheduler._claim_slot(now, monitor.schedule_interval_minutes)
            key = f"{monitor.id}:{int(slot.timestamp())}"
            for run in db.runs:
                if run.idempotency_key == key:
                    return run.id
            return None
        for run in db.runs:
            if run.monitor_id == monitor.id and run.status in _ACTIVE:
                return run.id
        return None

    db.scalar = fake_scalar  # type: ignore[method-assign]

    first = scheduler.claim_due_monitors(10)
    assert len(first) == 1
    assert len(db.runs) == 1
    key = db.runs[0].idempotency_key
    # Deterministic: no random suffix, stable per (monitor, slot).
    assert key == f"{monitor.id}:{int(scheduler._claim_slot(datetime.now(UTC), 60).timestamp())}"

    # The first run finishes (or the claim message is redelivered after the
    # active-run window): the active-run guard no longer sees it, but the
    # retry must still collapse onto the existing row via the key.
    db.runs[0].status = RunStatus.SUCCEEDED.value

    second = scheduler.claim_due_monitors(10)
    assert second == []
    assert len(db.runs) == 1
    assert db.runs[0].idempotency_key == key
