import time
from unittest.mock import MagicMock

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import AuthPrincipal, clerk_configured, verify_clerk_token
from app.config import Settings


def test_clerk_configured_false_by_default() -> None:
    s = Settings(clerk_jwks_url=None, clerk_issuer=None)
    assert clerk_configured(s) is False


def test_clerk_configured_true_when_set() -> None:
    s = Settings(
        clerk_jwks_url="https://example.clerk.accounts.dev/.well-known/jwks.json",
        issuer="https://example.clerk.accounts.dev",
        clerk_issuer="https://example.clerk.accounts.dev",
    )
    assert clerk_configured(s) is True


def test_internal_principal() -> None:
    p = AuthPrincipal(user=None, is_internal=True, email="internal@local")
    assert p.user_id is None
    assert p.is_internal is True


def test_verify_clerk_token_tolerates_clock_skew(monkeypatch) -> None:
    # Generate RSA keypair for testing RS256 token verification
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    issuer = "https://example.clerk.accounts.dev"
    now = int(time.time())
    # Token with nbf 20 seconds in the future (clock skew scenario)
    token = jwt.encode(
        {"sub": "user_clock_skew", "nbf": now + 20, "exp": now + 3600, "iss": issuer},
        private_key,
        algorithm="RS256",
    )

    mock_client = MagicMock()
    mock_signing_key = MagicMock()
    mock_signing_key.key = public_key
    mock_client.get_signing_key_from_jwt.return_value = mock_signing_key

    monkeypatch.setattr("app.auth._get_jwks_client", lambda s: mock_client)

    settings = Settings(
        clerk_jwks_url="https://example.clerk.accounts.dev/.well-known/jwks.json",
        clerk_issuer=issuer,
    )

    payload = verify_clerk_token(token, settings)
    assert payload["sub"] == "user_clock_skew"
