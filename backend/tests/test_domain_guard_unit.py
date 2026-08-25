from __future__ import annotations

import pytest

from app.services import domain_guard
from app.services.domain_guard import (
    DomainBlocked,
    acquire_domain_slot,
    domain_from_url,
    release_domain_slot,
)


def test_domain_from_url() -> None:
    assert domain_from_url("https://Example.COM/path") == "example.com"
    assert domain_from_url("http://sub.example.org:8080/") == "sub.example.org"


class _FakeRedis:
    """Minimal Redis stand-in for concurrency slot tests."""

    def __init__(self) -> None:
        self.data: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    def decr(self, key: str) -> int:
        self.data[key] = int(self.data.get(key, 0)) - 1
        return self.data[key]

    def expire(self, key: str, ttl: int) -> None:
        return None

    def delete(self, key: str) -> None:
        self.data.pop(key, None)

    def get(self, key: str):
        return self.data.get(key)


def test_acquire_domain_slot_rolls_back_when_over_limit(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(domain_guard, "_redis", lambda: fake)
    monkeypatch.setattr(
        domain_guard,
        "get_settings",
        lambda: type("S", (), {"per_domain_concurrency": 2})(),
    )

    acquire_domain_slot("example.com")
    acquire_domain_slot("example.com")
    assert fake.data["conc:example.com"] == 2

    with pytest.raises(DomainBlocked) as exc:
        acquire_domain_slot("example.com")
    assert "concurrency" in str(exc.value).lower()
    # Over-limit incr must be rolled back
    assert fake.data["conc:example.com"] == 2

    release_domain_slot("example.com")
    assert fake.data.get("conc:example.com", 0) == 1
