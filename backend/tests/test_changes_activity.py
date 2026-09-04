"""Tests for change-activity bucketing (pure helper + endpoint with stub DB)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.routers.monitors import _bucket_activity, change_activity


def _now():
    return datetime.now(UTC)


def test_buckets_every_event_oldest_first():
    now = _now()
    today = now.date()
    start_day = today - timedelta(days=13)
    rows = [
        (now - timedelta(hours=1), "pricing"),
        (now - timedelta(hours=2), "pricing"),
        (now - timedelta(hours=3), "content"),  # 3 events today, same monitor
        (now - timedelta(days=1, hours=1), None),  # yesterday, uncategorized
        (None, "pricing"),  # ignored
        (now - timedelta(days=30), "pricing"),  # out of range, ignored
    ]
    counts, per_day = _bucket_activity(rows, start_day, 14)
    assert len(counts) == 14
    assert counts[-1] == 3
    assert counts[-2] == 1
    assert sum(counts) == 4
    assert per_day[-1] == {"pricing": 2, "content": 1}
    assert per_day[-2] == {"uncategorized": 1}


def test_naive_datetimes_treated_as_utc():
    now = _now().replace(tzinfo=None)
    today = datetime.now(UTC).date()
    start_day = today - timedelta(days=6)
    counts, per_day = _bucket_activity([(now, "api")], start_day, 7)
    assert counts[-1] == 1
    assert per_day[-1] == {"api": 1}


class _StubDb:
    """Mimics Session.execute(...).all() returning unpackable row tuples."""

    def __init__(self, rows):
        self._rows = rows
        self.seen_query = None

    def execute(self, q):
        self.seen_query = str(q)
        return self

    def all(self):
        return self._rows


def _call(rows, **kwargs):
    ws_id = uuid4()

    class FakeWs:
        id = ws_id

    return change_activity(ws_id, _StubDb(rows), FakeWs(), **kwargs)  # type: ignore[arg-type]


def test_endpoint_counts_all_events_and_shapes_response():
    now = _now()
    rows = [
        (now - timedelta(hours=1), "pricing"),
        (now - timedelta(hours=2), None),
        (now - timedelta(hours=3), "pricing"),
    ]
    out = _call(rows, days=14)
    assert out.days == 14
    assert out.total == 3
    assert out.counts[-1] == 3
    assert len(out.buckets) == 14
    assert [b.count for b in out.buckets] == out.counts
    assert out.buckets[0].date == out.start_date
    assert out.buckets[-1].date == out.end_date
    # Back-compat fields intact; breakdown added.
    assert out.buckets[-1].by_category == {"pricing": 2, "uncategorized": 1}
    assert out.categories == ["pricing", "uncategorized"]


def test_endpoint_applies_noise_filter_in_sql():
    now = _now()
    out = _call([(now, "content")], days=14, include_noise=False)
    # Verify the generated SQL actually filters noise when excluded.
    db = _StubDb([(now, "content")])
    ws_id = uuid4()

    class FakeWs:
        id = ws_id

    change_activity(ws_id, db, FakeWs(), days=14, include_noise=False)  # type: ignore[arg-type]
    assert "is_noise" in db.seen_query
    db2 = _StubDb([(now, "content")])
    change_activity(ws_id, db2, FakeWs(), days=14, include_noise=True)  # type: ignore[arg-type]
    assert "is_noise" not in db2.seen_query
    assert out.total == 1
