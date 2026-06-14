"""JWKS fetcher with in-process TTL cache."""

from __future__ import annotations

import time
from typing import Any

import httpx


class JwksFetcher:
    """Fetches and caches a JWKS from an Entra ID tenant.

    The cache is keyed by kid and has a TTL of *ttl_seconds*.
    After the TTL expires the next call refetches the full JWKS.
    """

    def __init__(
        self,
        *,
        jwks_uri: str,
        ttl_seconds: int = 600,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._jwks_uri = jwks_uri
        self._ttl_seconds = ttl_seconds
        self._client = http_client
        self._owns_client = http_client is None
        self._cache: dict[str, Any] = {}
        self._fetched_at: float = 0.0

    async def get_keys(self) -> dict[str, Any]:
        """Return the cached JWK set, fetching if the cache is stale or empty."""
        now = time.monotonic()
        if self._cache and (now - self._fetched_at) < self._ttl_seconds:
            return self._cache

        client = self._client or httpx.AsyncClient()
        try:
            response = await client.get(self._jwks_uri)
            response.raise_for_status()
            jwks = response.json()
        finally:
            if self._owns_client:
                await client.aclose()

        self._cache = jwks
        self._fetched_at = now
        return self._cache

    async def aclose(self) -> None:
        """Close the underlying httpx.AsyncClient if we own it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    def reset(self) -> None:
        """Clear the cache (sync, for use in tests)."""
        self._cache = {}
        self._fetched_at = 0.0
