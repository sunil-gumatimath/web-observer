"""/metrics runs its aggregate queries at most once per TTL."""

from __future__ import annotations

import pytest

from app import main as main_module


class _CountingDB:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def scalar(self, _stmt):
        self.calls += 1
        if self.fail:
            raise RuntimeError("db down")
        return 7


@pytest.fixture(autouse=True)
def _reset_cache():
    main_module._metrics_cache = None
    yield
    main_module._metrics_cache = None


def _scrape(db) -> str:
    # ``__wrapped__`` skips slowapi's request-bound wrapper (same trick as
    # test_auth_request_path.py).
    resp = main_module.metrics.__wrapped__(None, db)  # type: ignore[attr-defined]
    return bytes(resp.body).decode()


def test_second_scrape_is_served_from_cache() -> None:
    db = _CountingDB()
    first = _scrape(db)
    calls_after_first = db.calls
    assert calls_after_first == 5
    assert "webobserver_monitors_total 7" in first
    assert _scrape(db) == first
    assert db.calls == calls_after_first


def test_cache_expires_after_the_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _CountingDB()
    _scrape(db)
    stamp, body = main_module._metrics_cache  # type: ignore[misc]
    monkeypatch.setattr(
        main_module, "_metrics_cache", (stamp - main_module._METRICS_TTL_SECONDS - 1, body)
    )
    _scrape(db)
    assert db.calls == 10


def test_failed_scrape_is_not_cached() -> None:
    failing = _CountingDB(fail=True)
    body = _scrape(failing)
    assert "webobserver_monitors_total 0" in body
    assert main_module._metrics_cache is None
    # The next scrape retries the database instead of replaying the zeros.
    healthy = _CountingDB()
    assert "webobserver_monitors_total 7" in _scrape(healthy)
