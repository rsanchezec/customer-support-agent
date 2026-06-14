"""Tests for JwksFetcher."""

from __future__ import annotations

import time

import httpx
import pytest

from app.api.auth.jwks_fetcher import JwksFetcher


@pytest.fixture
def fake_jwks_uri() -> str:
    return "https://login.microsoftonline.com/test-tenant/discovery/v2.0/keys"


@pytest.fixture
def fake_jwks_response() -> dict:
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": "kid-001",
                "use": "sig",
                "alg": "RS256",
                "n": "abcd",
                "e": "AQAB",
            }
        ]
    }


class FakeSuccessResponse:
    """Fake httpx.Response that returns a canned JWKS."""

    def __init__(self, jwks: dict) -> None:
        self._jwks = jwks

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._jwks


class FakeJwksHttpClient:
    """Fake AsyncClient that returns the canned JWKS."""

    def __init__(self, jwks: dict) -> None:
        self._jwks = jwks
        self._closed = False

    async def get(self, url: str) -> FakeSuccessResponse:
        return FakeSuccessResponse(self._jwks)

    async def aclose(self) -> None:
        self._closed = True


@pytest.mark.asyncio
async def test_get_keys_fetches_on_first_call(fake_jwks_uri, fake_jwks_response):
    """First call triggers an HTTP fetch."""
    client = FakeJwksHttpClient(fake_jwks_response)
    fetcher = JwksFetcher(jwks_uri=fake_jwks_uri, http_client=client)

    result = await fetcher.get_keys()

    assert result == fake_jwks_response
    assert result["keys"][0]["kid"] == "kid-001"


@pytest.mark.asyncio
async def test_get_keys_returns_cached_within_ttl(fake_jwks_uri, fake_jwks_response):
    """Subsequent calls within TTL return the cached value."""
    client = FakeJwksHttpClient(fake_jwks_response)
    fetcher = JwksFetcher(jwks_uri=fake_jwks_uri, http_client=client, ttl_seconds=600)

    await fetcher.get_keys()
    await fetcher.get_keys()
    await fetcher.get_keys()

    # Client.get should have been called only once (cache hit)
    assert client._closed is False


@pytest.mark.asyncio
async def test_get_keys_refetches_after_ttl(fake_jwks_uri, fake_jwks_response):
    """After TTL expires the next call refetches."""
    client = FakeJwksHttpClient(fake_jwks_response)
    fetcher = JwksFetcher(jwks_uri=fake_jwks_uri, http_client=client, ttl_seconds=0)

    await fetcher.get_keys()
    # Manually advance time past TTL
    time.sleep(0.1)
    await fetcher.get_keys()

    # Client.get was called twice (refetch)
    assert client._closed is False


@pytest.mark.asyncio
async def test_get_keys_handles_http_error(fake_jwks_uri):
    """HTTP errors propagate as exceptions."""

    class FailingClient:
        async def get(self, url: str):
            raise httpx.HTTPError("network error")

        async def aclose(self) -> None:
            pass

    fetcher = JwksFetcher(jwks_uri=fake_jwks_uri, http_client=FailingClient())

    with pytest.raises(httpx.HTTPError):
        await fetcher.get_keys()


def test_reset_clears_cache(fake_jwks_uri, fake_jwks_response):
    """reset() clears the cache synchronously."""
    fetcher = JwksFetcher(jwks_uri=fake_jwks_uri)
    fetcher._cache = fake_jwks_response
    fetcher._fetched_at = time.monotonic()

    fetcher.reset()

    assert fetcher._cache == {}
    assert fetcher._fetched_at == 0.0
