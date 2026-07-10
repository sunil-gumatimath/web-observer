"""Fetcher redirect SSRF tests using a local httpx mock transport."""

from __future__ import annotations

import httpx
import pytest

from app.services.fetcher import FetchError, fetch_url


class _RedirectToPrivateTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/start"):
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"}, request=request)
        return httpx.Response(200, text="ok", request=request)


def test_redirect_to_loopback_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure we do not follow redirects into blocked addresses.

    We patch httpx.Client so the first response is a redirect to 127.0.0.1;
    validation on the next hop must raise before any private request.
    """

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self._step = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str, **kwargs):
            # First call may be robots.txt — allow miss
            if url.endswith("robots.txt"):
                return httpx.Response(404, request=httpx.Request("GET", url))
            if self._step == 0:
                self._step += 1
                return httpx.Response(
                    302,
                    headers={"Location": "http://127.0.0.1/secret"},
                    request=httpx.Request("GET", url),
                )
            # Should never be called for private IP after SSRF check
            raise AssertionError(f"fetcher attempted private request: {url}")

    monkeypatch.setattr("app.services.fetcher.httpx.Client", FakeClient)

    with pytest.raises(FetchError) as exc:
        # Use a public host that passes initial SSRF; redirect target is blocked
        fetch_url(
            "https://example.com/start",
            timeout_seconds=10,
            max_response_bytes=1_000_000,
            respect_robots=True,
        )
    assert exc.value.code == "blocked_address"


def test_max_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    class LoopClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str, **kwargs):
            if url.endswith("robots.txt"):
                return httpx.Response(404, request=httpx.Request("GET", url))
            return httpx.Response(
                302,
                headers={"Location": "https://example.com/next"},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr("app.services.fetcher.httpx.Client", LoopClient)

    with pytest.raises(FetchError) as exc:
        fetch_url(
            "https://example.com/start",
            timeout_seconds=10,
            max_response_bytes=1_000_000,
            respect_robots=False,
        )
    assert exc.value.code == "redirect_limit"
