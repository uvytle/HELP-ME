# US terrestrial fiber network lines

Collects every openly downloadable map of US fiber *routes* (actual line
geometry, not availability/coverage) into GeoPackages for QGIS, and splits
them by state.

There is no public national fiber map: carriers treat routes as confidential,
the old HIFLD long-haul layer is gone, and the best academic dataset
(InterTubes) is access-gated. What *does* exist is hundreds of pieces that
cities, counties, state DOTs, public utilities, universities and some carriers
publish themselves on ArcGIS. This script finds and stitches those together.

## Run it

```
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
./.venv/Scripts/python.exe build_dataset.py
```

Takes ~10 minutes. Outputs (git-ignored, too large for the repo, ~1–3 GB):

- `data/us_fiber_network.gpkg`: one layer per source:
  `published_fiber_routes`, `carrier_map_files`, `osm_telecom_lines`, `interstates`.
- `data/us_fiber_by_state.gpkg`: the three fiber layers combined, de-duplicated
  across datasets (a line within 10 m of one already kept from another dataset is
  dropped; carrier's own copy > government > OSM) and split into
  one layer per state (named e.g. `Ohio`). Interstates are not included.

Other modes: `--discover` re-searches ArcGIS Online for new layers (~10 min),
`--refine` re-applies the filter rules to the catalog, `--by-state` redoes only
the state split, `--only published|files|osm|interstates` rebuilds one layer.

## Sources

| Layer | Source | Notes |
| --- | --- | --- |
| `published_fiber_routes` | Public ArcGIS layers listed in [`sources/arcgis_fiber_catalog.csv`](sources/arcgis_fiber_catalog.csv) | The bulk of the data. See the next section for how layers are chosen. Each feature keeps its publisher, dataset title, source URL, and the publisher's own attributes (as JSON in `attributes`). |
| `carrier_map_files` | KMZ/GeoJSON/GeoPDF files operators publish themselves ([`sources/carrier_files.py`](sources/carrier_files.py)) | US Signal and Midwest Fiber Networks (KMZs their website maps load), Vision Net (the GeoJSON behind its Montana coverage map), MassBroadband 123 (MBI's KMZ, via the Internet Archive), and Southern Telecom (GeoPDFs, extracted by [`tools/extract_geopdf.py`](tools/extract_geopdf.py) into a committed GeoJSON). |
| `osm_telecom_lines` | OpenStreetMap via Overpass (ODbL) | Ways tagged `communication=line`, `telecom=line`, `telecom:medium=fibre`, or `utility=telecom`. Only ~2,000 in the US, so it's sparse. |
| `interstates` | US DOT / BTS NTAD Eisenhower Interstate System | **Not fiber.** Included as context, because long-haul fiber largely follows highway rights-of-way. Generalized to ~50 m. |

Railroads were deliberately left out (user request), even though a lot of
long-haul fiber is also laid along rail.

## Leads from Infrapedia

[Infrapedia](https://www.infrapedia.com/) is a good terrestrial network atlas,
but it can't be used as a source: the map needs a LinkedIn login and its FAQ
says the data can't be downloaded. Its public sitemap
(`infrapedia.com/terrestrialnetworks.xml`, allowed by its robots.txt) does list
the ~220 networks it shows, though, and Infrapedia's data mostly comes from the
operators themselves. So each US network on that list was traced back to its
operator's own website map:

- **Traceable to downloadable data** (in this build): Uniti/Windstream (the
  ArcGIS map embedded on unitiwholesale.com), FiberLight (ArcGIS map on
  fiberlight.com), US Signal (KMZs), Southern Telecom (GeoPDFs), and Unite
  Private Networks (via Kansas City's public right-of-way layers). Tracing also
  turned up an FDOT District 7 project that publishes surveyed utilities by owner.
  These are in [`sources/carrier_maps.py`](sources/carrier_maps.py) and
  [`sources/carrier_files.py`](sources/carrier_files.py).
- **Regional follow-ups** (Plains and Northeast gaps): Vision Net (MT),
  MassBroadband 123 (MA). Dakota Carrier Network's "interactive" map is an
  unreferenced SVG drawing, Midco's GIS server needs a login, and CEN (CT), OpenCape (MA),
  NYSERNet, NJEdge and OneNet (OK) publish no route data.
- **Connecticut / Oklahoma follow-up** (searched ArcGIS inside each state for
  layers naming Infrapedia's operators, whatever the title says):
  - **Cox** (and OK co-ops/rural telcos), via **Oklahoma DOT's** "Broadband
    Lines" layer: route files providers submitted for state ARPA grant
    compliance, combined by ODOT. Downloaded with a row filter
    (`carrier_maps.LAYER_WHERE`) that drops one provider's conduit/civil copies
    and drops, wireless backhaul and "Proposed" rows. A middle-mile route
    stored once per co-applicant is collapsed to one copy.
  - **City of Owasso, OK** fiber, already in the catalog but excluded as an
    anonymous account. The account runs Owasso's city web maps, so it's now
    a hand-checked override.
  - **Internet2** ("university-corporation-for-internet-development") was
    checked and **not** used: its map's segments are straight city-to-city
    lines (NY–Hartford, Dallas–Tulsa–KC), not routes.
  - **Found, not used:** a 2012 statewide Fibertech (now Crown Castle) KML of
    Connecticut, shared by a personal ArcGIS account (it belongs to someone in
    CT state IT, going by its Nutmeg Network maps) with no agency org.
    That fails both the provenance rule and the Crown Castle rule.
  - **Second CT pass** (every telecom-ish item inside CT, any type): added
    Simsbury's town fiber and Torrington's traffic-signal fiber (mostly
    proposed). New Haven's "City Fiber" layers are no longer public, CEN's
    fiber map is a 2018 JPG, FirstLight's site blocks automated access, and
    Crown Castle publishes no map of its own (the public copies are other
    agencies', valid only in their own states).
- **Approximate, traced from an image (separate from the route data):** CEN's
  fiber map is only a 2018 JPG, so
  [`tools/trace_cen_image.py`](tools/trace_cen_image.py) georeferences it
  (fitting the real coastline and interstates) and vectorizes the blue fiber into
  `sources/static/cen_ct_traced_2018.geojson` (2,750 lines, ~170 m/px, off
  by up to ~1–2 km in places). It is **not** merged into the state layers or
  the route build.
- **Not traceable** (static image/PDF only, sales-gated, or no public map):
  WOW Business, Cox (own site; see ODOT above), Charter/Spectrum, Crown Castle/Lightower, ExteNet, Zayo,
  Arcadian Infracom, MOX, Transtelco, EarthLink, Edison Carrier Solutions, 123NET,
  Windstream's old KMZ page (now a 404).
- **Considered and skipped (Vy's call):** BLM's national right-of-way layer
  has ~8,200 telephone/fiber-optic grants with holder names, but its shapes are
  public-land survey sections, not cable paths.
- **Found but not used:** a public ArcGIS account named `geocode_Zayo` with
  ~200k Zayo fiber spans including strand counts and availability. It has no
  organization or profile, so it can't be verified as Zayo's own. It looks like
  internal operational data, and it falls under the Zayo rule anyway.

## How published layers are chosen

1. **Discovery** (`sources/arcgis_fiber.py: discover`): search ArcGIS Online
   for public Feature/Map Services about fiber whose extent is in the US,
   first nationally by keyword, then once per state with a bounding box (ArcGIS
   stops at 1,000 results per query, so the national pass alone misses layers).
   Open each service and keep polyline layers that look like fiber routes.
   Layers found by earlier runs are never dropped from the catalog.
2. **Content filter** (`REFINE_RULES`): drop service drops to individual
   buildings, electric layers bundled into utility maps, derived analysis
   products (buffers, "road within 1 mile of fiber", H3 estimates), coax/cable-TV
   routes, backups, older yearly snapshots, and duplicate views of the same
   dataset.
3. **Provenance filter** (`sources/publishers.py`): keep only layers
   published by **public entities** (governments, DOTs, public utilities and
   co-ops, tribes, universities, nonprofits) or by **a carrier publishing its
   own network**. Drop consultants, Esri demo/sample data, and anonymous
   uploads. Also drop Lumen/Zayo/Crown Castle routes unless that carrier or a
   **government agency** published them (agencies publish these from their own
   permit, right-of-way and survey records, e.g. City of Boston, Westchester
   County, FDOT). An agency's copy only counts **inside its own state**
   (`publishers.JURISDICTION`): Montgomery County, MD, for instance, also
   republishes Crown Castle's national network, which isn't its record.
   Anyone else's copy has no traceable provenance, and Lumen's terms prohibit
   duplication. The publisher is taken from the
   hosting ArcGIS organization when it's public, otherwise from the item's
   credits or server hostname, and in a few hand-checked cases from an
   unambiguous username (the `OVERRIDES` table).
   Vermont PSD's "fiber routes" are excluded because they're E911 road
   centerlines snapped to reported service availability, not physical routes.

Every dropped layer stays in the catalog with `include=0` and an
`exclude_reason`, so any decision can be audited or reversed. To drop a layer
by hand, set its `exclude_reason` to `manual: <why>`; its other copies are then dropped as duplicates too.

## Caveats

- **Coverage is uneven.** It's dense where local governments publish (Utah, Washington, parts of
  VA/NC/OH/TX) and empty elsewhere. A blank area means nothing was published there,
  not that there's no fiber.
- **Mostly metro and regional networks**, like city traffic/ITS fiber, municipal
  broadband and utility networks. The commercial long-haul backbone is still
  mostly absent, apart from a few carriers (Segra, Clearnetworx, Westelcom...).
- `status_guess` flags layers whose names say proposed/planned/future/design.
  It's a heuristic, so check `dataset_title` before citing a layer as built.
- Some publishers post overlapping copies under different names that the
  de-duplication can't match, so a few routes may appear twice.
