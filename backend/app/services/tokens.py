"""Opaque token generation + hashing for share links and team invites.

Only the token hash is ever stored in the database. The plaintext token is
returned exactly once at creation time and shown in the public URL. Raw
tokens must never be logged.

New tokens are HMAC-SHA-256 digests over an HKDF-derived purpose key
(domain-separated from the Fernet key), stored with a ``v2$`` scheme prefix.
Legacy rows still verify via dual-verify so old links keep working:

* ``v1$`` — HMAC keyed directly by SECRET_KEY (previous scheme, verify-only).
* unprefixed hex — unsalted SHA-256 digests from before HMAC (verify-only).

All newly issued tokens use the v2 scheme only.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from app.services.crypto import derive_purpose_key

HASH_PREFIX_LEN = 16
SCHEME_PREFIX = "v2$"
_LEGACY_SCHEME_PREFIX = "v1$"
_TOKEN_PURPOSE = b"web-observer:hmac:share-invite-tokens:v2"


def _hmac_key() -> bytes:
    return derive_purpose_key(_TOKEN_PURPOSE)


def new_token(*, prefix: str = "") -> tuple[str, str, str]:
    """Return ``(token, token_hash, token_prefix)``.

    ``token`` is an opaque, unguessable string. ``token_hash`` is the
    HMAC-SHA-256 digest (with scheme prefix) to persist. ``token_prefix`` is
    a short human-readable fragment.
    """
    random_part = secrets.token_urlsafe(24)
    # pi-lens-ignore: python-hardcoded-secrets - random via secrets lib
    token = f"{prefix}{random_part}"
    return token, hash_token(token), token[:HASH_PREFIX_LEN]


def hash_token(token: str) -> str:
    """Hash a token for storage (HMAC-SHA-256 over a purpose key, v2 scheme)."""
    digest = hmac.new(_hmac_key(), token.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{SCHEME_PREFIX}{digest}"


def legacy_hmac_hash_token(token: str) -> str:
    """``v1$`` HMAC keyed directly by SECRET_KEY (pre-HKDF scheme)."""
    from app.config import get_settings

    digest = hmac.new(
        get_settings().secret_key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{_LEGACY_SCHEME_PREFIX}{digest}"


def legacy_hash_token(token: str) -> str:
    """Unsalted SHA-256 digest used before the HMAC scheme (verify-only)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def candidate_hashes(token: str) -> list[str]:
    """All stored-hash forms a presented token may match (new + legacy)."""
    return [hash_token(token), legacy_hmac_hash_token(token), legacy_hash_token(token)]


def verify_token(token: str, stored_hash: str) -> bool:
    """Dual-verify a presented token against a stored hash.

    ``v2$``-prefixed rows verify with the HKDF purpose key; ``v1$`` rows with
    the legacy SECRET_KEY HMAC; anything else is a legacy unsalted digest.
    Comparison is constant-time either way.
    """
    if stored_hash.startswith(SCHEME_PREFIX):
        return hmac.compare_digest(hash_token(token), stored_hash)
    if stored_hash.startswith(_LEGACY_SCHEME_PREFIX):
        return hmac.compare_digest(legacy_hmac_hash_token(token), stored_hash)
    return hmac.compare_digest(legacy_hash_token(token), stored_hash)
