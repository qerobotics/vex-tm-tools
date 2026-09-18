"""Fernet-based credential encryption utilities, plus teleprompter HMAC
tokens.

Per Appendix B.1, all `secret: true` integration config fields are encrypted
with Fernet before being written to Postgres JSONB columns. `ENCRYPTION_KEY`
must be a 32-byte, base64url-encoded Fernet key.

Per Appendix B.8, teleprompter links (`/prompter/<entity_id>?token=<hmac>`)
carry an HMAC-SHA256 token derived from `entity_id` + a server secret
(`SECRET_KEY`) + a per-instance nonce (`timer_instances.token_nonce`) so a
"Regenerate Token" action in the UI can invalidate old links without
affecting other instances or requiring a server restart.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from backend.core.exceptions import QECompError
from backend.core.settings import settings

#: Prefix every generated API key is stamped with (plan Appendix B.7), so
#: keys are recognisable at a glance / in logs without decoding anything.
API_KEY_PREFIX = "qec_"


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


# ── Teleprompter token (plan Appendix A.1 / B.8) ────────────────────────


def _derive_instance_secret(nonce: str) -> bytes:
    """Derive a per-instance secret from `SECRET_KEY` + the instance's nonce.

    Using HMAC (rather than plain string concatenation) to combine the
    server secret and the nonce avoids ambiguity/collision issues that a
    naive `secret + nonce` string join can introduce, and keeps the server
    secret from ever appearing directly in the second HMAC's key material.
    """
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256
    ).digest()


def generate_prompter_token(entity_id: str, nonce: str) -> str:
    """Generate the HMAC-SHA256 teleprompter token for a Timer instance.

    Per Appendix B.8: `HMAC-SHA256(entity_id + server_secret)` where
    `server_secret` is derived from `SECRET_KEY`, combined with a
    per-instance `nonce` (`timer_instances.token_nonce`) so regenerating the
    token (rotating the nonce) invalidates all previously issued links.
    Returned as a URL-safe base64 string with padding stripped, per B.8's
    "URL-safe base64 string embedded in the URL" requirement.
    """
    instance_secret = _derive_instance_secret(nonce)
    digest = hmac.new(instance_secret, entity_id.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def validate_prompter_token(entity_id: str, nonce: str, token: str) -> bool:
    """Constant-time validation of a teleprompter token against the expected
    value for `entity_id` + `nonce`. Used server-side at WebSocket upgrade
    time (Wave 3's `/ws/prompter/<entity_id>` endpoint) and when rendering
    the standalone `prompter.html` page."""
    if not token:
        return False
    expected = generate_prompter_token(entity_id, nonce)
    return hmac.compare_digest(expected, token)


# ── API keys (plan Appendix B.7) ────────────────────────────────────────


def generate_api_key() -> str:
    """Generate a new raw API key: `qec_` + a 43-char base64url token
    (`secrets.token_urlsafe(32)`), per Appendix B.7. This raw value is shown
    to the operator exactly once and never stored — only its SHA-256 hash
    (see `hash_api_key`) is persisted."""
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hex digest of a raw API key, for storage/lookup in
    `api_keys.key_hash`. Per Appendix B.7 the raw key itself is never
    stored."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
