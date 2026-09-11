"""Retention must keep change events (and their snapshots) on purge.

Regression test: ``purge_expired_snapshots`` used to delete ``ChangeEvent``
rows pointing at expired snapshots (``new_snapshot_id`` is NOT NULL with
ON DELETE CASCADE). Expired snapshots still referenced as ``new_snapshot``
are now kept so the event — inbox history — survives with metadata intact,
while unreferenced snapshots are still purged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeDB:
    """In-memory stand-in for a Session, dispatching on statement text."""

    def __init__(self, *, snapshots, runs, events, referenced_ids):
        self.snapshots = snapshots
        self.runs = runs
        self.events = events
        self.referenced_ids = referenced_ids
        self.deleted = []
        self.committed = False

    def scalars(self, stmt):
        s = str(stmt)
        if "FROM snapshots" in s:
            return _Scalars(self.snapshots)
        if "previous_snapshot_id = " in s:
            return _Scalars([e for e in self.events if e.previous_snapshot_id is not None])
        if "new_snapshot_id IN" in s:
            return _Scalars(list(self.referenced_ids))
        if "FROM monitor_runs" in s:
            if "snapshot_id = " in s:
                linked = {r.snapshot_id for r in self.runs}
                return _Scalars([r for r in self.runs if r.snapshot_id in linked])
            return _Scalars([])  # old-runs query: none seeded as old
        if "FROM change_events" in s:
            return _Scalars([])
        raise AssertionError(f"unexpected statement: {s[:200]}")

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.committed = True


def _settings():
    return SimpleNamespace(snapshot_retention_days=30, run_retention_days=30)


def test_purge_keeps_event_and_referenced_snapshot(monkeypatch):
    from app.services import retention

    monkeypatch.setattr(retention, "get_settings", _settings)
    monkeypatch.setattr(retention, "delete_object", lambda key: None)

    old = datetime.now(UTC) - timedelta(days=60)
    snap_referenced = SimpleNamespace(
        id=uuid4(),
        monitor_id=uuid4(),
        run_id=uuid4(),
        raw_object_key="raw-key",
        text_object_key="text-key",
        created_at=old,
    )
    snap_orphan = SimpleNamespace(
        id=uuid4(),
        monitor_id=snap_referenced.monitor_id,
        run_id=uuid4(),
        raw_object_key="raw-key-2",
        text_object_key=None,
        created_at=old,
    )
    run = SimpleNamespace(id=uuid4(), snapshot_id=snap_referenced.id)
    event = SimpleNamespace(
        id=uuid4(),
        previous_snapshot_id=None,
        new_snapshot_id=snap_referenced.id,
        diff_summary="price dropped",
        ai_summary="ai says cheaper",
        new_hash="abc123",
    )
    db = _FakeDB(
        snapshots=[snap_referenced, snap_orphan],
        runs=[run],
        events=[event],
        referenced_ids=[snap_referenced.id],
    )

    result = retention.purge_expired_snapshots(db)  # type: ignore[arg-type]

    assert db.committed is True
    # The referenced snapshot and its event survive; the orphan is purged.
    assert snap_referenced not in db.deleted
    assert snap_orphan in db.deleted
    assert event not in db.deleted
    assert event.diff_summary == "price dropped"
    assert event.ai_summary == "ai says cheaper"
    assert event.new_hash == "abc123"
    assert event.new_snapshot_id == snap_referenced.id
    assert result.snapshots_deleted == 1
