"""The workspace-scoped inbox/run-log indexes exist in both the ORM and Alembic."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.models.entities import ChangeEvent, MonitorRun

_MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic/versions/017_workspace_created_indexes.py"
)


def _index_columns(table, name: str) -> list[str] | None:
    for index in table.indexes:
        if index.name == name:
            return [col.name for col in index.columns]
    return None


def test_change_events_has_workspace_created_index() -> None:
    cols = _index_columns(ChangeEvent.__table__, "ix_change_events_workspace_created")
    assert cols == ["workspace_id", "created_at"]


def test_monitor_runs_has_workspace_created_index() -> None:
    cols = _index_columns(MonitorRun.__table__, "ix_monitor_runs_workspace_created")
    assert cols == ["workspace_id", "created_at"]


def test_migration_chains_onto_previous_head() -> None:
    spec = importlib.util.spec_from_file_location("migration_017", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "017_workspace_created_indexes"
    assert module.down_revision == "016_share_link_note"
    # alembic_version.version_num is VARCHAR(32).
    assert len(module.revision) <= 32
