"""Tests for the Phase 9 security_scan mode (Cloudflare URL Scanner)."""

import httpx
import pytest

import app.services.security_scan as ss
from app.config import Settings
from app.services.fetcher import FetchError
from app.services.security_scan import scan_digest_text

# A trimmed URL Scanner v2 result payload.
_RESULT = {
    "task": {
        "uuid": "scan",
        "status": "finished",
        "domain": "example.com",
        "apexDomain": "example.com",
    },
    "verdicts": {
        "overall": {
            "malicious": False,
            "hasVerdicts": False,
            "categories": ["beta-category", "alphabet-category"],
            "tags": ["tag2", "tag1"],
        }
    },
    "lists": {
        "asns": ["15169"],
        "servers": ["cloudflare"],
        "certificates": [
            {
                "issuer": "Let's Encrypt",
                "subjectName": "example.com",
                "validFrom": 1,
                "validTo": 2,
            }
        ],
    },
    # Shape from Cloudflare's URL Scanner v2 result schema.
    "meta": {
        "processors": {
            "wappa": {
                "data": [
                    {"app": "nginx", "confidenceTotal": 100, "categories": []},
                    {"app": "Python", "confidenceTotal": 50, "categories": []},
                    {"app": "nginx", "confidenceTotal": 75, "categories": []},
                ]
            }
        }
    },
}


def test_monitor_modes_wiring() -> None:
    from app.models.entities import (
        LIST_DIFF_MODES,
        MONITOR_MODES,
        PLAIN_HTTP_MODES,
    )

    assert "security_scan" in MONITOR_MODES
    assert "security_scan" in PLAIN_HTTP_MODES
    assert "security_scan" in LIST_DIFF_MODES


def test_schemas_reject_js_required_for_security_scan() -> None:
    from app.schemas import MonitorCreate

    with pytest.raises(ValueError):
        MonitorCreate(
            workspace_id="00000000-0000-0000-0000-000000000000",
            name="scan",
            url="https://example.com/",
            mode="security_scan",
            js_required=True,
            schedule_interval_minutes=1440,
        )


def test_digest_is_deterministic_and_one_fact_per_line() -> None:
    first = scan_digest_text(_RESULT)
    second = scan_digest_text(_RESULT)
    assert first == second  # stable ordering — same scan, same text
    lines = first.splitlines()
    # one fact per line, and deduped tech facts
    assert "malicious=false" in lines
    assert any(line.startswith("categories=alphabet-category,beta-category") for line in lines)
    assert any(line.startswith("tags=tag1,tag2") for line in lines)
    assert "tech=Python" in lines
    assert lines.count("tech=nginx") == 1  # duplicate technologies collapsed
    assert "certificate=example.com issuer=Let's Encrypt" in lines
    assert not any("{" in line for line in lines)  # no stringified dicts
    assert "asn=15169" in lines


def test_digest_flips_on_verdict_change() -> None:
    changed = dict(_RESULT)
    changed["verdicts"] = {
        "overall": {"malicious": True, "hasVerdicts": True, "categories": [], "tags": []}
    }
    before = set(scan_digest_text(_RESULT).splitlines())
    after = {line for line in scan_digest_text(changed).splitlines() if line not in before}
    assert "malicious=true" in after


def test_digest_drops_volatile_counters() -> None:
    noisy = dict(_RESULT)
    noisy["data"] = {"requests": [], "links": [{"href": "/a"}], "cookies": [{"name": "x"}]}
    text = scan_digest_text(noisy)
    assert "links=" not in text
    assert "cookies=" not in text


def test_missing_configuration_is_a_clean_fetch_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.security_scan.get_settings",
        lambda: Settings(app_env="test", cloudflare_account_id="", cloudflare_urlscanner_token=""),
    )
    with pytest.raises(FetchError) as exc:
        ss.scan_url("https://example.com", timeout_seconds=30, max_response_bytes=10**6)
    assert exc.value.code == "scan_not_configured"


def test_scanner_ok_returns_config(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.security_scan.get_settings",
        lambda: Settings(
            app_env="test",
            cloudflare_account_id="acct",
            cloudflare_urlscanner_token="tok",
        ),
    )
    assert ss.scanner_ok() == ("acct", "tok")


def test_digest_ignores_certificate_validity_and_confidence() -> None:
    renewed = {
        **_RESULT,
        "lists": {
            **_RESULT["lists"],
            "certificates": [
                {
                    "issuer": "Let's Encrypt",
                    "subjectName": "example.com",
                    "validFrom": 99,
                    "validTo": 100,
                }
            ],
        },
    }
    assert scan_digest_text(renewed) == scan_digest_text(_RESULT)


def test_poll_waits_through_404_then_accepts_200_without_status(monkeypatch) -> None:
    monkeypatch.setattr(ss.time, "sleep", lambda _s: None)
    responses = [
        httpx.Response(404),
        httpx.Response(200, json={"verdicts": {}, "task": {"success": True}}),
    ]

    class FakeClient:
        def get(self, url: str, **kwargs: object) -> httpx.Response:
            return responses.pop(0)

    result = ss._poll_result(FakeClient(), "acct", "tok", "scan-id", 30)
    assert result["task"]["success"] is True
    assert responses == []


def test_poll_accepts_capitalized_status_and_rejects_failed_scan(monkeypatch) -> None:
    monkeypatch.setattr(ss.time, "sleep", lambda _s: None)

    class Finished:
        def get(self, url: str, **kwargs: object) -> httpx.Response:
            return httpx.Response(200, json={"task": {"status": "Finished"}})

    assert ss._poll_result(Finished(), "a", "t", "s", 30)["task"]["status"] == "Finished"

    class Failed:
        def get(self, url: str, **kwargs: object) -> httpx.Response:
            return httpx.Response(200, json={"task": {"success": False}})

    class FailedWithReason:
        def get(self, url: str, **kwargs: object) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "task": {
                        "success": False,
                        "errors": [{"message": "hostname was recently scanned", "code": 5021}],
                    }
                },
            )

    with pytest.raises(FetchError):
        ss._poll_result(Failed(), "a", "t", "s", 30)
    with pytest.raises(FetchError, match="recently scanned"):
        ss._poll_result(FailedWithReason(), "a", "t", "s", 30)


def test_digest_omits_empty_certificate_issuer() -> None:
    result = {
        **_RESULT,
        "lists": {"certificates": [{"issuer": "", "subjectName": "a.example"}]},
    }
    assert "certificate=a.example" in scan_digest_text(result).splitlines()


def test_scanner_uses_bearer_token_for_submit_and_poll() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.authorization_headers: list[str] = []

        def post(self, url: str, *, headers: dict[str, str], **kwargs: object) -> httpx.Response:
            self.authorization_headers.append(headers["Authorization"])
            return httpx.Response(200, json={"uuid": "scan-id"})

        def get(self, url: str, *, headers: dict[str, str], **kwargs: object) -> httpx.Response:
            self.authorization_headers.append(headers["Authorization"])
            return httpx.Response(200, json={"task": {"status": "finished"}})

    client = FakeClient()

    scan_id = ss._submit_scan(client, "account-id", "secret-token", "https://example.com")
    result = ss._poll_result(client, "account-id", "secret-token", scan_id, 30)

    assert result == {"task": {"status": "finished"}}
    assert client.authorization_headers == ["Bearer secret-token", "Bearer secret-token"]
