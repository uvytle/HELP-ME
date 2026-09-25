"""
Fiber routes that carriers publish as map *files* (KMZ, GeoPDF) rather than
ArcGIS layers. Found the same way as carrier_maps.py: by tracing Infrapedia's
US network list to each carrier's own website map.

- US Signal and Midwest Fiber Networks: their website maps draw fiber from
  KMZ files the carriers host themselves (listed in KMZ_SOURCES).
- Southern Telecom: GeoPDF network maps from southern-telecom.com, extracted
  once by tools/extract_geopdf.py into a committed GeoJSON (the pip GDAL has
  no PDF driver).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

from .arcgis import SESSION

US_SIGNAL = "https://s3.us-east-1.amazonaws.com/ussignalkmz/"
MWFN = "https://www.midwestfibernetworks.com/media/"
# (publisher, the carrier page whose public map loads the files, file URLs), as of 2026-09.
KMZ_SOURCES = [
    ("US Signal", "https://ussignal.com/connectivity/interactive-network-map/", [US_SIGNAL + f for f in [
        "Wisconsin_2024-03-22-141236_hxxd.kmz", "Pennsylvania_2024-03-22-141146_vqtj.kmz",
        "Ohio_2024-03-22-141102_dedn.kmz", "Missouri_2024-03-22-141017_uydy.kmz",
        "Minnesota_2024-03-22-140941_zimj.kmz", "Michigan_PartA.kmz", "Michigan_PartB.kmz",
        "Michigan_PartC.kmz", "Kentucky_2024-03-22-140744_vkpt.kmz", "Iowa_2024-03-22-140659_shfh.kmz",
        "Indiana_2024-03-22-140511_gxew.kmz", "Illinois_2024-03-22-140411_xqxw.kmz"]]),
    # The same page also loads "mwfn-nda-...-fiber-foot-print.kmz". It's deliberately
    # skipped: "nda" in the name suggests it's the non-disclosure version.
    ("Midwest Fiber Networks", "https://www.midwestfibernetworks.com/network-map/",
     [MWFN + "dzrk2urn/mwfn-website-3-26-2025-iru.kmz"]),
]
SOUTHERN_TELECOM = Path(__file__).parent / "static" / "southern_telecom_geopdf.geojson"


def _frame(gdf: gpd.GeoDataFrame, publisher: str, title: str, url: str, basis: str) -> gpd.GeoDataFrame:
    attr_cols = [c for c in gdf.columns if c != "geometry"]
    attrs = gdf[attr_cols].astype(object).where(gdf[attr_cols].notna(), None)
    return gpd.GeoDataFrame({
        "publisher": publisher,
        "publisher_type": "carrier",
        "dataset_title": title,
        "layer_name": basis,
        "status_guess": "existing",
        "layer_url": url,
        "attributes": [json.dumps({k: v for k, v in r.items() if v not in (None, "")}, default=str)
                       for r in attrs.to_dict("records")],
        "source": "Carrier map file",
    }, geometry=gdf.geometry.values, crs="EPSG:4326")


def fetch_kmz() -> gpd.GeoDataFrame:
    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        for publisher, page, urls in KMZ_SOURCES:
            for url in urls:
                path = Path(tmp) / url.rsplit("/", 1)[1]
                path.write_bytes(SESSION.get(url, timeout=120).content)
                for layer, _ in pyogrio.list_layers(path):
                    gdf = gpd.read_file(path, layer=layer, engine="pyogrio").to_crs("EPSG:4326")
                    gdf = gdf[gdf.geom_type.isin(["LineString", "MultiLineString"])]
                    if gdf.empty:
                        continue
                    gdf = gdf[[c for c in ("Name", "description", "geometry") if c in gdf]]
                    gdf["geometry"] = gdf.geometry.force_2d()
                    frames.append(_frame(gdf, publisher, f"{publisher} fiber: {layer}", url,
                                         f"carrier website: {page}"))
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def fetch_southern_telecom() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(SOUTHERN_TELECOM, engine="pyogrio")
    out = _frame(gdf[["pdf_layer", "pen_color", "geometry"]], "Southern Telecom",
                 "", "", "carrier website: southern-telecom.com/network.html (GeoPDF)")
    out["dataset_title"] = "Southern Telecom: " + gdf["map_file"].str.replace(".pdf", "", regex=False)
    out["layer_url"] = gdf["map_url"]
    return out


def fetch() -> gpd.GeoDataFrame:
    frames = []
    for fn in (fetch_kmz, fetch_southern_telecom):
        try:
            frames.append(fn())
            print(f"  {fn.__name__}: {len(frames[-1]):,} features")
        except Exception as exc:  # noqa: BLE001 - one carrier failing shouldn't kill the build
            print(f"  {fn.__name__}: FAILED ({exc})")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
