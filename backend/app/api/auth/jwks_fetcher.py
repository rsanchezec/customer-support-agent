"""JWKS fetcher with in-process TTL cache and JSON snapshot fallback.

Falls back to a JWKS snapshot loaded from `jwks_snapshot.json` (same dir)
when the live fetch fails. This is necessary because Render free tier
rate-limits "service-initiated" outbound traffic (see
https://render.com/docs/free#service-initiated-traffic-threshold) and a
per-request fetch loop can trigger the threshold and suspend the service.

How to refresh the snapshot when Microsoft rotates signing keys:
    1. Run `python example/fetch_jwks.py --write` (updates the JSON file)
    2. `git diff backend/app/api/auth/jwks_snapshot.json` to review changes
    3. `git commit + git push` — Render redeploys

Microsoft rotates signing keys on a slow cadence (configurable, default ~6
weeks). For a 1-2 week demo this won't be an issue.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# Path to the bundled JWKS snapshot. Loaded once at module import.
_SNAPSHOT_PATH = Path(__file__).parent / "jwks_snapshot.json"


def _load_snapshot() -> dict[str, Any]:
    """Load the bundled JWKS snapshot from disk.

    Returns an empty dict (no keys) if the file is missing or invalid, so
    the service still starts but every token will fail validation. The
    WARNING log makes this failure mode obvious in Render logs.
    """
    try:
        with _SNAPSHOT_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        logger.warning(
            "JWKS snapshot file not found at %s; "
            "token validation will fail until you restore it.",
            _SNAPSHOT_PATH,
        )
        return {"keys": []}
    except json.JSONDecodeError as exc:
        logger.warning(
            "JWKS snapshot file at %s is invalid JSON (%s); "
            "token validation will fail until you fix it.",
            _SNAPSHOT_PATH,
            exc,
        )
        return {"keys": []}
    # Strip the metadata key we add for humans; PyJWT only needs the keys array.
    return {"keys": data.get("keys", [])}


# Loaded once at import. Used as fallback when the live fetch fails.
_SNAPSHOT_JWKS: dict[str, Any] = _load_snapshot()


# When consecutive fetches fail, expand the cache TTL to avoid hammering
# the endpoint. After 3 failures in a row we use the bundled snapshot
# for at least 5 minutes before retrying the live endpoint.
_FALLBACK_TTL_SECONDS = 300
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = (1, 2, 4)


class JwksFetcher:
    """Fetches and caches a JWKS from an Entra ID tenant.

    The cache has a TTL of *ttl_seconds* (default 1h). After the TTL
    expires the next call refetches the full JWKS with exponential-backoff
    retries. If all retries fail, the fetcher falls back to the bundled
    snapshot (jwks_snapshot.json) so the service stays available in
    environments where login.microsoftonline.com is unreliable (e.g. Render
    free tier rate-limiting outbound traffic).
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

        # All retries failed. Use the bundled snapshot so the service stays
        # available. Logged at WARNING so it's visible in Render logs.
        num_keys = len(_SNAPSHOT_JWKS.get("keys", []))
        logger.warning(
            "JWKS live fetch failed after %d attempts (%s); using bundled "
            "snapshot (%d keys). Service-initiated outbound may be rate-limited "
            "by Render; check the JWKS endpoint manually if this persists.",
            _RETRY_ATTEMPTS,
            last_error,
            num_keys,
        )
        self._cache = _SNAPSHOT_JWKS
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
