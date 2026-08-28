"""Fernet-based credential encryption utilities.

Per Appendix B.1, all `secret: true` integration config fields are encrypted
with Fernet before being written to Postgres JSONB columns. `ENCRYPTION_KEY`
must be a 32-byte, base64url-encoded Fernet key.
"""
from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from backend.core.exceptions import QECompError
from backend.core.settings import settings


class EncryptionError(QECompError):
    """Raised when encryption/decryption fails."""


@lru_cache
def _get_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if not key:
        raise EncryptionError(
            "ENCRYPTION_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())"`'
        )
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise EncryptionError(f"ENCRYPTION_KEY is not a valid Fernet key: {exc}") from exc


def encrypt(value: str) -> str:
    """Encrypt a plaintext string, returning a base64url token string."""
    fernet = _get_fernet()
    return fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(value: str) -> str:
    """Decrypt a token previously produced by `encrypt`."""
    fernet = _get_fernet()
    try:
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise EncryptionError("Failed to decrypt value: invalid token") from exc
