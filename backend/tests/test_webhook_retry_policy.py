"""Webhook retry policy: which statuses retry, and how long the backoff is."""

from __future__ import annotations

import pytest

from app.services.webhooks import _backoff_seconds, _is_retryable_status


@pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504])
def test_transient_statuses_are_retried(status: int) -> None:
    assert _is_retryable_status(status) is True


@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 410, 413, 422])
def test_client_rejections_are_terminal(status: int) -> None:
    assert _is_retryable_status(status) is False


def test_backoff_grows_and_is_capped() -> None:
    assert [_backoff_seconds(n) for n in (1, 2, 3, 4, 5)] == [30, 120, 480, 1800, 1800]


def test_backoff_tolerates_a_zero_attempt_count() -> None:
    assert _backoff_seconds(0) == 30
