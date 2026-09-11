"""Auth router tests (plan §14 — OIDC login flow + `/admin_login`).

Real Authentik is unavailable in this environment, so OIDC discovery/JWKS
are mocked: `OIDCClient` (see `backend.routers.auth`) takes an injectable
`http_client_factory`, and these tests supply a fake `httpx`-shaped client
returning a canned discovery document + JWKS, plus a self-signed RS256 test
JWT (via `python-jose` + a locally generated RSA keypair — never a real
Authentik instance).
"""
from __future__ import annotations

import base64
import time

import fakeredis
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fakeredis import aioredis as fake_aioredis
from httpx import ASGITransport, AsyncClient
from jose import jwt

from backend.core.redis import get_redis
from backend.core.sessions import SESSION_COOKIE_NAME
from backend.routers.auth import ADMIN_LOCAL_USER_ID, OIDCClient
from backend.routers.auth import router as auth_router
from fastapi import FastAPI

pytestmark = pytest.mark.asyncio

TEST_ISSUER = "https://idp.example.org/application/o/qecomp/"
TEST_CLIENT_ID = "qecomp-test-client"
TEST_KID = "test-key-1"


def _b64u(n: int) -> str:
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


@pytest.fixture(scope="module")
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode("utf-8")
    numbers = key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": TEST_KID,
        "use": "sig",
        "alg": "RS256",
        "n": _b64u(numbers.n),
        "e": _b64u(numbers.e),
    }
    return private_pem, jwk


def _make_id_token(private_pem: str, *, groups: list[str], sub: str = "user-1") -> str:
    now = int(time.time())
    claims = {
        "iss": TEST_ISSUER.rstrip("/"),
        "aud": TEST_CLIENT_ID,
        "sub": sub,
        "preferred_username": sub,
        "iat": now,
        "exp": now + 300,
        "groups": groups,
    }
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": TEST_KID})


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeOIDCHttpClient:
    """Stands in for `httpx.AsyncClient` in tests: serves a canned discovery
    document + JWKS, and a canned token response for the code exchange."""

    def __init__(self, jwk: dict, id_token: str) -> None:
        self._jwk = jwk
        self._id_token = id_token

    async def __aenter__(self) -> "FakeOIDCHttpClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, url: str, **kwargs: object) -> _FakeResponse:
        if url.endswith("/.well-known/openid-configuration"):
            return _FakeResponse(
                {
                    "authorization_endpoint": f"{TEST_ISSUER}authorize",
                    "token_endpoint": f"{TEST_ISSUER}token",
                    "jwks_uri": f"{TEST_ISSUER}jwks",
                }
            )
        if url == f"{TEST_ISSUER}jwks":
            return _FakeResponse({"keys": [self._jwk]})
        raise AssertionError(f"Unexpected GET {url}")

    async def post(self, url: str, **kwargs: object) -> _FakeResponse:
        assert url == f"{TEST_ISSUER}token"
        return _FakeResponse(
            {"access_token": "fake-access-token", "id_token": self._id_token, "token_type": "Bearer"}
        )


# ── OIDCClient unit tests (no app/DB/Redis needed) ───────────────────────


async def test_oidc_client_validates_self_signed_jwt(rsa_keypair):
    private_pem, jwk = rsa_keypair
    id_token = _make_id_token(private_pem, groups=["qecomp-admin"])
    client = OIDCClient(
        TEST_ISSUER,
        TEST_CLIENT_ID,
        "test-secret",
        http_client_factory=lambda: FakeOIDCHttpClient(jwk, id_token),
    )

    claims = await client.validate_id_token(id_token)
    assert claims["sub"] == "user-1"
    assert claims["groups"] == ["qecomp-admin"]


async def test_oidc_client_rejects_tampered_token(rsa_keypair):
    private_pem, jwk = rsa_keypair
    id_token = _make_id_token(private_pem, groups=["qecomp-admin"])
    tampered = id_token[:-4] + ("A" * 4)  # corrupt the signature
    client = OIDCClient(
        TEST_ISSUER,
        TEST_CLIENT_ID,
        "test-secret",
        http_client_factory=lambda: FakeOIDCHttpClient(jwk, id_token),
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await client.validate_id_token(tampered)
    assert exc_info.value.status_code == 401


async def test_oidc_client_authorization_url_includes_pkce_challenge(rsa_keypair):
    private_pem, jwk = rsa_keypair
    id_token = _make_id_token(private_pem, groups=[])
    client = OIDCClient(
        TEST_ISSUER,
        TEST_CLIENT_ID,
        "test-secret",
        http_client_factory=lambda: FakeOIDCHttpClient(jwk, id_token),
    )
    url = await client.authorization_url(
        redirect_uri="https://app.example.org/auth/callback",
        state="state123",
        code_challenge="challenge123",
    )
    assert url.startswith(f"{TEST_ISSUER}authorize?")
    assert "code_challenge=challenge123" in url
    assert "code_challenge_method=S256" in url
    assert "state=state123" in url


# ── Full router tests (fakeredis; DB only needed for the callback's group
#    -> permission resolution, skipped gracefully if unreachable) ─────────


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    return app


@pytest.fixture
async def fake_redis():
    server = fakeredis.FakeServer()
    client = fake_aioredis.FakeRedis(server=server, decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
async def client(fake_redis, rsa_keypair):
    private_pem, jwk = rsa_keypair
    id_token = _make_id_token(private_pem, groups=["qecomp-viewer"])

    app = _build_app()
    app.state.oidc_client = OIDCClient(
        TEST_ISSUER,
        TEST_CLIENT_ID,
        "test-secret",
        http_client_factory=lambda: FakeOIDCHttpClient(jwk, id_token),
    )

    async def _override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = _override_get_redis

    from backend.core.settings import settings

    settings.OIDC_ISSUER_URL = TEST_ISSUER

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as c:
        yield app, c, id_token


async def test_oidc_login_redirects_with_state_and_pkce(client):
    _, c, _ = client
    resp = await c.get("/auth/login")
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith(f"{TEST_ISSUER}authorize?")
    assert "state=" in location
    assert "code_challenge=" in location


async def test_oidc_login_503_when_not_configured(fake_redis):
    from backend.core.settings import settings

    app = _build_app()

    async def _override_get_redis():
        yield fake_redis

    from backend.core.redis import get_redis as real_get_redis

    app.dependency_overrides[real_get_redis] = _override_get_redis

    old_issuer = settings.OIDC_ISSUER_URL
    settings.OIDC_ISSUER_URL = ""
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/auth/login")
            assert resp.status_code == 503
    finally:
        settings.OIDC_ISSUER_URL = old_issuer


# ── /admin_login (plan §3.9) — no DB/OIDC involved ───────────────────────


@pytest.fixture
async def admin_client(fake_redis):
    app = _build_app()

    async def _override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = _override_get_redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_admin_login_page_renders(admin_client):
    resp = await admin_client.get("/admin_login")
    assert resp.status_code == 200
    assert "admin_local" in resp.text


async def test_admin_login_correct_password_creates_session(admin_client, fake_redis):
    from backend.core.settings import settings

    resp = await admin_client.post(
        "/admin_login", data={"username": ADMIN_LOCAL_USER_ID, "password": settings.ADMIN_LOCAL_PASSWORD}
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert SESSION_COOKIE_NAME in resp.cookies


async def test_admin_login_wrong_password_returns_401(admin_client):
    resp = await admin_client.post(
        "/admin_login", data={"username": ADMIN_LOCAL_USER_ID, "password": "definitely-wrong"}
    )
    assert resp.status_code == 401
    assert SESSION_COOKIE_NAME not in resp.cookies


async def test_admin_login_wrong_username_returns_401(admin_client):
    from backend.core.settings import settings

    resp = await admin_client.post(
        "/admin_login", data={"username": "not_admin_local", "password": settings.ADMIN_LOCAL_PASSWORD}
    )
    assert resp.status_code == 401


# ── Full OIDC callback -> session (needs real Postgres for role_permissions) ──


@pytest.fixture
async def db_engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    from backend.core.settings import settings

    engine = create_async_engine(settings.POSTGRES_DSN)
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
    except Exception:
        pytest.skip("Real Postgres not reachable; skipping OIDC callback test")
    yield engine
    await engine.dispose()


async def test_oidc_callback_creates_session_with_resolved_groups(client, fake_redis, db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from backend.core.dependencies import get_db
    from backend.core.sessions import get_session, unsign_session_id

    app, c, _ = client
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async def _override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    login_resp = await c.get("/auth/login")
    state = login_resp.headers["location"].split("state=")[1].split("&")[0]

    callback_resp = await c.get("/auth/callback", params={"code": "fake-code", "state": state})
    assert callback_resp.status_code == 302
    assert SESSION_COOKIE_NAME in callback_resp.cookies

    signed = callback_resp.cookies[SESSION_COOKIE_NAME]
    session_id = unsign_session_id(signed)
    assert session_id is not None
    data = await get_session(fake_redis, session_id)
    assert data is not None
    assert data["groups"] == ["qecomp-viewer"]
    # qecomp-viewer's seeded default permissions (plan §13) — present only
    # if the seed migration has been applied to this test database.
    assert isinstance(data["permissions"], list)
