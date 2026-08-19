"""Object storage for raw snapshots (local filesystem or S3 / R2 / MinIO)."""

from __future__ import annotations

import logging
import uuid
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)


class StorageError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _use_local() -> bool:
    settings = get_settings()
    backend = (getattr(settings, "storage_backend", None) or "local").lower()
    if backend == "local":
        return True
    if backend == "s3":
        return False
    # auto: local if no endpoint
    return not settings.s3_endpoint_url


def _local_root() -> Path:
    settings = get_settings()
    root = Path(getattr(settings, "local_storage_path", None) or "./data/snapshots")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_local_path(key: str) -> Path | None:
    """Resolve ``key`` under the storage root, blocking path traversal.

    Returns *None* when the key escapes the storage root (or is otherwise
    unsafe), so callers can bail out instead of reading/writing an arbitrary
    file.  Object keys are always relative paths (``workspaces/...``,
    ``brand-assets/...``), so absolute paths or ``..`` segments are invalid.
    """
    root = _local_root().resolve()
    candidate = Path(key)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in key:
        logger.warning("storage_path_rejected key=%s", key)
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        logger.warning("storage_path_escape_rejected key=%s", key)
        return None
    return resolved


@lru_cache
def _client():
    import boto3

    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region or "auto",
    )


def snapshot_object_key(*, workspace_id: uuid.UUID, monitor_id: uuid.UUID, run_id: uuid.UUID) -> str:
    return (
        f"workspaces/{workspace_id}/monitors/{monitor_id}/"
        f"runs/{run_id}/{uuid.uuid4().hex}.html"
    )


def put_bytes(
    *,
    key: str,
    data: bytes,
    content_type: str = "text/html; charset=utf-8",
) -> str:
    if _use_local():
        path = _resolve_local_path(key)
        if path is None:
            raise StorageError("invalid_key", f"Unsafe storage key: {key}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    from botocore.exceptions import BotoCoreError, ClientError

    settings = get_settings()
    try:
        _client().put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.exception("storage_put_failed key=%s", key)
        raise StorageError("storage_failed", f"Failed to store object: {exc}") from exc
    return key

def get_bytes(key: str) -> bytes | None:
    if _use_local():
        path = _resolve_local_path(key)
        if path is None:
            return None
        try:
            if path.exists():
                return path.read_bytes()
        except OSError as exc:
            logger.warning("storage_get_failed key=%s error=%s", key, exc)
        return None

    from botocore.exceptions import BotoCoreError, ClientError
    settings = get_settings()
    try:
        response = _client().get_object(Bucket=settings.s3_bucket, Key=key)
        return response["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        logger.warning("storage_get_failed key=%s error=%s", key, exc)
        return None


def delete_object(key: str) -> None:
    if _use_local():
        path = _resolve_local_path(key)
        if path is None:
            return
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            logger.warning("storage_delete_failed key=%s error=%s", key, exc)
        return

    from botocore.exceptions import BotoCoreError, ClientError

    settings = get_settings()
    try:
        _client().delete_object(Bucket=settings.s3_bucket, Key=key)
    except (BotoCoreError, ClientError) as exc:
        logger.warning("storage_delete_failed key=%s error=%s", key, exc)


def presigned_get_url(key: str, *, expires_in: int = 3600) -> str:
    if _use_local():
        # Local-storage mode serves raw objects via the API snapshot endpoint
        # (normalized text), not via browser-usable URLs. Raising here lets
        # callers fall back to that endpoint instead of emitting a broken
        # file:// URI.
        raise StorageError(
            "local_not_supported",
            "Local storage serves objects via the API snapshot endpoint, not presigned URLs",
        )

    from botocore.exceptions import BotoCoreError, ClientError

    settings = get_settings()
    try:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": key},
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageError("storage_failed", f"Failed to sign URL: {exc}") from exc
