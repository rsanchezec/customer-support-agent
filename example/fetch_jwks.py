"""Fetch JWKS from Microsoft Entra ID for the customer-support-agent tenant.

Use this to refresh the bundled JWKS snapshot used by the backend as a
fallback. The snapshot lives at backend/app/api/auth/jwks_snapshot.json
and is loaded by backend/app/api/auth/jwks_fetcher.py on import.

Usage:
    # Just print the JSON (default):
    python example/fetch_jwks.py

    # Update the snapshot file in place (the typical refresh workflow):
    python example/fetch_jwks.py --write

    # Then review the change before committing:
    git diff backend/app/api/auth/jwks_snapshot.json

Microsoft rotates signing keys on a slow cadence (~6 weeks). For a 1-2 week
demo this won't be an issue, but for longer-running deployments refresh
when the BE logs start showing "kid not found" or validation failures.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


# Default tenant for the customer-support-agent demo.
DEFAULT_TENANT_ID = "4922a12a-f1fd-40bc-affe-c63dc44acc33"

# Where the JwksFetcher expects the snapshot.
DEFAULT_SNAPSHOT_PATH = (
    Path(__file__).resolve().parent.parent
    / "backend"
    / "app"
    / "api"
    / "auth"
    / "jwks_snapshot.json"
)


def fetch_jwks(tenant_id: str) -> dict:
    """Fetch the JWKS for the given tenant from Microsoft Entra ID.

    Returns the parsed JSON as a Python dict. Raises on network or HTTP errors.
    """
    url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    req = urllib.request.Request(url, headers={"User-Agent": "customer-support-agent/1.0"})
    with urllib.request.urlopen(req, timeout=10) as response:  # noqa: S310
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} fetching JWKS from {url}")
        return json.loads(response.read())


def write_snapshot(jwks: dict, tenant_id: str, path: Path) -> None:
    """Write the JWKS to the snapshot file, preserving the metadata header."""
    payload = {
        "_comment": (
            f"Hardcoded JWKS snapshot for tenant {tenant_id}. "
            f"Last refreshed {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
            f"via `python example/fetch_jwks.py --write`. "
            "Keys are RSA public keys (n, e) used to verify JWT signatures. "
            "Not secrets — anyone with the JWKS URL can fetch them. "
            "Rotate when Microsoft rotates signing keys (~6 weeks)."
        ),
        "keys": jwks.get("keys", []),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tenant_id",
        nargs="?",
        default=DEFAULT_TENANT_ID,
        help="Microsoft Entra tenant ID (default: the customer-support-agent tenant)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"Write the fetched JWKS to {DEFAULT_SNAPSHOT_PATH}",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT_PATH,
        help="Override the snapshot output path (default: the project's snapshot)",
    )
    args = parser.parse_args()

    try:
        jwks = fetch_jwks(args.tenant_id)
    except Exception as exc:
        print(f"Error fetching JWKS: {exc}", file=sys.stderr)
        return 1

    keys = jwks.get("keys", [])
    print(f"Fetched {len(keys)} key(s) from tenant {args.tenant_id}", file=sys.stderr)

    if args.write:
        write_snapshot(jwks, args.tenant_id, args.snapshot)
        print(f"Wrote snapshot to {args.snapshot}", file=sys.stderr)
        print(
            "Review the change with: git diff -- "
            f"{args.snapshot.relative_to(Path.cwd()) if args.snapshot.is_absolute() else args.snapshot}",
            file=sys.stderr,
        )
        return 0

    # Default behavior: print the raw JWKS to stdout for ad-hoc inspection.
    print(json.dumps(jwks, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
