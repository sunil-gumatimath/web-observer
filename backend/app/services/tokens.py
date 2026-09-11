"""Opaque token generation + hashing for share links and team invites.

Only the token hash is ever stored in the database. The plaintext token is
returned exactly once at creation time and shown in the public URL. Raw
tokens must never be logged.

New tokens are HMAC-SHA-256 digests keyed by SECRET_KEY, stored with a
``v1$`` scheme prefix. Legacy rows holding unsalted SHA-256 hex digests
(pre-HMAC) still verify via dual-verify so old links keep working; all
newly issued tokens use the HMAC scheme only.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from app.config import get_settings

HASH_PREFIX_LEN = 16
SCHEME_PREFIX = "v1$"


def _hmac_key() -> bytes:
    return get_settings().secret_key.encode("utf-8")


def new_token(*, prefix: str = "") -> tuple[str, str, str]:
    """Return ``(token, token_hash, token_prefix)``.

    ``token`` is an opaque, unguessable string. ``token_hash`` is the
    HMAC-SHA-256 digest (with scheme prefix) to persist. ``token_prefix``
    is a short human-readable fragment.
    """
    random_part = secrets.token_urlsafe(24)
    # pi-lens-ignore: python-hardcoded-secrets - random via secrets lib
    token = f"{prefix}{random_part}"
    return token, hash_token(token), token[:HASH_PREFIX_LEN]


def hash_token(token: str) -> str:
    """Hash a token for storage (HMAC-SHA-256, ``v1$`` scheme)."""
    digest = hmac.new(_hmac_key(), token.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{SCHEME_PREFIX}{digest}"


def legacy_hash_token(token: str) -> str:
    """Unsalted SHA-256 digest used before the HMAC scheme (verify-only)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def candidate_hashes(token: str) -> list[str]:
    """All stored-hash forms a presented token may match (new + legacy)."""
    return [hash_token(token), legacy_hash_token(token)]


def verify_token(token: str, stored_hash: str) -> bool:
    """Dual-verify a presented token against a stored hash.

    ``v1$``-prefixed rows verify with HMAC; anything else is treated as a
    legacy unsalted digest. Comparison is constant-time either way.
    """
    if stored_hash.startswith(SCHEME_PREFIX):
        return hmac.compare_digest(hash_token(token), stored_hash)
    return hmac.compare_digest(legacy_hash_token(token), stored_hash)


def build_url(*, base: str, kind: str, token: str) -> str:
    base = (base or "").rstrip("/")
    return f"{base}/{kind}/{token}"
