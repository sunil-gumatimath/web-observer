"""Add title, impact, confidence to change_events and semantic_trigger to monitors

Revision ID: 012_add_ai_intelligence_fields
Revises: 011_add_alert_config
Create Date: 2026-09-03

Adds:
- change_events.title VARCHAR(120)
- change_events.impact VARCHAR(32)
- change_events.confidence DOUBLE PRECISION
- monitors.semantic_trigger TEXT
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "012_add_ai_intelligence_fields"
down_revision: str | None = "011_add_alert_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE change_events ADD COLUMN IF NOT EXISTS title VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE change_events ADD COLUMN IF NOT EXISTS impact VARCHAR(32)"))
    op.execute(sa.text("ALTER TABLE change_events ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION"))
    op.execute(sa.text("ALTER TABLE monitors ADD COLUMN IF NOT EXISTS semantic_trigger TEXT"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE change_events DROP COLUMN IF EXISTS title"))
    op.execute(sa.text("ALTER TABLE change_events DROP COLUMN IF EXISTS impact"))
    op.execute(sa.text("ALTER TABLE change_events DROP COLUMN IF EXISTS confidence"))
    op.execute(sa.text("ALTER TABLE monitors DROP COLUMN IF EXISTS semantic_trigger"))
