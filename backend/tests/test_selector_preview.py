"""Unit tests for the visual selector preview (no DB, no network)."""

from __future__ import annotations

import pytest

from app.services.fetcher import FetchResult
from app.services.selector_preview import (
    PREVIEW_MAX_CHARS,
    PreviewError,
    fetch_selector_preview,
    sanitize_preview_html,
)


def test_strips_scripts_frames_and_handlers() -> None:
    html = (
        "<html><head><title>T</title><script>alert(1)</script></head>"
        "<body><iframe src='https://ads.example/x'></iframe>"
        "<a href='javascript:alert(1)' onclick='evil()' class='post'>hi</a></body></html>"
    )
    out = sanitize_preview_html(html, "https://example.com/page")
    assert "<script" not in out
    assert "<iframe" not in out
    assert "onclick" not in out
    assert "javascript:" not in out
    assert 'class="post"' in out
    assert ">hi</a>" in out


def test_neutralizes_data_uri_src() -> None:
    html = "<html><body><img src='data:text/html,<script>alert(1)</script>'></body></html>"
    out = sanitize_preview_html(html, "https://example.com/")
    assert "data:" not in out


def test_injects_base_after_head() -> None:
    out = sanitize_preview_html(
        "<html><head><title>T</title></head><body></body></html>", "https://example.com/a"
    )
    head_pos = out.lower().index("<head>")
    base_pos = out.lower().index('<base href="https://example.com/a">')
    assert base_pos > head_pos


def test_replaces_existing_base() -> None:
    out = sanitize_preview_html(
        '<html><head><base href="https://evil.example/"></head><body></body></html>',
        "https://example.com/a",
    )
    assert out.count("<base") == 1
    assert "evil.example" not in out


def test_rejects_non_html(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_fetch(url: str, **kwargs: object) -> FetchResult:
        return FetchResult(
            final_url=url,
            status_code=200,
            content=b"%PDF-1.4",
            text="",
            content_type="application/pdf",
            latency_ms=1,
        )

    monkeypatch.setattr("app.services.selector_preview.fetch_url", _fake_fetch)
    with pytest.raises(PreviewError) as exc:
        fetch_selector_preview("https://example.com/doc.pdf")
    assert exc.value.code == "unsupported_content_type"


def test_truncates_huge_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    big = "<html><body>" + ("x" * (PREVIEW_MAX_CHARS + 100)) + "</body></html>"

    def _fake_fetch(url: str, **kwargs: object) -> FetchResult:
        return FetchResult(
            final_url=url,
            status_code=200,
            content=b"",
            text=big,
            content_type="text/html",
            latency_ms=1,
        )

    monkeypatch.setattr("app.services.selector_preview.fetch_url", _fake_fetch)
    preview = fetch_selector_preview("https://example.com/big")
    assert preview.truncated is True
    assert "preview truncated" in preview.html


def test_happy_path_sanitizes(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_fetch(url: str, **kwargs: object) -> FetchResult:
        return FetchResult(
            final_url="https://example.com/final",
            status_code=200,
            content=b"",
            text="<html><head></head><body><article class='post'><h2>Hi</h2></article>"
            "<script>evil()</script></body></html>",
            content_type="text/html; charset=utf-8",
            latency_ms=1,
        )

    monkeypatch.setattr("app.services.selector_preview.fetch_url", _fake_fetch)
    preview = fetch_selector_preview("https://example.com/")
    assert preview.final_url == "https://example.com/final"
    assert preview.truncated is False
    assert "evil()" not in preview.html
    assert "post" in preview.html
    assert '<base href="https://example.com/final">' in preview.html


def test_blocks_private_target_without_network() -> None:
    # 127.0.0.1 is rejected by SSRF validation before any connection attempt.
    with pytest.raises(PreviewError) as exc:
        fetch_selector_preview("http://127.0.0.1/admin")
    assert exc.value.code == "blocked_address"
