"""phase3 browser fields and ignore rules

Revision ID: 002
Revises: 001
Create Date: 2026-07-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "monitors",
        sa.Column("js_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "monitors",
        sa.Column("ignore_selectors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "monitors",
        sa.Column("ignore_regexes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "monitors",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("monitors", "consecutive_failures")
    op.drop_column("monitors", "ignore_regexes")
    op.drop_column("monitors", "ignore_selectors")
    op.drop_column("monitors", "js_required")
