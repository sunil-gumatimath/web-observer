"""Widen webhook_endpoints.secret to TEXT for encryption-at-rest ciphertext.

Revision ID: 014_webhook_secret_ciphertext
Revises: 013_add_monitor_tags
Create Date: 2026-09-11

Fernet ciphertext (plus the enc:v1: scheme prefix) exceeds the old
VARCHAR(128); TEXT fits it. Data is untouched — plaintext and ciphertext
values are preserved as-is (no data wipe).
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "014_webhook_secret_ciphertext"
down_revision: str | None = "013_add_monitor_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE webhook_endpoints ALTER COLUMN secret TYPE TEXT"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE webhook_endpoints ALTER COLUMN secret TYPE VARCHAR(128)"))
