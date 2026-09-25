"""
Fiber routes that carriers, states, counties, cities, DOTs and utilities have
published themselves as public ArcGIS layers.

No one publishes a national fiber map, but hundreds of organizations publish
their own piece of one on ArcGIS Online (Segra, Everstream, FiberLight, NoaNet,
Vermont PSD, UDOT, Caltrans, city traffic/ITS networks, ...). This module:

  discover()  searches ArcGIS Online for public fiber layers located in the US,
              opens each service, keeps polyline layers that look like fiber
              routes, and writes them to arcgis_fiber_catalog.csv.
  fetch()     downloads every catalog row with include=1 into one layer.

The catalog is committed so a normal build is reproducible and doesn't depend
on search ranking; rerun discovery (`build_dataset.py --discover`) to pick up
newly published layers. To drop a bad layer by hand, set its exclude_reason
to "manual: <why>"; that survives rediscovery.
"""

from __future__ import annotations

import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import carrier_maps, publishers
from .arcgis import fetch_layer, get_json

CATALOG_PATH = Path(__file__).parent / "arcgis_fiber_catalog.csv"
SEARCH_URL = "https://www.arcgis.com/sharing/rest/search"

SEARCH_TERMS = [
    "fiber optic", "fibre optic", "fiber route", "fiber routes", "fiber network",
    "fiber lines", "fiber backbone", "long haul fiber", "middle mile fiber",
    "ITS fiber", "traffic fiber", "broadband fiber", "dark fiber", "fiber cable",
    "telecom lines", "communication lines", "conduit fiber",
]

# Item title/tags must look fiber/telecom related...
TOPIC_RE = re.compile(r"fib(er|re)|telecom|communication|conduit|\bits\b|backbone|dark fiber", re.I)
# ...and not be one of the many fiber-adjacent products that aren't routes:
# coverage/availability polygons, BEAD/BSL locations, grants, permits, costs,
# buffers, wish lists, survey forms.
ITEM_EXCLUDE_RE = re.compile(
    r"coverage|availab|serviceable|\bbsl|bead|grant|permit|cost|buffer|hex|"
    r"wish|need|priorit|survey|form\b|household|thiessen|speed|manufactur|"
    r"submarine|households|demand|eligib|challenge|address",
    re.I,
)
# A layer is kept if its own name says fiber/telecom, or if the service is
# fiber-titled and the layer isn't obviously another utility.
LAYER_FIBER_RE = re.compile(r"fib(er|re)|telecom|comm|conduit|optic|backbone|route|lateral|cable|span|ring|network|duct", re.I)
LAYER_EXCLUDE_RE = re.compile(
    r"water|sewer|storm|gas\b|electric|power|parcel|boundar|buffer|area|zone|"
    r"coverage|hex|permit|road|street(?!.*fib)|county|city limits|building|"
    r"pole|handhole|hand hole|vault|splice|node|pop|cabinet|pedestal|pit|manhole|"
    r"address|annotation|label|dimension",
    re.I,
)
PLANNED_RE = re.compile(r"propos|plan|future|design|potential|candidate|draft", re.I)

# Second pass over discovered layers, tuned by reading the first catalog. Each
# rule records why a layer was dropped (include=0, exclude_reason) instead of
# deleting the row, so the catalog stays auditable. (field, reason, pattern)
REFINE_RULES = [
    ("title+layer", "confidential", re.compile(r"confidential", re.I)),
    # Last-mile service drops to individual buildings, not network routes.
    ("title+layer", "service drop", re.compile(r"(?<![a-z])drops?(?![a-z])|service line|fiber service", re.I)),
    # Vermont PSD publishes cable-TV (coax) routes alongside its fiber routes.
    ("title+layer", "coax/cable TV", re.compile(r"(?<!fiber )cable routes|cable service", re.I)),
    # Electric-utility layers bundled in "fiber + electric" utility services.
    ("layer", "electric", re.compile(
        r"elec(?!om)|primary|secondary|conductor|\bmains?\b|lateral_lines|busbar|aadt|"
        r"overhead lines|underground lines", re.I)),
    # Analysis products derived from fiber (buffers, road segments near fiber,
    # hex/H3 estimates, corridors) and drafting layers (markup, labels).
    ("title+layer", "derived/not a route", re.compile(
        r"1mile|intersect|h3\b|_h3|est_h3|service ?corridor|face_of_curb|(?<!fiber )centerline|"
        r"markup|missing_counts|allocation|label|indoor|\bdetails\b|schematic|backup|background", re.I)),
    ("title+layer", "outside US", re.compile(r"canada|coquitlam", re.I)),
    # The per-state search's "conduit" term also finds non-telecom conduit:
    # stormwater/sewer/irrigation pipes, flood models, street-light conduit.
    ("title+layer", "not telecom (water/storm/lighting conduit)", re.compile(
        r"storm|sanitary|sewer|irrigat|drainage|flood|culvert|open channel|icm_model|"
        r"surcharge|capacityanalysis|water|street ?light|slconduit|lighting|"
        r"electric(?!.*fib)", re.I)),
    ("title+layer", "not a route (customers/prospects)", re.compile(r"potential|customers|prospect", re.I)),
]


YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d\d)(?!\d)")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _series_key(r: dict) -> tuple | None:
    """(owner, title-without-years) for yearly snapshots like "VT Fiber Routes 2022"."""
    if not YEAR_RE.search(r["title"]):
        return None
    return (r["owner"], _norm(YEAR_RE.sub("", r["title"])))


def refine(rows: list[dict]) -> list[dict]:
    """Mark non-route, sensitive, untraceable and duplicate layers include=0.

    Every dropped row keeps an exclude_reason so the catalog stays auditable.
    Needs publisher info, so looks up any rows that don't have it yet.
    """
    publishers.annotate(rows)
    seen: set = set()
    # Yearly snapshots of one dataset: only the newest year is kept.
    newest: dict[tuple, int] = {}
    for r in rows:
        if (k := _series_key(r)):
            newest[k] = max(newest.get(k, 0), max(map(int, YEAR_RE.findall(r["title"]))))
    # Visit acceptable publishers first, so when a dataset exists both as an
    # official layer and as someone's re-upload, the official one is kept.
    # Manual exclusions go first so their other copies are caught as duplicates.
    def is_manual(r: dict) -> bool:
        return r.get("exclude_reason", "").startswith("manual")

    for r in sorted(rows, key=lambda r: (not is_manual(r),
                                         bool(publishers.rejection_reason(r)),
                                         -int(r["feature_count"]))):
        # Views and re-shares of one dataset show up as separate items with the
        # same layer and the same feature count. Long, distinctive layer names
        # (e.g. SegraFiberNetworkFinal_06202024) identify one dataset even when
        # copies differ by a few features.
        keys = {(int(r["feature_count"]), _norm(r["layer_name"]))}
        if len(_norm(r["layer_name"])) >= 20:
            keys.add(_norm(r["layer_name"]))
        if is_manual(r):
            r["include"] = 0
            seen |= keys
            continue
        r["include"], r["exclude_reason"] = 0, ""
        texts = {"layer": r["layer_name"], "title+layer": f"{r['title']} {r['layer_name']}"}
        reason = next((why for field, why, pattern in REFINE_RULES
                       if pattern.search(texts[field])), "")
        reason = reason or publishers.rejection_reason(r)
        sk = _series_key(r)
        if not reason and sk and max(map(int, YEAR_RE.findall(r["title"]))) < newest[sk]:
            reason = "older yearly snapshot"
        if not reason and keys & seen:
            reason = "duplicate copy"
        if reason:
            r["exclude_reason"] = reason
        else:
            r["include"] = 1
            seen |= keys
    return rows


def merge_seeds(rows: list[dict]) -> list[dict]:
    """Add the hand-traced layers from carrier_maps, overriding publisher info
    on any row the keyword search had already found (e.g. Uniti's dark fiber,
    first seen as an anonymous upload before its account was traced to
    Uniti's own website)."""
    by_url = {r["layer_url"]: r for r in rows}
    for seed in carrier_maps.seed_rows():
        if seed["layer_url"] in by_url:
            by_url[seed["layer_url"]].update({k: seed[k] for k in (
                "publisher", "publisher_type", "publisher_basis", "seeded", "title", "status_guess")})
        else:
            rows.append(seed)
    return rows


def refine_catalog() -> None:
    """Re-apply the filter rules to the saved catalog without re-searching."""
    with CATALOG_PATH.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    _write_catalog(refine(merge_seeds(rows)))


def _write_catalog(rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: (-int(r["include"]), -int(r["feature_count"])))
    with CATALOG_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CATALOG_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    kept = [r for r in rows if int(r["include"])]
    print(f"  arcgis catalog: {len(kept)}/{len(rows)} layers included "
          f"({sum(int(r['feature_count']) for r in kept):,} features) -> {CATALOG_PATH.name}")

# Rough boxes for CONUS, Alaska, Hawaii, Puerto Rico. Only used to discard
# obviously foreign items before probing; downloaded features are clipped to
# the real US boundary in build_dataset.py.
US_BOXES = [(-125.0, 24.0, -66.5, 49.5), (-170.0, 51.0, -129.0, 71.5),
            (-161.0, 18.5, -154.5, 22.5), (-68.0, 17.5, -65.0, 18.7)]

CATALOG_FIELDS = ["include", "exclude_reason", "publisher", "publisher_type",
                  "publisher_basis", "status_guess", "title", "owner", "layer_name",
                  "feature_count", "layer_url", "item_id", "seeded"]


def _in_us(extent) -> bool:
    try:
        (x0, y0), (x1, y1) = extent
    except (TypeError, ValueError):
        return False
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return any(a <= cx <= c and b <= cy <= d for a, b, c, d in US_BOXES)


STATES_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_20m.zip"
# One combined query per state. Needed because ArcGIS search stops at 1,000
# results per query, so the national keyword queries above are truncated:
# a 2026-09 per-state check found Boston, Rochester and ErieNet fiber layers
# that the national queries never reached.
STATE_QUERY = ('(fiber OR fibre OR conduit OR telecom OR telecommunications OR "middle mile" '
               'OR backbone OR "dark fiber" OR ITS OR communications)')


def _keep(it: dict) -> bool:
    text = " ".join([it.get("title") or "", " ".join(it.get("tags") or [])])
    return bool(it.get("url") and TOPIC_RE.search(text)
                and not ITEM_EXCLUDE_RE.search(it.get("title") or "")
                and _in_us(it.get("extent")))


def _paged_search(params: dict, items: dict[str, dict]) -> None:
    start = 1
    while 0 < start <= 1000:  # ArcGIS search caps paging at 1,000 results
        res = get_json(SEARCH_URL, {**params, "num": 100, "start": start})
        for it in res.get("results", []):
            if _keep(it):
                items[it["id"]] = it
        start = res.get("nextStart", -1)


def _search_items() -> dict[str, dict]:
    items: dict[str, dict] = {}
    for term in SEARCH_TERMS:
        for kind in ("Feature Service", "Map Service"):
            _paged_search({"q": f'({term}) type:"{kind}"'}, items)
    print(f"  arcgis discovery: {len(items)} items from national keyword search")

    import geopandas as gpd  # only needed here; keeps --refine lightweight
    states = gpd.read_file(STATES_URL).to_crs("EPSG:4326")
    for _, st in states.iterrows():
        x0, y0, x1, y1 = st.geometry.bounds
        for kind in ("Feature Service", "Map Service"):
            _paged_search({"q": f'{STATE_QUERY} type:"{kind}"', "bbox": f"{x0},{y0},{x1},{y1}"}, items)
    print(f"  arcgis discovery: {len(items)} items after per-state search")
    return items


def _candidate_layers(item: dict) -> list[dict]:
    """Open one service and return its polyline layers that look like fiber."""
    url = item["url"].rstrip("/")
    title_is_fiber = bool(re.search(r"fib(er|re)", item["title"], re.I))
    out = []
    try:
        if re.search(r"/\d+$", url):  # item points straight at one layer
            layers = [{**get_json(url), "_url": url}]
        else:
            svc = get_json(url)
            layers = [{**lyr, "_url": f"{url}/{lyr['id']}"} for lyr in svc.get("layers", [])]
            # MapServer layer lists omit geometryType; fill it in per layer.
            for lyr in layers:
                if "geometryType" not in lyr and not lyr.get("subLayerIds"):
                    lyr.update(get_json(lyr["_url"]))
    except Exception:  # noqa: BLE001 - private/dead services are common; skip them
        return out

    for lyr in layers:
        name = lyr.get("name") or ""
        if lyr.get("geometryType") != "esriGeometryPolyline":
            continue
        if LAYER_EXCLUDE_RE.search(name) and not re.search(r"fib(er|re)", name, re.I):
            continue
        if not (LAYER_FIBER_RE.search(name) or title_is_fiber):
            continue
        try:
            count = get_json(f"{lyr['_url']}/query",
                             {"where": "1=1", "returnCountOnly": "true"}).get("count", 0)
        except Exception:  # noqa: BLE001 - layer not queryable anonymously
            continue
        if not count:
            continue
        label = f"{item['title']} {name}"
        out.append({
            "include": 1,
            "status_guess": "planned" if PLANNED_RE.search(label) else "existing",
            "title": item["title"],
            "owner": item.get("owner", ""),
            "layer_name": name,
            "feature_count": count,
            "layer_url": lyr["_url"],
            "item_id": item["id"],
        })
    return out


def discover() -> list[dict]:
    items = _search_items()
    print(f"  arcgis discovery: {len(items)} candidate US fiber items, probing layers...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_candidate_layers, items.values()))

    # The same layer is often shared as several items (views, web maps).
    by_url: dict[str, dict] = {}
    for rows in results:
        for row in rows:
            by_url.setdefault(row["layer_url"], row)
    rows = list(by_url.values())

    # Search ranking shifts between runs; never drop a layer that an earlier
    # discovery found just because this run's queries didn't surface it.
    if CATALOG_PATH.exists():
        with CATALOG_PATH.open(newline="", encoding="utf-8") as fh:
            for old_row in csv.DictReader(fh):
                if old_row["layer_url"] not in by_url and not old_row.get("seeded"):
                    rows.append(old_row)

    # Keep manual exclusions (exclude_reason=manual) from a previous catalog.
    if CATALOG_PATH.exists():
        with CATALOG_PATH.open(newline="", encoding="utf-8") as fh:
            old = {r["layer_url"]: r["exclude_reason"] for r in csv.DictReader(fh)
                      if r.get("exclude_reason", "").startswith("manual")}
        for r in rows:
            if r["layer_url"] in old:
                r["exclude_reason"] = old[r["layer_url"]]

    rows = refine(merge_seeds(rows))
    _write_catalog(rows)
    return rows


def _fetch_one(row: dict) -> gpd.GeoDataFrame | None:
    try:
        gdf = fetch_layer(row["layer_url"], where=carrier_maps.LAYER_WHERE.get(row["layer_url"], "1=1"))
    except Exception as exc:  # noqa: BLE001 - one dead layer shouldn't kill the build
        print(f"    skip {row['title']} / {row['layer_name']}: {exc}")
        return None
    if gdf.empty:
        return None
    if row["layer_url"] in carrier_maps.DEDUPE_GEOMETRY:
        gdf = gdf[~gdf.geometry.to_wkb().duplicated()]
    attr_cols = [c for c in gdf.columns if c != "geometry"]
    attrs = gdf[attr_cols].astype(object).where(gdf[attr_cols].notna(), None)
    return gpd.GeoDataFrame({
        "publisher": row["publisher"],
        "publisher_type": row["publisher_type"],
        "dataset_title": row["title"],
        "layer_name": row["layer_name"],
        "status_guess": row["status_guess"],
        "layer_url": row["layer_url"],
        # Every publisher uses its own schema; keep their attributes verbatim
        # as JSON rather than forcing them into columns that mostly don't line up.
        "attributes": [json.dumps(r, default=str) for r in attrs.to_dict("records")],
        "source": "Published ArcGIS layer",
    }, geometry=gdf.geometry.values, crs="EPSG:4326")


def fetch() -> gpd.GeoDataFrame:
    with CATALOG_PATH.open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["include"] == "1"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        frames = [f for f in pool.map(_fetch_one, rows) if f is not None]
    print(f"  arcgis: downloaded {len(frames)}/{len(rows)} layers")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
