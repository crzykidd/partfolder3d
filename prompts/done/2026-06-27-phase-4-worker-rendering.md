---
name: 2026-06-27-phase-4-worker-rendering
status: completed
created: 2026-06-27
model: sonnet            # coding against a locked plan; render backend is a spike
completed: 2026-06-27
result: "Phase 4 complete: Job model+API, scheduled-jobs framework, render job, frontend monitor pages; render spike resolved — pyrender+OSMesa works (VTK PyPI wheel requires X11/EGL, not pure offscreen); 167 backend tests pass, 50 frontend vitest pass, ruff/tsc/alembic/docker-compose all green; 3 render_mesh.py fixes applied (VTK probe via subprocess, EGL→OpenGL module cache cleanup, PyOpenGL version pin relaxed to >=3.1.0)."
---

# Task: Phase 4 — Worker jobs + rendering/thumbnails

Get background jobs running with a live monitor, and auto-generate mesh thumbnails. This is
**Phase 4** of [`docs/build-plan.md`](../docs/build-plan.md). The headless renderer is the
build plan's **known risk** — **start with the render spike (section 1) and treat it as a
go/no-go gate** before building thumbnail wiring on top of it.

**Exit criteria (build plan):** uploading/registering a model produces a PNG render; jobs
are visible in a monitor + manually runnable.

## Before you start

- Read [`docs/build-plan.md`](../docs/build-plan.md) **Phase 4** + the **Locked build-time
  technical decisions** (Mesh render: **trimesh** parse for STL/OBJ/PLY/3MF; offscreen via
  **pyrender + EGL** with a **VTK offscreen** fallback; **CPU-only**; "headless GL in a
  container is the known risk → start with a render spike").
- Read [`PRD.md`](../PRD.md) §7 (rendering/thumbnails — STL/3MF/OBJ/PLY → PNG, stored in the
  item's `renders/`, cache keyed to file hash, re-render on change), §4 (Job model),
  §8.3 (Job/Queue monitor), §8.4 (Scheduled Jobs view: last/next/running + run-now).
- Read [`CLAUDE.md`](../CLAUDE.md) operating rules.
- Read the existing backend (`backend/worker.py` — Phase 0 arq worker + the Phase 3
  `build_zip_bundle` task; `backend/app/routers/items.py`; `storage/`; `models/`), the root
  `Dockerfile` (you'll add system GL libs), and the frontend admin pages
  (`frontend/src/pages/admin/*`) for the monitor/scheduled-jobs UI.

## Working tree check

`git status --porcelain` — expect a clean tree on `dev` (only this prompt may be untracked).
Surface anything unexpected before proceeding.

## Scope & split guidance

Large. Do the **render spike + backend first**; the **frontend** (job monitor + scheduled-
jobs view) may split to `4b`. If too big for one clean pass, STOP after the backend and
write the `4b` handoff. **And** if section 1's spike shows headless rendering cannot be made
to work at all (no working CPU-only backend), STOP and report that as a blocker before
building the thumbnail wiring — do not fake renders.

**Out of scope (later phases):** the full scan/reconcile engine, Issues, Change Log, and
Auto/Review (Phase 6); sidecar⇄DB bidirectional sync (Phase 6); import wizard (Phase 5); AI
(Phase 8). Phase 4 builds only the **Job model + monitor + scheduled-jobs framework**, the
**render job**, and a couple of concrete jobs (render, expired-ZIP-bundle cleanup).

## What to do

### 1. Render spike (DO THIS FIRST — go/no-go)
- Parse STL/OBJ/PLY/3MF with **trimesh**. Render an offscreen PNG (fixed deterministic
  camera framing the mesh bounds, neutral lighting + background, configurable resolution,
  e.g. 1024²). **CPU-only:** a container has no GPU, so the EGL path likely needs a software
  GL stack — try **pyrender (EGL)**, then **OSMesa** (software), then **VTK offscreen**.
  Pick the first that works; make the backend **detected/configurable** and the failure
  modes explicit (clear error, never a crash loop).
- Add the needed **system libraries to the root `Dockerfile`** (e.g. `libgl1`, `libegl1`,
  `libosmesa6`, `libglib2.0-0`, freetype/`xvfb` only if required) and the Python deps to
  `backend/requirements.txt` (`trimesh`, `pyrender`, `numpy`, `Pillow`, and `vtk` for the
  fallback; `PyOpenGL`/`PyOpenGL-accelerate` as needed). Keep the image CPU-only.
- Provide a small runnable entry (a function + a tiny CLI or test) that renders a bundled
  sample mesh to a PNG. **Verify as far as this environment allows** (no Docker/GPU here):
  trimesh parsing must pass; attempt a real software render if OSMesa is installable in a
  venv. **Report honestly** what worked vs. what needs the Docker image / CI / user to
  confirm.

### 2. Job model + tracking
- **Job** model + migration: type, status (queued/running/succeeded/failed), progress,
  payload (JSON), log/error, created/started/finished timestamps (PRD §4). A thin helper so
  arq tasks create/update their Job row as they run.

### 3. Render job + thumbnail cache
- An arq task that renders an item's mesh files → the item's **`renders/`** dir, **cache
  keyed to the model file's SHA-256** (`renders/<sha256>.png`); skip if the cached render
  for that hash exists. **Re-render when a model file's hash/mtime changes.**
- Wire it in: enqueue a render job on **item create** (Phase 2 `POST /api/items`) and on
  **per-item Rescan** (Phase 2 `…/rescan`) for changed/added model files. A successful
  render becomes a selectable image / default-image fallback when the item has no images.
  Non-mesh types (Blender/CAD) get no render (generic icon in UI) — don't fail the job.

### 4. Scheduled-jobs framework + a cleanup job
- A **scheduled-jobs registry** (recurring jobs with cron schedule; track last run +
  outcome, next run, running-now) using arq's cron support. Seed it with at least:
  the **expired-ZIP-bundle cleanup** (Phase 3 `download_bundles` expire ~1 day) and a
  no-op/reindex placeholder. Each job is **run-now**-able on demand (enqueue immediately),
  independent of schedule.

### 5. API
- `GET /api/jobs` (live monitor: queued/running/failed with progress, filter/paginate),
  `GET /api/jobs/{id}`. `GET /api/scheduled-jobs` (last/next/running per recurring job) +
  `POST /api/scheduled-jobs/{name}/run` (run-now). Admin-only. Reuse Phase 1 auth deps.

### 6. Frontend (may be 4b)
- **Job/Queue monitor** (`/admin/jobs`) — live list (poll), status + progress, failed jobs
  surfaced; TanStack Query.
- **Scheduled Jobs view** (`/admin/scheduled-jobs`) — table of recurring jobs with last run
  (time + outcome), next run, running-now, and a **Run now** button.
- Item page / cards: show the render as an image when present (extends Phase 3 UI), generic
  placeholder otherwise. `npx tsc --noEmit` clean; vitest for non-trivial logic.

## Conventions to honor

- Match locked decisions + existing Phase 0–3 structure. No out-of-scope features (above).
- Worker/back-end is CPU-only; rendering must degrade gracefully (a render failure marks the
  Job failed and is visible — it must NOT crash the worker or block item creation).
- Secrets out of the repo; document new env (render resolution, backend selection) in
  `.env.example`.
- Verify locally what you can: `ruff check backend/`, `pytest`, `npx tsc --noEmit`,
  `vitest`, `alembic upgrade head` + `downgrade base` (ephemeral Postgres), `docker compose
  config --quiet`. **Headless GL rendering may only be verifiable in the Docker image / CI**
  — say so explicitly rather than claiming it.

## When done

1. Update frontmatter (`status`, `completed: 2026-06-27`, one-line `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`); if you split, write the `4b` handoff.
3. Add `docs/decisions.md` entries (newest at top): the **render backend that actually
   worked** (EGL vs OSMesa vs VTK) + why, Dockerfile GL libs, Job model shape, scheduled-jobs
   mechanism, render cache key.
4. **You are a spawned agent: do NOT commit, push, or change branch.** Prepare the tree and
   **report back** with: complete file list; proposed one-line `feat:` commit message; exact
   local check results; the **render spike outcome** (which backend works / what still needs
   Docker/CI/user verification); full phase vs split (+ 4b path + remaining); any decision
   made or thing you could not verify.
