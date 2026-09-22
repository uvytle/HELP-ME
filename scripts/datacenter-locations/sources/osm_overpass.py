"""
OpenStreetMap, via the public Overpass API — nodes/ways/relations tagged
telecom=data_center inside the US. Open data (ODbL); Overpass is a shared
public service, so this is a single bulk query rather than per-record hits.
"""

from __future__ import annotations

import requests

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; datacenter-locations-research/1.0)"}

QUERY = """
[out:json][timeout:180];
area["ISO3166-1"="US"][admin_level=2]->.us;
(
  node["telecom"="data_center"](area.us);
  way["telecom"="data_center"](area.us);
  relation["telecom"="data_center"](area.us);
);
out center tags;
"""


def _query_elements() -> list[dict]:
    last_error: Exception | None = None
    for url in OVERPASS_MIRRORS:
        try:
            resp = requests.post(url, headers=HEADERS, data={"data": QUERY}, timeout=200)
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception as exc:  # noqa: BLE001 - try the next mirror
            last_error = exc
    raise RuntimeError(f"All Overpass mirrors failed; last error: {last_error}")


def fetch() -> list[dict]:
    elements = _query_elements()

    records = []
    for el in elements:
        tags = el.get("tags", {})
        if "lat" in el and "lon" in el:
            lat, lon = el["lat"], el["lon"]
        else:
            center = el.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue

        address_parts = [
            tags.get("addr:housenumber"),
            tags.get("addr:street"),
        ]
        address = " ".join(p for p in address_parts if p)

        records.append(
            {
                "source": "osm",
                "source_id": f"{el.get('type')}/{el.get('id')}",
                "name": tags.get("name") or tags.get("operator") or "Unnamed data center",
                "operator": tags.get("operator"),
                "type": "colocation",
                "status": None,
                "address": address or None,
                "city": tags.get("addr:city"),
                "state": tags.get("addr:state"),
                "state_code": tags.get("addr:state"),
                "zip": tags.get("addr:postcode"),
                "country": "US",
                "latitude": lat,
                "longitude": lon,
                "size_mw": None,
                "year_built": None,
                "precision": "address" if address else "approximate",
                "url": tags.get("website") or tags.get("contact:website"),
            }
        )

    return records


if __name__ == "__main__":
    recs = fetch()
    print(f"osm: {len(recs)} records")
    if recs:
        print(recs[0])
