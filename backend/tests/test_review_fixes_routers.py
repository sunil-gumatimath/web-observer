"""Router-layer AI-review fixes: null PATCH values, reaper-safe re-enqueue,
post-commit storage cleanup, plan interval floor, audit trail, workspace roles,
pagination/sitemap caps and rate limits.

All tests are unit-level: they use small session doubles and never touch a DB.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import get_type_hints
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.routers import monitors
from app.schemas import MonitorCreate, MonitorUpdate
from app.services.plans import PlanLimits

WS_ID = uuid4()
PRINCIPAL = SimpleNamespace(user_id=uuid4(), email="review@example.com")
WORKSPACE = SimpleNamespace(id=WS_ID, plan="free")


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _MonitorDouble:
    """Monitor stand-in that records every setattr."""

    def __init__(self, **kw):
        object.__setattr__(self, "set_calls", [])
        self.__dict__.update(kw)

    def __setattr__(self, key, value):
        self.set_calls.append(key)
        object.__setattr__(self, key, value)


def _monitor(enabled: bool = True, **kw) -> _MonitorDouble:
    return _MonitorDouble(
        id=uuid4(),
        name="Original",
        url="https://example.com",
        mode="page_content",
        enabled=enabled,
        js_required=False,
        config_version=1,
        css_selector=None,
        schedule_interval_minutes=60,
        **kw,
    )


# --------------------------------------------------------------------------
# #2: explicit null PATCH values must be rejected before setattr.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    ["name", "schedule_interval_minutes", "timeout_seconds", "max_response_bytes"],
)
def test_update_monitor_rejects_explicit_null_before_setattr(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    mon = _monitor()
    monkeypatch.setattr(monitors, "_get_monitor", lambda *a, **k: mon)

    class _DB:
        def __init__(self):
            self.rollbacks = 0
            self.commits = 0

        def rollback(self):
            self.rollbacks += 1

        def commit(self):
            self.commits += 1

    db = _DB()
    body = MonitorUpdate(**{field: None})
    with pytest.raises(HTTPException) as exc:
        monitors.update_monitor(WS_ID, mon.id, body, db, PRINCIPAL, WORKSPACE)
    assert exc.value.status_code == 400
    assert field in str(exc.value.detail)
    assert db.rollbacks == 1
    assert db.commits == 0
    assert mon.set_calls == [], "no setattr may run before the null guard"


# --------------------------------------------------------------------------
# #11: plan min_interval_minutes floor enforced on update too.
# --------------------------------------------------------------------------


def test_update_monitor_enforces_plan_interval_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mon = _monitor()
    monkeypatch.setattr(monitors, "_get_monitor", lambda *a, **k: mon)
    monkeypatch.setattr(
        "app.services.plans.get_plan",
        lambda ws: PlanLimits(
            name="pro",
            max_monitors=100,
            max_checks_per_day=5000,
            max_browser_checks_per_day=200,
            min_interval_minutes=30,
            ai_summaries=True,
            ai_tokens_per_day=1,
            webhooks=True,
            api_keys=True,
            seats=5,
            price_monthly_usd=0,
        ),
    )
    db = SimpleNamespace(rollback=lambda: None, commit=lambda: None)
    body = MonitorUpdate(schedule_interval_minutes=20)  # >= schema min (15)
    with pytest.raises(HTTPException) as exc:
        monitors.update_monitor(WS_ID, mon.id, body, db, PRINCIPAL, WORKSPACE)
    assert exc.value.status_code == 400
    assert "Minimum interval for plan pro is 30 minutes" == exc.value.detail
    assert mon.set_calls == []


# --------------------------------------------------------------------------
# #6: stale QUEUED re-enqueue refreshes queued_at before enqueue_check.
# --------------------------------------------------------------------------


def test_manual_run_stale_queued_refreshes_queued_at_before_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mon = _monitor()
    monkeypatch.setattr(monitors, "_get_monitor", lambda *a, **k: mon)
    monkeypatch.setattr(monitors, "assert_can_run_check", lambda *a, **k: None)

    old = datetime.now(UTC) - timedelta(minutes=3)
    run = SimpleNamespace(
        id=uuid4(),
        status="queued",
        created_at=old,
        queued_at=old,
        started_at=None,
    )
    events = []

    class _DB:
        def scalar(self, stmt):
            return run

        def commit(self):
            events.append(("commit", run.queued_at))

    def _enqueue(run_id, *, needs_browser=False):
        events.append(("enqueue", run.queued_at))

    monkeypatch.setattr(monitors, "enqueue_check", _enqueue)
    out = monitors.manual_run.__wrapped__(  # type: ignore[attr-defined]
        request=None,
        workspace_id=WS_ID,
        monitor_id=mon.id,
        db=_DB(),
        _workspace=WORKSPACE,
    )
    assert out.run_id == run.id
    assert "Re-queued" in out.message
    assert [name for name, _ in events] == ["commit", "enqueue"]
    assert events[0][1] == events[1][1]  # no write between refresh and enqueue
    assert datetime.now(UTC) - events[0][1] < timedelta(seconds=10)
    assert events[0][1] != old


# --------------------------------------------------------------------------
# #10: object storage deletes happen after a successful DB commit.
# --------------------------------------------------------------------------


def test_delete_monitor_deletes_objects_only_after_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mid = uuid4()
    monkeypatch.setattr(
        monitors,
        "_get_monitor",
        lambda *a, **k: SimpleNamespace(id=mid, name="m"),
    )
    events = []
    monkeypatch.setattr(monitors, "write_audit", lambda *a, **k: events.append("audit"))
    monkeypatch.setattr(monitors, "delete_object", lambda key: events.append(("delete", key)))

    snapshots = [
        SimpleNamespace(raw_object_key="raw/1", text_object_key="text/1"),
        SimpleNamespace(raw_object_key=None, text_object_key="text/2"),
    ]

    class _DB:
        def scalars(self, stmt):
            return _Scalars(snapshots)

        def execute(self, stmt, **kw):
            events.append("execute")

        def expunge_all(self):
            events.append("expunge")

        def commit(self):
            events.append("commit")

    monitors.delete_monitor(WS_ID, mid, _DB(), PRINCIPAL, WORKSPACE)
    commit_at = events.index("commit")
    deletes = [e for e in events if isinstance(e, tuple)]
    assert {e[1] for e in deletes} == {"raw/1", "text/1", "text/2"}
    assert all(events.index(e) > commit_at for e in deletes)
    assert events.index("audit") < commit_at


def test_bulk_action_delete_objects_only_after_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mid = uuid4()
    mon = SimpleNamespace(id=mid, enabled=True, next_run_at=None)
    events = []
    monkeypatch.setattr(monitors, "write_audit", lambda *a, **k: events.append("audit"))
    monkeypatch.setattr(monitors, "delete_object", lambda key: events.append(("delete", key)))
    snapshots = [SimpleNamespace(raw_object_key="raw/bulk", text_object_key=None)]
    calls = {"n": 0}

    class _DB:
        def scalars(self, stmt):
            calls["n"] += 1
            return _Scalars([mon] if calls["n"] == 1 else snapshots)

        def execute(self, stmt, **kw):
            events.append("execute")

        def expunge_all(self):
            events.append("expunge")

        def commit(self):
            events.append("commit")

    body = monitors.BulkActionIn(monitor_ids=[mid], action="delete")
    result = monitors.bulk_action.__wrapped__(  # type: ignore[attr-defined]
        request=None,
        workspace_id=WS_ID,
        body=body,
        db=_DB(),
        principal=PRINCIPAL,
        _workspace=WORKSPACE,
    )
    assert result == {"deleted": 1, "missing": []}
    commit_at = events.index("commit")
    deletes = [e for e in events if isinstance(e, tuple)]
    assert [e[1] for e in deletes] == ["raw/bulk"]
    assert all(events.index(e) > commit_at for e in deletes)


# --------------------------------------------------------------------------
# #12: audit entries for create / pause / resume / bulk / pause-all / resume-all.
# --------------------------------------------------------------------------


def _audit_capture(monkeypatch):
    calls = []
    monkeypatch.setattr(monitors, "write_audit", lambda db, **kw: calls.append(kw["action"]))
    return calls


def test_create_monitor_writes_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.plans.assert_can_create_monitor", lambda db, ws: None)
    monkeypatch.setattr(
        "app.services.plans.get_plan",
        lambda ws: SimpleNamespace(name="free", min_interval_minutes=15),
    )
    monkeypatch.setattr(monitors, "validate_url_for_fetch", lambda *a, **k: None)
    monkeypatch.setattr(monitors, "enqueue_brand_enrichment", SimpleNamespace(send=lambda *a: None))
    calls = _audit_capture(monkeypatch)

    class _DB:
        def get(self, model, pk):
            return WORKSPACE

        def add(self, obj):
            pass

        def flush(self):
            pass

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    body = MonitorCreate(name="m", url="https://example.com", mode="page_content")
    result = monitors.create_monitor.__wrapped__(  # type: ignore[attr-defined]
        request=None,
        workspace_id=WS_ID,
        body=body,
        db=_DB(),
        principal=PRINCIPAL,
        _workspace=WORKSPACE,
    )
    assert calls == ["monitor.created"]
    assert result.name == "m"


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("pause", "monitor.paused"),
        ("resume", "monitor.resumed"),
    ],
)
def test_pause_resume_write_audit(
    monkeypatch: pytest.MonkeyPatch, action: str, expected: str
) -> None:
    mon = _monitor()
    monkeypatch.setattr(monitors, "_get_monitor", lambda *a, **k: mon)
    calls = _audit_capture(monkeypatch)
    db = SimpleNamespace(commit=lambda: None, refresh=lambda obj: None)
    fn = monitors.pause_monitor if action == "pause" else monitors.resume_monitor
    fn(WS_ID, mon.id, db, PRINCIPAL, WORKSPACE)
    assert calls == [expected]


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("pause", "monitor.bulk_pause"),
        ("resume", "monitor.bulk_resume"),
    ],
)
def test_bulk_pause_resume_write_audit(
    monkeypatch: pytest.MonkeyPatch, action: str, expected: str
) -> None:
    mon = SimpleNamespace(id=uuid4(), enabled=True, next_run_at=None)
    monkeypatch.setattr(monitors, "_get_monitor", lambda *a, **k: mon)
    calls = _audit_capture(monkeypatch)
    db = SimpleNamespace(
        scalars=lambda stmt: _Scalars([mon]),
        commit=lambda: None,
        execute=lambda *a, **k: None,
        expunge_all=lambda: None,
    )
    body = monitors.BulkActionIn(monitor_ids=[mon.id], action=action)
    monitors.bulk_action.__wrapped__(  # type: ignore[attr-defined]
        request=None,
        workspace_id=WS_ID,
        body=body,
        db=db,
        principal=PRINCIPAL,
        _workspace=WORKSPACE,
    )
    assert calls == [expected]


@pytest.mark.parametrize(
    ("fn", "expected"),
    [
        (monitors.pause_all_monitors, "monitor.pause_all"),
        (monitors.resume_all_monitors, "monitor.resume_all"),
    ],
)
def test_pause_all_resume_all_write_audit(monkeypatch, fn, expected: str) -> None:
    calls = _audit_capture(monkeypatch)
    db = SimpleNamespace(
        execute=lambda stmt: SimpleNamespace(rowcount=2),
        commit=lambda: None,
    )
    result = fn.__wrapped__(  # type: ignore[attr-defined]
        request=None, workspace_id=WS_ID, db=db, principal=PRINCIPAL, _workspace=WORKSPACE
    )
    assert result == {"updated": 2}
    assert calls == [expected]


# --------------------------------------------------------------------------
# #15: mutating workspace-scoped endpoints use the member-role dependency.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "monitor_brand_info",
        "selector_preview",
        "mark_change_read",
        "mark_all_alerts_read",
    ],
)
def test_member_ws_dependency_on_previously_any_ws_routes(name: str) -> None:
    fn = getattr(monitors, name)
    hints = get_type_hints(fn, include_extras=True)
    assert hints["_workspace"] is monitors.MemberWs


# --------------------------------------------------------------------------
# #17: pagination, sitemap cap, rate limits.
# --------------------------------------------------------------------------


def test_list_monitors_paginates() -> None:
    class _DB:
        def __init__(self):
            self.stmt = None

        def execute(self, stmt):
            self.stmt = stmt
            return SimpleNamespace(all=lambda: [])

    db = _DB()
    result = monitors.list_monitors(WS_ID, db, WORKSPACE, skip=5, limit=7)
    assert result == []
    sql = str(db.stmt.compile(dialect=postgresql.dialect()))
    assert "OFFSET" in sql and "LIMIT" in sql
    assert {5, 7}.issubset(set(db.stmt.compile(dialect=postgresql.dialect()).params.values()))


def test_sitemap_url_count_capped_at_200() -> None:
    with pytest.raises(ValidationError):
        monitors.SitemapDiscoverIn(url="https://example.com", max_urls=201)
    with pytest.raises(ValidationError):
        monitors.SitemapCreateIn(url="https://example.com", urls=["https://example.com/a"] * 201)
    # At the cap is valid.
    assert monitors.SitemapDiscoverIn(url="https://example.com", max_urls=200).max_urls == 200
    assert (
        len(
            monitors.SitemapCreateIn(
                url="https://example.com", urls=["https://example.com/a"] * 200
            ).urls
        )
        == 200
    )


@pytest.mark.parametrize("name", ["bulk_action", "pause_all_monitors", "resume_all_monitors"])
def test_bulk_endpoints_are_rate_limited(name: str) -> None:
    fn = getattr(monitors, name)
    assert hasattr(fn, "__wrapped__"), f"{name} must be wrapped by @limiter.limit"
    assert "request" in inspect.signature(fn).parameters


def test_slowapi_limit_registered_on_router() -> None:
    """The decorator must be applied to the registered endpoint, not a copy."""
    paths = {getattr(r, "path", ""): r for r in monitors.router.routes}
    for path in (
        "/api/v1/workspaces/{workspace_id}/monitors/bulk",
        "/api/v1/workspaces/{workspace_id}/monitors/pause-all",
        "/api/v1/workspaces/{workspace_id}/monitors/resume-all",
    ):
        route = paths[path]
        assert hasattr(route.endpoint, "__wrapped__")
