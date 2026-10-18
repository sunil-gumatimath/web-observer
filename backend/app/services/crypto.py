"""Workspace BYO secrets encryption at rest using Fernet (AES-128-CBC+HMAC).

Keys are derived from SECRET_KEY with HKDF (RFC 5869) and a per-purpose
``info`` label, so the Fernet encryption key is *not* the same material that
API-key and share/invite HMACs use (key separation: a leak or reuse of one
purpose's key should not compromise the others).

Ciphertext is versioned with a scheme prefix so key material can evolve
without a hard cutover:

* ``enc:v2:<token>`` — HKDF-derived key (writes always use this).
* ``enc:v1:<token>`` — legacy ``sha256(SECRET_KEY)`` key (verify-only dual
  read; re-encrypted on the next write via model validators).
* bare plaintext — pre-encryption rows (dual read; writes fail closed).

Rotating SECRET_KEY invalidates every stored ciphertext (documented
behaviour); the version prefix exists so future releases can introduce a
newer derivation without breaking the previous one.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

_V2_PREFIX = "enc:v2:"
_V1_PREFIX = "enc:v1:"

# Purpose labels: SHA256(secret_key) as the sole input for Fernet was not
# domain-separated from the other uses of SECRET_KEY (API-key HMAC, token
# HMAC). Each purpose now derives its own HKDF branch.
_FERNET_PURPOSE = b"web-observer:fernet:workspace-secrets:v2"


def _hkdf_key(purpose: bytes) -> bytes | None:
    """32-byte HKDF-derived key for *purpose*, urlsafe-b64 encoded for Fernet.

    Returns None when the cryptography backend is unavailable (the v1 path in
    tests monkeypatches ``_fernet`` anyway; hashing purposes use
    :func:`derive_purpose_key` which has a fallback).
    """
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    except ImportError:
        return None
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=purpose,
    )
    return hkdf.derive(get_settings().secret_key.encode())


def derive_purpose_key(purpose: bytes) -> bytes:
    """HKDF-derived 32-byte key for an HMAC purpose.

    Falls back to a domain-separated SHA-256 thunk when the cryptography
    package is missing so verification never breaks merely because an optional
    dep is absent (the fallback value is the same on every process that also
    lacks the package — it must NOT be mixed with HKDF-derived hash values,
    which is why the scheme prefixes in api_keys/tokens distinguish versions).
    """
    key = _hkdf_key(purpose)
    if key is not None:
        return key
    digest = hashlib.sha256(b"fallback:" + purpose + b":" + get_settings().secret_key.encode())
    return digest.digest()


def _v1_key() -> bytes:
    # Legacy derivation, kept byte-identical so enc:v1 rows keep decrypting.
    digest = hashlib.sha256(get_settings().secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> object | None:
    try:
        from cryptography.fernet import Fernet  # type: ignore
    except ImportError:
        return None
    key = _hkdf_key(_FERNET_PURPOSE)
    if key is None:
        # Fail closed rather than silently degrading to the legacy key for
        # NEW ciphertext: encryption must not produce material the reader
        # cannot version-distinguish.
        return None
    # Fernet expects the 32-byte key urlsafe-base64 encoded.
    return Fernet(base64.urlsafe_b64encode(key))


def _legacy_v1_fernet() -> object | None:
    try:
        from cryptography.fernet import Fernet  # type: ignore
    except ImportError:
        return None
    return Fernet(_v1_key())


def encrypt_secret(plaintext: str) -> str:
    # Fail closed: never silently persist plaintext when the crypto backend
    # is unavailable. Callers (webhook writes) must surface the error.
    f = _fernet()
    if f is None:
        raise RuntimeError("cannot encrypt secret: cryptography backend missing")
    token = f.encrypt(plaintext.encode()).decode()  # type: ignore[attr-defined]
    return f"{_V2_PREFIX}{token}"


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith(_V2_PREFIX):
        f = _fernet()
        if f is None:
            return None
        raw = value[len(_V2_PREFIX) :]
        try:
            return f.decrypt(raw.encode()).decode()  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            logger.warning("decrypt_failed error=%s", exc)
            return None
    if value.startswith(_V1_PREFIX):
        # Legacy sha256(SECRET_KEY)-derived ciphertext: verify-only.
        f = _legacy_v1_fernet()
        if f is None:
            return None
        raw = value[len(_V1_PREFIX) :]
        try:
            return f.decrypt(raw.encode()).decode()  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            logger.warning("decrypt_legacy_failed error=%s", exc)
            return None
    # Legacy plaintext rows pre-dating encryption-at-rest stay readable.
    # Dual-read only: new writes always go through encrypt_secret, and
    # legacy values are re-encrypted on next write (model validator).
    return value


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith((_V2_PREFIX, _V1_PREFIX)))
