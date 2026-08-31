"""Add alert_config JSONB to monitors (conditional thresholds)

Revision ID: 011_add_alert_config
Revises: 010_add_missing_foreign_keys
Create Date: 2026-08-31

Adds monitors.alert_config JSONB for per-monitor conditional alerting
(price_below/above, percent_change, regex filters, list thresholds).
String mode column already supports rss_feed (no DB enum), so no check constraint change.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "011_add_alert_config"
down_revision: str | None = "010_add_missing_foreign_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE monitors ADD COLUMN IF NOT EXISTS alert_config JSONB"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE monitors DROP COLUMN IF EXISTS alert_config"))
