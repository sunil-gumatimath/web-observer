"""Shared fixtures. Integration tests use PostgreSQL when available."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.db import Base
from app.models import *  # noqa: F401,F403


def _pg_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://monitor:monitor@127.0.0.1:5432/web_observer_test",
    )


def _url_is_safe_for_drop(url: str) -> bool:
    if os.environ.get("FORCE_TEST_DB") == "1":
        return True
    lower = url.lower()
    return "test" in lower or "_test" in lower or "/test" in lower


def postgres_available() -> bool:
    url = _pg_url()
    if not _url_is_safe_for_drop(url):
        return False
    try:
        # Fail fast when Postgres is down / unreachable (avoid multi-minute hangs).
        engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


def _upgrade_schema_via_alembic(engine: Engine) -> None:
    """Rebuild the public schema strictly from Alembic revisions (not create_all)."""
    backend_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()


def _truncate_app_tables(engine: Engine) -> None:
    table_names = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    if not table_names:
        return
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def _migrated_pg_engine() -> Generator[Engine, None, None]:
    if not postgres_available():
        pytest.skip(
            "PostgreSQL test DB not available. "
            "Create DB web_observer_test or set TEST_DATABASE_URL (must contain 'test')."
        )
    engine = create_engine(_pg_url(), pool_pre_ping=True)
    _upgrade_schema_via_alembic(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(_migrated_pg_engine: Engine) -> Generator[Session, None, None]:
    _truncate_app_tables(_migrated_pg_engine)
    SessionLocal = sessionmaker(bind=_migrated_pg_engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        _truncate_app_tables(_migrated_pg_engine)
