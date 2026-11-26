"""Regression tests for GitHub issues #56-#59."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (
    ChangeEvent,
    Monitor,
    MonitorRun,
    NotificationChannel,
    NotificationOutbox,
    Snapshot,
    UsageCounter,
    Workspace,
)
from app.models.entities import OutboxStatus, RunStatus
from app.services import digest, failure_notify, pipeline, usage
from app.services.domain_guard import DomainBlocked
from app.services.fetcher import FetchError, FetchResult
from app.workers import notifications as notif_worker
from app.workers import run_guard


def _sqlite_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# #56: Notification outbox retry budget matches Dramatiq max_retries + reaper
# ---------------------------------------------------------------------------


def test_outbox_delivery_marks_failed_after_dramatiq_budget_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _sqlite_session_factory()
    try:
        assert notif_worker.OUTBOX_MAX_ATTEMPTS == 6  # 1 initial + 5 Dramatiq retries

        with factory() as db:
            ws = Workspace(name="Outbox WS", plan="free")
            db.add(ws)
            db.flush()
            ch = NotificationChannel(
                workspace_id=ws.id,
                type="slack",
                address="https://hooks.slack.com/services/T00/B00/XXX",
                enabled=True,
            )
            db.add(ch)
            db.flush()
            outbox = NotificationOutbox(
                workspace_id=ws.id,
                channel_id=ch.id,
                payload={"kind": "change", "monitor_name": "Docs", "_quota_reserved": True},
                status=OutboxStatus.PENDING.value,
                idempotency_key=f"test:{uuid.uuid4()}",
            )
            db.add(outbox)
            db.commit()
            outbox_id = outbox.id

        monkeypatch.setattr(notif_worker, "SessionLocal", factory)
        monkeypatch.setattr(
            notif_worker,
            "_send_slack",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("slack down")),
        )

        # Attempts 1..5 fail transiently -> back to PENDING and re-raise for Dramatiq retry
        for expected_attempt in range(1, notif_worker.OUTBOX_MAX_ATTEMPTS):
            with pytest.raises(RuntimeError, match="slack down"):
                notif_worker.deliver_outbox_message(str(outbox_id))
            with factory() as db:
                row = db.get(NotificationOutbox, outbox_id)
                assert row is not None
                assert row.status == OutboxStatus.PENDING.value
                assert row.attempts == expected_attempt

        # 6th and final attempt -> terminal FAILED without re-raising
        notif_worker.deliver_outbox_message(str(outbox_id))
        with factory() as db:
            row = db.get(NotificationOutbox, outbox_id)
            assert row is not None
            assert row.status == OutboxStatus.FAILED.value
            assert row.attempts == notif_worker.OUTBOX_MAX_ATTEMPTS
            assert "slack down" in (row.last_error or "")
    finally:
        engine.dispose()


def test_outbox_pre_claim_guard_does_not_exceed_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _sqlite_session_factory()
    try:
        with factory() as db:
            ws = Workspace(name="Pre-claim WS", plan="free")
            db.add(ws)
            db.flush()
            ch = NotificationChannel(
                workspace_id=ws.id,
                type="slack",
                address="https://hooks.slack.com/services/T00/B00/YYY",
                enabled=True,
            )
            db.add(ch)
            db.flush()
            outbox = NotificationOutbox(
                workspace_id=ws.id,
                channel_id=ch.id,
                payload={"kind": "change", "monitor_name": "Docs", "_quota_reserved": True},
                status=OutboxStatus.PENDING.value,
                attempts=notif_worker.OUTBOX_MAX_ATTEMPTS,
                idempotency_key=f"test:{uuid.uuid4()}",
            )
            db.add(outbox)
            db.commit()
            outbox_id = outbox.id

        called: list[str] = []
        monkeypatch.setattr(notif_worker, "SessionLocal", factory)
        monkeypatch.setattr(notif_worker, "_send_slack", lambda *a, **k: called.append("sent"))

        notif_worker.deliver_outbox_message(str(outbox_id))
        assert called == []
        with factory() as db:
            row = db.get(NotificationOutbox, outbox_id)
            assert row is not None
            assert row.status == OutboxStatus.FAILED.value
            assert row.attempts == notif_worker.OUTBOX_MAX_ATTEMPTS
    finally:
        engine.dispose()


def test_outbox_reaper_marks_exhausted_rows_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    engine, factory = _sqlite_session_factory()
    try:
        sent: list[str] = []
        monkeypatch.setattr(notif_worker.deliver_outbox_message, "send", sent.append)
        old = datetime.now(UTC) - timedelta(minutes=30)
        with factory() as db:
            ws = Workspace(name="Reap WS", plan="free")
            db.add(ws)
            db.flush()
            ch = NotificationChannel(
                workspace_id=ws.id,
                type="email",
                address="alerts@example.com",
                enabled=True,
            )
            db.add(ch)
            db.flush()
            exhausted = NotificationOutbox(
                workspace_id=ws.id,
                channel_id=ch.id,
                payload={"kind": "change"},
                status=OutboxStatus.PENDING.value,
                attempts=notif_worker.OUTBOX_MAX_ATTEMPTS,
                available_at=old,
                created_at=old,
                updated_at=old,
                idempotency_key=f"test:{uuid.uuid4()}",
            )
            db.add(exhausted)
            db.commit()

            reaped = notif_worker.reap_stuck_outbox_messages(db, older_than_seconds=600)
            db.commit()
            assert reaped == 0
            assert sent == []
            assert exhausted.status == OutboxStatus.FAILED.value
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# #57: Docker build must never accept/export NEXT_PUBLIC_INTERNAL_API_TOKEN
# ---------------------------------------------------------------------------


def test_docker_files_do_not_expose_internal_token_as_public_build_arg() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dockerfile = (repo_root / "Dockerfile").read_text(encoding="utf-8")
    compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    docker_up = (repo_root / "scripts" / "docker-up.sh").read_text(encoding="utf-8")

    assert "ARG NEXT_PUBLIC_INTERNAL_API_TOKEN" not in dockerfile
    assert "ENV NEXT_PUBLIC_INTERNAL_API_TOKEN" not in dockerfile
    assert "NEXT_PUBLIC_INTERNAL_API_TOKEN=$NEXT_PUBLIC_INTERNAL_API_TOKEN" not in dockerfile
    assert "NEXT_PUBLIC_INTERNAL_API_TOKEN:" not in compose
    assert '[[ $key == "NEXT_PUBLIC_INTERNAL_API_TOKEN" ]] && continue' in docker_up


# ---------------------------------------------------------------------------
# #58: Notification quota cannot be exceeded by enabled channel count
# ---------------------------------------------------------------------------


def _seed_ws_with_channels(db, *, channel_count: int = 3, used: int, limit: int):
    ws = Workspace(name="Quota WS", plan="free")
    db.add(ws)
    db.flush()
    channels = []
    for i in range(channel_count):
        ch = NotificationChannel(
            workspace_id=ws.id,
            type="email",
            address=f"user{i}@example.com",
            enabled=True,
        )
        db.add(ch)
        channels.append(ch)
    db.flush()
    usage.increment_notifications(db, ws.id, n=used)
    db.flush()
    return ws, channels, limit


def test_queue_notifications_caps_outbox_rows_at_remaining_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _sqlite_session_factory()
    try:
        monkeypatch.setattr(
            "app.services.conditional.check_rate_limits",
            lambda *a, **k: (True, None),
            raising=False,
        )
        with factory() as db:
            limit = usage.notification_limit(Workspace(name="x", plan="free"))
            ws, _channels, _ = _seed_ws_with_channels(
                db, channel_count=4, used=limit - 1, limit=limit
            )
            mon = Monitor(
                workspace_id=ws.id,
                name="Site",
                url="https://example.com",
                mode="page_content",
                schedule_interval_minutes=60,
                timezone="UTC",
                next_run_at=datetime.now(UTC),
                enabled=True,
                config_version=1,
            )
            db.add(mon)
            db.flush()
            run = MonitorRun(
                monitor_id=mon.id,
                workspace_id=ws.id,
                config_version=1,
                idempotency_key=f"run:{uuid.uuid4()}",
                scheduled_at=datetime.now(UTC),
                status=RunStatus.RUNNING.value,
                attempt=1,
            )
            db.add(run)
            db.flush()
            snap = Snapshot(
                workspace_id=ws.id,
                monitor_id=mon.id,
                run_id=run.id,
                content_hash="h1",
                normalized_text="hello",
            )
            db.add(snap)
            db.flush()
            change = ChangeEvent(
                workspace_id=ws.id,
                monitor_id=mon.id,
                run_id=run.id,
                new_snapshot_id=snap.id,
                new_hash="h1",
                diff_summary="changed",
                is_noise=False,
            )
            db.add(change)
            db.flush()

            ctx = pipeline._ChangeContext(summary="changed", diff_text="+hi")
            outbox_ids, _webhook_ids = pipeline._queue_notifications(db, mon, change, ctx)
            db.commit()

            assert len(outbox_ids) == 1
            rows = db.scalars(
                select(NotificationOutbox).where(NotificationOutbox.workspace_id == ws.id)
            ).all()
            assert len(rows) == 1
            counter = usage.get_or_create_counter(db, ws.id)
            assert counter.notifications_count == limit
    finally:
        engine.dispose()


def test_digest_and_failure_notify_cap_outbox_rows_at_remaining_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _sqlite_session_factory()
    try:
        monkeypatch.setattr(digest, "build_digest_body", lambda db, ws, since: ("digest body", 2))
        with factory() as db:
            limit = usage.notification_limit(Workspace(name="x", plan="free"))
            ws, _channels, _ = _seed_ws_with_channels(
                db, channel_count=3, used=limit - 1, limit=limit
            )

            digest_ids = digest.enqueue_workspace_digest(
                db, ws, since=datetime.now(UTC) - timedelta(days=1), period_key="daily:20261126"
            )
            db.commit()
            assert len(digest_ids) == 1
            assert usage.get_or_create_counter(db, ws.id).notifications_count == limit

            # Failure notifications on a second workspace also cap at 1 remaining slot.
            ws2, _channels2, _ = _seed_ws_with_channels(
                db, channel_count=3, used=limit - 1, limit=limit
            )
            mon = Monitor(
                workspace_id=ws2.id,
                name="Failing",
                url="https://example.com",
                mode="page_content",
                schedule_interval_minutes=60,
                timezone="UTC",
                next_run_at=datetime.now(UTC),
                enabled=True,
                config_version=1,
                consecutive_failures=4,
            )
            db.add(mon)
            db.flush()
            failure_ids = failure_notify.record_run_outcome(
                db, monitor=mon, succeeded=False, error_code="http_error", error_message="503"
            )
            db.commit()
            assert len(failure_ids) == 1
            assert usage.get_or_create_counter(db, ws2.id).notifications_count == limit
    finally:
        engine.dispose()


def test_deliver_outbox_does_not_double_count_reserved_or_exceed_unreserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _sqlite_session_factory()
    try:
        monkeypatch.setattr(notif_worker, "SessionLocal", factory)
        sent: list[str] = []
        monkeypatch.setattr(notif_worker, "_send_slack", lambda to, *a: sent.append(to) or "msg-1")

        with factory() as db:
            limit = usage.notification_limit(Workspace(name="x", plan="free"))
            ws, channels, _ = _seed_ws_with_channels(db, channel_count=1, used=limit, limit=limit)
            reserved_row = NotificationOutbox(
                workspace_id=ws.id,
                channel_id=channels[0].id,
                payload={
                    "kind": "change",
                    "monitor_name": "Docs",
                    "channel_type": "slack",
                    "_quota_reserved": True,
                },
                status=OutboxStatus.PENDING.value,
                idempotency_key=f"reserved:{uuid.uuid4()}",
            )
            unreserved_row = NotificationOutbox(
                workspace_id=ws.id,
                channel_id=channels[0].id,
                payload={"kind": "change", "monitor_name": "Docs", "channel_type": "slack"},
                status=OutboxStatus.PENDING.value,
                idempotency_key=f"unreserved:{uuid.uuid4()}",
            )
            db.add_all([reserved_row, unreserved_row])
            db.commit()
            ws_id = ws.id
            reserved_id = reserved_row.id
            unreserved_id = unreserved_row.id

        # Reserved row sends without incrementing past limit.
        notif_worker.deliver_outbox_message(str(reserved_id))
        # Unreserved row is blocked because quota is already at limit.
        notif_worker.deliver_outbox_message(str(unreserved_id))

        assert len(sent) == 1
        with factory() as db:
            assert db.get(NotificationOutbox, reserved_id).status == OutboxStatus.SENT.value
            unres = db.get(NotificationOutbox, unreserved_id)
            assert unres.status == OutboxStatus.FAILED.value
            assert "quota" in (unres.last_error or "").lower()
            assert usage.get_or_create_counter(db, ws_id).notifications_count == limit
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# #59: Failed checks are charged against daily check quota
# ---------------------------------------------------------------------------


def _seed_running_monitor(db):
    ws = Workspace(name="Check Quota WS", plan="free")
    db.add(ws)
    db.flush()
    mon = Monitor(
        workspace_id=ws.id,
        name="Target",
        url="https://example.com/",
        mode="page_content",
        schedule_interval_minutes=60,
        timezone="UTC",
        next_run_at=datetime.now(UTC),
        enabled=True,
        config_version=1,
        timeout_seconds=30,
        max_response_bytes=1_000_000,
    )
    db.add(mon)
    db.flush()
    run = MonitorRun(
        monitor_id=mon.id,
        workspace_id=ws.id,
        config_version=1,
        idempotency_key=f"run:{uuid.uuid4()}",
        scheduled_at=datetime.now(UTC),
        queued_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
        status=RunStatus.RUNNING.value,
        attempt=1,
    )
    db.add(run)
    db.commit()
    return ws, mon, run


def test_in_pipeline_http_and_extraction_failures_charge_check_quota() -> None:
    engine, factory = _sqlite_session_factory()
    try:
        with factory() as db:
            ws, mon, run1 = _seed_running_monitor(db)
            res1 = pipeline.apply_fetch_result(
                db,
                monitor=mon,
                run=run1,
                result=FetchResult(
                    final_url="https://example.com/",
                    status_code=503,
                    content=b"unavailable",
                    text="unavailable",
                    content_type="text/html",
                    latency_ms=10,
                ),
                store_raw=False,
            )
            assert res1.status == RunStatus.FAILED.value
            assert run1.status == RunStatus.FAILED.value
            counter = db.scalar(select(UsageCounter).where(UsageCounter.workspace_id == ws.id))
            assert counter is not None
            assert counter.checks_count == 1

            # Second run fails with empty extraction
            run2 = MonitorRun(
                monitor_id=mon.id,
                workspace_id=ws.id,
                config_version=1,
                idempotency_key=f"run:{uuid.uuid4()}",
                scheduled_at=datetime.now(UTC),
                queued_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
                status=RunStatus.RUNNING.value,
                attempt=1,
            )
            db.add(run2)
            db.commit()
            res2 = pipeline.apply_fetch_result(
                db,
                monitor=mon,
                run=run2,
                result=FetchResult(
                    final_url="https://example.com/",
                    status_code=200,
                    content=b"   ",
                    text="   ",
                    content_type="text/html",
                    latency_ms=10,
                ),
                store_raw=False,
            )
            assert res2.status == RunStatus.FAILED.value
            db.expire(counter)
            assert counter.checks_count == 2
    finally:
        engine.dispose()


@pytest.mark.parametrize("failure_kind", ["fetch_error", "domain_blocked", "success"])
def test_execute_monitored_run_charges_check_quota_once_across_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    engine, factory = _sqlite_session_factory()
    try:
        with factory() as db:
            ws = Workspace(name="Guard Quota WS", plan="free")
            db.add(ws)
            db.flush()
            mon = Monitor(
                workspace_id=ws.id,
                name="Target",
                url="https://example.com/",
                mode="page_content",
                schedule_interval_minutes=60,
                timezone="UTC",
                next_run_at=datetime.now(UTC),
                enabled=True,
                config_version=1,
                timeout_seconds=30,
                max_response_bytes=1_000_000,
            )
            db.add(mon)
            db.flush()
            run = MonitorRun(
                monitor_id=mon.id,
                workspace_id=ws.id,
                config_version=1,
                idempotency_key=f"run:{uuid.uuid4()}",
                scheduled_at=datetime.now(UTC),
                queued_at=datetime.now(UTC),
                status=RunStatus.QUEUED.value,
                attempt=1,
            )
            db.add(run)
            db.commit()
            ws_id = ws.id
            run_id = run.id

        monkeypatch.setattr(run_guard, "SessionLocal", factory)
        monkeypatch.setattr(run_guard, "acquire_domain_slot", lambda d: None)
        monkeypatch.setattr(run_guard, "release_domain_slot", lambda d: None)
        monkeypatch.setattr(run_guard, "record_domain_failure", lambda d: None)
        monkeypatch.setattr(run_guard, "record_domain_success", lambda d: None)
        monkeypatch.setattr(run_guard, "enqueue_outbox", lambda ids: None)
        monkeypatch.setattr("app.services.pipeline.put_bytes", lambda **kw: kw["key"])

        if failure_kind == "domain_blocked":
            monkeypatch.setattr(
                run_guard,
                "assert_domain_allowed",
                lambda u: (_ for _ in ()).throw(DomainBlocked("example.com", "circuit open")),
            )
            fetch_fn = lambda m, d: None  # noqa: E731
        elif failure_kind == "fetch_error":
            monkeypatch.setattr(run_guard, "assert_domain_allowed", lambda u: "example.com")
            fetch_fn = lambda m, d: (_ for _ in ()).throw(  # noqa: E731
                FetchError("timeout", "timed out")
            )
        else:
            monkeypatch.setattr(run_guard, "assert_domain_allowed", lambda u: "example.com")
            html = b"<html><body><p>hello world</p></body></html>"
            fetch_fn = lambda m, d: FetchResult(  # noqa: E731
                final_url="https://example.com/",
                status_code=200,
                content=html,
                text=html.decode(),
                content_type="text/html",
                latency_ms=10,
            )

        run_guard.execute_monitored_run(str(run_id), fetch_fn)

        with factory() as db:
            row = db.get(MonitorRun, run_id)
            assert row is not None
            expected_status = (
                RunStatus.SUCCEEDED.value if failure_kind == "success" else RunStatus.FAILED.value
            )
            assert row.status == expected_status
            counter = db.scalar(select(UsageCounter).where(UsageCounter.workspace_id == ws_id))
            assert counter is not None
            assert counter.checks_count == 1
    finally:
        engine.dispose()
