"""Workspace BYO secrets encryption at rest using Fernet (AES-128-CBC+HMAC).

Derives a stable 32-byte key from SECRET_KEY via SHA-256 so rotation
invalidates old ciphertext (expected). Existing plaintext rows are readable
via fallback.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

_ENCRYPTED_PREFIX = "enc:v1:"


def _fernet() -> object | None:
    try:
        from cryptography.fernet import Fernet  # type: ignore
    except ImportError:
        return None
    settings = get_settings()
    # Derive 32-byte urlsafe key from SECRET_KEY
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    f = _fernet()
    if f is None:
        return plaintext
    token = f.encrypt(plaintext.encode()).decode()  # type: ignore[attr-defined]
    return f"{_ENCRYPTED_PREFIX}{token}"


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    if not value.startswith(_ENCRYPTED_PREFIX):
        # Legacy plaintext
        return value
    f = _fernet()
    if f is None:
        return None
    raw = value[len(_ENCRYPTED_PREFIX) :]
    try:
        return f.decrypt(raw.encode()).decode()  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        logger.warning("decrypt_failed error=%s", exc)
        return None


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(_ENCRYPTED_PREFIX))
