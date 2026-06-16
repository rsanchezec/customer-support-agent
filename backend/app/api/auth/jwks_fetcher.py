"""JWKS fetcher with in-process TTL cache and hardcoded fallback.

Falls back to a hardcoded JWKS snapshot when the live fetch fails. This is
necessary because Render free tier rate-limits "service-initiated" outbound
traffic (see https://render.com/docs/free#service-initiated-traffic-threshold)
and a per-request fetch loop can trigger the threshold and suspend the
service. The hardcoded snapshot is for tenant 4922a12a-f1fd-40bc-affe-c63dc44acc33.

How to refresh the hardcoded snapshot when Microsoft rotates signing keys:
    1. Run `python example/fetch_jwks.py` (prints paste-ready Python literal)
    2. Replace the _HARDCODED_JWKS constant below with the output
    3. git commit + git push — Render redeploys

Microsoft rotates signing keys on a slow cadence (configurable, default ~6
weeks). For a 1-2 week demo this won't be an issue.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx


logger = logging.getLogger(__name__)


# Hardcoded JWKS snapshot for tenant 4922a12a-f1fd-40bc-affe-c63dc44acc33.
# Pinned 2026-06-16. Rotate via example/fetch_jwks.py when Microsoft rotates
# signing keys. Keys are RSA public keys (modulus n, exponent e) used to
# verify JWT signatures. They are not secrets — anyone with the JWKS URL
# can fetch them — but pinning them here means we don't have to hit
# login.microsoftonline.com on every request (which would trigger Render's
# service-initiated traffic threshold).
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


# When consecutive fetches fail, expand the cache TTL to avoid hammering
# the endpoint. After 3 failures in a row we use the hardcoded fallback
# for at least 5 minutes before retrying the live endpoint.
_FALLBACK_TTL_SECONDS = 300
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = (1, 2, 4)


class JwksFetcher:
    """Fetches and caches a JWKS from an Entra ID tenant.

    The cache has a TTL of *ttl_seconds* (default 1h). After the TTL
    expires the next call refetches the full JWKS with exponential-backoff
    retries. If all retries fail, the fetcher falls back to a hardcoded
    snapshot so the service stays available in environments where
    login.microsoftonline.com is unreliable (e.g. Render free tier
    rate-limiting outbound traffic).
    """

    def __init__(
        self,
        *,
        jwks_uri: str,
        ttl_seconds: int = 3600,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._jwks_uri = jwks_uri
        self._ttl_seconds = ttl_seconds
        # Reuse one client for the lifetime of the fetcher. Previously
        # we created a new client per get_keys() call, which was wasteful
        # and made retry logic awkward.
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"User-Agent": "customer-support-agent/1.0"},
        )
        self._owns_client = http_client is None
        self._cache: dict[str, Any] = {}
        self._fetched_at: float = 0.0
        self._using_fallback: bool = False

    async def get_keys(self) -> dict[str, Any]:
        """Return the cached JWK set, fetching if the cache is stale or empty."""
        now = time.monotonic()
        cache_age = now - self._fetched_at
        # If we're on the fallback, hold it for at least _FALLBACK_TTL_SECONDS
        # to avoid hammering the endpoint with retries that we know will fail.
        effective_ttl = (
            _FALLBACK_TTL_SECONDS
            if self._using_fallback
            else self._ttl_seconds
        )
        if self._cache and cache_age < effective_ttl:
            return self._cache

        last_error: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                response = await self._client.get(self._jwks_uri)
                response.raise_for_status()
                jwks = response.json()
            except Exception as exc:
                last_error = exc
                if attempt < _RETRY_ATTEMPTS - 1:
                    backoff = _RETRY_BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "JWKS fetch attempt %d/%d failed (%s), retrying in %ds",
                        attempt + 1,
                        _RETRY_ATTEMPTS,
                        exc,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                continue
            # Success: update cache and return
            self._cache = jwks
            self._fetched_at = now
            if self._using_fallback:
                logger.info("JWKS live fetch recovered, dropping fallback")
            self._using_fallback = False
            return self._cache

        # All retries failed. Use hardcoded fallback so the service stays
        # available. Logged at WARNING so it's visible in Render logs.
        logger.warning(
            "JWKS live fetch failed after %d attempts (%s); using hardcoded "
            "fallback. Service-initiated outbound may be rate-limited by "
            "Render; check the JWKS endpoint manually if this persists.",
            _RETRY_ATTEMPTS,
            last_error,
        )
        self._cache = _HARDCODED_JWKS
        self._fetched_at = now
        self._using_fallback = True
        return self._cache

    async def aclose(self) -> None:
        """Close the underlying httpx.AsyncClient if we own it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    def reset(self) -> None:
        """Clear the cache (sync, for use in tests)."""
        self._cache = {}
        self._fetched_at = 0.0
        self._using_fallback = False
