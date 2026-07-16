"""Drop dead confirmation_required column from monitors

Revision ID: 008_drop_confirmation_required
Revises: 007_change_event_index
Create Date: 2026-07-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_drop_confirmation_required"
down_revision: Union[str, None] = "007_change_event_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("monitors", "confirmation_required")


def downgrade() -> None:
    op.add_column(
        "monitors",
        sa.Column("confirmation_required", sa.Boolean(), nullable=False),
    )
