"""Add webdog.ai-parity columns (brand, screenshots, BYO keys) and tables

Revision ID: 009_add_brand_workspace_keys
Revises: 008_drop_confirmation_required
Create Date: 2026-08-19

Adds the columns/tables that previously only existed via ``scripts/apply_007.py``:
  * monitors.brand (JSONB)            — brand-aware dashboard info
  * monitors.screenshots_enabled      — capture a screenshot on every check
  * workspaces.llm_api_key/base/model — per-account (bring-your-own) LLM keys
  * workspaces.resend_api_key         — per-account Resend key
  * workspaces.email_from             — per-account sender address
  * share_links / workspace_invites   — opaque-token share + invite tables

Also adds the composite index backing the prev-run lookup used by the change
pipeline (monitor_id + config_version + status + finished_at).

Idempotent: each statement runs only when its target is missing, so DBs that
already applied ``apply_007.py`` upgrade cleanly.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "009_add_brand_workspace_keys"
down_revision: str | None = "008_drop_confirmation_required"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in inspect(bind).get_columns(table)}


def _tables(bind) -> set[str]:
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()

    mon_cols = _columns(bind, "monitors")
    if "brand" not in mon_cols:
        op.add_column("monitors", sa.Column("brand", sa.JSON(), nullable=True))
    if "screenshots_enabled" not in mon_cols:
        op.add_column(
            "monitors",
            sa.Column(
                "screenshots_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    ws_cols = _columns(bind, "workspaces")
    ws_additions = {
        "llm_api_key": sa.Column("llm_api_key", sa.Text(), nullable=True),
        "llm_api_base": sa.Column("llm_api_base", sa.Text(), nullable=True),
        "llm_model": sa.Column("llm_model", sa.String(length=128), nullable=True),
        "resend_api_key": sa.Column("resend_api_key", sa.Text(), nullable=True),
        "email_from": sa.Column("email_from", sa.String(length=320), nullable=True),
    }
    for name, col in ws_additions.items():
        if name not in ws_cols:
            op.add_column("workspaces", col)

    existing_tables = _tables(bind)
    if "share_links" not in existing_tables:
        op.create_table(
            "share_links",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "workspace_id",
                sa.Uuid(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "monitor_id",
                sa.Uuid(),
                sa.ForeignKey("monitors.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
            sa.Column("token_prefix", sa.String(length=16), nullable=False),
            sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index("ix_share_links_workspace_id", "share_links", ["workspace_id"])
        op.create_index("ix_share_links_monitor_id", "share_links", ["monitor_id"])

    if "workspace_invites" not in existing_tables:
        op.create_table(
            "workspace_invites",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "workspace_id",
                sa.Uuid(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
            sa.Column("token_prefix", sa.String(length=16), nullable=False),
            sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
            sa.Column(
                "role",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'member'"),
            ),
            sa.Column("max_uses", sa.Integer(), nullable=False, server_default=sa.text("5")),
            sa.Column("use_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index("ix_workspace_invites_workspace_id", "workspace_invites", ["workspace_id"])

    indexes = {i["name"] for i in inspect(bind).get_indexes("monitor_runs")}
    if "ix_monitor_runs_config_status_finished" not in indexes:
        op.create_index(
            "ix_monitor_runs_config_status_finished",
            "monitor_runs",
            ["monitor_id", "config_version", "status", "finished_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {i["name"] for i in inspect(bind).get_indexes("monitor_runs")}
    if "ix_monitor_runs_config_status_finished" in indexes:
        op.drop_index("ix_monitor_runs_config_status_finished", table_name="monitor_runs")

    if "workspace_invites" in _tables(bind):
        op.drop_table("workspace_invites")
    if "share_links" in _tables(bind):
        op.drop_table("share_links")

    ws_cols = _columns(bind, "workspaces")
    for name in ("email_from", "resend_api_key", "llm_model", "llm_api_base", "llm_api_key"):
        if name in ws_cols:
            op.drop_column("workspaces", name)

    mon_cols = _columns(bind, "monitors")
    if "screenshots_enabled" in mon_cols:
        op.drop_column("monitors", "screenshots_enabled")
    if "brand" in mon_cols:
        op.drop_column("monitors", "brand")
