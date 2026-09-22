"""
usdatamap.com — the whole dataset ships as a static, unauthenticated JS bundle
(no API, no scraping of rendered HTML needed). robots.txt allows crawling
(Allow: /, only /admin and /lovable/ disallowed).
"""

from __future__ import annotations

import re

import json5  # type: ignore[import-untyped]
import requests

BASE_URL = "https://usdatamap.com/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; datacenter-locations-research/1.0)"}

# Map usdatamap's own "type" values onto our normalized taxonomy.
TYPE_MAP = {
    "colocation": "colocation",
    "hyperscale": "hyperscale",
    "cloud": "cloud",
    "managed": "managed_services",
    "managed_services": "managed_services",
    "edge": "edge",
}


def _find_facilities_bundle_url(session: requests.Session) -> str:
    resp = session.get(BASE_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    match = re.search(r'["\'](/assets/data-facilities-[\w-]+\.js)["\']', resp.text)
    if not match:
        raise RuntimeError(
            "Could not find the data-facilities-*.js bundle reference on "
            "usdatamap.com — the site's build output may have changed shape."
        )
    return BASE_URL.rstrip("/") + match.group(1)


def _extract_array_literal(js_source: str) -> str:
    match = re.search(r"=\s*(\[.*\])\s*;\s*export", js_source, re.DOTALL)
    if not match:
        raise RuntimeError(
            "Could not locate the facility array literal inside the "
            "data-facilities bundle — its structure may have changed."
        )
    return match.group(1)


def fetch() -> list[dict]:
    session = requests.Session()
    bundle_url = _find_facilities_bundle_url(session)
    resp = session.get(bundle_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    raw_records = json5.loads(_extract_array_literal(resp.text))

    records = []
    for r in raw_records:
        records.append(
            {
                "source": "usdatamap",
                "source_id": r.get("id"),
                "name": r.get("name"),
                "operator": r.get("company"),
                "type": TYPE_MAP.get(r.get("type"), r.get("type") or "unknown"),
                "status": r.get("status"),
                "address": None,
                "city": r.get("city"),
                "state": r.get("state"),
                "state_code": r.get("stateCode"),
                "zip": None,
                "country": "US",
                "latitude": r.get("lat"),
                "longitude": r.get("lng"),
                "size_mw": r.get("sizeMW"),
                "year_built": r.get("yearBuilt") or r.get("expectedCompletion"),
                "precision": "address",
                "url": None,
            }
        )
    return records


if __name__ == "__main__":
    recs = fetch()
    print(f"usdatamap: {len(recs)} records")
    print(recs[0])
