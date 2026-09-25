# Decisions log

Newest on top.

## 2026-09-24 — Regional gap-filling: per-state discovery, agency copies of Lumen/Zayo/Crown allowed, BLM skipped

- **Per-state discovery.** ArcGIS search stops at 1,000 results per query, so the
  national keyword sweep was silently truncated. Discovery now also runs one
  bounding-box query per state, which more than doubled the candidates (1,316 → 3,078)
  and found e.g. City of Boston, Pittsburgh, Dallas County and Concord MA fiber. The
  catalog never drops a layer an earlier run found. New content filters handle the
  "conduit" noise this brings (storm/sewer/irrigation/street-light conduit, prospect
  lists), and a missing "backup/background" rule was restored.
- **Rule change (Vy's call):** Lumen/Zayo/Crown Castle routes are now allowed when a
  *government agency* published them from its own permit/right-of-way/survey records
  (Boston, Westchester, Philadelphia, FDOT). Anonymous or other third-party copies stay
  excluded.
- **Cross-dataset de-duplication** in the state split (10 m, carrier > government >
  OSM), since agency copies of carrier networks would otherwise draw routes twice.
- **BLM right-of-way grants skipped (Vy's call):** ~8,200 fiber/telephone grants with
  holder names, but the geometry is PLSS survey sections, not cable paths.
- **Not usable:** Zayo's site (PNG maps only), DCN's map (an unreferenced SVG), Midco's
  GIS server (login), CEN/OpenCape/NYSERNet/NJEdge/OneNet (no route data published).

## 2026-09-24 — Infrapedia used for leads only; operator-published data traced from it

- **What:** Vy uses Infrapedia as a reference and asked for its sources. Infrapedia's map
  is login-gated and its FAQ rules out downloads, so none of its data is used. Only its
  public sitemap's list of network names is, as leads to trace to each operator's own
  website map. That added Uniti/Windstream, FiberLight, US Signal, Southern Telecom
  (GeoPDFs), Midwest Fiber Networks, Kansas City's right-of-way layers (incl. Unite
  Private Networks) and an FDOT D7 project (`carrier_maps.py`, `carrier_files.py`).
- **Judgment calls:** a public "geocode_Zayo" ArcGIS account with strand-level Zayo data
  was left out, since it's unverifiable as Zayo's and looks internal. A Midwest Fiber
  Networks KMZ with "nda" in its name was skipped in favour of the one labelled
  "website". Seeded layers still go through the content and Lumen/Zayo/Crown Castle rules.
- **Southern Telecom GeoPDFs** are extracted once with QGIS's GDAL
  (`tools/extract_geopdf.py`) and the result committed, because the pip GDAL wheel has
  no PDF driver.

## 2026-09-24 — US fiber route collector: provenance rule, no railroads, data not in git

- **What:** `scripts/us-fiber-network/` gathers publicly published US fiber *route*
  geometry (mostly ArcGIS layers from cities, counties, DOTs, utilities, carriers, plus
  OpenStreetMap) and splits it by state. The output feeds the "State & Regional Fiber
  Networks" group in Vy's thesis QGIS project as `<State> (compiled)` layers.
- **Provenance rule:** keep public entities + carriers publishing their own network;
  drop consultants, Esri demo data, anonymous uploads, and Lumen/Zayo/Crown Castle routes
  not published by that carrier. Vy picked this over "public only" and "everything". It
  matches the thesis log's earlier calls (Lumen's no-duplication terms, rejecting an
  untraceable Pennsylvania re-upload, rejecting Vermont's availability-snapped "routes").
  Excluded layers stay in the committed catalog CSV with a reason, so the rule can be
  revisited without re-running discovery.
- **Railroads left out** at Vy's request, even though a lot of long-haul fiber follows
  rail. Interstates are still collected as a context layer but aren't added to the map.
- **Generated data is git-ignored.** It's 1–2 GB, far past what belongs in a public
  Pages repo. The committed catalog makes a rebuild reproducible; the thesis copy lives
  in Vy's thesis folder.
- **Ruled out:** InterTubes and FiberLocator (gated/licensed), PeeringDB (AUP), Infrapedia
  (login plus no downloads). See the thesis methodology log for details.

## 2026-09-10 — Enabled entire.io CLI to capture AI session history in git

- **What:** Installed the [entire](https://entire.io) CLI and ran `entire enable`, which
  hooked into Claude Code (via `.claude/settings.json` hooks) and started capturing AI
  coding sessions as git refs (`refs/entire/checkpoints/...`) linked to commits. Added
  read-only `entire` subcommands (`status`, `session`, `checkpoint`, `blame`, `why`,
  `recap`, `doctor`, `version`) to the permission allowlist so they don't prompt.
- **Why:** Requested so anyone reading this repo's history later — Vy, the SWE, or a
  future Claude session — can see not just *what* changed but the actual AI session
  that produced it, without relying on chat transcripts living elsewhere.
- **Privacy tradeoff, explicitly accepted:** by default, checkpoints sync to `origin`
  alongside code (`entire status` confirms "Checkpoints sync to: origin"). HELP-ME is
  **public**, so this means captured AI session content (prompts, tool calls) becomes
  publicly visible in git history, not just the code. This was flagged before enabling
  and the call was made deliberately to let checkpoints go public rather than route
  them to a separate private remote. If that changes, checkpoint routing is reconfigured
  via `entire configure`, not by disabling capture entirely.
- **Not yet done:** `entire login` (browser OAuth to a hosted Entire account) — that's a
  one-time human step neither I nor a future session can complete on someone else's
  behalf. Local checkpoint capture works without it; login only gates hosted features
  (cross-repo `entire activity`, semantic `entire search`, etc.).

## 2026-09-10 — Repo set up as a GitHub Pages site with worktree + PR workflow

- **What:** Made the repo public, turned on GitHub Pages (source: `main` branch, root),
  and laid out folders: site content at the repo root (`index.html`, `css/`, `js/`,
  `assets/`, `pages/`), non-site tooling under `scripts/`, and this `docs/` folder for
  memory/rationale.
- **Why:** Repo previously had no structure (a loose script + gif at root) and Pages
  wasn't enabled. The site is meant to be one page reachable at one URL, navigated via
  tabs (see `js/main.js`), not a folder-per-project layout — so the root stays the
  site's home and `docs/` is reserved purely for this log rather than doubling as the
  Pages source.
- **Workflow going forward:** feature work happens on a branch (via a git worktree),
  pushed early via a PR, reviewed by the SWE before merging to `main`. No unit tests
  required (not production software) but changes should be manually verified — opened
  in a browser, script run once — before pushing. Keep commits small and the message
  focused on *why*.
- **Moved:** `ascii_network_animation.py` + `panopticon_network.gif` → `scripts/ascii-network-animation/`
  and `assets/` respectively; the GIF is now shown on the site's Projects tab as an
  example entry.
