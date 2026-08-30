"""Add missing foreign keys on columns that were only application-managed

Revision ID: 010_add_missing_foreign_keys
Revises: 009_add_brand_workspace_keys
Create Date: 2026-08-30

Several columns held UUIDs that pointed at another table but had no database
level foreign key, so referential integrity depended entirely on application
code staying correct:

  * snapshots.run_id                -> monitor_runs.id (SET NULL)
  * webhook_deliveries.workspace_id -> workspaces.id  (CASCADE)
  * audit_logs.actor_user_id        -> users.id       (SET NULL)
  * share_links.created_by_user_id  -> users.id       (SET NULL)
  * workspace_invites.created_by_user_id -> users.id  (SET NULL)

Adding a constraint to a populated column fails if any row is orphaned, so
each is cleaned first: nullable columns are NULLed, and the one NOT NULL
column (webhook_deliveries.workspace_id) has its orphan rows deleted.

Idempotent: each constraint is created only when it is missing.
"""

from collections.abc import Sequence

from sqlalchemy import inspect, text

from alembic import op

revision: str = "010_add_missing_foreign_keys"
down_revision: str | None = "009_add_brand_workspace_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, constraint_name, column, parent_table, parent_column, ondelete)
_FKS: Sequence[tuple[str, str, str, str, str, str]] = (
    ("snapshots", "fk_snapshots_run_id_monitor_runs", "run_id", "monitor_runs", "id", "SET NULL"),
    (
        "webhook_deliveries",
        "fk_webhook_deliveries_workspace_id_workspaces",
        "workspace_id",
        "workspaces",
        "id",
        "CASCADE",
    ),
    ("audit_logs", "fk_audit_logs_actor_user_id_users", "actor_user_id", "users", "id", "SET NULL"),
    (
        "share_links",
        "fk_share_links_created_by_user_id_users",
        "created_by_user_id",
        "users",
        "id",
        "SET NULL",
    ),
    (
        "workspace_invites",
        "fk_workspace_invites_created_by_user_id_users",
        "created_by_user_id",
        "users",
        "id",
        "SET NULL",
    ),
)


def _tables(bind) -> set[str]:
    return set(inspect(bind).get_table_names())


def _fk_names(bind, table: str) -> set[str]:
    return {fk.get("name") for fk in inspect(bind).get_foreign_keys(table) if fk.get("name")}


def _clean_orphans(bind, table, column, parent, parent_col, *, null_out: bool) -> None:
    """Remove rows that would violate the constraint about to be created."""
    if null_out:
        bind.execute(
            text(
                f"UPDATE {table} SET {column} = NULL "
                f"WHERE {column} IS NOT NULL "
                f"AND {column} NOT IN (SELECT {parent_col} FROM {parent})"
            )
        )
    else:
        bind.execute(
            text(f"DELETE FROM {table} WHERE {column} NOT IN (SELECT {parent_col} FROM {parent})")
        )


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = _tables(bind)

    for table, name, column, parent, parent_col, ondelete in _FKS:
        if table not in existing_tables or parent not in existing_tables:
            continue
        if name in _fk_names(bind, table):
            continue

        # webhook_deliveries.workspace_id is NOT NULL, so orphans are deleted
        # rather than nulled. Every other column here is nullable.
        _clean_orphans(bind, table, column, parent, parent_col, null_out=(ondelete == "SET NULL"))
        op.create_foreign_key(name, table, parent, [column], [parent_col], ondelete=ondelete)


def downgrade() -> None:
    bind = op.get_bind()
    existing_tables = _tables(bind)

    for table, name, _column, _parent, _parent_col, _ondelete in reversed(_FKS):
        if table not in existing_tables:
            continue
        if name in _fk_names(bind, table):
            op.drop_constraint(name, table, type_="foreignkey")
