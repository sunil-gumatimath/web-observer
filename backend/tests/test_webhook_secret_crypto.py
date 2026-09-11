"""Webhook secret encryption-at-rest, HMAC share/invite tokens, fail-closed crypto."""

from __future__ import annotations

import pytest

import app.services.crypto as crypto_mod
from app.services.crypto import decrypt_secret, encrypt_secret, is_encrypted
from app.services.tokens import (
    candidate_hashes,
    hash_token,
    legacy_hash_token,
    new_token,
    verify_token,
)


def test_encrypt_round_trip() -> None:
    stored = encrypt_secret("webhook-signing-secret")
    assert stored != "webhook-signing-secret"
    assert is_encrypted(stored)
    assert decrypt_secret(stored) == "webhook-signing-secret"


def test_legacy_plaintext_fallback_read() -> None:
    assert not is_encrypted("plain-legacy-secret")
    assert decrypt_secret("plain-legacy-secret") == "plain-legacy-secret"
    assert decrypt_secret(None) is None
    assert decrypt_secret("") is None


def test_token_new_scheme_verify() -> None:
    token, token_hash, _prefix = new_token()
    assert token_hash.startswith("v1$")
    assert hash_token(token) == token_hash
    assert token_hash in candidate_hashes(token)
    assert verify_token(token, token_hash)


def test_token_old_scheme_still_verifies() -> None:
    token, _new_hash, _prefix = new_token()
    legacy = legacy_hash_token(token)
    assert not legacy.startswith("v1$")
    assert legacy in candidate_hashes(token)
    assert verify_token(token, legacy)


def test_tampered_token_rejected() -> None:
    token, token_hash, _prefix = new_token()
    assert not verify_token(token + "tampered", token_hash)
    assert not verify_token(token + "tampered", legacy_hash_token(token))
    assert not verify_token("wrong-token", token_hash)


def test_encrypt_raises_when_crypto_backend_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crypto_mod, "_fernet", lambda: None)
    with pytest.raises(RuntimeError, match="cryptography backend missing"):
        encrypt_secret("must-not-persist-plaintext")


def test_model_encrypts_webhook_secret_on_write() -> None:
    from app.models import WebhookEndpoint

    ep = WebhookEndpoint(url="https://example.com/hook", secret="plain-secret", enabled=True)
    assert ep.secret != "plain-secret"
    assert is_encrypted(ep.secret)
    assert decrypt_secret(ep.secret) == "plain-secret"
