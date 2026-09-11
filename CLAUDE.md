# HELP-ME

A personal GitHub Pages site — one site, one URL, navigated via tabs (see `js/main.js`) —
plus whatever supporting scripts/tools produced its content. Public repo.

This is a shared account: Vy (non-technical, architect) is the primary user, and she
should never have to think about git/PRs/reviewing — work end-to-end and keep moving.
PRs exist for a clean, readable history a human SWE can look back through later, not
as an approval gate. Optimize for a reviewable git history over ceremony.

## Layout

- `/index.html`, `/css`, `/js`, `/assets`, `/pages` — the published site. GitHub Pages
  serves this from the `main` branch, root.
- `/scripts` — standalone tools that aren't part of the website itself (e.g.
  `scripts/ascii-network-animation/`, the generator for the Projects-tab GIF).
- `/docs` — Claude's running memory for *this repo*: decisions and rationale, tracked in
  git. Not the Pages source. Read [docs/README.md](docs/README.md) first; append to
  [docs/DECISIONS.md](docs/DECISIONS.md) after any non-obvious call.
- `.github/PULL_REQUEST_TEMPLATE.md` — every PR fills in What / Why / Verified.

## Workflow

- **New feature/task → worktree.** Use `EnterWorktree` before making changes so the
  main checkout stays clean on `main`. `ExitWorktree` with `remove` once the PR merges,
  `keep` if the work is still in flight.
- **PRs, then merge them yourself.** Push the branch, open a PR (`gh pr create`),
  verify it works, then merge (`gh pr merge --squash --delete-branch`) and move on —
  don't wait on approval.
- **Clean history.** Small, atomic, logically-scoped commits with messages that explain
  *why*, not just what — a reviewer with no chat history should be able to follow along
  from `git log` / the PR description alone.
- **Push early and often, in PRs.** Don't sit on uncommitted work; prefer several small
  PRs over one large one.
- **No unit tests required** (not production software) — but verify the change actually
  works (load the page, run the script) before pushing, and note how in the PR.

## GitHub Pages

Source: `main` branch, `/ (root)`. If a build step or static-site generator gets added
later, switch to an Actions-based deploy instead of branch-serving raw files.
