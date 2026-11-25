"""ORM column types and Alembic-migrated schema must stay in sync."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from app.db import Base
from app.models.entities import NotificationChannel

# Legacy differences already present in migrations 001-015 before drift checks
# were enforced. New tables, columns, FKs, constraints, indexes, or type
# changes must match in an Alembic revision and will fail CI otherwise.
_LEGACY_TYPE_DRIFT = frozenset(
    {
        ("monitors", "brand"),
        ("notification_channels", "address"),
    }
)
_LEGACY_INDEX_DRIFT = frozenset(
    {
        "ix_change_events_workspace_id",
        "ix_monitor_config_versions_monitor_id",
        "ix_monitor_runs_workspace_id",
        "ix_notification_channels_workspace_id",
        "ix_snapshots_monitor_id",
        "ix_snapshots_workspace_id",
    }
)
_BLOCKED_OPS = frozenset(
    {
        "add_table",
        "remove_table",
        "add_column",
        "remove_column",
        "add_fk",
        "remove_fk",
        "add_constraint",
        "remove_constraint",
    }
)


def test_notification_channel_address_matches_migration_type() -> None:
    column = NotificationChannel.__table__.c.address.type
    assert getattr(column, "length", None) == 320


@pytest.mark.integration
def test_alembic_schema_matches_orm_models(db_session) -> None:  # noqa: ANN001
    """Verify the Alembic-migrated PostgreSQL DB contains every ORM table/column."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    engine = db_session.get_bind()
    with engine.connect() as conn:
        inspector = inspect(conn)
        db_tables = set(inspector.get_table_names())
        missing_tables = sorted(set(Base.metadata.tables) - db_tables)
        assert not missing_tables, f"Tables missing from Alembic migrations: {missing_tables}"

        missing_columns: list[str] = []
        for table_name, table in sorted(Base.metadata.tables.items()):
            db_cols = {c["name"] for c in inspector.get_columns(table_name)}
            for col in table.columns:
                if col.name not in db_cols:
                    missing_columns.append(f"{table_name}.{col.name}")
        assert not missing_columns, f"Columns missing from Alembic migrations: {missing_columns}"

        mc = MigrationContext.configure(conn)
        raw_diffs = compare_metadata(mc, Base.metadata)

    unexpected: list[object] = []
    for entry in raw_diffs:
        ops = entry if isinstance(entry, list) else [entry]
        for op in ops:
            kind = op[0]
            if kind in _BLOCKED_OPS:
                unexpected.append(op)
            elif kind == "modify_type" and (op[2], op[3]) not in _LEGACY_TYPE_DRIFT:
                unexpected.append(op)
            elif kind == "add_index" and op[1].name not in _LEGACY_INDEX_DRIFT:
                unexpected.append(op)
    assert not unexpected, f"Model/migration drift detected: {unexpected}"
