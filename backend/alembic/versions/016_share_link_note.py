"""Persist optional note on share_links.

Revision ID: 016_share_link_note
Revises: 015_change_run_set_null
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016_share_link_note"
down_revision: str | None = "015_change_run_set_null"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("share_links", sa.Column("note", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("share_links", "note")
