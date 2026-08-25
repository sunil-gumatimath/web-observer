"""Opaque token generation + hashing for share links and team invites.

Only the SHA-256 hash of a token is ever stored in the database. The plaintext
token is returned exactly once at creation time and shown in the public URL.
"""

from __future__ import annotations

import hashlib
import secrets

HASH_PREFIX_LEN = 16


def new_token(*, prefix: str = "") -> tuple[str, str, str]:
    """Return ``(token, token_hash, token_prefix)``.

    ``token`` is an opaque, unguessable string. ``token_hash`` is the SHA-256
    hex digest to persist. ``token_prefix`` is a short human-readable fragment.
    """
    random_part = secrets.token_urlsafe(24)
    # pi-lens-ignore: python-hardcoded-secrets - random via secrets lib
    token = f"{prefix}{random_part}"
    return token, hash_token(token), token[:HASH_PREFIX_LEN]


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_url(*, base: str, kind: str, token: str) -> str:
    base = (base or "").rstrip("/")
    return f"{base}/{kind}/{token}"