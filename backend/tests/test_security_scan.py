"""Tests for the Phase 9 security_scan mode (Cloudflare URL Scanner)."""

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
        "certificates": ["CN=example.com"],
    },
    "meta": {
        "processors": {
            "wappa": {
                "data": [
                    {
                        "requestId": "1",
                        "technologies": [
                            {"name": "nginx", "version": ""},
                            {"name": "Python", "version": "3.12"},
                        ],
                    },
                    {
                        "requestId": "2",
                        "technologies": [{"name": "nginx", "version": ""}],
                    },
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
    assert any(line == "tech=Python 3.12" for line in lines)
    assert lines.count("tech=nginx") == 1  # duplicate technologies collapsed
    assert "certificate=CN=example.com" in lines
    assert "asn=15169" in lines


def test_digest_flips_on_verdict_change() -> None:
    changed = dict(_RESULT)
    changed["verdicts"] = {
        "overall": {"malicious": True, "hasVerdicts": True, "categories": [], "tags": []}
    }
    before = set(scan_digest_text(_RESULT).splitlines())
    after = {
        line
        for line in scan_digest_text(changed).splitlines()
        if line not in before
    }
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
        lambda: Settings(
            app_env="test", cloudflare_account_id="", cloudflare_urlscanner_token=""
        ),
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
