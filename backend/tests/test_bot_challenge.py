"""Tests for Cloudflare/Turnstile bot-challenge detection."""

from __future__ import annotations

from app.services.fetcher import detect_bot_challenge


def test_no_markers_is_clear() -> None:
    assert (
        detect_bot_challenge(
            status_code=200,
            headers={"content-type": "text/html"},
            text="<html><body>hello world</body></html>",
        )
        is None
    )


def test_403_without_challenge_content_is_clear() -> None:
    assert (
        detect_bot_challenge(
            status_code=403,
            headers={"server": "nginx"},
            text="<html>forbidden</html>",
        )
        is None
    )


def test_cf_mitigated_header() -> None:
    reason = detect_bot_challenge(
        status_code=200,
        headers={"cf-mitigated": "challenge"},
        text="<html>anything</html>",
    )
    assert reason is not None
    assert "cf-mitigated" in reason


def test_turnstile_widget_marker() -> None:
    html = (
        '<div class="cf-turnstile" data-sitekey="x"></div>'
        '<script src="/cdn-cgi/challenge-platform/h/orchestrate/jsch/v1"></script>'
    )
    reason = detect_bot_challenge(status_code=200, text=html)
    assert reason is not None
    assert "cf-turnstile" in reason or "challenge-platform" in reason


def test_classic_interstitial_needs_two_weak_markers() -> None:
    html = "Just a moment...<noscript>Please turn on JavaScript and cookies to continue.</noscript>"
    assert detect_bot_challenge(status_code=403, text=html) is None
    html2 = html + " Checking your browser before accessing the site."
    reason = detect_bot_challenge(status_code=403, text=html2)
    assert reason is not None


def test_single_weak_marker_is_ignored() -> None:
    assert (
        detect_bot_challenge(status_code=200, text="Just a moment please, loading...")
        is None
    )
