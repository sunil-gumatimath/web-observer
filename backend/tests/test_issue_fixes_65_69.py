"""Regression tests for GitHub issues #66-#69."""

from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from alembic import command
from app.auth import AuthPrincipal
from app.db import Base
from app.models import Monitor, ShareLink, Workspace
from app.routers.sharing import create_share_link, list_share_links
from app.schemas import ShareLinkCreate
from tests.conftest import _pg_url, _url_is_safe_for_drop, postgres_available

_VERSIONS_DIR = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _load_migration(filename: str):
    spec = importlib.util.spec_from_file_location(filename, _VERSIONS_DIR / filename)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# #68: Alembic 014 downgrade guards against encrypted secrets > 128 chars
# ---------------------------------------------------------------------------


def test_migration_014_downgrade_rejects_overlong_webhook_secrets() -> None:
    mig_014 = _load_migration("014_webhook_secret_ciphertext.py")
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE webhook_endpoints (id TEXT PRIMARY KEY, secret TEXT)"))
        conn.execute(
            text("INSERT INTO webhook_endpoints (id, secret) VALUES ('1', :s)"),
            {"s": "enc:v1:" + ("a" * 130)},
        )
        orig_get_bind = mig_014.op.get_bind
        mig_014.op.get_bind = lambda: conn  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError, match="exceeding 128 characters"):
                mig_014.downgrade()
        finally:
            mig_014.op.get_bind = orig_get_bind  # type: ignore[assignment]
    eng.dispose()


# ---------------------------------------------------------------------------
# #66: Alembic 015 downgrade preserves detached change_events rows
# ---------------------------------------------------------------------------


def test_migration_015_downgrade_restores_runs_instead_of_deleting_events() -> None:
    mig_015 = _load_migration("015_change_run_set_null.py")
    eng = create_engine("sqlite://")
    ws_id = uuid.uuid4().hex
    mon_id = uuid.uuid4().hex
    snap_id = uuid.uuid4().hex
    ce_id = uuid.uuid4().hex
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE monitors (id TEXT PRIMARY KEY, config_version INTEGER)"))
        conn.execute(
            text(
                "CREATE TABLE monitor_runs ("
                "id TEXT PRIMARY KEY, monitor_id TEXT, workspace_id TEXT, "
                "config_version INTEGER, idempotency_key TEXT, scheduled_at TEXT, "
                "finished_at TEXT, status TEXT, attempt INTEGER, "
                "content_hash TEXT, snapshot_id TEXT, created_at TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE change_events ("
                "id TEXT PRIMARY KEY, workspace_id TEXT, monitor_id TEXT, run_id TEXT, "
                "new_snapshot_id TEXT, new_hash TEXT, created_at TEXT)"
            )
        )
        conn.execute(
            text("INSERT INTO monitors (id, config_version) VALUES (:m, 2)"),
            {"m": mon_id},
        )
        conn.execute(
            text(
                "INSERT INTO change_events "
                "(id, workspace_id, monitor_id, run_id, new_snapshot_id, new_hash, created_at) "
                "VALUES (:id, :ws, :m, NULL, :s, 'h1', '2026-10-01T00:00:00Z')"
            ),
            {"id": ce_id, "ws": ws_id, "m": mon_id, "s": snap_id},
        )

        orig_get_bind = mig_015.op.get_bind
        orig_drop_fk = mig_015.op.drop_constraint
        orig_create_fk = mig_015.op.create_foreign_key
        orig_exec = mig_015.op.execute
        mig_015.op.get_bind = lambda: conn  # type: ignore[assignment]
        mig_015.op.drop_constraint = lambda *a, **k: None  # type: ignore[assignment]
        mig_015.op.create_foreign_key = lambda *a, **k: None  # type: ignore[assignment]
        mig_015.op.execute = lambda *a, **k: None  # type: ignore[assignment]
        try:
            mig_015.downgrade()
        finally:
            mig_015.op.get_bind = orig_get_bind  # type: ignore[assignment]
            mig_015.op.drop_constraint = orig_drop_fk  # type: ignore[assignment]
            mig_015.op.create_foreign_key = orig_create_fk  # type: ignore[assignment]
            mig_015.op.execute = orig_exec  # type: ignore[assignment]

        restored_run_id = conn.execute(
            text("SELECT run_id FROM change_events WHERE id = :id"), {"id": ce_id}
        ).scalar_one()
        assert restored_run_id is not None
        run_row = conn.execute(
            text("SELECT monitor_id, config_version, status FROM monitor_runs WHERE id = :id"),
            {"id": str(restored_run_id)},
        ).one()
        assert run_row[0] == mon_id
        assert run_row[1] == 2
        assert run_row[2] == "succeeded"
    eng.dispose()


# ---------------------------------------------------------------------------
# #69: Share-link note is persisted and returned on list
# ---------------------------------------------------------------------------


def test_share_link_note_is_persisted_and_listed() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    try:
        with factory() as db:
            ws = Workspace(name="Share WS")
            db.add(ws)
            db.flush()
            mon = Monitor(
                workspace_id=ws.id,
                name="Docs",
                url="https://example.com/",
                mode="page_content",
                schedule_interval_minutes=60,
                timezone="UTC",
                next_run_at=datetime.now(UTC),
                enabled=True,
                config_version=1,
            )
            db.add(mon)
            db.commit()

            principal = AuthPrincipal(user=None, is_internal=True)
            created = create_share_link(
                ws.id,
                mon.id,
                ShareLinkCreate(note="For the customer success team"),
                db,
                principal,
                ws,
            )
            assert created.note == "For the customer success team"

            stored = db.scalar(select(ShareLink).where(ShareLink.id == created.id))
            assert stored is not None
            assert stored.note == "For the customer success team"

            listed = list_share_links(ws.id, mon.id, db, ws)
            assert len(listed) == 1
            assert listed[0]["note"] == "For the customer success team"
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# #66, #67, #68: Populated PostgreSQL upgrade + downgrade round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_populated_database_upgrade_and_downgrade_round_trip() -> None:
    if not postgres_available():
        pytest.skip("PostgreSQL test DB not available")
    base_url = _pg_url()
    if not _url_is_safe_for_drop(base_url):
        pytest.skip("TEST_DATABASE_URL is not a test database")

    parsed = make_url(base_url)
    mig_db_name = f"{parsed.database}_mig_{uuid.uuid4().hex[:8]}"
    admin_engine = create_engine(base_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{mig_db_name}"'))

    mig_url = parsed.set(database=mig_db_name).render_as_string(hide_password=False)
    mig_engine = create_engine(mig_url, pool_pre_ping=True)
    backend_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))

    try:
        # 1. Start from an older revision (013) and seed populated data.
        with mig_engine.connect() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "013_add_monitor_tags")
            conn.commit()

        ws_id = uuid.uuid4()
        mon_id = uuid.uuid4()
        snap_id = uuid.uuid4()
        run1_id = uuid.uuid4()
        run2_id = uuid.uuid4()
        ce1_id = uuid.uuid4()
        ep_id = uuid.uuid4()
        sl_id = uuid.uuid4()

        with mig_engine.begin() as conn:
            conn.execute(
                sa.text("INSERT INTO workspaces (id, name) VALUES (:id, :name)"),
                {"id": ws_id, "name": "Mig WS"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO monitors (id, workspace_id, name, url, mode, "
                    "schedule_interval_minutes, timezone, next_run_at, enabled, config_version, "
                    "timeout_seconds, max_response_bytes) "
                    "VALUES (:id, :ws_id, 'Site', 'https://example.com', 'page_content', "
                    "60, 'UTC', NOW(), TRUE, 1, 30, 1000000)"
                ),
                {"id": mon_id, "ws_id": ws_id},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO snapshots (id, workspace_id, monitor_id, content_hash, normalized_text) "
                    "VALUES (:id, :ws_id, :mon_id, 'hash1', 'hello')"
                ),
                {"id": snap_id, "ws_id": ws_id, "mon_id": mon_id},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO monitor_runs (id, monitor_id, workspace_id, config_version, "
                    "idempotency_key, scheduled_at, status, attempt) "
                    "VALUES (:id, :mon_id, :ws_id, 1, :idem, NOW(), 'succeeded', 1)"
                ),
                {"id": run1_id, "mon_id": mon_id, "ws_id": ws_id, "idem": f"r1:{run1_id}"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO monitor_runs (id, monitor_id, workspace_id, config_version, "
                    "idempotency_key, scheduled_at, status, attempt) "
                    "VALUES (:id, :mon_id, :ws_id, 1, :idem, NOW(), 'succeeded', 1)"
                ),
                {"id": run2_id, "mon_id": mon_id, "ws_id": ws_id, "idem": f"r2:{run2_id}"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO change_events (id, workspace_id, monitor_id, run_id, "
                    "new_snapshot_id, new_hash) "
                    "VALUES (:id, :ws_id, :mon_id, :run_id, :snap_id, 'hash1')"
                ),
                {
                    "id": ce1_id,
                    "ws_id": ws_id,
                    "mon_id": mon_id,
                    "run_id": run1_id,
                    "snap_id": snap_id,
                },
            )
            conn.execute(
                sa.text(
                    "INSERT INTO webhook_endpoints (id, workspace_id, url, secret, enabled) "
                    "VALUES (:id, :ws_id, 'https://hooks.example.com', 'plain-short-secret', TRUE)"
                ),
                {"id": ep_id, "ws_id": ws_id},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO share_links (id, workspace_id, monitor_id, token_hash, token_prefix) "
                    "VALUES (:id, :ws_id, :mon_id, :th, 'mtw_')"
                ),
                {"id": sl_id, "ws_id": ws_id, "mon_id": mon_id, "th": f"hash:{sl_id}"},
            )

        # 2. Upgrade populated DB from 013 to head (016).
        with mig_engine.connect() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
            conn.commit()

        # 3. Simulate retention purging run1 -> ce1 becomes detached (run_id IS NULL).
        # Also simulate an encrypted webhook secret (> 128 chars) for #68 guard check.
        with mig_engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM monitor_runs WHERE id = :id"), {"id": run1_id})
            detached_run = conn.execute(
                sa.text("SELECT run_id FROM change_events WHERE id = :id"), {"id": ce1_id}
            ).scalar_one()
            assert detached_run is None
            conn.execute(
                sa.text("UPDATE webhook_endpoints SET secret = :s WHERE id = :id"),
                {"id": ep_id, "s": "enc:v1:" + ("x" * 130)},
            )

        # 4. Downgrade 016 -> 014: 015 must preserve ce1 (no data loss!).
        with mig_engine.connect() as conn:
            cfg.attributes["connection"] = conn
            command.downgrade(cfg, "014_webhook_secret_ciphertext")
            conn.commit()

        with mig_engine.connect() as conn:
            ce_count = conn.execute(
                sa.text("SELECT COUNT(*) FROM change_events WHERE id = :id AND run_id IS NOT NULL"),
                {"id": ce1_id},
            ).scalar_one()
            assert ce_count == 1

        # 5. Downgrading 014 -> 013 with >128 char secret must fail cleanly with RuntimeError.
        with mig_engine.connect() as conn:
            cfg.attributes["connection"] = conn
            with pytest.raises(RuntimeError, match="exceeding 128 characters"):
                command.downgrade(cfg, "013_add_monitor_tags")
            conn.rollback()

        # 6. Once secret is short again, full downgrade -> upgrade round-trip succeeds.
        with mig_engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE webhook_endpoints SET secret = 'short' WHERE id = :id"),
                {"id": ep_id},
            )
        with mig_engine.connect() as conn:
            cfg.attributes["connection"] = conn
            command.downgrade(cfg, "013_add_monitor_tags")
            command.upgrade(cfg, "head")
            conn.commit()

        with mig_engine.connect() as conn:
            assert (
                conn.execute(
                    sa.text("SELECT COUNT(*) FROM change_events WHERE id = :id"),
                    {"id": ce1_id},
                ).scalar_one()
                == 1
            )
    finally:
        mig_engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{mig_db_name}" WITH (FORCE)'))
        admin_engine.dispose()
