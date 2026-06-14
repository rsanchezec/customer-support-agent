"""Pytest fixtures for API auth tests."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.settings import Settings

# ---------------------------------------------------------------------------
# RSA key pair for test token signing
# ---------------------------------------------------------------------------


def _generate_rsa_keypair() -> tuple[bytes, bytes]:
    """Return (private_key_pem, public_key_pem)."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


_private_key_pem, _public_key_pem = _generate_rsa_keypair()
_kid = "test-kid-001"


# ---------------------------------------------------------------------------
# Settings fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    """Return a Settings instance with test Entra ID values."""
    s = Settings()
    object.__setattr__(s, "entra_tenant_id", "test-tenant")
    object.__setattr__(s, "entra_client_id", "test-client")
    object.__setattr__(s, "entra_app_audience", "api://test-client")
    return s


# ---------------------------------------------------------------------------
# In-memory SQLite engine + session
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    """In-memory SQLite engine with FK enforcement, per-test rollback."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine):
    """AsyncSession factory bound to the in-memory engine."""
    return async_sessionmaker(bind=engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# JWKS HTTP mock
# ---------------------------------------------------------------------------


def make_jwks_response(kid: str, public_key_pem: bytes) -> dict[str, Any]:
    """Return a JWKS response dict for the given kid and public key."""
    public = serialization.load_pem_public_key(public_key_pem, backend=default_backend())
    if not isinstance(public, rsa.RSAPublicKey):
        raise TypeError("Expected RSA public key")
    numbers = public.public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": kid,
                "use": "sig",
                "alg": "RS256",
                "n": base64.urlsafe_b64encode(numbers.n.to_bytes(256, byteorder="big")).rstrip(
                    b"="
                ),
                "e": base64.urlsafe_b64encode(numbers.e.to_bytes(256, byteorder="big")).rstrip(
                    b"="
                ),
            }
        ]
    }


class FakeJwksResponse(httpx.Response):
    """A fake JWKS HTTP response."""

    def __init__(self, jwks: dict[str, Any]) -> None:
        super().__init__(
            status_code=200,
            json=jwks,
            request=httpx.Request("GET", "https://example.com/jwks"),
        )


class FakeJwksClient(httpx.AsyncClient):
    """A fake AsyncClient that returns a canned JWKS for any GET."""

    def __init__(self, jwks: dict[str, Any]) -> None:
        super().__init__()
        self._jwks = jwks

    async def get(self, url: str | httpx.URL, **kwargs) -> httpx.Response:  # type: ignore[override]
        return FakeJwksResponse(self._jwks)


# ---------------------------------------------------------------------------
# Token factory
# ---------------------------------------------------------------------------


def create_test_token(
    private_key_pem: bytes,
    kid: str,
    *,
    oid: str = "test-oid-001",
    email: str = "test@example.com",
    audience: str = "api://test-client",
    issuer: str = "https://login.microsoftonline.com/test-tenant/v2.0",
    exp_offset_seconds: int = 3600,
) -> str:
    """Create a signed JWT for testing."""
    now = datetime.now(UTC)
    payload = {
        "oid": oid,
        "email": email,
        "preferred_username": email,
        "aud": audience,
        "iss": issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_offset_seconds)).timestamp()),
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256", headers={"kid": kid})
