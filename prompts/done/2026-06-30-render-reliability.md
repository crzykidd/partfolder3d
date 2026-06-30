---
name: 2026-06-30-render-reliability
status: completed        # pending | completed | failed
created: 2026-06-30
model: sonnet            # backend + infra
completed: 2026-06-30
result: Render now runs in a killable spawn subprocess with wall-clock timeout + thread caps; orphaned "running" jobs recovered + re-enqueued on worker startup; added RENDER_MODE (all/no_images/off) background-render gate. Verified by live render smoke (cube→PNG, garbage→RenderError) + 7 capped pytest.
---

# Task: Harden the mesh-render pipeline (CPU cap, real timeout, crash recovery)

Mesh renders currently (1) peg 100% CPU, (2) get stuck in "Running" forever on big/hung
files, and (3) are never recovered if the worker dies mid-render. **Root cause:** the
render is a synchronous, blocking C call (`trimesh` + pyrender/OSMesa/VTK) executed
directly in the worker's asyncio event loop, so it grabs every core (no thread caps) and
arq's cooperative `job_timeout` cannot interrupt it. This task fixes all three by running
the render in a **killable child process** with thread caps and a wall-clock timeout, plus
startup recovery of orphaned jobs.

## Before you start

- Read `prompts/startnewsession.md` (current state) and `CLAUDE.md` (operating rules:
  you are a spawned agent on `dev`; do NOT commit/push — prepare the tree and report back).
- Read these files fully before editing — they are the whole surface:
  - `backend/app/worker/tasks/render.py` — the `render_item(ctx, item_id)` arq task.
  - `backend/app/worker/render_mesh.py` — `render_mesh_file(path, resolution)`, the blocking render.
  - `backend/app/worker/job_tracker.py` — `create_job` / `update_job_progress` / `finish_job`.
  - `backend/worker.py` — `WorkerSettings`, `startup()` (on_startup hook), `max_jobs=10`, `job_timeout=600`.
  - `backend/app/config.py` — `Settings`.
  - `backend/app/models/job.py` — the `Job` model (status is a free `String(16)`: queued/running/succeeded/failed).
  - `Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml` — the `worker` service.
- **Do NOT touch the job model schema, the jobs router, or the frontend** — those are a
  separate prompt (job lifecycle). Stay within render reliability. The ONLY new Job status
  you may introduce is nothing — keep the existing 4 statuses; orphans become `failed`.

## Working tree check

`git status --porcelain` first. Expect clean `dev`. If any file above has unrelated
uncommitted changes, list them and ask before touching.

## What to do

1. **Config** (`backend/app/config.py`): add two settings with env overrides and sane defaults:
   - `RENDER_TIMEOUT_S: int = 300` — wall-clock kill for a single file's render.
   - `RENDER_CPU_THREADS: int = 2` — thread cap for the render process.
   Document them in `.env.example` too.

2. **Run the render in a killable subprocess with a wall-clock timeout.** In
   `render.py` (or a small new helper module under `backend/app/worker/`), replace the
   direct `render_mesh_file(...)` call with an offloaded version:
   - Use `multiprocessing.get_context("spawn")` (NOT fork — fork after GL/threads init can
     deadlock). The child runs a top-level function that calls `render_mesh_file` and writes
     the PNG bytes to a temp file (or returns via a `Queue`/`Pipe`); on error it reports the
     message + nonzero exit.
   - Parent: start the process, then **`await asyncio.to_thread(proc.join, RENDER_TIMEOUT_S)`**
     so the event loop is never blocked. If the process is still alive after the timeout →
     `proc.terminate()`, join a few seconds, `proc.kill()` if needed, and raise a
     `RenderTimeout`/`RenderError` for that file (mark it errored, continue to the next file).
   - Read the PNG bytes back from the temp file on success.
   - Keep the existing per-file behavior: SHA-256 cache check (skip if `renders/<sha>.png`
     exists), progress updates, `_reconcile_render_images`, multi-file loop.

3. **Thread caps so a render stops pegging all cores.** Set these env vars for the `worker`
   service (value = `RENDER_CPU_THREADS`, default 2) in BOTH compose files and as image
   defaults in the `Dockerfile`, AND defensively set them in `os.environ` at worker startup
   BEFORE the first render (spawned children inherit them):
   `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `VECLIB_MAXIMUM_THREADS`,
   `NUMEXPR_NUM_THREADS`, and **`LP_NUM_THREADS`** (llvmpipe / Mesa software rasterizer —
   this is the one that caps OSMesa's own threads). Drive all of them from the single
   `RENDER_CPU_THREADS` value.

4. **Finalize the Job row on cancellation/crash, not just normal exceptions.** Today
   `render_item` only catches `Exception`, so `asyncio.CancelledError` (a `BaseException`
   from timeout/shutdown) leaks a "running" row. Restructure so:
   - Normal render *content* failures (RenderError, our RenderTimeout) → mark the Job
     `failed` with the error and **return normally** (do NOT re-raise) so arq does not
     auto-retry and spawn duplicate rows.
   - On `BaseException` (CancelledError / worker shutdown) → best-effort `finish_job(failed,
     error="worker stopped / cancelled")` using a FRESH DB session (the in-flight session may
     be poisoned), then re-raise. A `try/finally` that finalizes if not already finalized is
     acceptable too — just guarantee no path leaves the row "running".

5. **Crash recovery on startup** (the owner's "pick it back up and complete it" requirement).
   In `backend/worker.py` `startup()`, after seeding scheduled jobs, scan the `jobs` table
   for `type="render"` rows still in `status="running"` (these are orphans — the worker just
   started, so nothing of ours is legitimately running yet). For each: mark the orphaned row
   `failed` (error e.g. "orphaned by worker restart — re-queued") AND **re-enqueue
   `render_item(item_id)`** from its `payload`/`item_id`. Renders are idempotent (cache by
   sha), so a completed render just cache-hits; an incomplete one finishes. Dedup by item_id
   so N orphans for the same item enqueue once.

6. **Tame arq auto-retry duplication.** With render content-failures now returning normally
   (step 4), arq won't retry those. Confirm `WorkerSettings` doesn't otherwise multiply
   render rows; if needed, set explicit `retry_jobs`/`max_tries` — but justify any global
   change since other tasks (zip/import) share the worker. Document the choice in
   `docs/decisions.md`.

## Conventions to honor

- No new dependencies (multiprocessing + threadpool env are stdlib/OS).
- Match surrounding style; keep the lazy `# noqa: PLC0415` import pattern where used.
- **Tests** (ephemeral-PG, REQUIRED): add coverage that does NOT need real GL — mock
  `render_mesh_file` to (a) sleep past `RENDER_TIMEOUT_S` → assert the job ends `failed`
  (timeout kill) not stuck "running"; (b) raise RenderError → assert `failed` + no duplicate
  rows. For startup recovery, seed a `running` render Job row, run `startup()` (or the
  extracted recovery function), assert the row is `failed` and `render_item` was re-enqueued
  (mock the redis enqueue). Prefer extracting the recovery logic into a testable function.
- **Verify discipline (REQUIRED before reporting done):**
  - `ruff check backend/` with pinned ruff **0.8.4** (use `backend/.venv/bin/ruff` —
    it's 0.8.4; run it from the repo root exactly as CI does: `ruff check backend/`).
    Ignore any extra findings that only appear when you pass `--config` explicitly (that
    changes isort's first-party root and yields false I001 — not what CI runs).
  - Ephemeral Postgres (`postgres:16-alpine` on `:5433`, creds
    `partfolder3d`/`testpass`/`partfolder3d`), `alembic upgrade head` FIRST, then pytest.
    Report exact pass counts. No new migration in this task (no schema change).

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-30`, `result`).
2. `git mv` it into `prompts/done/` (success) or `prompts/failed/` (failure).
3. **Do NOT edit `docs/decisions.md`** (a parallel agent shares it — concurrent edits would
   race). Instead, include your decision note (root cause + subprocess/timeout/recovery
   design + any arq-retry choice) in your report-back; the orchestrator records it.
4. **Do NOT commit.** Prepare the tree; report back: files changed, the decision note for
   `docs/decisions.md`, a one-line `fix:`-prefixed commit message, ruff result, and
   ephemeral-PG pass counts.
