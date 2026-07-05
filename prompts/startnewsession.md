# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** This is the **live-state handoff** — a
current, limited view so a new session can orient fast, then go deeper via the docs it points to.
It is NOT a full reference: durable rules live in `CLAUDE.md`, the module map + gotchas in
`docs/architecture.md`, history in `CHANGELOG.md` / `docs/decisions.md`. Keep it LEAN; refresh
"Current state" + "Next phases" before every `/clear`.

**Last updated:** 2026-07-05 — v0.3.0 on `main`; a **large unreleased batch on `dev` is ready**;
the **immediate next action is to cut the release**.

## Current state

- **Latest release: `v0.3.0`** on `main` (tagged, GitHub release live). Full app shipping
  (identity, libraries + atomic-move storage, import wizard + bulk import, catalog, item pages with
  3D viewer + object breakdown, reconcile, print history + sharing, AI tagging, admin, worker limits).
- **`dev` is well AHEAD of `main` — a big unreleased batch, every push CI-green, suites ≈769 backend / ≈357 frontend:**
  - **Audit remediation** (two rounds; `docs/audit-2026-07-03.md`, ~83/93 done): docs/PRD/
    Claude-ergonomics; the **security cluster** (SSRF, `javascript:` XSS, authz, Redis auth + nginx
    headers + DB-fail-fast + CORS + CI SHA-pinning, exception hygiene, data-safety); operational
    hygiene (generalized crash recovery + daily reclamation cron); file-split refactors
    (items→package, catalog/imports pages, commit.py, issue_action).
  - **Features / bug-fixes:** #20+#30 queued/analyze job visibility · #28 full-res scraper images +
    title/desc/creator cleanup · #27 **partial** (tags-immediate + Files row) · #31 auto-approve-tags
    + bulk approve-all · #25 move-assets-between-libraries · #26 wizard "Try to render file" capture ·
    analyze-on-import fix · catalog-pagination + scraped-images-in-file-list + dev-worker-DEBUG fixes ·
    second-library compose support (`FS_BROWSE_ROOTS`).
  - `closes #N` is in the commits → those issues auto-close on the **dev→main merge** (still open now).
- **Owner is testing** the app (notably the new **second-library** setup) before cutting the release.
  The `:dev` docker stack runs **on this host** — diagnose live via `docker logs`/`exec` + the app DB
  (`docker exec partfolder3d-db-1 psql -U partfolder3d -d partfolder3d`).

## Next phases (roadmap)

**Phase 1 — CUT THE RELEASE (immediate next action).** The dev batch is a broad security + features
release. Flow: `/release-prep <version>` → merge the dev→main PR (only when all required checks are
green) → `:latest` publishes → `/release-cut <version>`. Likely a **minor** (e.g. `0.4.0`) — owner
picks the number. We do **NOT** archive old changelog series.
⚠️ **Upgrade caveats to put in the release notes:**
  - **Drain the worker queue** across the upgrade — the arq serializer changed pickle→JSON (in-flight
    pickled jobs won't deserialize; queue is normally empty, so usually a non-event).
  - Prod now **fails fast on the default `changeme` DB password** — operators must set a real
    `POSTGRES_PASSWORD` **and** `REDIS_PASSWORD` (Redis now runs with `--requirepass`).
  - New knobs to mention: `TRASH_RETENTION_DAYS`, `ORPHAN_PRINTS_DELETE`, `SCRAPE_IMAGE_MAX_MB` /
    `SCRAPE_HTML_MAX_MB`, `FS_BROWSE_ROOTS` (multi-library).
  - CodeQL may flag items on the release PR — fix real ones, dismiss FPs (CI notes in `docs/architecture.md`).

**Phase 2 — owner-decision items (BLOCKED on owner input — don't guess).** All in `docs/decisions.md`:
  - **#27 core fork** — URL import attaches no model file. Pick: (a) auto-fetch the file
    (fragile/login-gated on most sites), (b) add a manual-upload step to the URL wizard, or
    (c) accept metadata-only (the Files-row 0-file warning already ships).
  - **#23 FlareSolverr** — the written prompt (`prompts/2026-07-03-23-flaresolverr.md`) has OPEN
    design questions (Q1/Q5 on the pluggable-scraper-backend UI). Answer those first; also wants a
    live FlareSolverr instance to validate end-to-end.
  - **Bulk move-assets UI** (#25 follow-up) — the backend bulk endpoint is live + tested; the UI needs
    a catalog **multi-select** affordance that doesn't exist yet (a real UX decision).

**Phase 3 — remaining backlog** — `gh issue list` after the above.

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

- **Done on `dev`, awaiting release:** #20, #30, #28, #31, #25, #26 (+ #27 partial).
- **Needs owner decision (Phase 2):** #27 core, #23 (FlareSolverr, open Qs), bulk-move UI.
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
