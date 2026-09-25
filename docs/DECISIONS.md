# Decisions log

Newest on top.

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
