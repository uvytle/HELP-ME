"""
Who published each ArcGIS fiber layer, and whether that publisher is one we
use.

Provenance rule (chosen by the user for the thesis map): keep layers
published by public entities (governments, DOTs, public utilities, tribes,
universities, nonprofits) and by carriers publishing their own network. Drop
engineering consultants, Esri demo/sample data, anonymous uploads, and any
layer that copies Lumen/Zayo/Crown Castle routes unless that carrier itself
published it. Lumen's own terms say "no duplication permitted"; copies uploaded
by someone else have no traceable provenance.

The publisher is resolved, most to least reliable, from:
  1. the ArcGIS Online organization that hosts the service (from the org ID
     embedded in services*.arcgis.com/<orgId>/ URLs),
  2. the item's "credits" (accessInformation) field,
  3. the hostname of a self-hosted ArcGIS Server (e.g. maps.kytc.ky.gov),
  4. the owner's username (only accepted for classification if it clearly
     names an organization, e.g. "...@cityofchesapeake.net").
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from .arcgis import get_json

ORG_URL_RE = re.compile(r"https://services\w*(?:-\w+)?\.arcgis\.com/([A-Za-z0-9]+)/")

PUBLIC_RE = re.compile(
    r"\bcity\b|cityof|county|\btown\b|townof|village|borough|township|parish|"
    r"department|\bdept\b|\bdot\b|transportation|state\b|commonwealth|government|"
    r"commission|council|authority|planning|metropolitan|\bmpo\b|regional|cabinet|"
    r"office|\bpud\b|public|utilit|power|electric coop|cooperative|\bco-?op\b|"
    r"nation\b|tribe|tribal|port of|university|college|\bschool|\.gov\b|\.us\b|"
    r"\.edu\b|\.mil\b|governor|broadband office|noanet|mcnc|oshean|kinber|"
    r"information office|\bgis\b.*(county|city)|(county|city).*\bgis\b|"
    r"land information|tax department|consortium|uplan|vcgi|kytc|municipal",
    re.I,
)
# Carriers publishing their own network map.
CARRIER_RE = re.compile(
    r"segra|everstream|fiberlight|clearnetworx|atc communications|wideband group|"
    r"ls networks|uniti|norvado|allo\b|bluepeak|westelcom|wightman|sparklight|"
    r"shentel|green mountain power|gmpvt|telecom\b|communications\b|broadband\b",
    re.I,
)
CONSULTANT_RE = re.compile(
    r"horrocks|michael baker|jacobs|\bhdr\b|srf consulting|lochner|rummel klepper|"
    r"mead & hunt|gei consultants|\bdlz\b|creighton manning|constructors|allgeier|"
    r"integra design|gcw, inc|qcgis|enfocus|gis webtech|biohabitats|nv5|olsson|"
    r"kimley|\bwsp\b|stantec|emery ?sapp|trihydro|tilson|hr ?green|telamon|"
    r"crest solutions|cloudpoint|engineering|consult|associates|\bllp\b|\bpsc\b",
    re.I,
)
DEMO_RE = re.compile(
    r"arcgis solutions|arcgis team|^arcgis online$|^agol$|esri|salesforce|"
    r"tryitlive|arcgisfortelco|utilitysolutions|arcgistelecomteam|sample|demo|\btest\b",
    re.I,
)
# Carriers whose routes must only come from the carrier itself.
RESTRICTED_CARRIER_RE = re.compile(r"lumen|centurylink|level[ _]?3|zayo|crown[ _]?castle", re.I)
# Publishers whose "fiber route" lines are really availability data. Vermont
# PSD's routes are E911 road centerlines snapped to provider-reported service
# (checked earlier for the thesis log and excluded there for the same reason).
AVAILABILITY_PUBLISHER_RE = re.compile(r"vermont (department of )?public service", re.I)


# Hand-checked identifications for publishers the rules above can't place:
# ArcGIS org names that don't say "city"/"county", and account usernames that
# unambiguously name a public body or carrier. A bare personal username is
# never enough on its own and stays "unknown" (excluded).
OVERRIDES: dict[str, tuple[str, str]] = {
    # ArcGIS org names / credits
    "Greenville, North Carolina": ("City of Greenville, NC", "public"),
    "Auburn / DeKalb / Garrett / Butler": ("DeKalb County, IN area GIS", "public"),
    "BostonMaps": ("City of Boston", "public"),
    "CDOT ArcGIS Online": ("Colorado DOT", "public"),
    "DiExSys, CDOT": ("Colorado DOT", "public"),
    "NMDOT ArcGIS Online": ("New Mexico DOT", "public"),
    "District 11 GIS, District 11 Traffic Operations": ("Caltrans District 11", "public"),
    "Corvallis Maps Online": ("City of Corvallis, OR", "public"),
    "Gables GIS": ("City of Coral Gables, FL", "public"),
    "Madison-Rexburg GIS": ("Madison County / City of Rexburg, ID", "public"),
    "Makah GIS Lab": ("Makah Tribe", "public"),
    "Milford": ("Town of Milford", "public"),
    "Monterey Park": ("City of Monterey Park, CA", "public"),
    "Rockford, Illinois": ("City of Rockford, IL", "public"),
    "West Jordan": ("City of West Jordan, UT", "public"),
    "William & Mary": ("College of William & Mary", "public"),
    "Fishers, IN GIS": ("City of Fishers, IN", "public"),
    "LACSD": ("LA County Sanitation Districts", "public"),
    "USGS, ADNR": ("Alaska DNR / USGS", "public"),
    "portal.greenvilleillinois.com": ("City of Greenville, IL", "public"),
    # Horrocks Engineering hosts UDOT's own fiber inventory as UDOT's GIS
    # contractor (the thesis log already accepts this source for Utah).
    "gis.horrocks.com": ("Utah DOT (hosted by Horrocks, UDOT's GIS contractor)", "public"),
    "www.mymanatee.org": ("Manatee County, FL", "public"),
    "Telluride Ski Resort": ("Telluride Ski Resort", "other"),
    # Usernames that name their organization
    "sttammanygis": ("St. Tammany Parish, LA", "public"),
    "blountGIS": ("Blount County, TN", "public"),
    "Smyrna_GA": ("City of Smyrna, GA", "public"),
    "QueenCreekGIS": ("Town of Queen Creek, AZ", "public"),
    "StormLake": ("City of Storm Lake, IA", "public"),
    "ColumbiaHeights": ("City of Columbia Heights, MN", "public"),
    "jbohn_Norfolkne": ("City of Norfolk, NE", "public"),
    "roymartinez_mcallen": ("City of McAllen, TX", "public"),
    "jsalgado_tomball": ("City of Tomball, TX", "public"),
    "sandie_botetourt": ("Botetourt County, VA", "public"),
    "bmarquard_CravenGIS": ("Craven County, NC", "public"),
    "gisadmin_harnett": ("Harnett County, NC", "public"),
    "fruita_GIS": ("City of Fruita, CO", "public"),
    "ToledoPort1955": ("Toledo-Lucas County Port Authority", "public"),
    "regionviipdc": ("Region VII Planning & Development Council, WV", "public"),
    "nstephens@carolinemd.org_CCMD": ("Caroline County, MD", "public"),
    "christian.acevedo@westpoint.edu_usma": ("US Military Academy West Point", "public"),
    "tbagley_SMU": ("Southern Methodist University", "public"),
    "ecoleman_sjra": ("San Jacinto River Authority, TX", "public"),
    "DunawayNISD": ("Northside ISD, TX", "public"),
    "fiber_logis": ("LOGIS (MN municipal consortium)", "public"),
    "Breck_GIS": ("Town of Breckenridge, CO", "public"),
    "ChoptankAdmin": ("Choptank Electric Cooperative", "public"),
    "blovett_jwemc": ("Jackson EMC (electric co-op)", "public"),
    "dgoodnight@blueridgeenergy.onmicrosoft.com": ("Blue Ridge Energy (electric co-op)", "public"),
    "nolan.west@otelco.com_otelco": ("Otelco", "carrier"),
    "WTC_Edit_Slic_GIS": ("Westelcom", "carrier"),
    "lakelandinternet": ("Lakeland Internet", "carrier"),
    "jim_aspenwireless": ("Aspen Wireless", "carrier"),
}


def _org_names(org_ids: set[str]) -> dict[str, str | None]:
    def one(org_id: str):
        try:
            return org_id, get_json(f"https://www.arcgis.com/sharing/rest/portals/{org_id}").get("name")
        except Exception:  # noqa: BLE001 - private orgs don't expose their name
            return org_id, None
    with ThreadPoolExecutor(max_workers=10) as pool:
        return dict(pool.map(one, org_ids))


def _item_meta(item_ids: set[str]) -> dict[str, dict]:
    def one(item_id: str):
        try:
            return item_id, get_json(f"https://www.arcgis.com/sharing/rest/content/items/{item_id}")
        except Exception:  # noqa: BLE001
            return item_id, {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        return dict(pool.map(one, item_ids))


def classify(publisher: str, basis: str) -> str:
    if not publisher:
        return "unknown"
    if DEMO_RE.search(publisher):
        return "demo/sample"
    if CONSULTANT_RE.search(publisher):
        return "consultant"
    if CARRIER_RE.search(publisher) and not PUBLIC_RE.search(publisher):
        return "carrier"
    if PUBLIC_RE.search(publisher):
        return "public"
    # A bare username that names no organization isn't evidence of anything.
    return "unknown" if basis == "owner username" else "other"


def annotate(rows: list[dict]) -> None:
    """Fill publisher, publisher_basis, publisher_type on catalog rows in place.

    Rows that already have a publisher (from a previous run) are left alone so
    `--refine` works offline.
    """
    todo = [r for r in rows if not r.get("publisher_type")]
    if not todo:
        return
    org_ids = {m.group(1) for r in todo if (m := ORG_URL_RE.match(r["layer_url"]))}
    orgs = _org_names(org_ids)
    items = _item_meta({r["item_id"] for r in todo})
    for r in todo:
        m = ORG_URL_RE.match(r["layer_url"])
        credits = re.sub(r"<[^>]+>", " ", items.get(r["item_id"], {}).get("accessInformation") or "").strip()
        host = urlparse(r["layer_url"]).hostname or ""
        if m and orgs.get(m.group(1)):
            pub, basis = orgs[m.group(1)], "arcgis org"
        elif credits:
            pub, basis = credits[:120], "item credits"
        elif not m and host != "utility.arcgis.com":
            pub, basis = host, "server hostname"
        else:
            pub, basis = r.get("owner", ""), "owner username"
        if pub in OVERRIDES:
            pub, ptype = OVERRIDES[pub]
            basis += " (hand-checked)"
        else:
            ptype = classify(pub, basis)
        r["publisher"], r["publisher_basis"], r["publisher_type"] = pub, basis, ptype


def rejection_reason(r: dict) -> str:
    """Why a layer fails the provenance rule, or "" if it passes."""
    if r["publisher_type"] not in ("public", "carrier"):
        return f"publisher: {r['publisher_type']}"
    label = f"{r['title']} {r['layer_name']}"
    # Vermont's state-owned (SOV) fiber layer is an actual asset inventory.
    if AVAILABILITY_PUBLISHER_RE.search(r["publisher"]) and not re.search(r"sov-owned", label, re.I):
        return "availability data, not routes"
    carrier = RESTRICTED_CARRIER_RE.search(label)
    if carrier and not RESTRICTED_CARRIER_RE.search(r["publisher"]):
        return f"copy of {carrier.group(0)} routes"
    return ""
