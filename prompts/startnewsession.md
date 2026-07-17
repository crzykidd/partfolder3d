# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** This is the **live-state handoff** — a
current, limited view so a new session can orient fast, then go deeper via the docs it points to.
It is NOT a full reference: durable rules live in `CLAUDE.md`, the module map + gotchas in
`docs/architecture.md`, history in `CHANGELOG.md` / `docs/decisions.md`. Keep it LEAN; refresh
"Current state" + "Next phases" before every `/clear`.

**Last updated:** 2026-07-17 (v0.5.1 released 2026-07-05; owner rebooting host) — `dev` is
**one commit ahead of `main`** (What's-New-modal fix, queued for next release). **Open thread:
prod MakerWorld imports missing creator info** — diagnosis points at the AgentQL fallback;
awaiting prod-side evidence from owner (see below).

## Current state

- **Latest release: `v0.5.1`** (2026-07-05, PR #35 — hotfix). What shipped:
  - **Prod nginx CSP fix** — `img-src` now allows `https:`; the old `'self'`-only policy made
    the browser block the wizard's hotlinked scraped-image previews in prod (dev nginx has no
    CSP → looked fine). This was the "prod doesn't show images" bug.
  - **Side-nav user-menu z-order fix** (dropdown rendered behind stat strip / widget rail —
    backdrop-filter stacking-context trap; header got explicit `position:relative; z-index`).
- **Queued on `dev` (unreleased, commit 63c55a4):** the post-upgrade **"What's New" modal was
  empty for 0.5.0/0.5.1** — it reads a curated map in `frontend/src/lib/releaseNotes.ts`
  (does NOT parse the changelog); entries added + `/release-prep` gained **Step 4b** so every
  release adds one. (One cosmetic edit to the command's commit template was permission-blocked;
  substantive fix landed.)
- **OPEN DIAGNOSIS — prod MakerWorld imports missing creator/tags:** verified from this host
  that the FlareSolverr path (shared `https://flaresolverr.crzynet.com/`) extracts creator +
  profile + tags + gallery correctly (repro script hit a live model page through the repo
  pipeline). The **AgentQL fallback returns NO creator by design** (query is only
  `{ title description images[] }`). Suspicion: prod scrapes are landing on AgentQL. Waiting on
  owner to check prod: Admin → Site Capabilities usage rows (provider per URL), FlareSolverr
  card enabled/priority/Test-connection, and `docker logs partfolder3d-worker | grep
  flaresolverr` for the failure reason. **Candidate issue to file:** extend the AgentQL query
  with creator fields so the fallback isn't creator-blind.
- **Prod deploy facts** (compose in `~/projects/docker-compose/apps/partfolder3d/` on this
  host, deployed elsewhere via Komodo): `:latest` images, Traefik ingress
  (`partfolder3d.crzynet.com`), NFS library, `user: 2000:66000`, worker capped
  `cpus:2 / 6G` (matches `RENDER_CPU_THREADS=2`; `WORKER_MAX_JOBS=2`, `RENDER_CONCURRENCY=1`
  defaults). Shared FlareSolverr compose in `~/projects/docker-compose/apps/flaresolverr/`.
- **The dev docker stack on THIS host was DOWN at last check** (only `pf3d-pg-v` test PG up).
  Bring up with `docker compose -f docker-compose.dev.yml up -d`. When up: backend/frontend
  hot-reload from the repo; the **worker does NOT** (restart after worker/task/scraper edits).

## Next phases (roadmap)

- **Resolve the MakerWorld-creator thread** (above) once owner reports prod evidence.
- **Bulk move-assets UI** (#25 follow-up) — last Phase 2 item. Backend bulk endpoint live +
  tested; catalog needs a **multi-select** affordance (real UX decision — discuss with owner
  before building).
- **Issue tracker is EMPTY** (everything through #31 closed). Unfiled candidates: AgentQL
  creator-fields query (above); opportunistic auto-fetch of model files on the scraper
  framework (login-gated on Printables/MakerWorld — deferred from #27).
- Next release = `/release-prep <next>` when a batch is ready (What's-New fix already queued).
  Standing gotchas: CodeQL on big diffs surfaces pre-existing alerts (`sanitize_for_log` real
  ones; dismiss path-injection FPs with existing `resolve()`+`is_relative_to()` barriers);
  transient pip-download timeouts in the Image build check — just re-run the failed job.

## How we work (recap — full rules in `CLAUDE.md`)

- Central **Opus planning session**: plan, write handoff prompts in `prompts/`, dispatch **Sonnet
  subagents** to execute, report back. Owner doesn't babysit. Bigger than ~1–2 files → handoff prompt.
- **Auto-commit on `dev`** with conventional prefixes; **`main` is PR-only, never direct-push.** Use
  `closes #N` so issues auto-close. Every feat/fix commit updates `CHANGELOG.md [Unreleased]` same commit.
- **During active build/test sessions the owner wants each verified item committed AND pushed to `dev`**
  (not just committed) so pushing rebuilds the `:dev` images and the owner's on-host stack + testers can
  pull. Gate each push on `make verify` (full backend suite + fresh frontend build/vitest).
- **Flag genuine design forks** for the owner instead of guessing.
- **Live-iteration caveat:** owner runs the vite dev server / the `:dev` stack on this repo; for bigger
  changes while they test, dispatch to an **isolated worktree** (Agent `isolation: worktree`).
- **Verify + gotchas are NOT here.** Verify discipline: `CLAUDE.md` + `scripts/verify-*.sh` (`make verify`).
  Load-bearing gotchas (render backend, 3MF, modals, worker-no-hot-reload, CI shape, merge-dup-symbols):
  `docs/architecture.md`.

## Backlog (themes — `gh issue list` is the source of truth for what we build **now**, not the PRD)

- **Tracker is empty.** Candidates to file: AgentQL creator fields; auto-fetch model files.
- **Needs owner decision:** bulk-move multi-select UX.
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
- **Dev stack on THIS host** (when up): `partfolder3d-{backend,worker,db,redis,nginx,frontend,flaresolverr}-1`
  on `:dev` images. `docker logs`/`exec` to diagnose; app DB via `docker exec partfolder3d-db-1 psql -U
  partfolder3d -d partfolder3d`. Separate ephemeral **test** pg: `pf3d-pg-v` on :5433 (pytest only).
  Dev scraper config in DB points at the **shared** FlareSolverr (`https://flaresolverr.crzynet.com/`).
- **Run from scratch:** `cp .env.example .env` → `docker compose -f docker-compose.dev.yml up --build`
  (dev) or `docker compose up -d --build` (prod) → http://localhost:8973 first-run wizard. Migrations
  auto-run via the backend entrypoint. External port **8973** (nginx).
- **No sandbox here** — bash may prompt unless auto-approve is on. **System Python is PEP-668** (pip
  blocked); `backend/.venv` exists and runs repo code directly (used for the scrape repro).

## Before-`/clear` checklist

1. Update **Last updated** + **Current state** + **Next phases** (release cut? `dev` vs `main`?).
2. Refresh **Backlog** themes — `gh issue list` is the source of truth; don't enumerate.
3. Ensure in-flight `prompts/` frontmatter + `done|failed/` placement is right; record decisions in
   `docs/decisions.md`.
4. Confirm work is committed **and pushed** on `dev` (note anything intentionally unpushed).
