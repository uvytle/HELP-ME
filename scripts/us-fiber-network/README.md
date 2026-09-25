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
  `published_fiber_routes`, `osm_telecom_lines`, `interstates`.
- `data/us_fiber_by_state.gpkg`: the two fiber layers combined and split into
  one layer per state (named e.g. `Ohio`). Interstates are not included.

Other modes: `--discover` re-searches ArcGIS Online for new layers (~10 min),
`--refine` re-applies the filter rules to the catalog, `--by-state` redoes only
the state split, `--only osm|published|interstates` rebuilds one layer.

## Sources

| Layer | Source | Notes |
| --- | --- | --- |
| `published_fiber_routes` | Public ArcGIS layers listed in [`sources/arcgis_fiber_catalog.csv`](sources/arcgis_fiber_catalog.csv) | The bulk of the data. See the next section for how layers are chosen. Each feature keeps its publisher, dataset title, source URL, and the publisher's own attributes (as JSON in `attributes`). |
| `osm_telecom_lines` | OpenStreetMap via Overpass (ODbL) | Ways tagged `communication=line`, `telecom=line`, `telecom:medium=fibre`, or `utility=telecom`. Only ~2,000 in the US, so it's sparse. |
| `interstates` | US DOT / BTS NTAD Eisenhower Interstate System | **Not fiber.** Included as context, because long-haul fiber largely follows highway rights-of-way. Generalized to ~50 m. |

Railroads were deliberately left out (user request), even though a lot of
long-haul fiber is also laid along rail.

## How published layers are chosen

1. **Discovery** (`sources/arcgis_fiber.py: discover`): search ArcGIS Online
   for public Feature/Map Services about fiber whose extent is in the US. Open
   each service and keep polyline layers that look like fiber routes. This
   gives about 1,160 layers.
2. **Content filter** (`REFINE_RULES`): drop service drops to individual
   buildings, electric layers bundled into utility maps, derived analysis
   products (buffers, "road within 1 mile of fiber", H3 estimates), coax/cable-TV
   routes, backups, older yearly snapshots, and duplicate views of the same
   dataset.
3. **Provenance filter** (`sources/publishers.py`): keep only layers
   published by **public entities** (governments, DOTs, public utilities and
   co-ops, tribes, universities, nonprofits) or by **a carrier publishing its
   own network**. Drop consultants, Esri demo/sample data, and anonymous
   uploads. Also drop any Lumen/Zayo/Crown Castle routes not published by that
   carrier, since those are third-party copies with no traceable provenance,
   and Lumen's terms prohibit duplication. The publisher is taken from the
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
