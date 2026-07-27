# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** This is the **live-state handoff** — a
current, limited view so a new session can orient fast, then go deeper via the docs it points to.
It is NOT a full reference: durable rules live in `CLAUDE.md`, the module map + gotchas in
`docs/architecture.md`, history in `CHANGELOG.md` / `docs/decisions.md`. Keep it LEAN; refresh
"Current state" + "Next phases" before every `/clear`.

**Last updated:** 2026-07-26 — **`v0.8.0` RELEASED.** Tag `v0.8.0` cut on `main`, GitHub release
published, `release`-triggered "Build and publish Docker images" run kicked off (publishes prod
`:latest`/`:0.8.0`/`:0` for all three images: backend/frontend/nginx). A big batch — **5 features + 1
fix** (see Current state). `dev` == `main`.

> **⏭️ NO RELEASE IN FLIGHT, no forced next task.** `dev` == `main` (v0.8.0). Next build pickup is an
> owner **choice** (`gh issue list` is the source of truth). Only **one open issue**:
> **[#41](https://github.com/crzykidd/partfolder3d/issues/41)** automatic Let's Encrypt/ACME at nginx.
> Other candidates (Next phases): **bulk move-assets UI** (#25 follow-up); refresh a `.3mf`'s embedded
> slicer thumbnail on in-place edit; a manual **"re-render `.scad`"** button (deferred from #46).

> **⚠️ DEPLOY NOTE for v0.8.0:** the on-host stack must **pull the new `:latest` images and restart**
> to pick this up — v0.8.0 adds the **`openscad` binary** (image change, ~+370 MB) and **migration
> `0026`** (auto-runs on backend-container start). The restart is also what makes the **sidecar-sync
> fix** live, which clears the recurring `sidecar_error` Issues (dev DB: #9/#12/#13/#20 — Retry rescan
> will succeed once deployed).

## Current state

- **Latest release `v0.8.0`** (2026-07-26, on `main`; `:latest`/`:0.8.0`/`:0` published). Full
  per-bullet detail in `CHANGELOG.md` `[0.8.0]` and `docs/decisions.md` (2026-07-26 entries).
  Shipped this batch:
  - **Edit item description + add/remove tags in-app** (`feat:`, closes #47). Reused the existing
    write-through `PATCH /api/items/{key}` (`routers/items/core.py`) — updates DB + on-disk `.yml`
    sidecar + FTS in one op, marks a legit local edit (no reconcile drift). New tags land `pending`
    unless `tags.auto_approve`. Inline editor on `frontend/src/pages/item/ItemMetadata.tsx`. **Title
    edit deferred** (a rename triggers an atomic dir move — heavier flow).
  - **Server-side OpenSCAD render** (`feat:`, closes #46). Worker compiles `.scad`→STL in an isolated
    subprocess (`worker/scad_subprocess.py`, `worker/tasks/scad_render.py`; timeout + `RLIMIT_*` +
    scratch dir, cloned from render/analyze). Derived STL flows through the **existing**
    render/analyze/viewer pipeline. Recorded as a generated asset (`files.generated_from_file_id` /
    `generated_source_sha256`, migration **0026**), excluded from sidecar + reconcile drift.
    `SCAD_RENDER_*` config knobs (default **ON**; soft-skips if the `openscad` binary is absent).
    `openscad` added to the shared `./Dockerfile`. No manual re-render UI (deferred).
  - **Inline PDF viewer** (`feat:`). `download_file` (`routers/downloads.py`) gained `?inline=1`,
    honored **PDF-only** (`.pdf` ext + `%PDF-` magic + `X-Content-Type-Options: nosniff`); every other
    type keeps the attachment/octet-stream default (XSS safety). **View PDF** modal (`<iframe>`,
    browser-native, no PDF.js) in `DownloadsPanel.tsx`.
  - **One-click "Clear failed"** (`feat:`). Always-visible button in `JobsPage.tsx` calling the
    pre-existing `POST /api/jobs/clear?status=failed`; hides the contextual clear when the failed
    filter is active.
  - **stlflix.com scraping** (`feat:`). Host-gated (`stlflix.com` apex/subdomain — look-alikes
    rejected) `__NEXT_DATA__` extractor in `storage/scraper.py` (`_enrich_from_next_data_stlflix` +
    Strapi `.data.attributes` unwrap helpers). Product is at `props.pageProps` (a Strapi shape, unlike
    MakerWorld's `pageProps.design`); httpx already handles the `NEXT_LOCALE` 307. Creator defaults to
    `"STLFLIX"` (fallback-only).
  - **fix: reconcile sidecar-sync `greenlet_spawn` crash.** `reconcile.py::_write_sidecar_for_item`
    deduped onto the corrected `item_helpers._write_item_sidecar` (eager-loads `item.creator`), AND
    `_behavior_sidecar_sync` now refreshes a possibly-flush-expired `item.updated_at` before reading
    it. Killed the recurring, unclearable `sidecar_error` Issues; they auto-resolve on the next
    successful sync (`_action_retry` flips to `resolved` when `errors` is empty).
- **Earlier releases** (`v0.1.1`–`v0.7.5`): full history in `CHANGELOG.md`. Recent highlights —
  v0.7.5 OpenSCAD `.scad` read-only viewer; v0.7.4 MakerWorld octet-stream image-save fix; v0.7.2
  corruption-vs-legit-edit reconcile fix + bulk review approve/reject; v0.7.1 built-in HTTPS/TLS;
  v0.7.0 prinnit.com import; v0.6.0 Manyfold import.
- **Prod deploy facts** (compose in `~/projects/docker-compose/apps/partfolder3d/` on this host,
  deployed elsewhere via Komodo): `:latest` images, Traefik ingress (`partfolder3d.crzynet.com`),
  NFS library, `user: 2000:66000`, worker capped `cpus:2 / 6G` (`WORKER_MAX_JOBS=2`,
  `RENDER_CONCURRENCY=1`, `ANALYZE_CONCURRENCY=2`). Shared FlareSolverr in
  `~/projects/docker-compose/apps/flaresolverr/`.
- **The dev docker stack on THIS host** — up/down with
  `docker compose -f docker-compose.dev.yml {up -d,stop}`. backend/frontend hot-reload from the repo;
  the **worker does NOT** (`make worker-restart` after worker/task/scraper edits). Dev DB has a
  configured Manyfold instance + committed test imports (items ~11, 25, 29–35) and the open
  `sidecar_error` Issues that the v0.8.0 fix will clear on redeploy.
- **CI vs local gotcha (recurring):** the local `verify-frontend`/vitest gate flakes hard under host
  CPU load — nondeterministic `waitFor` 5s timeouts in a *different* heavy-async test set each run
  (catalog-page / reviews-page / scrapers / tag-admin / manyfold-admin / import-wizard), **zero real
  assertion failures**. This host runs load-avg ~10 (owner's stacks). Confirm by re-running the named
  files in isolation (`npx vitest run <file> --no-file-parallelism`) — they pass. **CI on a clean
  runner is authoritative.** Backend (`pytest -n auto`) does NOT have this problem.

## Next phases (roadmap)

- **Automatic Let's Encrypt/ACME at nginx** (issue [#41](https://github.com/crzykidd/partfolder3d/issues/41)) —
  the only open issue; follow-up to v0.7.1's BYO/self-signed TLS. Bigger lift (certbot companion or
  Caddy edge; needs public 80/443 + DNS + renewal). Owner decides approach at build time.
- **Bulk move-assets UI** (#25 follow-up) — last Phase 2 item. Backend bulk endpoint live + tested;
  catalog needs a **multi-select** affordance (real UX decision — discuss with owner first).
- **Deferred v0.8.0 follow-ups (NEW):**
  - **Refresh a `.3mf`'s embedded slicer thumbnail on in-place edit** — the v0.7.2 re-render/adoption
    path re-renders but does NOT refresh the embedded thumbnail; route it through `_enqueue_analyze`
    (not just render).
  - **Manual "re-render `.scad`" button** — v0.8.0 only auto-enqueues the `.scad`→STL compile on
    import/upload (when no model file exists). Add an item-page action to re-run it (the task is
    idempotent via the source-sha cache). Pairs with in-app `.scad` editing (a future companion to
    #47's write path).
  - **Optionally isolate `validate_model_file`'s STL/OBJ/PLY path** with the same subprocess/RLIMIT
    rigor as analyze/render (currently size-bounded only).
- **Older unfiled:** partial analysis of very large 3MFs (streaming/decimation) if ever wanted;
  a lighter prinnit `/designs/<sub>` fetch (returns the whole catalog for one design).
- **Next release = `/release-prep <next>` when a batch is ready** (v0.8.0 is fully cut; next is
  `0.8.1`, or `0.9.0` for another feature batch). Standing gotchas: CodeQL on the PR surfaces
  path-injection FPs on `routers/downloads.py` (guarded by `resolve()`+`is_relative_to()` — dismiss as
  false-positive, matching prior dismissals #3/#4/#5/#37/#62/#63); `make verify` via a pipe (`| tail`,
  `| cat`) **masks the real exit code** — run it via a background task with NO pipe and read the
  summary. Dispatch discipline: spawned agents must NOT run the full gate (shared test PG collision) —
  they run ruff/tsc only; the orchestrator runs the authoritative `make verify` and finalizes.

## How we work (recap — full rules in `CLAUDE.md`)

- Central **Opus planning session**: plan, write handoff prompts in `prompts/`, dispatch **Sonnet
  subagents** to execute, report back. Owner doesn't babysit. Bigger than ~1–2 files → handoff prompt.
- **Auto-commit on `dev`** with conventional prefixes; **`main` is PR-only, never direct-push.** Use
  `closes #N` so issues auto-close on merge. Every feat/fix commit updates `CHANGELOG.md [Unreleased]`
  same commit.
- **During active build/test sessions the owner wants each verified item committed AND pushed to `dev`**
  so pushing rebuilds the `:dev` images and the owner's on-host stack + testers can pull. Gate each
  push on `make verify` (full backend suite + fresh frontend build/vitest).
- **Spawned-agent orchestration (learned the hard way):** tell agents to run **only** fast DB-free
  checks (ruff / tsc) and **never** the full `make verify` / `pytest` gate — a second concurrent
  pytest corrupts the single shared ephemeral test PG (`pf3d-pg-v`). The orchestrator runs ONE
  authoritative gate and finalizes (kill orphans, `docker rm -f pf3d-pg-v`, verify with no pipe,
  commit, push). Concurrent agents are safe only on **disjoint files with disjoint gates** (e.g.
  frontend vs backend) and told to skip CHANGELOG/docs (orchestrator adds those at commit).
- **Flag genuine design forks** for the owner instead of guessing; verify diagnoses on the live stack
  before building a fix.
- **Live-iteration caveat:** owner runs the vite dev server / the `:dev` stack on this repo; for bigger
  concurrent changes, an isolated worktree (Agent `isolation: worktree`) avoids stomping — but a fresh
  worktree lacks `.venv`/`node_modules`, so the agent can't run local gates there (orchestrator gates).
- **Verify + gotchas are NOT here.** Verify discipline: `CLAUDE.md` + `scripts/verify-*.sh` (`make
  verify`). Load-bearing gotchas: `docs/architecture.md`.

## Backlog (themes — `gh issue list` is the source of truth for what we build **now**, not the PRD)

- **Open issues (run `gh issue list`):** only [#41](https://github.com/crzykidd/partfolder3d/issues/41)
  automatic Let's Encrypt/ACME at nginx. (#46 and #47 shipped in v0.8.0 and auto-closed.)
- **Needs owner decision:** #41 approach; bulk-move multi-select UX (#25 follow-up); whether the NEW
  v0.8.0 follow-ups (`.3mf` thumbnail refresh, manual `.scad` re-render) get filed as issues.
- Older PRD §18 notes: real slicing for filament estimates, trash-purge UI, `.bgcode`/multi-filament
  gcode.

## Session start order

1. **This file** — live state + next phases.
2. **`CLAUDE.md`** — operating rules + verify discipline.
3. **`docs/architecture.md`** — where things live (module map) + load-bearing gotchas.
4. **`docs/decisions.md`** (newest-first ADR log) + **`CHANGELOG.md`** — the detailed look-back.
5. **`docs/audit-2026-07-03.md`** — the audit worklist (mostly done; deferrals noted).

## Repo, remotes, environment (quick-start)

- **Code:** GitHub [`crzykidd/partfolder3d`](https://github.com/crzykidd/partfolder3d). `main` protected
  (PR-only, required CI checks). Work on `dev`. `gh` authed as `crzykidd`.
- **Dev stack on THIS host** (when up): `partfolder3d-{backend,worker,db,redis,nginx,frontend,flaresolverr}-1`
  on `:dev` images. `docker logs`/`exec` to diagnose; app DB via `docker exec partfolder3d-db-1 psql -U
  partfolder3d -d partfolder3d`. Separate ephemeral **test** pg: `pf3d-pg-v` on :5433 (pytest only).
  Dev scraper config in DB points at the **shared** FlareSolverr (`https://flaresolverr.crzynet.com/`).
- **Stale-network recovery:** if `up` leaves containers stuck in `Created` with
  `failed to set up container networking: network <id> not found`, run
  `docker compose -f docker-compose.dev.yml down --remove-orphans` then `up -d` — always `down` before
  `up`, never `up` onto a half-running stack.
- **Run from scratch:** `cp .env.example .env` → `docker compose -f docker-compose.dev.yml up --build`
  (dev) or `docker compose up -d --build` (prod) → http://localhost:8973 first-run wizard. Migrations
  auto-run via the backend entrypoint. External port **8973** (nginx).
- **No sandbox here** — bash may prompt unless auto-approve is on. **System Python is PEP-668** (pip
  blocked); `backend/.venv` exists and runs repo code directly.

## Before-`/clear` checklist

1. Update **Last updated** + **Current state** + **Next phases** (release cut? `dev` vs `main`?).
2. Refresh **Backlog** themes — `gh issue list` is the source of truth; don't enumerate.
3. Ensure in-flight `prompts/` frontmatter + `done|failed/` placement is right; record decisions in
   `docs/decisions.md`.
4. Confirm work is committed **and pushed** on `dev` (note anything intentionally unpushed).
