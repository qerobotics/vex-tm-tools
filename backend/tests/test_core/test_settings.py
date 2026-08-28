"""Tests for backend.core.settings loading from environment variables."""
from __future__ import annotations

from backend.core.settings import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_DSN", "postgresql+asyncpg://u:p@host:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://otherhost:6379/2")
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://auth.example.com/")
    monkeypatch.setenv("OIDC_CLIENT_ID", "client-123")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "secret-456")
    monkeypatch.setenv("OIDC_GROUPS_CLAIM", "my_groups")
    monkeypatch.setenv("ADMIN_LOCAL_PASSWORD", "super-secret")
    monkeypatch.setenv("SECRET_KEY", "sk-test")
    monkeypatch.setenv("ENCRYPTION_KEY", "fernet-key-test")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_BUCKET", "mybucket")
    monkeypatch.setenv("S3_ACCESS_KEY", "access")
    monkeypatch.setenv("S3_SECRET_KEY", "secretkey")
    monkeypatch.setenv("S3_REGION", "eu-west-1")
    monkeypatch.setenv("APP_PORT", "9001")

    s = Settings(_env_file=None)

    assert s.POSTGRES_DSN == "postgresql+asyncpg://u:p@host:5432/db"
    assert s.REDIS_URL == "redis://otherhost:6379/2"
    assert s.OIDC_ISSUER_URL == "https://auth.example.com/"
    assert s.OIDC_CLIENT_ID == "client-123"
    assert s.OIDC_CLIENT_SECRET == "secret-456"
    assert s.OIDC_GROUPS_CLAIM == "my_groups"
    assert s.ADMIN_LOCAL_PASSWORD == "super-secret"
    assert s.SECRET_KEY == "sk-test"
    assert s.ENCRYPTION_KEY == "fernet-key-test"
    assert s.S3_ENDPOINT_URL == "http://minio:9000"
    assert s.S3_BUCKET == "mybucket"
    assert s.S3_ACCESS_KEY == "access"
    assert s.S3_SECRET_KEY == "secretkey"
    assert s.S3_REGION == "eu-west-1"
    assert s.APP_PORT == 9001


def test_settings_defaults_are_sane():
    s = Settings(_env_file=None)

    assert s.OIDC_GROUPS_CLAIM == "groups"
    assert s.APP_PORT == 8000
    assert s.S3_ENDPOINT_URL is None
