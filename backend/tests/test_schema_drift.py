"""ORM column types and Alembic-migrated schema must stay in sync."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from app.db import Base
from app.models.entities import NotificationChannel

# Legacy differences already present in migrations 001-015 before drift checks
# were enforced. Policy: default-deny on every Alembic `compare_metadata`
# operation (tables, columns, FKs, constraints, add/remove indexes, type changes,
# nullability changes, server defaults, or any other op kind). Only the exact
# frozen baseline below is tolerated until cleaned up in a migration; any new
# or changed mismatch fails CI.
_LEGACY_TYPE_DRIFT: dict[tuple[str, str], tuple[type, type, int | None]] = {
    # (table, column): (expected_db_type, expected_orm_type, expected_orm_length)
    ("monitors", "brand"): (postgresql.JSON, postgresql.JSONB, None),
    ("notification_channels", "address"): (sa.TEXT, sa.String, 320),
}
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
_LEGACY_NULLABLE_DRIFT = frozenset(
    {
        ("api_keys", "created_at"),
        ("audit_logs", "created_at"),
        ("change_events", "created_at"),
        ("monitor_config_versions", "created_at"),
        ("monitor_runs", "created_at"),
        ("monitors", "created_at"),
        ("monitors", "updated_at"),
        ("notification_channels", "created_at"),
        ("notification_deliveries", "created_at"),
        ("notification_outbox", "available_at"),
        ("notification_outbox", "created_at"),
        ("notification_outbox", "updated_at"),
        ("snapshots", "created_at"),
        ("users", "created_at"),
        ("users", "updated_at"),
        ("webhook_deliveries", "created_at"),
        ("webhook_deliveries", "updated_at"),
        ("webhook_endpoints", "created_at"),
        ("workspace_members", "created_at"),
        ("workspaces", "created_at"),
        ("workspaces", "updated_at"),
    }
)


def _match_legacy_op(op: tuple) -> tuple[str, object] | None:
    """Return a legacy-key tag if *op* matches the frozen baseline, else None."""
    kind = op[0]
    if kind == "modify_type":
        key = (op[2], op[3])
        spec = _LEGACY_TYPE_DRIFT.get(key)
        if spec is None:
            return None
        db_type, orm_type, orm_len = spec
        existing_type, new_type = op[5], op[6]
        if (
            type(existing_type) is db_type
            and type(new_type) is orm_type
            and getattr(new_type, "length", None) == orm_len
        ):
            return ("type", key)
        return None
    if kind == "add_index" and op[1].name in _LEGACY_INDEX_DRIFT:
        return ("index", op[1].name)
    if kind == "modify_nullable":
        key = (op[2], op[3])
        if key in _LEGACY_NULLABLE_DRIFT and op[5] is True and op[6] is False:
            return ("nullable", key)
        return None
    return None


def _classify_diffs(raw_diffs: list) -> tuple[list[object], set[tuple[str, object]]]:
    """Return (unexpected_ops, matched_legacy_tags) from Alembic compare_metadata output."""
    unexpected: list[object] = []
    matched_legacy: set[tuple[str, object]] = set()
    for entry in raw_diffs:
        ops = entry if isinstance(entry, list) else [entry]
        for op in ops:
            tag = _match_legacy_op(op)
            if tag is not None:
                matched_legacy.add(tag)
            else:
                unexpected.append(op)
    return unexpected, matched_legacy


def test_notification_channel_address_matches_migration_type() -> None:
    column = NotificationChannel.__table__.c.address.type
    assert getattr(column, "length", None) == 320


def test_schema_drift_policy_blocks_non_legacy_changes() -> None:
    # Exact legacy notification_channels.address mismatch is tolerated;
    # any other type pair or length on the same column must be flagged.
    legacy_addr = (
        "modify_type",
        None,
        "notification_channels",
        "address",
        {},
        sa.TEXT(),
        sa.String(length=320),
    )
    wrong_len = (
        "modify_type",
        None,
        "notification_channels",
        "address",
        {},
        sa.TEXT(),
        sa.String(length=64),
    )
    removed_idx = ("remove_index", sa.Index("ix_snapshots_monitor_id", sa.Column("monitor_id")))
    new_nullable = ("modify_nullable", None, "monitors", "name", {}, True, False)

    unexpected, matched = _classify_diffs([[legacy_addr], [wrong_len], removed_idx, [new_nullable]])
    assert matched == {("type", ("notification_channels", "address"))}
    assert unexpected == [wrong_len, removed_idx, new_nullable]


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

    unexpected, matched_legacy = _classify_diffs(raw_diffs)
    assert not unexpected, f"Model/migration drift detected: {unexpected}"

    expected_legacy = (
        {("type", k) for k in _LEGACY_TYPE_DRIFT}
        | {("index", k) for k in _LEGACY_INDEX_DRIFT}
        | {("nullable", k) for k in _LEGACY_NULLABLE_DRIFT}
    )
    stale_legacy = sorted(expected_legacy - matched_legacy)
    assert not stale_legacy, f"Stale legacy exceptions no longer present in schema: {stale_legacy}"
