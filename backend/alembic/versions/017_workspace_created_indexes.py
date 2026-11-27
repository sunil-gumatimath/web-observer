"""Add (workspace_id, created_at) indexes for the inbox and run-log queries.

The alerts inbox, its summary counts, the activity rollup and the run-logs
list/export all filter on ``workspace_id`` and order by ``created_at``. The
existing indexes lead with ``monitor_id`` (or are single-column), so those
queries fell back to a bitmap scan plus sort once a workspace accumulated
history.

Revision ID: 017_workspace_created_indexes
Revises: 016_share_link_note
Create Date: 2026-11-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "017_workspace_created_indexes"
down_revision: str | None = "016_share_link_note"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_change_events_workspace_created",
        "change_events",
        ["workspace_id", "created_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_monitor_runs_workspace_created",
        "monitor_runs",
        ["workspace_id", "created_at"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_monitor_runs_workspace_created", table_name="monitor_runs", if_exists=True
    )
    op.drop_index(
        "ix_change_events_workspace_created", table_name="change_events", if_exists=True
    )
