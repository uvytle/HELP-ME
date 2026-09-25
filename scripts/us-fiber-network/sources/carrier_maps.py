"""
ArcGIS layers found by tracing the US terrestrial networks listed on
Infrapedia (infrapedia.com/terrestrialnetworks.xml, its public sitemap) back to
data the operators or public agencies publish themselves.

Infrapedia's own map is login-gated and its FAQ says its data can't be
downloaded, so we don't touch it. We only use its list of network *names* as
leads. For each lead, the carrier's own website map was opened and, where it
was an embedded ArcGIS map, traced to the public layers behind it (the same
technique used earlier for FiberLight). Title-keyword discovery misses these
because their titles don't say "fiber" (e.g. "National Core Network 6.12").

These rows are merged into the ArcGIS catalog with their publisher already
set, so they skip the automatic publisher lookup. They still go through every
other filter (content rules, the Lumen/Zayo/Crown Castle rule, de-duplication).
"""

from __future__ import annotations

import re

from .arcgis import get_json

UNITI = "https://services.arcgis.com/QO7AhQX53d0m9M2s/arcgis/rest/services"
UNITI_BASIS = "carrier website: unitiwholesale.com/network-map embeds this ArcGIS map"
FIBERLIGHT_BASIS = "carrier website: fiberlight.com network coverage map embeds this ArcGIS map"
KCMO = "https://mapd.kcmo.org/kcgis/rest/services/external/FiberLayersNonKCMO/FeatureServer"
KCMO_BASIS = "public agency server (mapd.kcmo.org, City of Kansas City, MO)"
NTIA_MM = ("https://utility.arcgis.com/usrsvcs/servers/53d104cecb964033a75c5cd05cab3657/rest/services/"
           "MM_Dashboard_Layers_ForPublic/FeatureServer")
NTIA_BASIS = "federal agency: NTIA's public Middle Mile dashboard layers (NBAM org)"
ODOT_LINES = "https://services6.arcgis.com/RBtoEUQ2lmN0K3GY/arcgis/rest/services/Broadband_Lines/FeatureServer/0"

# (layer_url, dataset title, publisher, publisher_type, basis, status_guess)
SEED_LAYERS = [
    # Uniti (which merged with Windstream; Infrapedia's "Windstream core network").
    (f"{UNITI}/National_Core_Network_6_12/FeatureServer/191", "Uniti National Core Network", "Uniti", "carrier", UNITI_BASIS, "existing"),
    (f"{UNITI}/Regional_Transport_Network_6_13/FeatureServer/194", "Uniti Regional Transport Network", "Uniti", "carrier", UNITI_BASIS, "existing"),
    (f"{UNITI}/Uniti_Wholesale_Dark_Fiber/FeatureServer/74", "Uniti Wholesale Dark Fiber", "Uniti", "carrier", UNITI_BASIS, "existing"),
    (f"{UNITI}/Uniti_Wholesale_Map_Demo_4_WFL1/FeatureServer/26", "Kinetic (ex-Windstream ILEC) Dark Fiber", "Uniti", "carrier", UNITI_BASIS, "existing"),
    (f"{UNITI}/Key_Strategic_Routes_731/FeatureServer/199", "Uniti Key Strategic Routes", "Uniti", "carrier", UNITI_BASIS, "existing"),
    (f"{UNITI}/Uniti_Wholesale_Map_Demo_4_WFL1/FeatureServer/54", "Uniti Developing Routes (under review)", "Uniti", "carrier", UNITI_BASIS, "planned"),
    # FiberLight's national network (the thesis already has its Northern VA detail).
    ("https://services.arcgis.com/cmtiXjnD63zmtycz/arcgis/rest/services/FiberLightNetwork/FeatureServer/3",
     "FiberLight Network", "FiberLight", "carrier", FIBERLIGHT_BASIS, "existing"),
    # Kansas City, MO publishes other operators' fiber from its right-of-way records.
    *[(f"{KCMO}/{i}", f"KCMO right-of-way fiber: {name}", "City of Kansas City, MO", "public", KCMO_BASIS, "existing")
      for i, name in [(0, "Johnson County"), (1, "Unified Government (KCK)"), (2, "KC Scout (MoDOT/KDOT ITS)"),
                      (3, "Unite Private Networks")]],
    # Found while filling gaps in MT/WY/ND/SD/OK: public-agency grant and DOT
    # layers whose titles never say "fiber", so keyword discovery misses them.
    (f"{NTIA_MM}/1", "NTIA Enabling Middle Mile awarded routes", "NTIA (National Broadband Availability Map)",
     "public", NTIA_BASIS, "planned"),
    (f"{NTIA_MM}/0", "NTIA Middle Mile awardees' existing IRU routes", "NTIA (National Broadband Availability Map)",
     "public", NTIA_BASIS, "existing"),
    ("https://services5.arcgis.com/YjiGkfGCdfjouFLC/arcgis/rest/services/Middle_Mile_Projects/FeatureServer/0",
     "Oklahoma middle mile projects", "Oklahoma Broadband Office", "public",
     "public agency ArcGIS org (Oklahoma Broadband Office)", "planned"),
    ("https://services1.arcgis.com/dKlvxNSUvl36IGMp/arcgis/rest/services/Anaconda_Butte_Broadband_Routes/FeatureServer/0",
     "MDT Anaconda-Butte broadband routes", "Montana Department of Transportation", "public",
     "public agency ArcGIS org (Montana DOT)", "existing"),
    # Oklahoma DOT combines the route files broadband providers submitted for
    # state (ARPA/SLFRF) grant compliance: Cox (an Infrapedia network with no
    # public map of its own), electric co-ops and rural telcos. See ODOT_WHERE.
    (ODOT_LINES, "ODOT provider-submitted broadband lines", "Oklahoma Department of Transportation",
     "public", "public agency ArcGIS org (OKDOT_GIS): 'Data provided by Broadband service "
     "providers and combined by ODOT'", "existing"),
]

# Per-layer row filters applied when a seeded layer is downloaded.
# ODOT's layer mixes in things that aren't fiber routes: one provider's
# conduit/civil/path copies of its own cable routes and its service drops, a
# few wireless-backhaul links, and routes still marked "Proposed".
LAYER_WHERE = {
    ODOT_LINES: ("(FileName IS NULL OR (FileName NOT LIKE '%DROP%' AND FileName NOT LIKE 'Civil%' "
                 "AND FileName NOT LIKE 'Conduit%' AND FileName NOT LIKE 'Path%' "
                 "AND FileName NOT LIKE 'Underground path%')) "
                 "AND (Type IS NULL OR Type <> 'Wireless Backhaul') "
                 "AND (STATUS IS NULL OR STATUS <> 'Proposed')"),
}
# Layers where the same line is stored once per co-applicant (ODOT repeats one
# shared middle-mile route for each of the eight companies on the grant), so
# exact duplicate geometries are collapsed to one feature.
DEDUPE_GEOMETRY = {ODOT_LINES}

# FDOT District 7's Tampa Westshore Interchange project publishes the surveyed
# existing utilities in its corridor, one layer per owner (UTEXRD_<OWNER>_<date>).
# Only telecom owners are kept; restricted carriers are removed later by the
# provenance rule like any other copy.
FDOT_D7_OWNER = "joel.wixson_fdotd7westshore"
FDOT_D7_TELECOM_RE = re.compile(
    r"^UTEXRD_(ATT|BRIGHT_HOUSE|SPECTRUM|TIME_WARNER|TECO_TELECOM|FIBERLIGHT(?:_XO_COMMUNICATIONS)?|"
    r"FRONTIER|INTERMEDIA|MCI|MFS|UNITI_FIBER|FDOT_ITS_TRAFFIC|ACSI_01|CENTURYLINK|LEVEL_3|ZAYO|"
    r"CROWN_CASTLE)(?:_(\d{8}))?")


def _fdot_d7_rows() -> list[tuple]:
    items, start = [], 1
    while start > 0:
        r = get_json("https://www.arcgis.com/sharing/rest/search",
                     {"q": f'owner:"{FDOT_D7_OWNER}" title:UTEXRD', "num": 100, "start": start})
        items += r["results"]
        start = r.get("nextStart", -1)
    latest: dict[str, tuple[str, dict]] = {}
    for it in items:
        m = FDOT_D7_TELECOM_RE.match(it["title"])
        if not m or not it.get("url"):
            continue
        # Several owners were re-exported on different dates; keep the newest.
        if m.group(1) not in latest or (m.group(2) or "") > latest[m.group(1)][0]:
            latest[m.group(1)] = (m.group(2) or "", it)
    rows = []
    for owner, (_, it) in sorted(latest.items()):
        svc = get_json(it["url"])
        for lyr in svc.get("layers", []):
            if lyr.get("geometryType") == "esriGeometryPolyline":
                rows.append((f"{it['url'].rstrip('/')}/{lyr['id']}",
                             f"FDOT D7 Westshore surveyed utilities: {owner.replace('_', ' ').title()}",
                             "Florida DOT District 7 (Westshore Interchange project)", "public",
                             "public agency project account (hand-checked)", "existing"))
    return rows


def seed_rows() -> list[dict]:
    """Catalog rows for all seeded layers, with live feature counts."""
    rows = []
    for url, title, pub, ptype, basis, status in SEED_LAYERS + _fdot_d7_rows():
        try:
            info = get_json(url)
            count = get_json(f"{url}/query", {"where": LAYER_WHERE.get(url, "1=1"),
                                              "returnCountOnly": "true"}).get("count", 0)
        except Exception as exc:  # noqa: BLE001 - a moved layer shouldn't break the build
            print(f"    seed unavailable: {title}: {exc}")
            continue
        rows.append({
            "include": 1, "exclude_reason": "", "publisher": pub, "publisher_type": ptype,
            "publisher_basis": basis, "status_guess": status, "title": title,
            "owner": "", "layer_name": info.get("name", ""), "feature_count": count,
            "layer_url": url, "item_id": "", "seeded": "infrapedia lead",
        })
    return rows
