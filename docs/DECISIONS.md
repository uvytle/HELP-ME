# Decisions log

Newest on top.

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
