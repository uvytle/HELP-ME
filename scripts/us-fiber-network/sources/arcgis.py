"""
Shared helpers for pulling features out of public ArcGIS REST layers
(FeatureServer/<n> or MapServer/<n>) as GeoDataFrames in EPSG:4326.

Layers cap how many features one request returns (maxRecordCount, usually
1000-2000), so everything here pages by object ID: ask for the full ID list
once, then fetch the features in chunks. That works on every server version,
including old MapServers that don't support resultOffset paging.
"""

from __future__ import annotations

import time

import geopandas as gpd
import pandas as pd
import requests

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "HELP-ME us-fiber-network builder (github.com/uvytle/HELP-ME)"

TIMEOUT = 90


def get_json(url: str, params: dict | None = None, retries: int = 3) -> dict:
    """GET (or POST, for long ID lists) an ArcGIS REST URL and return parsed JSON.

    ArcGIS reports most failures as HTTP 200 with an {"error": ...} body, so
    that case is raised as an exception too.
    """
    params = {**(params or {}), "f": params.get("f", "json") if params else "json"}
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            if sum(len(str(v)) for v in params.values()) > 500:
                resp = SESSION.post(url, data=params, timeout=TIMEOUT)
            else:
                resp = SESSION.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "error" in data:
                raise RuntimeError(f"ArcGIS error: {data['error']}")
            return data
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_exc = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url}: {last_exc}")


def layer_info(layer_url: str) -> dict:
    return get_json(layer_url)


def fetch_layer(
    layer_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    max_offset_deg: float | None = None,
    chunk: int | None = None,
) -> gpd.GeoDataFrame:
    """Download every feature matching `where` from one ArcGIS layer.

    max_offset_deg: optional server-side line generalization (in degrees).
    Used for the big NTAD context layers, where full survey-grade vertex
    density just bloats the file without changing what a US-scale map shows.
    """
    info = layer_info(layer_url)
    ids = get_json(
        f"{layer_url}/query", {"where": where, "returnIdsOnly": "true"}
    ).get("objectIds") or []
    if not ids:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    ids.sort()
    step = chunk or min(int(info.get("maxRecordCount") or 1000), 1000)

    frames = []
    for i in range(0, len(ids), step):
        params = {
            "objectIds": ",".join(map(str, ids[i : i + step])),
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": "4326",
            "geometryPrecision": "6",
            "f": "geojson",
        }
        if max_offset_deg:
            params["maxAllowableOffset"] = str(max_offset_deg)
        fc = get_json(f"{layer_url}/query", params)
        feats = [f for f in fc.get("features", []) if f.get("geometry")]
        if feats:
            frames.append(gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326"))
    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
