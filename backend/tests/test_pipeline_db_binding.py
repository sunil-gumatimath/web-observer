"""Regression tests for two bugs that broke the CI integration job.

Both are checkable without a live PostgreSQL server:

1. ``snapshots.run_id`` carried a ``use_alter=True`` foreign key **without a
   name**. Alembic creates the constraint as
   ``fk_snapshots_run_id_monitor_runs`` (migration 010), but an unnamed
   ``use_alter`` FK cannot be dropped, so ``Base.metadata.drop_all()`` raised
   "Can't emit DROP CONSTRAINT for constraint ... it has no name" and every
   integration test errored in fixture setup. The ORM must declare the same
   name the migration uses, otherwise a dev database created with
   ``create_all`` also drifts from the Alembic-managed schema.

2. ``services.pipeline._live_run_status`` opened its "fresh session" probe
   from the global ``app.db.SessionLocal``, which is bound to the configured
   ``DATABASE_URL``. When the caller runs against a *test* database the probe
   queried a different PostgreSQL server entirely (and failed with
   "database \\"web_observer\\" does not exist" in CI). The probe must bind to
   the caller's own engine.
"""

from __future__ import annotations

import sqlalchemy.orm

from app.models.entities import MonitorRun, Snapshot
from app.services.pipeline import _live_run_status

# ---------------------------------------------------------------------------
# 1. The snapshots -> monitor_runs constraint must carry the migration's name
# ---------------------------------------------------------------------------

MIGRATION_CONSTRAINT_NAME = "fk_snapshots_run_id_monitor_runs"


def test_snapshots_run_id_fk_uses_the_migration_constraint_name():
    names = {fk.name for fk in Snapshot.__table__.foreign_keys}
    assert MIGRATION_CONSTRAINT_NAME in names, (
        "the snapshots.run_id foreign key must be named "
        f"{MIGRATION_CONSTRAINT_NAME} so drop_all() can drop it and so the "
        f"ORM schema matches migration 010 (got {sorted(n for n in names if n)})"
    )


def test_snapshots_run_id_fk_targets_monitor_runs_with_set_null():
    fk = next(fk for fk in Snapshot.__table__.foreign_keys if fk.name == MIGRATION_CONSTRAINT_NAME)
    assert fk.target_fullname == "monitor_runs.id"
    assert fk.ondelete == "SET NULL"


def test_every_use_alter_foreign_key_is_named():
    """An unnamed ``use_alter`` FK is undroppable - drop_all() fails on it."""
    unnamed = []
    for table in Snapshot.metadata.sorted_tables:
        for fk in table.foreign_keys:
            if fk.use_alter and not fk.name:
                unnamed.append(f"{table.name}.{fk.parent.name}")
    assert not unnamed, f"unnamed use_alter foreign keys: {unnamed}"


# ---------------------------------------------------------------------------
# 2. The live-run-status probe must use the caller's engine
# ---------------------------------------------------------------------------


class _Recorder:
    """Stands in for ``sqlalchemy.orm.Session`` inside the probe."""

    binds: list[object] = []

    def __init__(self, **kwargs):
        _Recorder.binds.append(kwargs.get("bind"))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def scalar(self, *args, **kwargs):
        return "running"


class _FakeSession:
    """A session whose ``get_bind()`` points at a sentinel engine."""

    def __init__(self, bind):
        self._bind = bind

    def get_bind(self):
        return self._bind


def test_live_run_status_probe_binds_to_the_callers_engine(monkeypatch):
    sentinel_engine = object()
    _Recorder.binds = []
    monkeypatch.setattr(sqlalchemy.orm, "Session", _Recorder)

    db = _FakeSession(sentinel_engine)
    run = MonitorRun(id="run-uuid")

    assert _live_run_status(db, run) == "running"
    assert _Recorder.binds == [sentinel_engine], (
        "the probe must bind to the caller's engine, not to the global "
        "app.db.SessionLocal (which points at the configured DATABASE_URL)"
    )


def test_live_run_status_probe_unwraps_a_bound_connection(monkeypatch):
    """A session bound to a Connection must still probe via its Engine.

    Binding the probe straight to the caller's Connection would reuse the
    caller's open transaction, which defeats the whole point of the fence.
    """
    sentinel_engine = object()

    class _FakeConnection:
        engine = sentinel_engine

    _Recorder.binds = []
    monkeypatch.setattr(sqlalchemy.orm, "Session", _Recorder)

    db = _FakeSession(_FakeConnection())
    run = MonitorRun(id="run-uuid")

    assert _live_run_status(db, run) == "running"
    assert _Recorder.binds == [sentinel_engine]
