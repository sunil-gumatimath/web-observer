"""ORM column types must match the Alembic-managed DDL."""

from __future__ import annotations

from app.models.entities import NotificationChannel


def test_notification_channel_address_matches_migration_type() -> None:
    column = NotificationChannel.__table__.c.address.type
    assert getattr(column, "length", None) == 320
