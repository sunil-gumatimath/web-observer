from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.entities import Snapshot
from app.routers.monitors import get_snapshot, get_snapshot_raw
from app.services.storage import StorageError


def test_get_snapshot_screenshots_fallback():
    ws_id = uuid.uuid4()
    snap_id = uuid.uuid4()
    mon_id = uuid.uuid4()
    run_id = uuid.uuid4()

    mock_snap = Snapshot(
        id=snap_id,
        workspace_id=ws_id,
        monitor_id=mon_id,
        run_id=run_id,
        content_hash="abcd",
        normalized_text="ahash:0000\nsha256:1234",
        raw_object_key="screenshots/test.png",
        content_type="image/png",
        byte_size=1024,
        created_at=datetime.now(UTC),
    )

    db = MagicMock()
    db.scalar.return_value = mock_snap

    with patch(
        "app.routers.monitors.presigned_get_url", side_effect=StorageError("local", "no s3")
    ):
        res = get_snapshot(
            workspace_id=ws_id,
            snapshot_id=snap_id,
            db=db,
            _workspace=MagicMock(),
        )

    assert res.raw_download_url == "/api/v1/public/assets/screenshots/test.png"
    assert res.normalized_text == "ahash:0000\nsha256:1234"


def test_get_snapshot_raw_fallback():
    ws_id = uuid.uuid4()
    snap_id = uuid.uuid4()
    mon_id = uuid.uuid4()
    run_id = uuid.uuid4()

    mock_snap = Snapshot(
        id=snap_id,
        workspace_id=ws_id,
        monitor_id=mon_id,
        run_id=run_id,
        content_hash="abcd",
        normalized_text="Hello world",
        raw_object_key="workspaces/raw.html",
        content_type="text/html",
        byte_size=500,
        created_at=datetime.now(UTC),
    )

    db = MagicMock()
    db.scalar.return_value = mock_snap

    with patch(
        "app.routers.monitors.presigned_get_url", side_effect=StorageError("local", "no s3")
    ):
        res = get_snapshot(
            workspace_id=ws_id,
            snapshot_id=snap_id,
            db=db,
            _workspace=MagicMock(),
        )

    assert res.raw_download_url == f"/api/v1/workspaces/{ws_id}/snapshots/{snap_id}/raw"


def test_get_snapshot_raw_endpoint_serves_bytes():
    ws_id = uuid.uuid4()
    snap_id = uuid.uuid4()
    mon_id = uuid.uuid4()
    run_id = uuid.uuid4()

    mock_snap = Snapshot(
        id=snap_id,
        workspace_id=ws_id,
        monitor_id=mon_id,
        run_id=run_id,
        content_hash="abcd",
        normalized_text="test",
        raw_object_key="workspaces/raw.html",
        content_type="text/html; charset=utf-8",
        byte_size=12,
        created_at=datetime.now(UTC),
    )

    db = MagicMock()
    db.scalar.return_value = mock_snap

    with patch("app.routers.monitors.get_bytes", return_value=b"<html></html>"):
        response = get_snapshot_raw(
            workspace_id=ws_id,
            snapshot_id=snap_id,
            db=db,
            _workspace=MagicMock(),
        )

    assert response.body == b"<html></html>"
    assert response.media_type == "text/html; charset=utf-8"


def test_get_snapshot_raw_endpoint_404_when_missing():
    ws_id = uuid.uuid4()
    snap_id = uuid.uuid4()

    db = MagicMock()
    db.scalar.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        get_snapshot_raw(
            workspace_id=ws_id,
            snapshot_id=snap_id,
            db=db,
            _workspace=MagicMock(),
        )
    assert exc_info.value.status_code == 404
