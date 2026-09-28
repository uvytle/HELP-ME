#!/usr/bin/env python3
"""
MODELED Idaho and Wyoming long-haul routes, inferred from reference map images.

Vy supplied two screenshots of a regional fiber map (2026-09-28) showing long-haul
routes that no public dataset has for ID/WY. Each route below was read off those
images as the sequence of towns it passes, and then drawn along the real road network
(OSRM on OpenStreetMap). Fiber in this region follows highway rights-of-way, so the
shape formally matches the reference, but the position is only as good as that
assumption. These are *not* surveyed or published routes.

Where a route reaches a state line, it's extended along the road to the nearest
existing line in the neighbouring state's layer (from data/us_fiber_by_state.gpkg),
so the modeled network connects to the adjacent states.

Run from scripts/us-fiber-network/:
    python tools/infer_idwy_routes.py <output.gpkg>
"""

from __future__ import annotations

import sys
import time

import geopandas as gpd
import requests
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

BY_STATE = "data/us_fiber_by_state.gpkg"
OSRM = "https://router.project-osrm.org/route/v1/driving/"

# (state, route name, corridor, [start neighbour], waypoints (lon, lat), [end neighbour])
# A neighbour entry (state layer, lon, lat) snaps that end to the nearest existing line
# in that state around the given border crossing.
ROUTES = [
    ("Idaho", "Spokane - Coeur d'Alene - Lookout Pass - St. Regis", "I-90",
     ("Washington", -117.04, 47.70),
     [(-116.95, 47.71), (-116.78, 47.68), (-116.12, 47.54), (-115.93, 47.47), (-115.70, 47.46)],
     # Vision Net runs along I-90 from St. Regis; its nearest point to Lookout
     # Pass is off at Thompson Falls, which would bend the route north.
     ("Montana", -115.10, 47.30)),
    ("Idaho", "Coeur d'Alene - Sandpoint - Clark Fork", "US-95 / ID-200",
     None,
     [(-116.78, 47.68), (-116.71, 47.95), (-116.55, 48.28), (-116.30, 48.25), (-116.18, 48.15)],
     ("Montana", -116.05, 48.10)),
    ("Idaho", "Pullman - Moscow - Lewiston - Clarkston", "WA-270 / US-95",
     ("Washington", -117.04, 46.73),
     [(-117.00, 46.73), (-116.93, 46.55), (-117.01, 46.42)],
     ("Washington", -117.05, 46.42)),
    ("Idaho", "Ontario - Boise - Twin Falls - Pocatello - Malad", "I-84 / I-86 / I-15",
     ("Oregon", -116.95, 44.05),
     [(-116.92, 44.01), (-116.69, 43.66), (-116.56, 43.58), (-116.20, 43.61), (-115.69, 43.13),
      (-114.95, 42.93), (-114.52, 42.72), (-113.79, 42.54), (-113.63, 42.52), (-112.86, 42.78),
      (-112.45, 42.87), (-112.19, 42.65), (-112.25, 42.19)],
     ("Utah", -112.25, 42.00)),
    ("Wyoming", "Evanston - Rock Springs - Rawlins - Laramie - Cheyenne", "I-80",
     ("Utah", -111.05, 41.25),
     [(-110.96, 41.27), (-110.30, 41.33), (-109.86, 41.54), (-109.47, 41.53), (-109.22, 41.59),
      (-108.79, 41.68), (-107.97, 41.67), (-107.24, 41.79), (-106.84, 41.76), (-106.21, 41.59),
      (-105.59, 41.31), (-105.30, 41.12), (-104.82, 41.14)],
     None),
    ("Wyoming", "Walcott - Medicine Bow - Laramie - Cheyenne", "US-30/287 / WY-210",
     None,
     [(-106.84, 41.76), (-106.56, 41.87), (-106.20, 41.90), (-105.97, 41.74), (-105.69, 41.57),
      (-105.59, 41.31), (-105.23, 41.17), (-104.82, 41.14)],
     None),
    ("Wyoming", "Cheyenne - Fort Collins", "I-25",
     # Joined at Fort Collins: the Colorado layer's nearest line to the border is a
     # piece poking north into Cheyenne, which would make the route double back.
     None, [(-104.82, 41.14), (-104.95, 41.00)], ("Colorado", -105.00, 40.70)),
    ("Wyoming", "Cheyenne - Casper - Ten Sleep - Greybull - Lovell - Billings", "I-25 / US-20/26 / WY-434 / US-310",
     None,
     [(-104.82, 41.14), (-104.82, 41.76), (-104.95, 42.05), (-104.95, 42.50), (-105.38, 42.76),
      (-105.87, 42.86), (-106.32, 42.85), (-106.99, 43.03), (-107.19, 43.06), (-107.35, 43.11),
      # Big Trails, on the Nowood Road (WY-434). Without it the router detours
      # west via Shoshoni and Thermopolis, away from the reference line.
      (-107.33, 43.80), (-107.45, 44.03), (-107.60, 44.25), (-107.96, 44.27), (-108.04, 44.38),
      (-108.06, 44.49), (-108.39, 44.84), (-108.47, 44.88), (-108.62, 44.97)],
     ("Montana", -108.62, 45.00)),
]


def neighbour_point(state: str, lon: float, lat: float) -> Point:
    """Nearest point on an existing line in `state`'s layer to a border crossing."""
    g = gpd.read_file(BY_STATE, layer=state, engine="pyogrio",
                      bbox=(lon - 1.5, lat - 1.5, lon + 1.5, lat + 1.5)).to_crs(5070)
    here = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(5070).iloc[0]
    line = g.geometry.iloc[g.distance(here).argmin()]
    snapped = nearest_points(line, here)[0]
    return gpd.GeoSeries([snapped], crs=5070).to_crs(4326).iloc[0]


def road_route(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    coords = ";".join(f"{x:.5f},{y:.5f}" for x, y in points)
    for attempt in range(4):
        r = requests.get(OSRM + coords, params={"overview": "full", "geometries": "geojson"}, timeout=120)
        if r.ok and r.json().get("code") == "Ok":
            return r.json()["routes"][0]["geometry"]["coordinates"]
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"OSRM failed: {r.status_code} {r.text[:200]}")


def main(out_path: str) -> None:
    rows = []
    for state, name, corridor, start, waypoints, end in ROUTES:
        pts = list(waypoints)
        head = neighbour_point(*start) if start else None
        tail = neighbour_point(*end) if end else None
        if head: pts.insert(0, (head.x, head.y))
        if tail: pts.append((tail.x, tail.y))
        line = road_route(pts)
        # OSRM starts/ends on the nearest road; close the gap to the neighbour's line.
        if head: line.insert(0, (head.x, head.y))
        if tail: line.append((tail.x, tail.y))
        rows.append({"state": state, "route": name, "corridor": corridor,
                     "connects_to": ", ".join(s[0] for s in (start, end) if s) or "",
                     "method": "MODELED: traced from reference map images, drawn along OSM roads (OSRM)",
                     "confidence": "approximate", "geometry": LineString(line)})
        time.sleep(1)  # be polite to the public OSRM demo server
    gdf = gpd.GeoDataFrame(rows, crs=4326)
    gdf["km"] = (gdf.to_crs(5070).length / 1000).round(1)
    for state, part in gdf.groupby("state"):
        part.to_file(out_path, layer=f"{state} (inferred)", driver="GPKG", engine="pyogrio")
        print(f"{state}: {len(part)} routes, {part.km.sum():,.0f} km")
        print(part[["route", "km", "connects_to"]].to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
