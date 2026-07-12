"""Shared fixtures. Integration tests use PostgreSQL when available."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import *  # noqa: F401,F403


def _pg_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://monitor:monitor@localhost:5432/web_observer_test",
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


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    if not postgres_available():
        pytest.skip(
            "PostgreSQL test DB not available. "
            "Create DB web_observer_test or set TEST_DATABASE_URL (must contain 'test')."
        )
    url = _pg_url()
    engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
