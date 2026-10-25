"""Unit tests for the readme mode fetch path (mocked fetch_url only)."""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock

import pytest

from app.services import readme as readme_mod
from app.services.fetcher import FetchError, FetchResult
from app.services.readme import (
    GitHubRateLimited,
    _candidate_raw_urls,
    _fetch_github_api_readme,
    parse_github_repo,
)


def _api_result(payload: dict, status_code: int = 200, text: str | None = None) -> FetchResult:
    return FetchResult(
        final_url="https://api.github.com/repos/o/r/readme",
        status_code=status_code,
        content=(text or json.dumps(payload)).encode(),
        text=text if text is not None else json.dumps(payload),
        content_type="application/json",
        latency_ms=5,
    )


def _readme_payload(content: bytes) -> dict:
    return {
        "content": base64.b64encode(content).decode(),
        "encoding": "base64",
        "download_url": "https://raw.githubusercontent.com/o/r/dev/README.md",
    }


class TestParseGithubRepo:
    def test_mid_url_git_suffix_is_stripped(self):
        # Regression: the .git strip only handled inputs *ending* in .git, so
        # ".../r.git/tree/main" fed the raw "r.git" segment into both the
        # api.github.com URL and raw.githubusercontent.com — guaranteed 404s.
        assert parse_github_repo("https://github.com/o/r.git/tree/main") == ("o", "r", "main")
        assert parse_github_repo("https://github.com/o/r.git") == ("o", "r", None)

    def test_shorthand_unchanged(self):
        assert parse_github_repo("owner/repo") == ("owner", "repo", None)

    def test_branch_hint_detected(self):
        assert parse_github_repo("https://github.com/o/r/tree/feature/x") == (
            "o",
            "r",
            "feature/x",
        )


class TestApiBranchHint:
    def test_branch_hint_pinned_via_ref_query(self, monkeypatch):
        captured: dict = {}

        def fake_fetch(url, **kwargs):
            captured["url"] = url
            return _api_result(_readme_payload(b"# Title\n"))

        monkeypatch.setattr(readme_mod, "fetch_url", fake_fetch)
        result = _fetch_github_api_readme(
            "o",
            "r",
            timeout_seconds=10,
            max_response_bytes=2_000_000,
            branch_hint="dev",
        )
        # Regression: without ?ref= the API returns the default-branch README,
        # so a /tree/<branch> monitor silently tracked the wrong branch.
        assert captured["url"] == "https://api.github.com/repos/o/r/readme?ref=dev"
        assert result is not None
        assert result[0].startswith("# Title")

    def test_branch_hint_with_slash_is_percent_encoded(self, monkeypatch):
        captured: dict = {}

        def fake_fetch(url, **kwargs):
            captured["url"] = url
            return _api_result(_readme_payload(b"# Hi\n"))

        monkeypatch.setattr(readme_mod, "fetch_url", fake_fetch)
        _fetch_github_api_readme(
            "o",
            "r",
            timeout_seconds=10,
            max_response_bytes=2_000_000,
            branch_hint="feature/x",
        )
        assert captured["url"].endswith("readme?ref=feature%2Fx")

    def test_no_branch_hint_leaves_clean_url(self, monkeypatch):
        captured: dict = {}

        def fake_fetch(url, **kwargs):
            captured["url"] = url
            return _api_result(_readme_payload(b"# Hi\n"))

        monkeypatch.setattr(readme_mod, "fetch_url", fake_fetch)
        _fetch_github_api_readme("o", "r", timeout_seconds=10, max_response_bytes=2_000_000)
        assert captured["url"] == "https://api.github.com/repos/o/r/readme"

    def test_rate_limit_raises_and_counts(self, monkeypatch):
        monkeypatch.setattr(
            readme_mod,
            "fetch_url",
            MagicMock(
                return_value=_api_result(
                    {}, status_code=403, text='{"message":"API rate limit exceeded"}'
                )
            ),
        )
        with pytest.raises(GitHubRateLimited):
            _fetch_github_api_readme("o", "r", timeout_seconds=10, max_response_bytes=2_000_000)


class TestRawProbeBudget:
    def test_budget_exhaustion_stops_fanout_and_mentions_it(self, monkeypatch):
        """Regression: (branch_hint + main + master) x 7 filenames = 21 probes
        x 10s could exceed the worker's 120s dramatiq time_limit and get the
        run killed with no recorded error. The wall-clock budget must cut the
        fan-out and surface the reason in the error message."""
        calls: list[str] = []

        def fake_fetch(url, **kwargs):
            calls.append(url)
            raise FetchError("connection_timeout", f"simulated hang for {url}")

        monkeypatch.setattr(readme_mod, "fetch_url", fake_fetch)
        monkeypatch.setattr(readme_mod, "_RAW_PROBE_BUDGET_SECONDS", 0.0)

        with pytest.raises(readme_mod.ExtractionError) as exc_info:
            readme_mod.fetch_readme_text("https://github.com/o/r/tree/dev")

        assert "budget" in str(exc_info.value).lower()
        # The API attempt (1 call) plus zero-or-one probes — never the
        # unbounded fan-out that would blow the worker time limit.
        assert len(calls) <= 2

    def test_fanout_candidate_count(self):
        # 3 branches x 7 filenames with dedupe: branch hint plus main/master.
        urls = _candidate_raw_urls("o", "r", "dev")
        assert len(urls) == 21
        assert urls[0] == "https://raw.githubusercontent.com/o/r/dev/README.md"

    def test_full_pipeline_returns_raw_fallback(self, monkeypatch):
        """API transport failure falls through to raw probes and succeeds."""

        def fake_fetch(url, **kwargs):
            if "api.github.com" in url:
                raise FetchError("dns_error", "simulated transport failure")
            return FetchResult(
                final_url=url,
                status_code=200,
                content=b"# Raw\n",
                text="# Raw\n",
                content_type="text/plain",
                latency_ms=5,
            )

        monkeypatch.setattr(readme_mod, "fetch_url", fake_fetch)
        text, final_url = readme_mod.fetch_readme_text("https://github.com/o/r/tree/dev")
        assert text.startswith("# Raw")
        assert "/dev/README" in final_url  # branch hint is probed first

    def test_rate_limited_final_message_mentions_it(self, monkeypatch):
        def fake_fetch(url, **kwargs):
            if "api.github.com" in url:
                return _api_result(
                    {}, status_code=403, text='{"message":"API rate limit exceeded"}'
                )
            raise FetchError("http_error", f"HTTP 404 for {url}")

        monkeypatch.setattr(readme_mod, "fetch_url", fake_fetch)
        with pytest.raises(readme_mod.ExtractionError) as exc_info:
            readme_mod.fetch_readme_text("owner/repo")
        assert "rate limit" in str(exc_info.value).lower()
