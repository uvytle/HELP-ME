#!/usr/bin/env python3
"""
MODELED NY / NJ / NH / MA routes, inferred from reference map images.

Same method as infer_idwy_routes.py. Vy supplied three screenshots of a regional
fiber map (2026-09-28): New Hampshire / northern Massachusetts, NYC / Jersey City,
and the NY-NJ metro. They show carrier routes (Zayo, Zenfi, EarthLink, GTT/Hibernia,
FirstLight, Crown Castle) that no public dataset has. Each route is read off the images
as the places it passes and drawn along the real street/road network:

- "car":      OSRM driving on OpenStreetMap, for highways and regional routes.
- "foot":     OSRM foot profile (routing.openstreetmap.de). Used inside Manhattan and
              the boroughs, so one-way streets don't bend an avenue route.
- "straight": a straight segment, for river crossings (tunnels, bridges and
              under-river conduit), which the reference also draws straight.

Border ends are extended to the nearest existing line in the neighbouring state's layer.
In the dense cores (Manhattan, Jersey City, downtown Brooklyn) only the trunk routes are
drawn (main avenues, crosstown streets and crossings), not the block-by-block laterals
the reference shows.

Run from scripts/us-fiber-network/:
    python tools/infer_ne_routes.py <output.gpkg>
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import LineString

sys.path.insert(0, str(Path(__file__).parent))
from infer_idwy_routes import neighbour_point  # noqa: E402

ROUTERS = {"car": "https://router.project-osrm.org/route/v1/driving/",
           "foot": "https://routing.openstreetmap.de/routed-foot/route/v1/driving/"}

# (state, route, corridor, profile, start neighbour, waypoints (lon, lat), end neighbour)
R = [
    # --- New Hampshire / Massachusetts (reference 1) ---
    # Northeastern MA has few published lines to join, and the reference runs these
    # routes into Boston, so they start at Boston's network. US-3 and NH-125 branch
    # off I-93 at Woburn and Methuen.
    ("New Hampshire", "Boston - Methuen - Salem - Manchester - Concord - Plymouth", "I-93", "car",
     ("Massachusetts", -71.06, 42.36),
     [(-71.06, 42.37), (-71.09, 42.42), (-71.12, 42.53), (-71.17, 42.65), (-71.19, 42.73), (-71.20, 42.77), (-71.30, 42.88), (-71.43, 42.98), (-71.46, 43.10), (-71.54, 43.21),
      (-71.60, 43.44), (-71.69, 43.76)], None),
    ("New Hampshire", "Woburn - Burlington - Lowell - Nashua - Manchester", "US-3 / Everett Turnpike", "car",
     None,
     [(-71.12, 42.53), (-71.20, 42.50), (-71.30, 42.56), (-71.36, 42.62), (-71.42, 42.67), (-71.42, 42.72), (-71.47, 42.77), (-71.50, 42.87), (-71.46, 42.99)], None),
    ("New Hampshire", "Manchester - Epping - Exeter - Portsmouth", "NH-101", "car",
     None, [(-71.46, 42.99), (-71.30, 43.02), (-71.07, 43.03), (-70.95, 42.98), (-70.79, 43.07)], None),
    ("New Hampshire", "Hooksett - Epsom - Northwood - Dover", "US-4 / NH-28", "car",
     None, [(-71.46, 43.10), (-71.34, 43.22), (-71.15, 43.20), (-70.99, 43.18), (-70.87, 43.20)], None),
    ("New Hampshire", "Methuen - Haverhill - Plaistow - Kingston - Epping - Northwood", "I-495 / NH-125", "car",
     None,
     [(-71.19, 42.73), (-71.08, 42.78), (-71.09, 42.83), (-71.10, 42.91), (-71.08, 43.03), (-71.15, 43.20)], None),
    ("New Hampshire", "Boston - Lynn - Newburyport - Seabrook - Portsmouth - Kittery", "US-1 / I-95", "car",
     ("Massachusetts", -71.06, 42.36),
     [(-71.05, 42.38), (-70.95, 42.47), (-70.93, 42.55), (-70.95, 42.70), (-70.88, 42.81), (-70.87, 42.89),
      (-70.855, 42.94), (-70.78, 43.06), (-70.74, 43.09)], ("Maine", -70.70, 43.15)),
    ("New Hampshire", "Manchester - Goffstown - Hillsborough - Keene - Northfield", "NH-114 / NH-9 / NH-10", "car",
     None, [(-71.46, 42.99), (-71.60, 43.02), (-71.90, 43.11), (-72.05, 43.03), (-72.28, 42.93),
            (-72.35, 42.82)], ("Massachusetts", -72.45, 42.70)),
    ("New Hampshire", "Hillsborough - Newport - Claremont - Lebanon", "NH-10 / NH-12A", "car",
     None, [(-71.90, 43.11), (-72.17, 43.37), (-72.34, 43.37), (-72.25, 43.64)], ("Vermont", -72.32, 43.65)),
    # --- Manhattan trunks (reference 2), walked along the avenues ---
    ("New York", "Manhattan: West Side (West St / 12th Ave / Riverside)", "West Side Hwy", "foot",
     None, [(-74.0165, 40.7045), (-74.0134, 40.7170), (-74.0100, 40.7400), (-74.0035, 40.7575),
            (-73.9870, 40.7810), (-73.9590, 40.8190), (-73.9480, 40.8500), (-73.9270, 40.8650)], None),
    ("New York", "Manhattan: Broadway", "Broadway", "foot",
     None, [(-74.0136, 40.7049), (-74.0012, 40.7190), (-73.9903, 40.7359), (-73.9877, 40.7505),
            (-73.9857, 40.7580), (-73.9819, 40.7681), (-73.9723, 40.7939), (-73.9580, 40.8150),
            (-73.9398, 40.8404), (-73.9270, 40.8650), (-73.9110, 40.8745)], None),
    ("New York", "Manhattan: Lafayette / Park Ave", "Park Ave", "foot",
     None, [(-74.0060, 40.7128), (-73.9990, 40.7230), (-73.9860, 40.7400), (-73.9772, 40.7527),
            (-73.9690, 40.7640), (-73.9530, 40.7860), (-73.9375, 40.8045)], None),
    ("New York", "Manhattan: East Side (South St / 1st Ave)", "1st Ave / FDR", "foot",
     None, [(-74.0030, 40.7060), (-73.9760, 40.7150), (-73.9800, 40.7310), (-73.9720, 40.7440),
            (-73.9600, 40.7590), (-73.9420, 40.7840), (-73.9330, 40.8010)], None),
    *[("New York", f"Manhattan: {name} crosstown", name, "foot", None, pts, None) for name, pts in [
        ("Canal St", [(-74.0100, 40.7230), (-73.9960, 40.7140), (-73.9920, 40.7140)]),
        ("14th St", [(-74.0080, 40.7400), (-73.9760, 40.7300)]),
        ("34th St", [(-74.0020, 40.7570), (-73.9710, 40.7445)]),
        ("42nd St", [(-73.9990, 40.7610), (-73.9690, 40.7480)]),
        ("57th St", [(-73.9920, 40.7710), (-73.9610, 40.7580)]),
        ("96th St", [(-73.9750, 40.7960), (-73.9420, 40.7830)]),
        ("125th St", [(-73.9590, 40.8190), (-73.9330, 40.8030)])]],
    # --- River crossings, drawn straight ---
    *[("New York", f"Crossing: {name}", name, "straight", None, pts, None) for name, pts in [
        ("George Washington Bridge", [(-73.9690, 40.8520), (-73.9480, 40.8500)]),
        ("Lincoln Tunnel", [(-74.0200, 40.7650), (-73.9975, 40.7590)]),
        ("Holland Tunnel", [(-74.0400, 40.7270), (-74.0080, 40.7260)]),
        ("PATH Hoboken - Christopher St", [(-74.0280, 40.7350), (-74.0070, 40.7330)]),
        ("PATH Exchange Place - WTC", [(-74.0330, 40.7160), (-74.0120, 40.7120)]),
        ("Brooklyn Bridge", [(-73.9990, 40.7110), (-73.9900, 40.7010)]),
        ("Manhattan Bridge", [(-73.9920, 40.7140), (-73.9840, 40.7000)]),
        ("Williamsburg Bridge", [(-73.9790, 40.7160), (-73.9580, 40.7110)]),
        ("Queensboro Bridge", [(-73.9610, 40.7590), (-73.9420, 40.7530)]),
        ("Queens-Midtown Tunnel", [(-73.9730, 40.7470), (-73.9480, 40.7440)]),
        ("Triborough / RFK", [(-73.9330, 40.8010), (-73.9270, 40.8030)]),
        ("Verrazzano-Narrows Bridge", [(-74.0590, 40.6040), (-74.0350, 40.6090)]),
        ("Bayonne Bridge", [(-74.1400, 40.6480), (-74.1420, 40.6380)])]],
    # --- Boroughs (reference 2 / 3) ---
    ("New York", "Brooklyn: BQE (Brooklyn Bridge - Greenpoint - Astoria)", "BQE", "car",
     None, [(-73.9900, 40.7010), (-73.9580, 40.7110), (-73.9450, 40.7270), (-73.9200, 40.7550),
            (-73.9020, 40.7700)], None),
    ("New York", "Brooklyn: Atlantic Ave to Jamaica", "Atlantic Ave", "foot",
     None, [(-73.9950, 40.6910), (-73.9750, 40.6840), (-73.9000, 40.6780), (-73.8090, 40.7000)], None),
    ("New York", "Brooklyn: Flatbush Ave", "Flatbush Ave", "foot",
     None, [(-73.9840, 40.6900), (-73.9600, 40.6600), (-73.9200, 40.6100)], None),
    ("New York", "Brooklyn: 4th Ave to Bay Ridge", "4th Ave", "foot",
     None, [(-73.9780, 40.6830), (-74.0000, 40.6500), (-74.0300, 40.6130), (-74.0350, 40.6090)], None),
    ("New York", "Queens: Queens Blvd to Jamaica", "Queens Blvd", "foot",
     None, [(-73.9400, 40.7500), (-73.8700, 40.7370), (-73.8300, 40.7150), (-73.8000, 40.7050)], None),
    ("New York", "Queens: Northern Blvd to Flushing", "Northern Blvd", "foot",
     None, [(-73.9360, 40.7520), (-73.8800, 40.7560), (-73.8300, 40.7600)], None),
    ("New York", "Queens / Long Island: LIE to Riverhead", "I-495", "car",
     None, [(-73.9480, 40.7440), (-73.8900, 40.7300), (-73.8100, 40.7400), (-73.7420, 40.7600),
            (-73.6000, 40.7800), (-73.4100, 40.7900), (-73.2000, 40.8200), (-72.9500, 40.8600),
            (-72.6600, 40.9200)], None),
    ("New York", "Long Island: Jamaica - Valley Stream - Babylon - Patchogue - Shirley", "Sunrise Hwy", "car",
     None, [(-73.8000, 40.7050), (-73.7000, 40.6600), (-73.5800, 40.6600), (-73.3300, 40.6900),
            (-73.0200, 40.7650), (-72.8700, 40.8000)], None),
    ("New York", "Bronx: Major Deegan to Yonkers and Tarrytown", "I-87", "car",
     None, [(-73.9270, 40.8030), (-73.9280, 40.8290), (-73.8980, 40.8900), (-73.8800, 40.9300),
            (-73.8600, 41.0700)], None),
    ("New York", "Bronx / Westchester: Cross Bronx - New Rochelle - Port Chester", "I-95", "car",
     None, [(-73.9300, 40.8480), (-73.8900, 40.8400), (-73.8300, 40.8280), (-73.8000, 40.8900),
            (-73.6700, 41.0000)], ("Connecticut", -73.63, 41.03)),
    ("New York", "Staten Island: Goethals - SIE - Verrazzano", "I-278", "car",
     None, [(-74.1900, 40.6350), (-74.1200, 40.6100), (-74.0590, 40.6040)], None),
    # --- Jersey City / Hudson County (reference 2) ---
    ("New Jersey", "Kennedy Blvd: Bayonne - Journal Square - Union City - Fort Lee", "Kennedy Blvd", "car",
     None, [(-74.1100, 40.6550), (-74.0630, 40.7330), (-74.0300, 40.7700), (-74.0100, 40.7950),
            (-73.9690, 40.8520)], None),
    ("New Jersey", "NJ Turnpike Newark Bay Extension: Jersey City - Newark Airport", "I-78 ext", "car",
     None, [(-74.0420, 40.7230), (-74.0900, 40.7000), (-74.1600, 40.6900)], None),
    ("New Jersey", "Route 1&9 / Pulaski Skyway: Jersey City - Newark", "US-1/9", "car",
     None, [(-74.0700, 40.7300), (-74.1100, 40.7350), (-74.1500, 40.7300)], None),
    ("New Jersey", "Route 3: Lincoln Tunnel - Secaucus - Clifton", "NJ-3", "car",
     None, [(-74.0200, 40.7650), (-74.0700, 40.7900), (-74.1500, 40.8500)], None),
    ("New Jersey", "Route 21: Newark - Passaic - Clifton", "NJ-21", "car",
     None, [(-74.1640, 40.7340), (-74.1250, 40.8600), (-74.1500, 40.8800)], None),
    ("New Jersey", "Hoboken - Weehawken waterfront", "River Rd", "foot",
     None, [(-74.0330, 40.7160), (-74.0280, 40.7350), (-74.0200, 40.7650)], None),
    # --- New Jersey long-haul (reference 3) ---
    ("New Jersey", "NJ Turnpike: Newark Airport - New Brunswick - Trenton", "I-95 / NJ Tpk", "car",
     None, [(-74.1745, 40.6895), (-74.2100, 40.6600), (-74.2800, 40.5600), (-74.4200, 40.4800),
            (-74.5200, 40.2800), (-74.6700, 40.1500), (-74.8000, 40.1100)], ("Pennsylvania", -74.85, 40.10)),
    ("New Jersey", "Northeast Corridor: Newark - New Brunswick - Princeton - Trenton", "US-1", "car",
     None, [(-74.1640, 40.7340), (-74.2150, 40.6670), (-74.2770, 40.6080), (-74.3630, 40.5430),
            (-74.4460, 40.4960), (-74.6230, 40.3160), (-74.7550, 40.2180)], ("Pennsylvania", -74.78, 40.20)),
    ("New Jersey", "Garden State Parkway: Union - Red Bank - Asbury Park - Toms River", "GSP", "car",
     None, [(-74.2600, 40.7000), (-74.2900, 40.5600), (-74.2300, 40.4200), (-74.0700, 40.3500),
            (-74.0500, 40.2200), (-74.0600, 40.1600), (-74.2000, 39.9700)], None),
    ("New Jersey", "I-78: Newark - Somerville - Clinton - Phillipsburg", "I-78", "car",
     None, [(-74.1900, 40.7100), (-74.3200, 40.6900), (-74.6300, 40.6000), (-74.9100, 40.6400),
            (-75.1900, 40.6900)], ("Pennsylvania", -75.21, 40.69)),
    ("New Jersey", "I-80: Fort Lee - Hackensack - Paterson - Parsippany - Water Gap", "I-80", "car",
     None, [(-73.9800, 40.8500), (-74.0500, 40.8800), (-74.1700, 40.9100), (-74.4300, 40.8700),
            (-74.7000, 40.9000), (-75.1400, 40.9700)], ("Pennsylvania", -75.16, 40.98)),
    ("New Jersey", "Route 17: Hackensack - Mahwah - Suffern", "NJ-17 / I-287", "car",
     None, [(-74.0700, 40.9400), (-74.1400, 41.0900)], ("New York", -74.15, 41.11)),
]


def drop_spurs(line: list[tuple[float, float]], tol_m: float = 80, max_loop_m: float = 5000) -> list:
    """Cut out out-and-back spurs and small loops.

    A waypoint that lands on a side street makes the router go in and come back
    out the same way. Whenever the line returns to within tol_m of a point it
    passed less than max_loop_m ago, the detour between them is removed. The
    tolerance is wide because on divided highways the detour comes back on the
    opposite carriageway, tens of metres from where it left.
    """
    import numpy as np
    xy = gpd.GeoSeries([LineString(line)], crs=4326).to_crs(5070).iloc[0].coords
    xy = np.asarray(xy)
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
    keep, i = [0], 1
    while i < len(xy):
        # look back along the kept path for a point we've come back to
        back = [k for k in keep[-400:] if seg[i] - seg[k] < max_loop_m and seg[i] - seg[k] > 3 * tol_m
                and np.hypot(*(xy[i] - xy[k])) < tol_m]
        if back:
            keep = keep[:keep.index(back[0]) + 1]
        else:
            keep.append(i)
        i += 1
    return [line[k] for k in keep]


def route(profile: str, pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if profile == "straight":
        return list(pts)
    coords = ";".join(f"{x:.5f},{y:.5f}" for x, y in pts)
    for attempt in range(4):
        r = requests.get(ROUTERS[profile] + coords, params={"overview": "full", "geometries": "geojson"}, timeout=120)
        if r.ok and r.json().get("code") == "Ok":
            return drop_spurs(r.json()["routes"][0]["geometry"]["coordinates"])
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"{profile} routing failed: {r.status_code} {r.text[:200]}")


def main(out_path: str) -> None:
    rows = []
    for state, name, corridor, profile, start, waypoints, end in R:
        pts = list(waypoints)
        head = neighbour_point(*start) if start else None
        tail = neighbour_point(*end) if end else None
        if head: pts.insert(0, (head.x, head.y))
        if tail: pts.append((tail.x, tail.y))
        line = route(profile, pts)
        if head and profile != "straight": line.insert(0, (head.x, head.y))
        if tail and profile != "straight": line.append((tail.x, tail.y))
        rows.append({"state": state, "route": name, "corridor": corridor, "profile": profile,
                     "connects_to": ", ".join(s[0] for s in (start, end) if s) or "",
                     "method": "MODELED: traced from reference map images, drawn along OSM streets/roads (OSRM)",
                     "confidence": "approximate", "geometry": LineString(line)})
        time.sleep(0 if profile == "straight" else 1)  # be polite to the public routers
    gdf = gpd.GeoDataFrame(rows, crs=4326)
    gdf["km"] = (gdf.to_crs(5070).length / 1000).round(1)
    for state, part in gdf.groupby("state"):
        part.to_file(out_path, layer=f"{state} (inferred)", driver="GPKG", engine="pyogrio")
        print(f"{state}: {len(part)} routes, {part.km.sum():,.0f} km")


if __name__ == "__main__":
    main(sys.argv[1])
