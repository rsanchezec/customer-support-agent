"""JWKS fetcher with in-process TTL cache.

Falls back to a hardcoded JWKS when the live fetch fails (e.g. on Render
free tier where outbound to login.microsoftonline.com is blocked). The
hardcoded snapshot is for tenant 4922a12a-f1fd-40bc-affe-c63dc44acc33
and should be rotated every 3-6 months (Microsoft publishes new signing
keys on a slow cadence).
"""

from __future__ import annotations

import time
from typing import Any

import httpx


# Hardcoded JWKS snapshot for tenant 4922a12a-f1fd-40bc-affe-c63dc44acc33
# Last fetched: 2026-06-16. Replace when keys rotate (rare).
_HARDCODED_JWKS: dict[str, Any] = {
    "keys": [
        {
            "kty": "RSA",
            "use": "sig",
            "kid": "cYovdPYWG6Wi4m9upkiJFv0-K_k",
            "x5t": "cYovdPYWG6Wi4m9upkiJFv0-K_k",
            "n": "oF7hyLvRZlWKRB9PRg8ZXZfs37XFsMQG30Ihv4uhC3GK3hBUHRbF9t46exQHronUMCGvO418qng5qXVP-mvfyAkzS-v_kgEix8Oq205h43gsSvk_YBCZBH1nxjT8GLcbRI4uXpzfopmuYXbYEXfFkKCh7TBz1oIjnP43nMqi8LHCzUUiHA9EWYLMGS8pu1iNjntW0dbd3R78ybBVfps-hwZNLWEQjxPI2lUy7fycAyafQQE1xvtF4Rf5m9D6pByQu3b-hudXhDcfR97ubix2trL8EUz5jqTs20PIQ8p-r5aVbsllfZENaXcQLGIgwIL_q76iACMgI-krJBCg8YXZ-w",
            "e": "AQAB",
        },
        {
            "kty": "RSA",
            "use": "sig",
            "kid": "wh06sEkzLHJ5sNNaUyRY2_6O8K0",
            "x5t": "wh06sEkzLHJ5sNNaUyRY2_6O8K0",
            "n": "vOPjy3R_ACXnxYPAVvvQiXWl4Saa7fagNNf5q53Bb5Pj1o2TtY4cTiRooFDvpKeE-FVrC0ZclenTOiTPvgJqxHQnxCTBBZYRQ9UF7KDf3fFAAUnn4HsLQRir6dwb-E5GRG4T7i_y3pzAGun5QFsA9-eNLRucDfGpONcxhujoCTMnfqo6ac2h6BUQqlWza9Ko8wEeTHmzGlkr5bCqJXI4vtjcapQlCpvs5DSTpxWMwbHU-h-jIDsI97wIIlIn-jkmkbhUp7PZdlrot9-LBsVD3ZUyPD2poLmr161QW5i4lOEn4lhxfRtEmn9d6C0N0SQXCp5pk-kA15gyNZavP3n5sQ",
            "e": "AQAB",
        },
        {
            "kty": "RSA",
            "use": "sig",
            "kid": "k2MRQ8fu3BbJrTPLnDOyWDq1m60",
            "x5t": "k2MRQ8fu3BbJrTPLnDOyWDq1m60",
            "n": "kuZEJyH4lGC6nsedsIaeO4i1_-_Xv6aJU4uXVGzYhfwi1Cc0hKqdQ_ITktP6Cyfos-UPbXO6FEv6VwF2I88cnWrV1riiFIS9L99r8YuSh5z260hdJewk9wwtLlZ54RrfOoLqESgEiBSWVwHyCJEwV0kUSFsU1TEFOZPFYeHJBQXSASS6t4V2hPHgpKiQ-_3E7WS6XlPMQGXGcKa7P4Feo4yo5Ut6h4xKdGny5fFCvOQHjDbn4HGDa_Aup8435n6A9rlK_bsf_z-uirXOQX7-YTaLex5KrurGNJU6Yi3tC87-eziipo8H8D0hJW1yteHm7n5VdfOYUEMNI7zcSBLPnQ",
            "e": "AQAB",
        },
        {
            "kty": "RSA",
            "use": "sig",
            "kid": "aFkmKVFc-4WV6sXCBvNZkXI505Y",
            "x5t": "aFkmKVFc-4WV6sXCBvNZkXI505Y",
            "n": "okYm9VU3RbibMexFuFthuBL7vG5a2UUtHaUpBZOLOogVhpWZYIiHedAOhb2oeZvdUVHcqsSckZLnUBqnzK-UfjWG9fep_hY-jPQRgpsF5SUp8M8d-fvbAqn25O0STfGFBB2lz6vVurnd7MskkhD_K8a0OfyKzEw03ncN4vXekn7-Sn-yCHQoHQYxKIHJaCjxBlP6Jj3kMwMy93Pz6gSep4CbtGdIRGqmzDTc0tAz9MNEnenptTTOkNgXO4a__bIE-pqRCFCuU7tLHbJCxbVe9kE_QtrZG7ERzssJCHWKIhCmyB8v3LWx8zZIYritNp34aV_8UZVSqf-JVsJgfQixOQ",
            "e": "AQAB",
        },
        {
            "kty": "RSA",
            "use": "sig",
            "kid": "Xt33b5Me9iaL3_mKDW6EfTCTJkI",
            "x5t": "Xt33b5Me9iaL3_mKDW6EfTCTJkI",
            "n": "ntVetG6jtU9jEUWOb72tiOoaPK8S1fgJ0EWwb72dQ7WYbz4oOGguKI2J6hygTnM4JCpLRWvPVUtDpmns391naHEWRHXgTYHinb3kzjPaBW7R40m1RAbW2SwnZR_rQDDMgI6XcnGA5481Nu8VqIEePScCiGrgBiFgAxWpVOLnkgzXmgBcmtafnYkYeA6V4UfDBhkQLcOt2FXmi4Jlm6J95qeHf42KZtWDpGUliJnQDRlwu3ZscDzlAHIf1yUTlCb7VcYcnhjyGxUUbFXvbif2M1gJ2D4UKmLN6Pp07tYBNM6CX3A8rjrUWTOaFCqkwWODx6dGPk9g-8qFymY-SU5Piw",
            "e": "AQAB",
        },
    ]
}


class JwksFetcher:
    """Fetches and caches a JWKS from an Entra ID tenant.

    The cache is keyed by kid and has a TTL of *ttl_seconds*.
    After the TTL expires the next call refetches the full JWKS.

    If the live fetch fails, falls back to a hardcoded snapshot so the
    service stays available in environments where login.microsoftonline.com
    is unreachable (e.g. Render free tier outbound restrictions).
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

        try:
            client = self._client or httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
                headers={"User-Agent": "customer-support-agent/1.0"},
            )
            try:
                response = await client.get(self._jwks_uri)
                response.raise_for_status()
                jwks = response.json()
                self._cache = jwks
                self._fetched_at = now
                return self._cache
            finally:
                if self._owns_client:
                    await client.aclose()
        except Exception:
            # Fallback to hardcoded JWKS so the service stays available
            # in environments that can't reach login.microsoftonline.com
            # (e.g. Render free tier). The keys were fetched once and
            # pinned here; rotate every 3-6 months.
            self._cache = _HARDCODED_JWKS
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
