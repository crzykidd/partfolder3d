# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** This is the **live-state handoff** — a
current, limited view so a new session can orient fast, then go deeper via the docs it points to.
It is NOT a full reference: durable rules live in `CLAUDE.md`, the module map + gotchas in
`docs/architecture.md`, history in `CHANGELOG.md` / `docs/decisions.md`. Keep it LEAN; refresh
"Current state" + "Next phases" before every `/clear`.

**Last updated:** 2026-07-05 (late) — **post-v0.4.0 batch of 8 commits on `dev`, pushed** (`:dev`
images rebuilding). #27 + #23 both RESOLVED on `dev` (auto-close on next merge to `main`). Next up =
bulk move-assets UI (last Phase 2 item) or release the batch.

## Current state

- **Latest release: `v0.4.0`** (2026-07-05, in prod). **`dev` is now 8 commits ahead of `main`**
  (pushed to origin; suites 822 backend / 401 frontend green). The batch (details in
  `CHANGELOG.md [Unreleased]` + `docs/decisions.md`):
  - **#23 DONE** — pluggable fallback-scraper framework per `docs/scrapers-spec.md`: dispatcher tries
    enabled backends by priority (default FlareSolverr → AgentQL); per-scraper enable/priority/timeout/
    test-connection; usage rows + daily retention cron + manual clear; `flaresolverr` service added to
    `docker-compose.dev.yml` (internal `http://flaresolverr:8191`, enabled + validated on the live
    stack — real MakerWorld imports came back "Fetched via FlareSolverr").
  - **#27 DONE (option b)** — URL-import wizard attaches files mid-wizard: relaxed
    `POST /api/import-sessions/{id}/files` (url + pending_wizard, lazy staging dir), DELETE staged
    file, inline "Attach Model Files" section on Review & Commit **plus** an attach-or-create-
    without-objects modal for zero-file URL imports. Auto-fetch of model files stays deferred
    (login-gated on Printables/MakerWorld; possible later per-site on the #23 framework — NOT filed
    as an issue yet).
  - **MakerWorld extraction** — `__NEXT_DATA__` enrichment (Designer name/profile, clean title,
    category tags, official `design_pictures` gallery) + generic image hygiene (query-string dedupe,
    <400px width-hint drop, `/comment/` path drop).
  - **Scrapers admin UI** — collapsible per-scraper sections (name + Enabled/Disabled pill,
    sessionStorage-persisted, expanded default), drag-to-reorder priority (desktop-only) + up/down
    arrows (touch fallback). Numeric priority inputs removed.
  - **Catalog has-asset** — `has_asset` flag (roles model+gcode) + All/With files/Without files
    filter + card/table icon.
  - **Bug fixes found in testing:** CSRF cookie now has `max_age` matching the session cookie
    (was browser-session-only → "Missing X-CSRF-Token header" after browser restart; users with
    old cookies must log out/in once); upload endpoint gained CSRF + stale-`files`-collection fix.
- **The docker stack runs on THIS host** — diagnose live via `docker logs`/`exec` + the app DB
  (`docker exec partfolder3d-db-1 psql -U partfolder3d -d partfolder3d`). Backend routes + frontend
  **hot-reload** from the repo; the **worker does NOT** (restart it after worker/task/scraper edits).
  FlareSolverr container is running and configured (Admin → Site Capabilities).

## Next phases (roadmap)

**Phase 2 — owner-decision items.** #27 ✅ and #23 ✅ (above). Remaining:
  - **Bulk move-assets UI** (#25 follow-up) — the backend bulk endpoint is live + tested; the UI needs
    a catalog **multi-select** affordance that doesn't exist yet (a real UX decision — discuss with
    owner before building).

**Phase 3 — release v0.5.0 (owner approved 2026-07-05), then remaining backlog.** Owner chose
**0.5.0** (feature batch → minor bump; 0.4.1 rejected as misleading). Pre-release items already
handled on `dev`: prod `docker-compose.yml` has a **commented-out FlareSolverr example** (owner:
users opt in themselves; not enabled by default) and the CHANGELOG carries the **CSRF re-login
upgrade note**. **Release gotcha:** the CodeQL PR check surfaces pre-existing/moved alerts on large
diffs — fix real log-injections (`sanitize_for_log`), dismiss path-injection FPs that already have a
`resolve()`+`is_relative_to()` barrier. CodeQL is non-required but shows red. Then `gh issue list`
for the rest.

## How we work (recap — full rules in `CLAUDE.md`)

- Central **Opus planning session**: plan, write handoff prompts in `prompts/`, dispatch **Sonnet
  subagents** to execute, report back. Owner doesn't babysit. Bigger than ~1–2 files → handoff prompt.
- **Auto-commit on `dev`** with conventional prefixes; **`main` is PR-only, never direct-push.** Use
  `closes #N` so issues auto-close. Every feat/fix commit updates `CHANGELOG.md [Unreleased]` same commit.
- **During active build/test sessions the owner wants each verified item committed AND pushed to `dev`**
  (not just committed) so pushing rebuilds the `:dev` images and the owner's on-host stack + testers can
  pull. Gate each push on `make verify` (full backend suite + fresh frontend build/vitest).
- **Flag genuine design forks** (like #27 core / #23 open questions) for the owner instead of guessing.
- **Live-iteration caveat:** owner runs the vite dev server / the `:dev` stack on this repo; for bigger
  changes while they test, dispatch to an **isolated worktree** (Agent `isolation: worktree`).
- **Verify + gotchas are NOT here.** Verify discipline: `CLAUDE.md` + `scripts/verify-*.sh` (`make verify`).
  Load-bearing gotchas (render backend, 3MF, modals, worker-no-hot-reload, CI shape, merge-dup-symbols):
  `docs/architecture.md`.

## Backlog (themes — `gh issue list` is the source of truth for what we build **now**, not the PRD)

- **Done on `dev`, awaiting release:** #23, #27 (auto-close on merge; both have status comments).
- **Needs owner decision:** bulk-move multi-select UI; whether to file the opportunistic
  auto-fetch-model-file idea as an issue.
- Older PRD §18 notes: real slicing for filament estimates, trash-purge UI, `.bgcode`/multi-filament gcode.

## Session start order

1. **This file** — live state + next phases.
2. **`CLAUDE.md`** — operating rules + verify discipline.
3. **`docs/architecture.md`** — where things live (module map) + load-bearing gotchas.
4. **`docs/decisions.md`** (newest-first ADR log) + **`CHANGELOG.md`** — the detailed look-back.
5. **`docs/audit-2026-07-03.md`** — the audit worklist (mostly done; deferrals noted).

## Repo, remotes, environment (quick-start)

- **Code:** GitHub [`crzykidd/partfolder3d`](https://github.com/crzykidd/partfolder3d). `main` protected
  (PR-only, 6 required CI checks). Work on `dev`. `gh` authed as `crzykidd`.
- **Live stack on THIS host:** `partfolder3d-{backend,worker,db,redis,nginx,frontend}-1` on `:dev`
  images. `docker logs`/`exec` to diagnose; app DB via `docker exec partfolder3d-db-1 psql -U
  partfolder3d -d partfolder3d`. Separate ephemeral **test** pg: `pf3d-pg-v` on :5433 (pytest only).
- **Run from scratch:** `cp .env.example .env` → `docker compose -f docker-compose.dev.yml up --build`
  (dev) or `docker compose up -d --build` (prod) → http://localhost:8973 first-run wizard. Migrations
  auto-run via the backend entrypoint. External port **8973** (nginx).
- **No sandbox here** — bash may prompt unless auto-approve is on. **System Python is PEP-668** (pip
  blocked); a scratchpad venv exists for image work — recreate if gone.

## Before-`/clear` checklist

1. Update **Last updated** + **Current state** + **Next phases** (release cut? `dev` vs `main`?).
2. Refresh **Backlog** themes — `gh issue list` is the source of truth; don't enumerate.
3. Ensure in-flight `prompts/` frontmatter + `done|failed/` placement is right; record decisions in
   `docs/decisions.md`.
4. Confirm work is committed **and pushed** on `dev` (note anything intentionally unpushed).
