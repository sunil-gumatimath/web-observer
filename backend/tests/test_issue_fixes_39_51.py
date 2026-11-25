"""Regression tests for GitHub issues #39-#47."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# #39: per-plan seat limit enforced on invite creation and redemption
# ---------------------------------------------------------------------------


def test_assert_can_add_member_enforces_plan_seats() -> None:
    from app.services.plans import assert_can_add_member
    from app.services.usage import QuotaExceeded

    ws = SimpleNamespace(id=uuid.uuid4(), plan="free")

    class _DB:
        def __init__(self, count: int) -> None:
            self._count = count

        def scalar(self, stmt):
            return self._count

    assert_can_add_member(_DB(4), ws)
    with pytest.raises(QuotaExceeded):
        assert_can_add_member(_DB(5), ws)


def test_redeem_invite_rejects_when_workspace_at_seat_capacity() -> None:
    from app.routers.sharing import redeem_invite

    ws_id = uuid.uuid4()
    uid = uuid.uuid4()
    invite = SimpleNamespace(
        workspace_id=ws_id,
        role="member",
        expires_at=None,
        use_count=0,
        max_uses=10,
    )
    ws = SimpleNamespace(id=ws_id, name="Team", plan="free")

    class _DB:
        def __init__(self) -> None:
            self.rolled_back = 0

        def scalar(self, stmt):
            s = str(stmt)
            if "workspace_invites" in s:
                return invite
            if "count(" in s.lower():
                return 5
            return None

        def get(self, model, pk):
            return ws

        def execute(self, stmt):
            return SimpleNamespace(rowcount=1)

        def rollback(self):
            self.rolled_back += 1

    db = _DB()
    principal = SimpleNamespace(user=SimpleNamespace(id=uid))
    with pytest.raises(HTTPException) as exc:
        redeem_invite("tok", db, principal)
    assert exc.value.status_code == 409
    assert db.rolled_back == 1


# ---------------------------------------------------------------------------
# #40: change_activity groups in SQL with no 20k row cap
# ---------------------------------------------------------------------------


def test_change_activity_uses_sql_group_by_without_20k_limit() -> None:
    from app.routers.monitors import change_activity

    now = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    today_str = now.date().isoformat()
    ws_id = uuid.uuid4()

    class _DB:
        def __init__(self) -> None:
            self.seen_query = ""

        def execute(self, q):
            self.seen_query = str(q)
            return self

        def all(self):
            # Simulates grouped SQL rows exceeding 20,000 events
            return [(today_str, "pricing", 25_000), (today_str, None, 5_000)]

    db = _DB()
    out = change_activity(ws_id, db, SimpleNamespace(id=ws_id), days=14)
    assert "GROUP BY" in db.seen_query.upper()
    assert "LIMIT" not in db.seen_query.upper()
    assert out.total == 30_000
    assert out.counts[-1] == 30_000


# ---------------------------------------------------------------------------
# #45: notification-channel test endpoint enforces daily notification quota
# ---------------------------------------------------------------------------


def test_notification_channel_test_checks_and_increments_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from starlette.requests import Request
    from app.routers import notifications
    from app.services import usage

    ws_id = uuid.uuid4()
    ch_id = uuid.uuid4()
    ws = SimpleNamespace(id=ws_id, plan="free")
    channel = SimpleNamespace(id=ch_id, workspace_id=ws_id, type="slack", address="https://hooks.slack.com/x")

    class _DB:
        def __init__(self) -> None:
            self.committed = 0

        def scalar(self, stmt):
            return channel

        def commit(self):
            self.committed += 1

    called = {"inc": 0}
    monkeypatch.setattr(usage, "assert_can_use_notifications", lambda db, w: None)
    monkeypatch.setattr(
        usage,
        "increment_notifications",
        lambda db, wid, n=1: called.__setitem__("inc", called["inc"] + 1),
    )
    import app.workers.notifications as notif_worker

    monkeypatch.setattr(notif_worker, "_send_slack", lambda *a, **k: None)

    req = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
    db = _DB()
    res = notifications.test_notification_channel(req, ws_id, ch_id, db, ws)
    assert res["ok"] is True
    assert called["inc"] == 1
    assert db.committed == 1

    def _raise_quota(db, w):
        raise usage.QuotaExceeded("Daily notification quota exceeded (200/day)")

    monkeypatch.setattr(usage, "assert_can_use_notifications", _raise_quota)
    with pytest.raises(HTTPException) as exc:
        notifications.test_notification_channel(req, ws_id, ch_id, db, ws)
    assert exc.value.status_code == 429


# ---------------------------------------------------------------------------
# #46: webhook delivery retry rejects in-flight deliveries and keeps attempts
# ---------------------------------------------------------------------------


def test_webhook_retry_rejects_processing_and_preserves_attempts() -> None:
    from app.routers.enterprise import retry_webhook_delivery

    ws_id = uuid.uuid4()
    del_id = uuid.uuid4()
    processing = SimpleNamespace(id=del_id, workspace_id=ws_id, status="processing", attempts=2)

    class _DB:
        def scalar(self, stmt):
            return processing

        def execute(self, stmt):
            raise AssertionError("Should not update non-failed delivery")

    res = retry_webhook_delivery(
        ws_id,
        del_id,
        _DB(),
        SimpleNamespace(user_id=uuid.uuid4()),
        SimpleNamespace(id=ws_id),
    )
    assert res["retried"] is False
    assert res["status"] == "processing"


# ---------------------------------------------------------------------------
# #47: CSV cells neutralize spreadsheet formula injection
# ---------------------------------------------------------------------------


def test_csv_cell_neutralizes_formula_prefixes() -> None:
    from app.routers.enterprise import _csv_cell

    for dangerous in ("=HYPERLINK(\"http://evil\",\"x\")", "+cmd", "-1+1", "@SUM(1,2)", "\t=1", "\r=1", "\n=1"):
        escaped = _csv_cell(dangerous)
        assert isinstance(escaped, str)
        assert escaped.startswith("'")
        assert escaped[1:] == dangerous

    assert _csv_cell("normal name") == "normal name"
    assert _csv_cell(None) == ""
    assert _csv_cell(42) == 42
