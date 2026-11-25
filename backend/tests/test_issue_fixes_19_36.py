"""Regression tests for GitHub issues #19 and #23-#36."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import redis
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

# ---------------------------------------------------------------------------
# #19: digest_hour_utc=0 must not fall back to 14
# ---------------------------------------------------------------------------


def test_digest_hour_utc_zero_is_preserved() -> None:
    from app.services.digest import due_digest_workspaces

    ws = SimpleNamespace(
        id=uuid.uuid4(),
        digest_cadence="daily",
        digest_hour_utc=0,
    )

    class _Scalars:
        def all(self):
            return [ws]

    class _DB:
        def scalars(self, stmt):
            return _Scalars()

    midnight = datetime(2026, 11, 25, 0, 5, 0, tzinfo=UTC)
    two_pm = datetime(2026, 11, 25, 14, 5, 0, tzinfo=UTC)

    assert len(due_digest_workspaces(_DB(), now=midnight)) == 1
    assert len(due_digest_workspaces(_DB(), now=two_pm)) == 0


# ---------------------------------------------------------------------------
# #23: single & bulk delete clean up screenshot keys (and bulk cleans brand)
# ---------------------------------------------------------------------------


def test_delete_monitor_includes_screenshot_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import monitors

    mid = uuid.uuid4()
    run_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    monkeypatch.setattr(
        monitors,
        "_get_monitor",
        lambda *a, **k: SimpleNamespace(
            id=mid, name="m", brand={"logo_path": f"brand-assets/{mid}/logo.png"}
        ),
    )
    deleted: list[str] = []
    monkeypatch.setattr(monitors, "write_audit", lambda *a, **k: None)
    monkeypatch.setattr(monitors, "delete_object", lambda key: deleted.append(key))

    snapshots = [SimpleNamespace(raw_object_key="raw/1", text_object_key="text/1", run_id=run_id)]

    class _Scalars:
        def all(self):
            return snapshots

    class _DB:
        def scalars(self, stmt):
            return _Scalars()

        def execute(self, stmt, **kw):
            return None

        def expunge_all(self):
            return None

        def commit(self):
            return None

    principal = SimpleNamespace(user_id=uuid.uuid4(), email="a@b.com")
    monitors.delete_monitor(ws_id, mid, _DB(), principal, SimpleNamespace(id=ws_id))

    assert f"brand-assets/{mid}/logo.png" in deleted
    assert "raw/1" in deleted
    assert "text/1" in deleted
    assert f"screenshots/{mid}/{run_id}.png" in deleted


def test_bulk_delete_includes_brand_and_screenshot_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.requests import Request
    from app.routers import monitors

    mid = uuid.uuid4()
    run_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    mon = SimpleNamespace(
        id=mid,
        enabled=True,
        next_run_at=None,
        brand={"hero_path": f"brand-assets/{mid}/hero.png"},
    )
    deleted: list[str] = []
    monkeypatch.setattr(monitors, "write_audit", lambda *a, **k: None)
    monkeypatch.setattr(monitors, "delete_object", lambda key: deleted.append(key))
    snapshots = [SimpleNamespace(raw_object_key="raw/b", text_object_key=None, run_id=run_id)]
    calls = {"n": 0}

    class _Scalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _DB:
        def scalars(self, stmt):
            calls["n"] += 1
            return _Scalars([mon] if calls["n"] == 1 else snapshots)

        def execute(self, stmt, **kw):
            return None

        def expunge_all(self):
            return None

        def commit(self):
            return None

    req = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
    principal = SimpleNamespace(user_id=uuid.uuid4(), email="a@b.com")
    body = monitors.BulkActionIn(action="delete", monitor_ids=[mid])
    res = monitors.bulk_action(req, ws_id, body, _DB(), principal, SimpleNamespace(id=ws_id))
    assert res["deleted"] == 1
    assert f"brand-assets/{mid}/hero.png" in deleted
    assert "raw/b" in deleted
    assert f"screenshots/{mid}/{run_id}.png" in deleted


# ---------------------------------------------------------------------------
# #24: rate limit middleware resolves verified principal before SlowAPI
# ---------------------------------------------------------------------------


def test_rate_limit_middleware_populates_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import FastAPI
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from app import auth, main, rate_limit

    monkeypatch.setattr(auth, "clerk_configured", lambda s: True)
    monkeypatch.setattr(
        auth,
        "verify_clerk_token",
        lambda token, s: {"sub": "user_alice" if token == "tok_a" else "user_bob"},
    )

    test_app = FastAPI()
    test_app.state.limiter = Limiter(key_func=rate_limit._key_func, default_limits=["1/minute"])
    test_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    test_app.add_middleware(SlowAPIMiddleware)
    test_app.middleware("http")(main._rate_limit_principal_middleware)

    @test_app.get("/ping")
    def ping():
        return {"ok": True}

    with TestClient(test_app) as client:
        r1 = client.get("/ping", headers={"Authorization": "Bearer tok_a"})
        r2 = client.get("/ping", headers={"Authorization": "Bearer tok_a"})
        r3 = client.get("/ping", headers={"Authorization": "Bearer tok_b"})

    assert r1.status_code == 200
    assert r2.status_code == 429
    assert r3.status_code == 200


# ---------------------------------------------------------------------------
# #25: PATCH monitor rejects explicit nulls for non-nullable columns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["timezone", "mode", "enabled", "js_required", "screenshots_enabled"])
def test_patch_monitor_rejects_explicit_null_for_non_nullable_fields(
    field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.routers import monitors
    from app.schemas import MonitorUpdate

    ws_id = uuid.uuid4()
    mid = uuid.uuid4()
    mon = SimpleNamespace(
        id=mid,
        workspace_id=ws_id,
        name="m",
        url="https://example.com",
        mode="page_content",
        css_selector=None,
        schedule_interval_minutes=60,
        timezone="UTC",
        timeout_seconds=30,
        max_response_bytes=2_000_000,
        enabled=True,
        js_required=False,
        screenshots_enabled=False,
        config_version=1,
        brand=None,
    )
    monkeypatch.setattr(monitors, "_get_monitor", lambda *a, **k: mon)

    class _DB:
        def rollback(self):
            return None

    body = MonitorUpdate.model_validate({field: None})
    with pytest.raises(HTTPException) as exc:
        monitors.update_monitor(
            ws_id,
            mid,
            body,
            _DB(),
            SimpleNamespace(user_id=uuid.uuid4(), email="a@b.com"),
            SimpleNamespace(id=ws_id, plan="free"),
        )
    assert exc.value.status_code == 400
    assert field in str(exc.value.detail)


# ---------------------------------------------------------------------------
# #26: bulk import and SitemapCreateIn enforce regex/selector/alert caps
# ---------------------------------------------------------------------------


def test_bulk_import_rejects_excessive_ignore_regexes(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import bulk_import

    monkeypatch.setattr(bulk_import, "get_plan", lambda ws: SimpleNamespace(name="free", min_interval_minutes=5))
    monkeypatch.setattr(bulk_import, "validate_url_for_fetch", lambda *a, **k: None)

    class _Scalars:
        def all(self):
            return []

    class _DB:
        def scalars(self, stmt):
            return _Scalars()

    rows = [
        {
            "name": "bad",
            "url": "https://example.com",
            "ignore_regexes": [f"pat{i}" for i in range(21)],
        }
    ]
    res = bulk_import.import_monitors(_DB(), SimpleNamespace(id=uuid.uuid4(), plan="free"), rows)
    assert len(res.created) == 0
    assert len(res.errors) == 1


def test_sitemap_create_in_rejects_excessive_ignore_regexes() -> None:
    from app.routers.monitors import SitemapCreateIn

    with pytest.raises(ValidationError):
        SitemapCreateIn(
            url="https://example.com/sitemap.xml",
            urls=["https://example.com/a"],
            ignore_regexes=[f"pat{i}" for i in range(21)],
        )


# ---------------------------------------------------------------------------
# #27: schema max_length matches DB VARCHAR bounds
# ---------------------------------------------------------------------------


def test_schema_max_lengths_match_db_columns() -> None:
    from app.schemas import (
        MonitorCreate,
        MonitorUpdate,
        NotificationChannelCreate,
        NotificationChannelUpdate,
        WorkspaceUpdate,
    )

    with pytest.raises(ValidationError):
        MonitorCreate(name="m", url="https://example.com", timezone="x" * 65)
    with pytest.raises(ValidationError):
        MonitorUpdate(timezone="x" * 65)
    with pytest.raises(ValidationError):
        WorkspaceUpdate(email_from="a" * 321)
    with pytest.raises(ValidationError):
        NotificationChannelCreate(type="email", address="a" * 315 + "@b.com")
    with pytest.raises(ValidationError):
        NotificationChannelUpdate(address="a" * 321)


# ---------------------------------------------------------------------------
# #28: redeeming invite as existing member does not increment use_count
# ---------------------------------------------------------------------------


def test_redeem_invite_existing_member_does_not_consume_use() -> None:
    from app.routers.sharing import redeem_invite

    ws_id = uuid.uuid4()
    uid = uuid.uuid4()
    invite = SimpleNamespace(
        workspace_id=ws_id,
        role="member",
        expires_at=None,
        use_count=0,
        max_uses=1,
    )
    existing_member = SimpleNamespace(workspace_id=ws_id, user_id=uid, role="member")
    ws = SimpleNamespace(id=ws_id, name="Team")

    class _DB:
        def __init__(self):
            self.executed = 0
            self.committed = 0

        def scalar(self, stmt):
            s = str(stmt)
            if "workspace_invites" in s:
                return invite
            return existing_member

        def get(self, model, pk):
            return ws

        def execute(self, stmt):
            self.executed += 1
            return SimpleNamespace(rowcount=1)

        def commit(self):
            self.committed += 1

    db = _DB()
    principal = SimpleNamespace(user=SimpleNamespace(id=uid))
    out = redeem_invite("tok", db, principal)
    assert out.workspace_id == ws_id
    assert db.executed == 0
    assert db.committed == 0


# ---------------------------------------------------------------------------
# #29: workspace-scoped API key lists only its own workspace
# ---------------------------------------------------------------------------


def test_list_user_workspaces_scopes_to_api_key_workspace() -> None:
    from app.auth import AuthPrincipal, list_user_workspaces

    ws_a = SimpleNamespace(id=uuid.uuid4(), name="A")
    ws_b = SimpleNamespace(id=uuid.uuid4(), name="B")
    user = SimpleNamespace(id=uuid.uuid4())
    principal = AuthPrincipal(
        user=user,
        is_internal=False,
        email="u@example.com",
        api_key_workspace_id=ws_a.id,
        role_hint="admin",
    )

    class _DB:
        def get(self, model, pk):
            return ws_a if pk == ws_a.id else ws_b

        def scalars(self, stmt):
            raise AssertionError("Should not query all user memberships for API key")

    result = list_user_workspaces(_DB(), principal)
    assert result == [ws_a]


# ---------------------------------------------------------------------------
# #30: concurrent upsert_clerk_user handles IntegrityError without 500
# ---------------------------------------------------------------------------


def test_upsert_clerk_user_recovers_from_integrity_error() -> None:
    from contextlib import contextmanager
    from app.auth import upsert_clerk_user

    winner = SimpleNamespace(id=uuid.uuid4(), clerk_user_id="clerk_1", email="a@example.com")

    class _DB:
        def __init__(self):
            self.calls = 0

        def scalar(self, stmt):
            self.calls += 1
            # First two calls (by clerk_id, by email) see nothing; after IntegrityError, return winner
            return None if self.calls <= 2 else winner

        def add(self, obj):
            return None

        def expunge(self, obj):
            return None

        @contextmanager
        def begin_nested(self):
            yield self

        def flush(self):
            raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    res = upsert_clerk_user(_DB(), clerk_user_id="clerk_1", email="a@example.com")
    assert res is winner


# ---------------------------------------------------------------------------
# #32: reaped run's idempotency_key is suffixed so replacement can claim
# ---------------------------------------------------------------------------


def test_reap_stuck_runs_frees_idempotency_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.entities import RunStatus
    from app.services import run_reaper

    now = datetime.now(UTC)
    run_id = uuid.uuid4()
    mon_id = uuid.uuid4()
    orig_key = f"{mon_id}:1700000000"
    run = SimpleNamespace(
        id=run_id,
        monitor_id=mon_id,
        status=RunStatus.QUEUED.value,
        queued_at=now - timedelta(minutes=10),
        started_at=None,
        idempotency_key=orig_key,
    )
    mon = SimpleNamespace(id=mon_id, next_run_at=now + timedelta(hours=1), js_required=False, mode="page_content")
    captured_values: dict = {}

    class _Scalars:
        def all(self):
            return [run]

    class _DB:
        def scalars(self, stmt):
            return _Scalars()

        def get(self, model, pk):
            return mon

        def execute(self, stmt):
            for k, v in stmt._values.items():
                captured_values[k.key] = v.value
            return SimpleNamespace(rowcount=1)

        def commit(self):
            return None

    monkeypatch.setattr(run_reaper, "record_run_outcome", lambda *a, **k: [])
    reaped = run_reaper.reap_stuck_runs(_DB())
    assert reaped == 1
    assert captured_values["idempotency_key"].startswith(f"{orig_key}:reaped:")
    assert captured_values["idempotency_key"] != orig_key


# ---------------------------------------------------------------------------
# #33: DomainBlocked and SSRFError branches enqueue outbox notifications
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("exc_factory", ["domain", "ssrf"])
def test_run_guard_enqueues_outbox_for_domain_blocked_and_ssrf(
    exc_factory: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.security.ssrf import SSRFError
    from app.services.domain_guard import DomainBlocked
    from app.workers import run_guard

    run_id = uuid.uuid4()
    mon_id = uuid.uuid4()
    run = SimpleNamespace(id=run_id, monitor_id=mon_id, status="queued")
    mon = SimpleNamespace(id=mon_id, url="https://example.com", enabled=True, workspace_id=uuid.uuid4())
    enqueued: list = []

    class _DB:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, model, pk):
            return run if model.__name__ == "MonitorRun" else mon

        def execute(self, stmt):
            return SimpleNamespace(rowcount=1)

        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(run_guard, "SessionLocal", lambda: _DB())
    monkeypatch.setattr(run_guard, "fail_run", lambda *a, **k: None)
    monkeypatch.setattr(run_guard, "_record_failure_outcome", lambda *a, **k: ["outbox-1"])
    monkeypatch.setattr(run_guard, "enqueue_outbox", lambda ids: enqueued.extend(ids))
    monkeypatch.setattr(run_guard, "release_domain_slot", lambda d: None)

    if exc_factory == "domain":
        monkeypatch.setattr(
            run_guard,
            "assert_domain_allowed",
            MagicMock(side_effect=DomainBlocked("example.com", "circuit open")),
        )
    else:
        monkeypatch.setattr(run_guard, "assert_domain_allowed", lambda u: "example.com")
        monkeypatch.setattr(run_guard, "acquire_domain_slot", lambda d: None)
        monkeypatch.setattr(
            run_guard,
            "apply_fetch_result",
            MagicMock(side_effect=SSRFError("blocked_address", "private ip")),
        )

    run_guard.execute_monitored_run(
        str(run_id),
        fetch_fn=lambda m, db: SimpleNamespace(),
        worker_label="test",
    )
    assert enqueued == ["outbox-1"]


# ---------------------------------------------------------------------------
# #34: transient Redis error in record_domain_success does not fail run
# ---------------------------------------------------------------------------


def test_record_domain_success_ignores_redis_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import domain_guard

    broken = MagicMock()
    broken.delete.side_effect = redis.ConnectionError("redis down")
    monkeypatch.setattr(domain_guard, "_redis", lambda: broken)

    domain_guard.record_domain_success("example.com")  # must not raise


# ---------------------------------------------------------------------------
# #35: Context.dev failover triggers on plain HTTP 401/403/429 FetchResult
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_code", [401, 403, 429])
def test_provider_fallback_triggers_on_plain_http_blocked_status(
    status_code: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import context_dev
    from app.services.fetcher import FetchResult
    from app.workers.checks import fetch_page_with_provider_fallback

    monkeypatch.setattr(context_dev, "is_configured", lambda: True)
    monkeypatch.setattr(context_dev, "scrape_markdown", lambda url, timeout_seconds=30: "# Fallback")

    def fake_primary(url, **kwargs):
        return FetchResult(
            final_url=url,
            status_code=status_code,
            content=b"rate limited",
            text="rate limited",
            content_type="text/html",
            latency_ms=10,
        )

    res = fetch_page_with_provider_fallback(
        "https://example.com",
        monitor_mode="page_content",
        timeout_seconds=30,
        max_response_bytes=100_000,
        primary=fake_primary,
    )
    assert res.status_code == 200
    assert res.provider_markdown == "# Fallback"


# ---------------------------------------------------------------------------
# #36: one Redis enqueue failure does not abort remaining scheduler batch
# ---------------------------------------------------------------------------


def test_scheduler_enqueue_batch_continues_after_single_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import scheduler

    called: list[str] = []

    def flaky_enqueue(run_id: str, *, needs_browser: bool = False) -> None:
        called.append(run_id)
        if len(called) == 2:
            raise redis.ConnectionError("broker down")

    monkeypatch.setattr(scheduler, "enqueue_check", flaky_enqueue)
    jobs = [(uuid.uuid4(), False) for _ in range(5)]
    scheduler._enqueue_batch(jobs)
    assert len(called) == 5
