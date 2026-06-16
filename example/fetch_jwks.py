"""Fetch JWKS from Microsoft Entra ID for the customer-support-agent tenant.

Use this to refresh the hardcoded JWKS in
backend/app/api/auth/jwks_fetcher.py when Microsoft rotates its signing keys
(typically every ~6 weeks).

Usage:
    python example/fetch_jwks.py
    python example/fetch_jwks.py <tenant_id>
    python example/fetch_jwks.py <tenant_id> --out jwks.json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path


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


def render_paste_ready(jwks: dict, tenant_id: str) -> str:
    """Render the JWKS as a Python literal ready to paste into jwks_fetcher.py."""
    keys = jwks.get("keys", [])
    header = (
        f"# JWKS for tenant {tenant_id}\n"
        f"# Fetched with: python example/fetch_jwks.py {tenant_id}\n"
        f"# {len(keys)} key(s) — rotate when Microsoft rotates signing keys (~6 weeks).\n"
        f"_HARDCODED_JWKS: dict[str, Any] = "
    )
    return header + json.dumps(jwks, indent=4) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tenant_id",
        nargs="?",
        default="4922a12a-f1fd-40bc-affe-c63dc44acc33",
        help="Microsoft Entra tenant ID (default: the one for customer-support-agent)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional path to write the raw JWKS JSON to",
    )
    args = parser.parse_args()

    try:
        jwks = fetch_jwks(args.tenant_id)
    except Exception as exc:
        print(f"Error fetching JWKS: {exc}", file=sys.stderr)
        return 1

    if args.out:
        args.out.write_text(json.dumps(jwks, indent=2), encoding="utf-8")
        print(f"Wrote {len(jwks.get('keys', []))} key(s) to {args.out}", file=sys.stderr)

    print(render_paste_ready(jwks, args.tenant_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
