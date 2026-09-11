"""Add tags to monitors for fleet organization.

Revision ID: 013_add_monitor_tags
Revises: 012_add_ai_intelligence_fields
Create Date: 2026-09-11

Adds:
- monitors.tags JSONB (array of strings, null = untagged)
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "013_add_monitor_tags"
down_revision: str | None = "012_add_ai_intelligence_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE monitors ADD COLUMN IF NOT EXISTS tags JSONB"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE monitors DROP COLUMN IF EXISTS tags"))
