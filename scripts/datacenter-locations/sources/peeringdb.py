"""
PeeringDB — public, unauthenticated REST API of network facilities
(mostly colocation / carrier-neutral data centers). See https://www.peeringdb.com/apidocs/.
Unauthenticated requests are rate-limited hard, so this fetches everything in
ONE request (a high `limit` well above the real US facility count) instead of
paginating — fewer requests means less chance of tripping the limiter — and
retries with a long backoff if that single request gets a 429.
"""

from __future__ import annotations

import time

import requests

API_URL = "https://www.peeringdb.com/api/fac"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; datacenter-locations-research/1.0)"}
FETCH_LIMIT = 20000
BACKOFF_SECONDS = [10, 30, 60, 120]


def _fetch_all(session: requests.Session) -> list[dict]:
    params = {"country": "US", "limit": FETCH_LIMIT}
    last_error: Exception | None = None

    for delay in [0, *BACKOFF_SECONDS]:
        if delay:
            time.sleep(delay)
        resp = session.get(API_URL, headers=HEADERS, params=params, timeout=120)
        if resp.status_code == 429:
            last_error = RuntimeError("429 rate-limited")
            continue
        resp.raise_for_status()
        return resp.json().get("data", [])

    raise RuntimeError(f"PeeringDB kept rate-limiting us (429) after repeated backoff: {last_error}")


def fetch() -> list[dict]:
    session = requests.Session()
    records = []

    for r in _fetch_all(session):
        address_parts = [r.get("address1"), r.get("address2")]
        address = ", ".join(p for p in address_parts if p)
        records.append(
            {
                "source": "peeringdb",
                "source_id": r.get("id"),
                "name": r.get("name"),
                "operator": r.get("org_name"),
                "type": "colocation",
                "status": r.get("status"),
                "address": address or None,
                "city": r.get("city"),
                "state": r.get("state"),
                "state_code": r.get("state"),
                "zip": r.get("zipcode"),
                "country": r.get("country") or "US",
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "size_mw": None,
                "year_built": None,
                "precision": "address",
                "url": r.get("website"),
            }
        )

    return records


if __name__ == "__main__":
    recs = fetch()
    print(f"peeringdb: {len(recs)} records")
    print(recs[0])
