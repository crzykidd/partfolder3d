---
name: 2026-07-01-render-rework-a-backend-3mf-read
status: done
created: 2026-07-01
model: sonnet
completed: 2026-07-01
result: >
  All 7 tasks completed. New threemf.py (GL-free 3MF reader), migration 0021
  (ImageSource.embedded via autocommit ALTER TYPE), analysis task wired to
  extract embedded thumbnails + sliced metadata, render bounded to STL/OBJ/PLY
  with RENDER_MAX_FILE_MB/RENDER_MAX_TRIANGLES caps, VTK-only stack (pyrender/
  PyOpenGL/EGL/OSMesa removed from requirements + Dockerfile), preview_3d on
  FileOut, three new config settings. Ruff clean on all changed files; 11/11
  threemf unit tests pass; existing 60 pure-Python tests pass. Migration and
  Docker image build not verified locally (no PG / no Docker) — orchestrator
  to verify migration on ephemeral PG; image build + render smoke test is a
  CI/Docker follow-up per the decisions.md spec.
---

# Task: Backend — read-don't-render foundation (3MF extraction, bounded STL/OBJ render, VTK-only stack)

Rework the mesh pipeline so the server stops CPU-rendering heavy files. 3MF is **read**
(embedded thumbnail + real slice metadata), not rendered; server rendering is bounded to
raw STL/OBJ as a fallback; the render backend chain collapses to VTK-only. This is Phase A
of a four-phase feature — B (ZIP extraction) and C/D (frontend) build on it.

## Before you start

- Read `docs/decisions.md` (top entry, **2026-07-01 — Asset-detail / 3D-preview rework**) —
  it is the authoritative spec for this work. Also `docs/sidecar-schema.md` and
  `prompts/startnewsession.md` (verify discipline, gotchas).
- The current pipeline map (accurate as of this prompt):
  - `backend/app/worker/render_mesh.py` — EGL→OSMesa→VTK backend detection + render.
  - `backend/app/worker/render_subprocess.py` — subprocess isolation + timeout.
  - `backend/app/worker/tasks/render.py` — `render_item` arq task + Image-row reconcile.
  - `backend/app/worker/mesh_analysis.py` — trimesh metadata (volume/dims/colors), incl. a
    3MF geometry-color parser via lxml.
  - `backend/app/worker/tasks/analysis.py` — `analyze_item` arq task.
  - `backend/app/models/file.py` (`object_analysis` JSONB), `backend/app/models/image.py`
    (`ImageSource` enum), `backend/app/services/item_helpers.py`
    (`_enqueue_render`/`_enqueue_analyze`, default-image logic), `backend/app/routers/items.py`
    (`FileOut`/`ImageOut`/`ItemDetail`), `backend/app/config.py`, `backend/app/worker/worker.py`.
- **Do NOT** touch the frontend, ZIP handling, or import-commit flow — those are later phases.

## Working tree check

Run `git status --porcelain` and cross-reference the files below. If any are already dirty,
list them and ask before touching. Untracked sibling prompts (`prompts/2026-07-01-render-rework-b/c/d-*.md`)
are expected — surface once, don't block, don't touch them.

## What to do

1. **3MF reader (new, no GL)** — `backend/app/worker/threemf.py`:
   - Open the `.3mf` as a zip (`zipfile`). Extract the best embedded thumbnail, preferring
     `Metadata/plate_1.png` → `Metadata/top_plate_1.png` → `Metadata/thumbnail.png` (accept
     `.jpg` too). Return the raw bytes + which entry was used.
   - Detect **sliced**: any `Metadata/plate_*.gcode` entry (or non-empty `gcode_file` in
     `model_settings.config`).
   - Parse `slice_info.config` (XML, lxml): per-plate `prediction` (print seconds), `weight`
     (g), and per-`<filament>` `used_m` / `used_g` (+ slot id, 1-indexed).
   - Parse `project_settings.config` (JSON): `filament_colour[]` (hex), `filament_type[]`,
     `printer_model`, slicer name/version (also readable from the file header / `3dmodel.model`
     metadata — best effort).
   - Parse `model_settings.config` (XML) best-effort for plate/object layout (`plater_id`,
     object names). Never raise on a malformed/partial 3MF — return whatever parsed.
   - Return a structured dict: `{sliced, slicer, plate_count, objects_total, print_time_s,
     total_filament_g, filament: [{slot, type, color_hex, used_g, used_m}], plates: [...]}`.
2. **ImageSource.embedded + migration** — add `embedded` to the `ImageSource` enum
   (`models/image.py`). Alembic migration **0021** (current head is 0020): PG enum value add
   via `ALTER TYPE ... ADD VALUE 'embedded'`. **Gotcha:** `ADD VALUE` cannot run inside the
   alembic transaction — use the documented pattern (`op.execute("COMMIT")` first, or
   `with op.get_context().autocommit_block():`). Downgrade for an enum value-add is a no-op
   (document that in the migration).
3. **Wire 3MF into `analyze_item`** (`tasks/analysis.py` + `mesh_analysis.py`): for `.3mf`,
   call the reader. Populate `File.object_analysis` with the sliced fields and
   `est_method="sliced"` when sliced; fall back to the existing trimesh volume estimate for
   unsliced. Write the embedded thumbnail into the item dir (a dedicated subdir, e.g.
   `thumbs/embedded/<sha>.png`, **not** `renders/`) and create/reconcile an `Image` row with
   `source=ImageSource.embedded`, SHA-cached like renders. Embedded thumbnails are **excluded
   from the sidecar** (same rule as renders — regenerated from the portable 3MF on scan).
4. **Bound + cut the renderer** (`render_mesh.py`, `tasks/render.py`):
   - **Never render `.3mf`** — remove it from the renderable set.
   - Render only `.stl/.obj/.ply`, and only when the file is under caps
     `RENDER_MAX_FILE_MB` (default 50) and `RENDER_MAX_TRIANGLES` (default 1_000_000). Over
     cap → skip cleanly (log + no Image row), **not** an error.
   - **Thumbnail priority chain** in the default-image logic (`item_helpers.py` +
     `render.py` reconcile): user-default > curated (scraped/uploaded) > embedded > render.
     Only enqueue/use a render when no higher-priority image exists. Update `_enqueue_render`
     to skip 3MF always and skip STL/OBJ when a usable image already exists or the file is
     over cap.
5. **Collapse the render stack to VTK-only** (`render_mesh.py`, `render_subprocess.py`):
   remove the EGL/OSMesa/pyrender code paths, keep VTK offscreen. Drop `pyrender` and
   `PyOpenGL` from `backend/requirements.txt`; remove `libegl1`, `libgbm1`, `libosmesa6`
   (and any pyglet-only X libs no longer needed) from the `Dockerfile`. Keep `trimesh`,
   `vtk`, `lxml`, `Pillow`. **Note in your report:** image-build + render smoke test is a
   CI/Docker follow-up (not locally verifiable — consistent with prior render work).
6. **API surface** (`routers/items.py`, `config.py`): add `preview_3d: bool` to `FileOut`
   (true when extension ∈ {stl,obj,3mf} and `size` ≤ `BROWSER_PREVIEW_MAX_MB`, new config,
   default 50). Ensure `ImageOut.source` serializes `embedded`. Surface the new
   `object_analysis` sliced fields through `ItemDetail` as needed for the frontend.
7. **Config** (`config.py`): `RENDER_MAX_FILE_MB=50`, `RENDER_MAX_TRIANGLES=1_000_000`,
   `BROWSER_PREVIEW_MAX_MB=50`. Follow the existing settings pattern (env + DB-setting
   override where the others do).

## Conventions to honor

- **Changelog:** update `CHANGELOG.md [Unreleased]` in this same change (Changed: render
  policy/stack; Added: 3MF slice metadata + embedded thumbnails). Per project rule, docs +
  changelog ship in the commit with the code.
- **Verify before reporting** (see `startnewsession.md`): `ruff check backend/` (pinned 0.8.4
  + `backend/pyproject.toml`); write unit tests for `threemf.py` using a **small crafted
  fixture 3MF** (build a minimal sliced + unsliced `.3mf` zip in the test). Run pytest +
  `alembic upgrade head` on an ephemeral Postgres if available; **if no Postgres is
  reachable, say so explicitly** — the orchestrator will verify the migration on ephemeral PG
  (`postgres:16-alpine` on :5433). Worker has **no hot-reload** (n/a here, but don't assume a
  running worker picks up changes).
- Match existing module/style conventions; best-effort/never-crash on malformed input.

## When done

1. Set this file's frontmatter (`status`, `completed`, `result`), then `git mv` it into
   `prompts/done/` (success) or `prompts/failed/` (failure).
2. Record any non-obvious decisions in `docs/decisions.md`.
3. **You are a spawned agent: do NOT commit and do NOT push.** Prepare the working tree, run
   the verifications, and **report back**: the exact list of paths to stage, a one-line
   `feat:`/`fix:`/`chore:` conventional-commit message, and the verification results
   (including anything you could not verify locally). The orchestrating session auto-commits
   on `dev`. Never `git add -A`.
