"""Digest scheduling: catch-up window after a missed hour, and stable period keys."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.digest import DIGEST_CATCHUP_HOURS, due_digest_workspaces


def _db(*workspaces):
    class _Scalars:
        def all(self):
            return list(workspaces)

    class _DB:
        def scalars(self, _stmt):
            return _Scalars()

    return _DB()


def _ws(cadence: str = "daily", hour: int = 14):
    return SimpleNamespace(id=uuid.uuid4(), digest_cadence=cadence, digest_hour_utc=hour)


def test_due_at_the_scheduled_hour() -> None:
    ws = _ws(hour=14)
    due = due_digest_workspaces(_db(ws), now=datetime(2026, 11, 25, 14, 5, tzinfo=UTC))
    assert [(w, key) for w, key, _ in due] == [(ws, "daily:20261125")]


def test_still_due_after_the_hour_when_the_job_was_down() -> None:
    ws = _ws(hour=14)
    now = datetime(2026, 11, 25, 14, 0, tzinfo=UTC) + timedelta(hours=DIGEST_CATCHUP_HOURS - 1)
    assert len(due_digest_workspaces(_db(ws), now=now)) == 1


def test_not_due_once_the_catchup_window_has_passed() -> None:
    ws = _ws(hour=14)
    now = datetime(2026, 11, 25, 14, 0, tzinfo=UTC) + timedelta(hours=DIGEST_CATCHUP_HOURS)
    assert due_digest_workspaces(_db(ws), now=now) == []


def test_not_due_before_the_scheduled_hour() -> None:
    ws = _ws(hour=14)
    assert due_digest_workspaces(_db(ws), now=datetime(2026, 11, 25, 13, 55, tzinfo=UTC)) == []


def test_period_key_is_stable_across_every_pass_in_the_window() -> None:
    ws = _ws(hour=14)
    keys = {
        key
        for minute in (0, 5, 55, 120, 300)
        for _, key, _ in due_digest_workspaces(
            _db(ws), now=datetime(2026, 11, 25, 14, 0, tzinfo=UTC) + timedelta(minutes=minute)
        )
    }
    assert keys == {"daily:20261125"}


def test_window_crossing_midnight_keeps_the_scheduled_day() -> None:
    ws = _ws(hour=23)
    due = due_digest_workspaces(_db(ws), now=datetime(2026, 11, 26, 2, 0, tzinfo=UTC))
    assert [key for _, key, _ in due] == ["daily:20261125"]


def test_since_is_anchored_to_the_scheduled_time() -> None:
    ws = _ws(hour=14)
    due = due_digest_workspaces(_db(ws), now=datetime(2026, 11, 25, 16, 30, tzinfo=UTC))
    assert len(due) == 1
    assert due[0][2] == datetime(2026, 11, 24, 14, 0, tzinfo=UTC)


def test_weekly_only_on_monday_and_catches_up() -> None:
    ws = _ws(cadence="weekly", hour=14)
    monday = datetime(2026, 11, 23, 16, 0, tzinfo=UTC)  # 2026-11-23 is a Monday
    tuesday = datetime(2026, 11, 24, 14, 5, tzinfo=UTC)
    assert len(due_digest_workspaces(_db(ws), now=monday)) == 1
    assert due_digest_workspaces(_db(ws), now=tuesday) == []


def test_hour_zero_is_still_honoured() -> None:
    ws = _ws(hour=0)
    assert len(due_digest_workspaces(_db(ws), now=datetime(2026, 11, 25, 0, 5, tzinfo=UTC))) == 1
    assert due_digest_workspaces(_db(ws), now=datetime(2026, 11, 25, 14, 5, tzinfo=UTC)) == []
