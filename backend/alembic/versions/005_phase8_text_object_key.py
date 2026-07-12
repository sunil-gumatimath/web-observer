"""Add text_object_key to Snapshot

Revision ID: 005_phase8
Revises: 004_phase6_7
Create Date: 2026-07-12 20:53:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005_phase8"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add text_object_key column
    op.add_column('snapshots', sa.Column('text_object_key', sa.Text(), nullable=True))
    
    # We alter normalized_text to be nullable since we are moving it out
    # If the user still inserts to it as a preview (truncated to 500 chars), it could be non-nullable,
    # but making it nullable is safer for the migration if they stop writing to it entirely eventually.
    # The fix_plan said "keep normalized_text in Postgres but truncate to first 500 chars", so we'll keep it nullable=True just in case.
    op.alter_column('snapshots', 'normalized_text', existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column('snapshots', 'normalized_text', existing_type=sa.Text(), nullable=False)
    op.drop_column('snapshots', 'text_object_key')
