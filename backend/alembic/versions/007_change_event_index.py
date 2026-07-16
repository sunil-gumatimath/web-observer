"""Add missing ix_change_events_monitor_created index

Revision ID: 007_change_event_index
Revises: 006_alerts
Create Date: 2026-07-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007_change_event_index"
down_revision: Union[str, None] = "006_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_change_events_monitor_created",
        "change_events",
        ["monitor_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_change_events_monitor_created", table_name="change_events")
