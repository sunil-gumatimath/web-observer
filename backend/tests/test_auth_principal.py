from app.auth import AuthPrincipal, clerk_configured
from app.config import Settings


def test_clerk_configured_false_by_default() -> None:
    s = Settings(clerk_jwks_url=None, clerk_issuer=None)
    assert clerk_configured(s) is False


def test_clerk_configured_true_when_set() -> None:
    s = Settings(
        clerk_jwks_url="https://example.clerk.accounts.dev/.well-known/jwks.json",
        clerk_issuer="https://example.clerk.accounts.dev",
    )
    assert clerk_configured(s) is True


def test_internal_principal() -> None:
    p = AuthPrincipal(user=None, is_internal=True, email="internal@local")
    assert p.user_id is None
    assert p.is_internal is True
