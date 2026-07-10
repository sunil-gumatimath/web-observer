"""phase5 ai fields, digests, longer channel addresses

Revision ID: 003
Revises: 002
Create Date: 2026-07-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("change_events", sa.Column("ai_summary", sa.Text(), nullable=True))
    op.add_column("change_events", sa.Column("change_category", sa.String(64), nullable=True))
    op.add_column(
        "change_events",
        sa.Column("is_noise", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "workspaces",
        sa.Column("digest_cadence", sa.String(16), nullable=False, server_default="none"),
    )
    op.add_column(
        "workspaces",
        sa.Column("digest_hour_utc", sa.Integer(), nullable=False, server_default="14"),
    )
    op.add_column(
        "workspaces",
        sa.Column("ai_summaries_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.alter_column(
        "notification_channels",
        "address",
        existing_type=sa.String(length=320),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "notification_channels",
        "address",
        existing_type=sa.Text(),
        type_=sa.String(length=320),
        existing_nullable=False,
    )
    op.drop_column("workspaces", "ai_summaries_enabled")
    op.drop_column("workspaces", "digest_hour_utc")
    op.drop_column("workspaces", "digest_cadence")
    op.drop_column("change_events", "is_noise")
    op.drop_column("change_events", "change_category")
    op.drop_column("change_events", "ai_summary")
