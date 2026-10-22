"""Tests for the storage key-prefix -> bucket routing contract.

Screenshot objects (``screenshots/...``) route to the dedicated public bucket
when ``S3_SCREENSHOT_BUCKET`` is set; everything else stays in the primary
bucket. Every storage function must agree on that routing — this file exists
because ``delete_object`` silently disagreed with ``put_bytes``/``get_bytes``
once already (review find #1, 2026-10-21).
"""

from __future__ import annotations

import app.services.storage as storage
from app.config import Settings


def _settings(s3_screenshot_bucket: str | None) -> Settings:
    """S3-mode settings with a distinct primary bucket."""
    return Settings(
        app_env="test",
        storage_backend="s3",
        s3_endpoint_url="https://acct.r2.cloudflarestorage.com",
        s3_access_key="access",
        s3_secret_key="secret",
        s3_bucket="primary-bucket",
        s3_screenshot_bucket=s3_screenshot_bucket,
    )


def _patch_settings(bucket: str | None, monkeypatch) -> None:
    monkeypatch.setattr(storage, "get_settings", lambda: _settings(bucket))


def test_snapshot_keys_route_to_primary_bucket(monkeypatch) -> None:
    _patch_settings("public-bucket", monkeypatch)
    assert storage._bucket_for("workspaces/ws1/monitors/m1/runs/r1/x.html") == "primary-bucket"
    assert storage._bucket_for("brand-assets/whatever.png") == "primary-bucket"


def test_screenshot_keys_route_to_public_bucket(monkeypatch) -> None:
    _patch_settings("public-bucket", monkeypatch)
    assert storage._bucket_for("screenshots/m1/r1.png") == "public-bucket"


def test_screenshot_keys_fall_back_without_public_bucket(monkeypatch) -> None:
    """Unset S3_SCREENSHOT_BUCKET = screenshots live in the primary bucket
    (legacy proxy behaviour)."""
    _patch_settings(None, monkeypatch)
    assert storage._bucket_for("screenshots/m1/r1.png") == "primary-bucket"


class _FakeS3:
    def __init__(self) -> None:
        self.deletes: list[tuple[str, str]] = []

    def delete_object(self, Bucket: str, Key: str) -> None:  # noqa: A002 - boto3 API name
        self.deletes.append((Bucket, Key))


def test_delete_object_uses_routed_bucket_for_screenshots(monkeypatch) -> None:
    """Regression: delete_object must target the bucket the object was
    written to, not hardcode the primary bucket."""
    _patch_settings("public-bucket", monkeypatch)
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    storage.delete_object("screenshots/m1/r1.png")
    storage.delete_object("workspaces/ws1/runs/r1/x.html")

    assert fake.deletes == [
        ("public-bucket", "screenshots/m1/r1.png"),
        ("primary-bucket", "workspaces/ws1/runs/r1/x.html"),
    ]
