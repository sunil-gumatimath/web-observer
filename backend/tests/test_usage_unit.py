from datetime import UTC, datetime

from app.services.usage import period_start_utc


def test_period_start_is_midnight_utc() -> None:
    now = datetime(2026, 7, 10, 15, 45, 0, tzinfo=UTC)
    start = period_start_utc(now)
    assert start.hour == 0
    assert start.minute == 0
    assert start.day == 10
