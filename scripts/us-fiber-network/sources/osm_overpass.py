"""
OpenStreetMap telecom lines inside the US, via the public Overpass API (ODbL).

OSM coverage of telecom cables is sparse (~2,000 ways nationally as of
2026-09) — mappers mostly add them where a cable is visibly marked on the
ground — so this is a supplement, not a backbone.
"""

from __future__ import annotations

import geopandas as gpd
import requests
from shapely.geometry import LineString

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {
    "User-Agent": "HELP-ME us-fiber-network builder (github.com/uvytle/HELP-ME)",
    "Accept": "application/json",
}

QUERY = """
[out:json][timeout:180];
area["ISO3166-1"="US"][admin_level=2]->.us;
(
  way["communication"="line"](area.us);
  way["telecom"="line"](area.us);
  way["telecom:medium"~"fib"](area.us);
  way["utility"="telecom"](area.us);
);
out tags geom;
"""

KEEP_TAGS = ["name", "operator", "owner", "communication", "telecom", "telecom:medium",
             "location", "utility", "cables", "ref"]


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


def fetch() -> gpd.GeoDataFrame:
    rows, geoms = [], []
    for el in _query_elements():
        pts = [(p["lon"], p["lat"]) for p in el.get("geometry") or []]
        if len(pts) < 2:
            continue
        tags = el.get("tags", {})
        rows.append({"osm_id": f"way/{el['id']}", **{k: tags.get(k) for k in KEEP_TAGS}})
        geoms.append(LineString(pts))
    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")
    gdf["source"] = "OpenStreetMap (Overpass)"
    return gdf
