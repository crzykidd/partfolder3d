---
name: 2026-06-27-phase-6-reconcile-engine
status: completed
created: 2026-06-27
model: sonnet            # coding against a locked plan
completed: 2026-06-27
result: "Backend 6a complete: Issue/ChangeLog/ReviewItem models + migration 0007; reconcile engine; issues/changes/reviews routers; worker integration; 25 tests passing (214 total, 0 regressions); ruff clean; alembic round-trip clean. 6b frontend handoff written."
---

# Task: Phase 6 — Reconciliation / scan engine

Make the **filesystem a peer source of truth**: detect out-of-band edits/additions/deletions
and reconcile them — automatically or after review — surfacing conflicts and problems on an
**Issues** page and every change on a **Change Log**. This is **Phase 6** of
[`docs/build-plan.md`](../docs/build-plan.md) and PRD **§8** (a first-class subsystem).

**Exit criteria (build plan):** out-of-band edits/additions/deletions are detected and (auto
or after review) reconciled; conflicts + problems surface on the Issues page.

## Before you start

- Read [`docs/build-plan.md`](../docs/build-plan.md) **Phase 6** + the **Locked build-time
  technical decisions**.
- Read [`PRD.md`](../PRD.md) **§8 in full** — §8.1 the four behaviors (sidecar⇄DB bidirectional
  sync; re-render on file change; detect new/removed/extra files; orphans/dead-links/integrity),
  §8.2 **Auto vs. Review** per behavior + review list, §8.3 **Change Log** + **Issues page**,
  §8.4 schedule/run-now, §8.5 atomic-moves/rollback contract, §8.6 per-item rescan. Also
  **§5.4** (tag changes → sidecar) and **§3.2/§3.3** (storage/paths invariants).
- Read [`CLAUDE.md`](../CLAUDE.md) operating rules and [`docs/decisions.md`](../docs/decisions.md)
  (esp. the move-journal + sidecar entries).
- **Read the existing code you will build on / reuse — do NOT reinvent it:**
  - `backend/app/storage/inventory.py` — `inventory_item()`, `hash_file_sha256()`,
    `infer_role()`, `FileRecord`, `_mtime_utc()`. This is your file-diff primitive.
  - `backend/app/routers/items.py` — **`rescan_item()`** already implements per-item
    re-inventory + sidecar resync + re-render (PRD §8.6). **Refactor the shared reconcile
    logic into a reusable engine and have BOTH the per-item rescan and the library scan call
    it** — don't fork two copies. Also reuse `_write_item_sidecar`, `_apply_file_records`,
    `_update_search_vector`, `_enqueue_render`, `_attach_tags`.
  - `backend/app/storage/sidecar.py` — `read_sidecar`, `build_sidecar`, `write_sidecar`,
    `SidecarData`. The bidirectional sync compares the on-disk sidecar against the DB.
  - `backend/app/storage/journal.py` — `atomic_rename`, **`recover_stale_journals`**,
    `move_to_trash`, `MoveError`. Any structure-changing fix must go through the journal
    (§8.5). Crash recovery already exists; wire it into the scan startup if not already.
  - `backend/worker.py` — `SCHEDULED_JOB_REGISTRY`, the cron framework, and **`inbox_scan`**
    (`_inbox_scan_core`) as the template for a new scheduled **reconcile scan** job.
  - `backend/app/models/setting.py` — namespaced settings (e.g. `scan.auto_mode`); store the
    per-behavior Auto/Review modes here.
  - Frontend `frontend/src/pages/admin/*`, `JobsPage.tsx`/`ScheduledJobsPage.tsx` (Phase 4),
    `frontend/src/lib/api.ts`, routing in `App.tsx`, and the item page's existing **Rescan**
    button — for the Issues/Change-Log/Review UI.

## Working tree check

`git status --porcelain` — expect a clean tree on `dev` (only this prompt untracked). Phase 5
is committed (`2d032cf`). Surface anything unexpected before proceeding.

## Scope & split guidance

**Large — plan to split.** Do the **backend (6a) first and completely**; the **frontend (6b)**
(Issues page, Change Log, Review list, Auto/Review settings UI, per-item rescan surfacing) may
split to `2026-06-27-phase-6b-*.md`. If the backend is a clean full pass but the frontend won't
fit, **STOP after the backend, write the 6b handoff, and report.** Mirror Phases 4–5.

**Out of scope (later phases) — do NOT build:**
- **Print history + sharing + instance-to-instance import** — Phase 7.
- **AI** tagging/description/summarization — Phase 8.
- inotify/real-time file watching — explicitly a later enhancement (PRD §8.4); a scheduled +
  run-now periodic scan is the Phase 6 deliverable.

## What to do

### 1. Models — Issue, ChangeLog, ReviewItem (migration 0007)
- **Issue** — a detected problem: type (conflict / dead-link / corruption / orphan / missing-
  file / extra-file …), severity, status (open / resolved / ignored), item FK (nullable for
  library-level orphans), human-readable detail, **suggested action**, timestamps.
- **ChangeLog** — an applied change: behavior/type, item FK (nullable), before→after summary,
  source (auto / review-approved / per-item-rescan), actor (system/user), timestamp.
- **ReviewItem** (pending change) — a proposed change awaiting approval when its behavior is in
  **Review** mode: behavior/type, item FK, a serialized **proposed action** the worker can
  apply on approval, status (pending / approved / rejected), timestamps. (Or fold "pending"
  into Issue with an action payload — pick the cleaner model and record the choice.)
- Wire into `models/__init__.py`. `alembic upgrade head` **and** `downgrade base` must pass.

### 2. The reconcile engine (the core)
- A single engine module (e.g. `backend/app/storage/reconcile.py` or
  `backend/app/worker/reconcile.py`) that reconciles **one item** by running the four §8.1
  behaviors, returning a structured result (changes applied, review-items proposed, issues
  found). Reuse `inventory_item()` for the file diff and the sidecar reader for sync.
  - **(a) Sidecar⇄DB bidirectional sync.** Sidecar newer/changed on disk → pull fields into
    DB; DB changed since last sync → write sidecar out; both diverged → **conflict Issue**
    (do not silently clobber). Need a per-item "last synced" signal (sidecar mtime/hash) to
    decide direction — record how you determine direction.
  - **(b) Re-render on file change.** Detect model-file hash/mtime change vs. stored File rows
    → enqueue a render job (reuse `_enqueue_render`); cache is already hash-keyed (Phase 4).
  - **(c) New / removed / extra files.** Inventory diff: ingest manually-added files (new File
    rows), flag removed/missing files (Issue or auto-remove per mode).
  - **(d) Orphans, dead links, integrity.** Item dirs with no DB row (and DB rows with no
    dir) → orphan Issue; **verify file hashes** for corruption → Issue; **validate source
    URLs resolve** → dead-link Issue. **Network calls (URL validation) must be mockable and
    must NOT run in unit tests against real sites** — gate behind a flag / inject the client.
- A **library-wide scan** that iterates items and calls the per-item engine, **each item an
  isolated transaction** (§8.5 — one bad/locked item fails alone as an Issue, never blocks the
  rest). Run **stale-journal recovery** (`recover_stale_journals`) at scan start.

### 3. Auto vs. Review (§8.2)
- Each of the four behaviors has a mode setting (**Auto** or **Review**) stored in `settings`
  (namespaced, e.g. `scan.sidecar_sync.mode`). Sensible defaults — pick conservative ones
  (e.g. structural/destructive → Review) and record them.
- **Auto** → apply the change immediately + write a **ChangeLog** entry. **Review** → create a
  **ReviewItem** (pending) instead of applying; a **run-when-approved** path applies it (via
  the worker / journal for structural changes) + writes a ChangeLog entry. Approve/reject is
  user-driven.

### 4. Scheduled reconcile scan + per-item rescan
- Add a **reconcile scan** scheduled job (default **daily**, **run-now**-able) to
  `SCHEDULED_JOB_REGISTRY`, modeled on `inbox_scan`.
- **Refactor `rescan_item`** to drive the same engine so the per-item **Rescan disk** button
  (§8.6) produces the same Issues/ChangeLog/Review outcomes as the scheduled scan.

### 5. API (admin/authenticated; reuse Phase 1 auth deps)
- Issues: `GET /api/issues` (filter by status/type, paginate), `GET /api/issues/{id}`,
  resolve/ignore actions.
- Change Log: `GET /api/changes` (paginate/filter).
- Review list: `GET /api/reviews` (pending), `POST /api/reviews/{id}/approve`,
  `POST /api/reviews/{id}/reject`.
- Scan: trigger a full reconcile scan now (reuse the Phase 4 scheduled-job run-now if it fits);
  Auto/Review mode settings read/write (reuse the settings router pattern).

### 6. Frontend — MAY SPLIT TO 6b
- **Issues page** (`/admin/issues`) — list with type/severity/status, suggested action,
  resolve/ignore; filter + paginate (TanStack Query).
- **Change Log page** (`/admin/changes`) — human-readable feed, paginated/filterable.
- **Review list** (`/admin/reviews`) — pending proposed changes with approve/reject.
- **Auto/Review settings** — per-behavior mode toggles in the admin settings area.
- **Per-item Rescan** — ensure the existing item-page button reflects engine results (issues
  raised / changes made). `npx tsc --noEmit` clean; vitest for non-trivial logic.

## Conventions to honor

- Match locked decisions + existing Phase 0–5 structure; **reuse** inventory, journal, sidecar,
  settings, and the job/scheduled-job framework rather than duplicating.
- **No half-moved state ever persists** (§8.5): structural fixes go through the journal; bulk =
  N isolated per-item transactions; a failure becomes an Issue, never a crash or partial write.
- A failing scan/behavior **marks the job/issue and is visible** — never crashes the worker or
  corrupts the library. Network (URL validation) is mockable and off by default in tests.
- Secrets out of the repo; document any new env/settings in `.env.example`.
- Verify locally what you can: `ruff check backend/`, `pytest`, `npx tsc --noEmit`, `vitest`,
  `alembic upgrade head` + `downgrade base`, `docker compose config --quiet`.
  **Bring up an ephemeral Postgres** for the migration + async DB tests (the orchestrator does
  this for every schema phase):
  `docker run -d --name pf3d-test-pg -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p 5433:5432 postgres:16-alpine`
  then `export DATABASE_URL="postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d"`,
  run `alembic upgrade head && alembic downgrade base && alembic upgrade head`, then `pytest`.
  Recreate the scratchpad venv at
  `/tmp/claude-1000/-home-manderse-projects-partfolder3d/bd4b77b1-dcc4-4fbf-8dc0-d3990161f59a/scratchpad/venv`
  if gone (system Python is PEP-668; ruff/pytest are not global; needs `python-multipart`).

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-27`, one-line `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`); **if you split, write the 6b handoff**
   (`prompts/2026-06-27-phase-6b-*.md`) describing exactly the remaining frontend scope.
3. Add `docs/decisions.md` entries (newest at top): Issue/ChangeLog/ReviewItem model shapes,
   how sidecar⇄DB **sync direction** is decided + conflict rule, default Auto/Review modes,
   how the engine is shared between scheduled scan and per-item rescan, and the
   isolated-per-item-transaction approach.
4. **You are a spawned agent: do NOT commit, push, or change branch.** Prepare the tree and
   **report back** with: complete file list; proposed one-line `feat:` commit message; exact
   local check results (incl. the ephemeral-PG migration round-trip + pytest count); full-phase
   vs. split (+ 6b path + what remains); any decision made or thing you could not verify.
