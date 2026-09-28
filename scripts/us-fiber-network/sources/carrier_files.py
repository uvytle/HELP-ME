"""
Fiber routes that carriers publish as map *files* (KMZ, GeoPDF) rather than
ArcGIS layers. Found the same way as carrier_maps.py: by tracing Infrapedia's
US network list to each carrier's own website map.

- US Signal and Midwest Fiber Networks: their website maps draw fiber from
  KMZ files the carriers host themselves (listed in KMZ_SOURCES).
- Vision Net: the GeoJSON behind its website's coverage map.
- MassBroadband 123: the Massachusetts Broadband Institute's own KMZ of the
  state-built middle-mile network.
- Southern Telecom: GeoPDF network maps from southern-telecom.com, extracted
  once by tools/extract_geopdf.py into a committed GeoJSON (the pip GDAL has
  no PDF driver).
- Pilot Fiber (NYC): a KMZ shared on ArcGIS by the carrier's own account.
- WEBMAP_COLLECTIONS: line layers saved inside ArcGIS web maps rather than as
  services (NYC's record of Verizon micro-trenching).
"""

from __future__ import annotations

import json
import re
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

from .arcgis import SESSION

US_SIGNAL = "https://s3.us-east-1.amazonaws.com/ussignalkmz/"
MWFN = "https://www.midwestfibernetworks.com/media/"
MB123 = ("http://web.archive.org/web/2022id_/https://broadband.masstech.org/sites/mbi/files/"
         "documents/map-gallery/massbroadband-123-service-area-and-network-20140123.zip")
ALL_LINES = r"."
# (publisher, publisher_type, page that publishes/loads the files, file URLs,
#  regex of KML layer names to keep), as of 2026-09.
KMZ_SOURCES = [
    ("US Signal", "carrier", "https://ussignal.com/connectivity/interactive-network-map/", [US_SIGNAL + f for f in [
        "Wisconsin_2024-03-22-141236_hxxd.kmz", "Pennsylvania_2024-03-22-141146_vqtj.kmz",
        "Ohio_2024-03-22-141102_dedn.kmz", "Missouri_2024-03-22-141017_uydy.kmz",
        "Minnesota_2024-03-22-140941_zimj.kmz", "Michigan_PartA.kmz", "Michigan_PartB.kmz",
        "Michigan_PartC.kmz", "Kentucky_2024-03-22-140744_vkpt.kmz", "Iowa_2024-03-22-140659_shfh.kmz",
        "Indiana_2024-03-22-140511_gxew.kmz", "Illinois_2024-03-22-140411_xqxw.kmz"]], ALL_LINES),
    # The same page also loads "mwfn-nda-...-fiber-foot-print.kmz". It's deliberately
    # skipped: "nda" in the name suggests it's the non-disclosure version.
    ("Midwest Fiber Networks", "carrier", "https://www.midwestfibernetworks.com/network-map/",
     [MWFN + "dzrk2urn/mwfn-website-3-26-2025-iru.kmz"], ALL_LINES),
    # Vision Net (Montana): its website's network-coverage map loads this GeoJSON.
    # The number in the filename is a build stamp and will change when Vision Net
    # updates the map; if the fetch 404s, find the new name in the page's network log.
    ("Vision Net", "carrier", "https://vision.net/network-coverage/",
     ["https://vision.net/wp-content/uploads/fiver-map-viewer-3/dist/data/kmz-folders/"
      "enabled-lines-1779911864.geojson"], ALL_LINES),
    # MassBroadband 123: the state-built middle mile (Infrapedia: "massbroadband-123").
    # MBI published this KMZ on its "MassBroadband 123 Maps & Data" page, which has
    # since been removed; fetched from the Internet Archive's copy. The file's
    # "Lightower Fiber" layer (leased third-party fiber, now Crown Castle) is left out.
    ("Massachusetts Broadband Institute", "public",
     "broadband.masstech.org MassBroadband 123 Maps & Data (Jan 2014, via Internet Archive)",
     [MB123], r"^(Operational|Accepted|Final Review) Fiber$"),
    # Pilot Fiber (NYC): a KMZ of its network shared publicly on ArcGIS by a
    # pilotfiber.com account, i.e. the carrier's own file (July 2020).
    ("Pilot Fiber", "carrier", "ArcGIS item 'Pilot_Fiber_20200707' (owner kpittman@pilotfiber.com)",
     ["https://www.arcgis.com/sharing/rest/content/items/3dbdd2ac54b747ceb2883303f74c245e/data"], ALL_LINES),
]

# Line layers stored inside ArcGIS web maps as feature collections (no service
# URL), as (item id, layer title, publisher, publisher_type, basis, dataset title).
WEBMAP_COLLECTIONS = [
    # NYC's telecom franchise staff (DoITT, now OTI; the account also holds the
    # city's CityBridge/LinkNYC and FiOS build-verification maps) mapping Verizon's
    # micro-trenched fiber from permit records (Oct 2018).
    ("f5fde963e3d84ed8a628c27930d2b28f", "MapMT_VZ_Polylines 10262018", "NYC DoITT / OTI (telecom franchise staff)",
     "public", "city franchise staff account (pmcnicholas; hand-checked)", "NYC record of Verizon micro-trenched fiber"),
]
SOUTHERN_TELECOM = Path(__file__).parent / "static" / "southern_telecom_geopdf.geojson"


def _frame(gdf: gpd.GeoDataFrame, publisher: str, title: str, url: str, basis: str,
           publisher_type: str = "carrier") -> gpd.GeoDataFrame:
    attr_cols = [c for c in gdf.columns if c != "geometry"]
    attrs = gdf[attr_cols].astype(object).where(gdf[attr_cols].notna(), None)
    records = attrs.to_dict("records") if attr_cols else [{} for _ in range(len(gdf))]
    return gpd.GeoDataFrame({
        "publisher": publisher,
        "publisher_type": publisher_type,
        "dataset_title": title,
        "layer_name": basis,
        "status_guess": "existing",
        "layer_url": url,
        "attributes": [json.dumps({k: v for k, v in r.items() if v not in (None, "")}, default=str)
                       for r in records],
        "source": "Carrier map file",
    }, geometry=gdf.geometry.values, crs="EPSG:4326")


def fetch_kmz() -> gpd.GeoDataFrame:
    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        for publisher, ptype, page, urls, keep_layers in KMZ_SOURCES:
            for url in urls:
                name = url.rsplit("/", 1)[1]
                if name == "data":  # an ArcGIS item download: .../items/<id>/data
                    name = url.rsplit("/", 2)[1] + ".kmz"
                path = Path(tmp) / name
                path.write_bytes(SESSION.get(url, timeout=120).content)
                if path.suffix == ".zip":  # a KMZ shipped inside a zip
                    with zipfile.ZipFile(path) as zf:
                        inner = next(n for n in zf.namelist() if n.lower().endswith(".kmz"))
                        path = Path(tmp) / Path(inner).name
                        path.write_bytes(zf.read(inner))
                for layer, _ in pyogrio.list_layers(path):
                    if not re.search(keep_layers, layer):
                        continue
                    gdf = gpd.read_file(path, layer=layer, engine="pyogrio").to_crs("EPSG:4326")
                    gdf = gdf[gdf.geom_type.isin(["LineString", "MultiLineString"])]
                    if gdf.empty:
                        continue
                    gdf = gdf[[c for c in gdf.columns if c.lower() in ("name", "description", "geometry")]]
                    gdf["geometry"] = gdf.geometry.force_2d()
                    frames.append(_frame(gdf, publisher, f"{publisher} fiber: {layer}", url,
                                         f"published on: {page}", ptype))
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def fetch_southern_telecom() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(SOUTHERN_TELECOM, engine="pyogrio")
    out = _frame(gdf[["pdf_layer", "pen_color", "geometry"]], "Southern Telecom",
                 "", "", "carrier website: southern-telecom.com/network.html (GeoPDF)")
    out["dataset_title"] = "Southern Telecom: " + gdf["map_file"].str.replace(".pdf", "", regex=False)
    out["layer_url"] = gdf["map_url"]
    return out


def fetch_webmap_collections() -> gpd.GeoDataFrame:
    from shapely.geometry import MultiLineString
    frames = []
    for item_id, layer_title, publisher, ptype, basis, title in WEBMAP_COLLECTIONS:
        url = f"https://www.arcgis.com/sharing/rest/content/items/{item_id}/data"
        data = SESSION.get(url, params={"f": "json"}, timeout=120).json()
        for op in data.get("operationalLayers", []):
            for fl in (op.get("featureCollection") or {}).get("layers", []):
                if fl.get("layerDefinition", {}).get("name") != layer_title and op.get("title") != layer_title:
                    continue
                feats = fl.get("featureSet", {}).get("features", [])
                wkid = (fl.get("featureSet", {}).get("spatialReference")
                        or fl.get("layerDefinition", {}).get("spatialReference") or {"wkid": 102100})
                crs = "EPSG:3857" if wkid.get("latestWkid", wkid.get("wkid")) in (102100, 3857) else f"EPSG:{wkid['wkid']}"
                geoms = [MultiLineString(f["geometry"]["paths"]) for f in feats if f.get("geometry", {}).get("paths")]
                attrs = [f.get("attributes", {}) for f in feats if f.get("geometry", {}).get("paths")]
                gdf = gpd.GeoDataFrame(pd.DataFrame(attrs), geometry=geoms, crs=crs).to_crs("EPSG:4326")
                frames.append(_frame(gdf, publisher, title, f"https://www.arcgis.com/home/item.html?id={item_id}",
                                     basis, ptype))
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def fetch() -> gpd.GeoDataFrame:
    frames = []
    for fn in (fetch_kmz, fetch_southern_telecom, fetch_webmap_collections):
        try:
            frames.append(fn())
            print(f"  {fn.__name__}: {len(frames[-1]):,} features")
        except Exception as exc:  # noqa: BLE001 - one carrier failing shouldn't kill the build
            print(f"  {fn.__name__}: FAILED ({exc})")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
