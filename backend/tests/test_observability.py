"""Optional Sentry wiring: off without a DSN, and credentials are scrubbed."""

from __future__ import annotations

from types import SimpleNamespace

from app.observability import init_error_tracking, scrub_event


def test_disabled_without_a_dsn() -> None:
    for dsn in (None, "", "   "):
        settings = SimpleNamespace(sentry_dsn=dsn, app_env="production")
        assert init_error_tracking(settings) is False  # type: ignore[arg-type]


def test_scrub_event_filters_credential_headers_and_cookies() -> None:
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret",
                "X-Internal-Token": "tok",
                "Cookie": "a=b",
                "User-Agent": "curl",
            },
            "cookies": {"a": "b"},
        }
    }
    out = scrub_event(event)
    headers = out["request"]["headers"]
    assert headers["Authorization"] == "[Filtered]"
    assert headers["X-Internal-Token"] == "[Filtered]"
    assert headers["Cookie"] == "[Filtered]"
    assert headers["User-Agent"] == "curl"
    assert "cookies" not in out["request"]


def test_scrub_event_tolerates_events_without_a_request() -> None:
    assert scrub_event({"message": "boom"}) == {"message": "boom"}
