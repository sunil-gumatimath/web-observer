"""Add is_read on change_events and watch_note on monitors

Revision ID: 006_alerts
Revises: 005_phase8
Create Date: 2026-07-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_alerts"
down_revision: Union[str, None] = "005_phase8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "change_events",
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("monitors", sa.Column("watch_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("monitors", "watch_note")
    op.drop_column("change_events", "is_read")
