"""Tests for get_current_user FastAPI dependency."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.auth.deps import get_current_user
from app.api.auth.jwks_fetcher import JwksFetcher
from app.domain.user import User
from app.services.user_service import UserService

from .conftest import (
    _kid,
    _private_key_pem,
    _public_key_pem,
    create_test_token,
    make_jwks_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeJwksClient:
    """Fake HTTP client that returns the canned JWKS."""

    def __init__(self, jwks: dict) -> None:
        self._jwks = jwks

    async def get(self, url: str):
        jwks = self._jwks

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                return jwks

        return R()


def _generate_different_private_key() -> bytes:
    """Generate a second RSA private key (for wrong-signature tests)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_user() -> User:
    """Return a User with a stable UUID for assertions."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.entraid_oid = "test-oid-001"
    user.email = "test@example.com"
    return user


@pytest.fixture
def fake_jwks(settings) -> JwksFetcher:
    """A JwksFetcher pre-loaded with the test RSA public key."""
    jwks_response = make_jwks_response(_kid, _public_key_pem)
    http_client = FakeJwksClient(jwks_response)
    return JwksFetcher(
        jwks_uri=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/discovery/v2.0/keys",
        http_client=http_client,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_user_returns_user_for_valid_token(settings, fake_jwks, fake_user):
    """A valid bearer token → the upserted User is returned."""
    mock_user_service = AsyncMock(spec=UserService)
    mock_user_service.get_or_create_by_oid.return_value = fake_user

    token = create_test_token(_private_key_pem, _kid)

    with patch("app.api.auth.deps.get_settings", return_value=settings):
        user = await get_current_user(
            authorization=f"Bearer {token}",
            jwks=fake_jwks,
            user_service=mock_user_service,
        )

    assert user == fake_user
    mock_user_service.get_or_create_by_oid.assert_called_once_with(
        oid="test-oid-001", email="test@example.com"
    )


@pytest.mark.asyncio
async def test_get_current_user_upserts_user_on_first_login(settings, fake_jwks):
    """First login: UserService.get_or_create_by_oid is called with the token's oid/email."""
    created_user = MagicMock(spec=User)
    created_user.id = uuid4()
    created_user.entraid_oid = "brand-new-oid"
    created_user.email = "newuser@example.com"

    mock_user_service = AsyncMock(spec=UserService)
    mock_user_service.get_or_create_by_oid.return_value = created_user

    token = create_test_token(
        _private_key_pem, _kid, oid="brand-new-oid", email="newuser@example.com"
    )

    with patch("app.api.auth.deps.get_settings", return_value=settings):
        user = await get_current_user(
            authorization=f"Bearer {token}",
            jwks=fake_jwks,
            user_service=mock_user_service,
        )

    assert user == created_user
    mock_user_service.get_or_create_by_oid.assert_called_once_with(
        oid="brand-new-oid", email="newuser@example.com"
    )


@pytest.mark.asyncio
async def test_raises_401_for_missing_header(fake_jwks, fake_user):
    """No Authorization header → 401 'missing or invalid authorization header'."""
    from fastapi import HTTPException

    mock_user_service = AsyncMock(spec=UserService)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            authorization="",
            jwks=fake_jwks,
            user_service=mock_user_service,
        )

    assert exc_info.value.status_code == 401
    assert "missing or invalid authorization header" in exc_info.value.detail


@pytest.mark.asyncio
async def test_raises_401_for_malformed_header(fake_jwks, fake_user):
    """Authorization without 'Bearer ' prefix → 401."""
    from fastapi import HTTPException

    mock_user_service = AsyncMock(spec=UserService)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            authorization="Basic abc123",
            jwks=fake_jwks,
            user_service=mock_user_service,
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_raises_401_for_expired_token(settings, fake_jwks, fake_user):
    """Expired token → 401 'token expired'."""
    from fastapi import HTTPException

    mock_user_service = AsyncMock(spec=UserService)
    token = create_test_token(_private_key_pem, _kid, exp_offset_seconds=-10)

    with pytest.raises(HTTPException) as exc_info:
        with patch("app.api.auth.deps.get_settings", return_value=settings):
            await get_current_user(
                authorization=f"Bearer {token}",
                jwks=fake_jwks,
                user_service=mock_user_service,
            )

    assert exc_info.value.status_code == 401
    assert "token expired" in exc_info.value.detail


@pytest.mark.asyncio
async def test_raises_401_for_invalid_signature(settings, fake_jwks, fake_user):
    """Token signed with wrong key → 401 'invalid token'."""
    from fastapi import HTTPException

    mock_user_service = AsyncMock(spec=UserService)
    wrong_private = _generate_different_private_key()
    token = create_test_token(wrong_private, _kid)

    with pytest.raises(HTTPException) as exc_info:
        with patch("app.api.auth.deps.get_settings", return_value=settings):
            await get_current_user(
                authorization=f"Bearer {token}",
                jwks=fake_jwks,
                user_service=mock_user_service,
            )

    assert exc_info.value.status_code == 401
    assert "invalid token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_raises_401_for_wrong_audience(settings, fake_jwks, fake_user):
    """Token with wrong audience → 401 'invalid token'."""
    from fastapi import HTTPException

    mock_user_service = AsyncMock(spec=UserService)
    token = create_test_token(_private_key_pem, _kid, audience="api://wrong-client")

    with pytest.raises(HTTPException) as exc_info:
        with patch("app.api.auth.deps.get_settings", return_value=settings):
            await get_current_user(
                authorization=f"Bearer {token}",
                jwks=fake_jwks,
                user_service=mock_user_service,
            )

    assert exc_info.value.status_code == 401
    assert "invalid token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_raises_401_for_wrong_issuer(settings, fake_jwks, fake_user):
    """Token with wrong issuer → 401 'invalid token'."""
    from fastapi import HTTPException

    mock_user_service = AsyncMock(spec=UserService)
    token = create_test_token(
        _private_key_pem,
        _kid,
        issuer="https://login.microsoftonline.com/wrong-tenant/v2.0",
    )

    with pytest.raises(HTTPException) as exc_info:
        with patch("app.api.auth.deps.get_settings", return_value=settings):
            await get_current_user(
                authorization=f"Bearer {token}",
                jwks=fake_jwks,
                user_service=mock_user_service,
            )

    assert exc_info.value.status_code == 401
    assert "invalid token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_accepts_multitenant_issuer_when_enabled(settings, fake_jwks, fake_user):
    """A valid token from another tenant is accepted only in public demo mode."""
    object.__setattr__(settings, "entra_allow_multitenant_issuers", True)

    mock_user_service = AsyncMock(spec=UserService)
    mock_user_service.get_or_create_by_oid.return_value = fake_user

    token = create_test_token(
        _private_key_pem,
        _kid,
        oid="external-user-oid",
        issuer="https://login.microsoftonline.com/external-tenant/v2.0",
        tenant_id="external-tenant",
    )

    with patch("app.api.auth.deps.get_settings", return_value=settings):
        user = await get_current_user(
            authorization=f"Bearer {token}",
            jwks=fake_jwks,
            user_service=mock_user_service,
        )

    assert user == fake_user
    mock_user_service.get_or_create_by_oid.assert_called_once_with(
        oid="external-tenant:external-user-oid", email="test@example.com"
    )


@pytest.mark.asyncio
async def test_rejects_multitenant_issuer_when_tid_mismatches(settings, fake_jwks):
    """The dynamic issuer must still match the token's tid claim."""
    from fastapi import HTTPException

    object.__setattr__(settings, "entra_allow_multitenant_issuers", True)
    mock_user_service = AsyncMock(spec=UserService)
    token = create_test_token(
        _private_key_pem,
        _kid,
        issuer="https://login.microsoftonline.com/external-tenant/v2.0",
        tenant_id="different-tenant",
    )

    with pytest.raises(HTTPException) as exc_info:
        with patch("app.api.auth.deps.get_settings", return_value=settings):
            await get_current_user(
                authorization=f"Bearer {token}",
                jwks=fake_jwks,
                user_service=mock_user_service,
            )

    assert exc_info.value.status_code == 401
    assert "invalid token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_raises_401_for_unknown_kid(settings, fake_jwks, fake_user):
    """Token with unknown kid → 401 'unknown kid'."""
    from fastapi import HTTPException

    mock_user_service = AsyncMock(spec=UserService)
    token = create_test_token(_private_key_pem, "unknown-kid")

    with pytest.raises(HTTPException) as exc_info:
        with patch("app.api.auth.deps.get_settings", return_value=settings):
            await get_current_user(
                authorization=f"Bearer {token}",
                jwks=fake_jwks,
                user_service=mock_user_service,
            )

    assert exc_info.value.status_code == 401
    assert "invalid token" in exc_info.value.detail
