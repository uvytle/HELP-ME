#!/usr/bin/env python3
"""
Collect every openly available map of US terrestrial fiber routes, plus the
interstate rights-of-way long-haul fiber follows, into one GeoPackage
for QGIS.

Run:
    python build_dataset.py              # download everything
    python build_dataset.py --only osm   # one source (published|files|osm|interstates)
    python build_dataset.py --discover   # re-search ArcGIS Online for fiber layers first
    python build_dataset.py --refine     # re-apply catalog filter rules, no download

    python build_dataset.py --by-state   # only redo the per-state split

Output:
    data/us_fiber_network.gpkg    one layer per source (see README.md)
    data/us_fiber_by_state.gpkg   the fiber layers (published + OSM, not the
                                  interstates) split into one layer per state
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd

from sources import arcgis_fiber, carrier_files, ntad, osm_overpass, publishers

OUTPUT_PATH = Path(__file__).parent / "data" / "us_fiber_network.gpkg"
BY_STATE_PATH = Path(__file__).parent / "data" / "us_fiber_by_state.gpkg"
US_BOUNDARY_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_nation_20m.zip"
STATES_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_20m.zip"
FIBER_LAYERS = ["published_fiber_routes", "carrier_map_files", "osm_telecom_lines"]
OSM_TAGS = ["osm_id", "name", "operator", "owner", "communication", "telecom",
            "telecom:medium", "location", "utility", "cables", "ref"]

# GeoPackage layer name -> fetcher
SOURCES = {
    "published_fiber_routes": arcgis_fiber.fetch,
    "carrier_map_files": carrier_files.fetch,
    "osm_telecom_lines": osm_overpass.fetch,
    "interstates": ntad.fetch_interstates,
}
ALIASES = {"published": "published_fiber_routes", "files": "carrier_map_files",
           "osm": "osm_telecom_lines", "interstates": "interstates"}


def clip_to_us(gdf: gpd.GeoDataFrame, us: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep line features that touch US territory; drop non-line geometry.

    Published layers are found by a rough bounding-box test, so a few Canadian
    or Mexican border-town networks slip through discovery; this removes them.
    """
    gdf = gdf[~(gdf.geometry.isna() | gdf.geometry.is_empty)]
    gdf = gdf[gdf.geom_type.isin(["LineString", "MultiLineString"])]
    hits = gdf.sindex.query(us.geometry.iloc[0], predicate="intersects")
    return gdf.iloc[sorted(hits)].reset_index(drop=True)


DEDUPE_METERS = 10
PRIORITY = {"carrier": 0, "public": 1}  # anything else (OSM) comes last


def dedupe_across_datasets(group: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop features that repeat a route already present in another dataset.

    Many routes are published more than once, e.g. a county's copy of a
    carrier's network next to the carrier's own. Datasets are visited in
    priority order (the carrier's own copy, then government, then OSM; bigger
    datasets first within a tier). A feature is dropped when a point on it
    lies within DEDUPE_METERS of a feature already kept from a *different*
    dataset. Features within one dataset are never compared with each other.
    """
    g = group.to_crs("EPSG:5070")
    order = (g.groupby("dataset_title")
               .agg(prio=("publisher_type", lambda t: PRIORITY.get(t.iloc[0], 2)), n=("geometry", "size"))
               .sort_values(["prio", "n"], ascending=[True, False]).index)
    kept: list[gpd.GeoDataFrame] = []
    for title in order:
        part = g[g["dataset_title"] == title]
        if kept:
            ref = gpd.GeoDataFrame(pd.concat(kept, ignore_index=True)[["geometry"]], crs=g.crs)
            pts = gpd.GeoDataFrame(geometry=part.geometry.representative_point(), crs=g.crs)
            near = gpd.sjoin_nearest(pts, ref, max_distance=DEDUPE_METERS, how="left")
            near = near[~near.index.duplicated()]["index_right"].notna()
            part = part[~near.reindex(part.index, fill_value=False).values]
        kept.append(part)
    return gpd.GeoDataFrame(pd.concat(kept), crs=g.crs).to_crs("EPSG:4326").sort_index()


def split_by_state() -> None:
    """Write each fiber feature to a layer named after the state it falls in.

    A feature is assigned to the state containing its representative point
    (a point guaranteed to lie on the line), so a segment that crosses a state
    line lands in exactly one state rather than being cut in two. Routes that
    appear in several datasets are then de-duplicated per state.
    """
    frames = []
    for layer in FIBER_LAYERS:
        gdf = gpd.read_file(OUTPUT_PATH, layer=layer, engine="pyogrio")
        if layer == "osm_telecom_lines":
            # Put OSM into the published layer's schema: tags go in attributes.
            tags = gdf[[c for c in OSM_TAGS if c in gdf.columns]]
            gdf = gpd.GeoDataFrame({
                "publisher": "OpenStreetMap contributors",
                "publisher_type": "open data (ODbL)",
                "dataset_title": "OpenStreetMap telecom lines",
                "layer_name": "",
                "status_guess": "existing",
                "layer_url": "https://www.openstreetmap.org/" + tags["osm_id"],
                "attributes": [json.dumps({k: v for k, v in r.items() if v}) for r in
                               tags.astype(object).where(tags.notna(), None).to_dict("records")],
                "source": gdf["source"],
            }, geometry=gdf.geometry, crs=gdf.crs)
        frames.append(gdf)
    fiber = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    # Some sources ship a whole network as one multi-part line (Vision Net is a
    # single feature spanning Montana). Split them so each piece is assigned
    # to the state it's actually in.
    fiber = fiber.explode(index_parts=False).reset_index(drop=True)

    states = gpd.read_file(STATES_URL).to_crs("EPSG:4326")[["NAME", "STUSPS", "geometry"]]
    points = gpd.GeoDataFrame(geometry=fiber.geometry.representative_point(), crs="EPSG:4326")
    hits = gpd.sjoin(points, states, how="left", predicate="within")
    hits = hits[~hits.index.duplicated()]
    fiber["state"] = hits["NAME"]
    fiber["state_abbr"] = hits["STUSPS"]

    # Agency copies of Lumen/Zayo/Crown Castle only count inside the agency's state.
    label = fiber["dataset_title"].fillna("") + " " + fiber["layer_name"].fillna("")
    outside = [publishers.outside_jurisdiction(p or "", l, st or "")
               for p, l, st in zip(fiber["publisher"], label, fiber["state_abbr"])]
    print(f"  dropped {sum(outside):,} agency-copied Lumen/Zayo/Crown Castle features outside the agency's state")
    fiber = fiber[[not o for o in outside]]

    BY_STATE_PATH.unlink(missing_ok=True)
    for name, group in sorted(fiber.dropna(subset=["state"]).groupby("state")):
        deduped = dedupe_across_datasets(group)
        deduped.to_file(BY_STATE_PATH, layer=name, driver="GPKG", engine="pyogrio")
        print(f"  {name}: {len(deduped):,} ({len(group) - len(deduped):,} cross-dataset duplicates dropped)")
    print(f"-> {BY_STATE_PATH} ({fiber['state'].isna().sum():,} features fell just offshore/outside a state)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=sorted(ALIASES))
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--refine", action="store_true")
    ap.add_argument("--by-state", action="store_true")
    args = ap.parse_args()

    if args.discover:
        arcgis_fiber.discover()
    if args.refine:
        arcgis_fiber.refine_catalog()
        return

    if args.by_state:
        split_by_state()
        return

    us = gpd.read_file(US_BOUNDARY_URL).to_crs("EPSG:4326")
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    targets = [ALIASES[args.only]] if args.only else list(SOURCES)
    for layer in targets:
        t0 = time.time()
        print(f"{layer}:")
        try:
            gdf = clip_to_us(SOURCES[layer](), us)
        except Exception as exc:  # noqa: BLE001 - one source failing shouldn't kill the run
            print(f"  FAILED ({exc})")
            continue
        gdf.to_file(OUTPUT_PATH, layer=layer, driver="GPKG", engine="pyogrio")
        print(f"  {len(gdf):,} features written in {time.time() - t0:.0f}s")
    print(f"-> {OUTPUT_PATH}")
    if not args.only:
        print("by state:")
        split_by_state()


if __name__ == "__main__":
    main()
