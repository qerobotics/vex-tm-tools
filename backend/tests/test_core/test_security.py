"""Tests for backend.core.security Fernet encrypt/decrypt round-trip."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from backend.core import security


def test_encrypt_decrypt_round_trip(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(security.settings, "ENCRYPTION_KEY", key)
    security._get_fernet.cache_clear()

    plaintext = "super-secret-api-key-value"
    token = security.encrypt(plaintext)

    assert token != plaintext
    assert security.decrypt(token) == plaintext

    security._get_fernet.cache_clear()


def test_decrypt_invalid_token_raises(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(security.settings, "ENCRYPTION_KEY", key)
    security._get_fernet.cache_clear()

    with pytest.raises(security.EncryptionError):
        security.decrypt("not-a-valid-fernet-token")

    security._get_fernet.cache_clear()


def test_missing_encryption_key_raises(monkeypatch):
    monkeypatch.setattr(security.settings, "ENCRYPTION_KEY", "")
    security._get_fernet.cache_clear()

    with pytest.raises(security.EncryptionError):
        security.encrypt("value")

    security._get_fernet.cache_clear()
