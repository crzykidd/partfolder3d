---
name: 2026-07-25-server-side-scad-render
status: done          # pending | in-progress | done | failed
created: 2026-07-25
model: sonnet             # coding task
completed: 2026-07-25
result: >
  Implemented. .scad -> STL compile in an isolated asyncio subprocess
  (RLIMIT_AS/RLIMIT_CPU + wall-clock timeout + scratch workdir), reusing the
  existing render/analyze/viewer pipeline unchanged. Migration 0026 adds
  generated_from_file_id/generated_source_sha256 to files. Enqueued at
  import-commit and direct .scad upload when the item has no other model
  file yet; SCAD_RENDER_ENABLED default True. openscad added to the
  Dockerfile deps stage (~370 MB measured, Qt5 is a hard Depends). Tests in
  backend/tests/test_scad_render.py, real-binary test skip-gated. No
  frontend changes this cut (no manual "render preview" UI action — flagged
  as a deferred judgement call). Backend-only; orchestrator runs the full
  verify gate.
---

# Task: Optional server-side OpenSCAD (.scad) render/preview (closes #46)

Optionally compile a self-designed item's `.scad` **source** file server-side into an
STL mesh, then feed that derived STL through the **existing** render/analyze/viewer
pipeline so the item gets an in-app thumbnail + 3D viewer + mesh stats — without the user
bringing their own STL. This is the deferred companion to the v0.7.5 read-only `.scad`
viewer.

## Before you start

- **Read `prompts/startnewsession.md`, `CLAUDE.md`, and `docs/architecture.md`** (module
  map + gotchas). Read the v0.7.5 `.scad` viewer entries in `CHANGELOG.md` /
  `docs/decisions.md` and the code it added: `FileRole.source` in
  `backend/app/models/file.py`, `backend/app/storage/inventory.py` `infer_role`,
  `backend/app/storage/scad_meta.py`.
- **Study the existing subprocess-isolation pattern** — this is the model to copy:
  `backend/app/worker/render_subprocess.py` and `analyze_subprocess.py` (wall-clock
  timeout + `RLIMIT_AS`/`RLIMIT_CPU` + temp workdir), driven from `render_mesh.py` /
  `mesh_analysis.py`. `.scad` is a Turing-complete language (can loop, allocate, and read
  files via `import()`/`include()`) so the compile MUST run in an isolated subprocess with
  a wall-clock timeout, memory/CPU rlimits, and a scratch workdir — same rigor as
  analyze/render.
- **The worker has NO hot-reload.** After any worker/task edit, `make worker-restart`.
  Also: adding the `openscad` binary changes the image — the live `:dev` stack won't have
  it until the image rebuilds; guard tests so they **skip when `openscad` is absent** (or
  mock the subprocess) rather than hard-failing CI/local verify.
- **DO NOT run the full `make verify` / backend `pytest` gate.** The orchestrator runs
  the authoritative gate itself (the shared ephemeral test PG `pf3d-pg-v` on :5433 is a
  single instance — a second concurrent pytest run corrupts it). Your local checks are
  limited to fast, DB-free ones: **`ruff` (pinned 0.8.4 + `backend/pyproject.toml`) on the
  files you changed**, and if you touch the frontend, `tsc`/`npm run build`. Write the
  tests, reason about them, but leave running the suite to the orchestrator. **Never
  background a long check and exit** — it gets relaunched on re-invocation and collides.
- **Next migration number: `0026`** (the orchestrator confirms/overrides this at dispatch;
  do not assume another). You will likely need one to mark a File as **generated/derived
  from** its `.scad` source (see step 4).
- Config knobs go in `backend/app/config.py` next to the existing `RENDER_*` / `ANALYZE_*`
  knobs and mirror their naming/defaults conventions.

## Working tree check

Run `git status --porcelain` and cross-reference the files below. If any have
uncommitted changes, list them and ask before touching. Surface unrelated dirty files
once; they don't block. This prompt file is exempt.

## What to do

1. **Add the `openscad` binary to the worker image** (`./Dockerfile`, the `deps` stage's
   `apt-get install` — this is the shared backend+worker image; the worker overrides CMD).
   STL export (`openscad -o out.stl in.scad`) needs **no** GL/xvfb (unlike PNG export), so
   avoid pulling GL/Qt display deps where possible. Note the image-size cost in your
   report; if `--no-install-recommends` bloats badly, note the tradeoff (a headless/
   Manifold build is a possible future optimization — out of scope now).
2. **New worker compile step:** `.scad` → `.stl`, run in an **isolated subprocess** with a
   wall-clock timeout + `RLIMIT_AS` + `RLIMIT_CPU` + a temp scratch workdir, cloning the
   `render_subprocess`/`analyze_subprocess` pattern. Compile **only the files uploaded
   together**; on any failure (missing `include`/`use`, BOSL2/library not present, timeout,
   OOM, non-zero exit) **fall back to "store source, skip preview"** — do NOT crash the
   worker and do NOT spam Issues for an expected compile failure (log it; decide whether a
   soft, non-drift note is warranted — flag this call in your report).
3. **Reuse the existing pipeline** for the derived STL: run it through the current render
   (VTK thumbnail), analyze (mesh stats), and browser-viewer paths. **Write no new preview
   code** — the whole point is that the derived STL is just another mesh asset the existing
   machinery already handles.
4. **Record the derived STL as a generated asset** clearly linked to its `.scad` source
   (e.g. a `generated_from_file_id`/`generated` marker on the File — you design the exact
   shape; migration `0026`). **Reconcile must treat the derived STL as generated** and NOT
   flag it as drift/corruption or as an unexpected on-disk file — check
   `backend/app/worker/reconcile.py` and make it aware. Decide where the derived STL is
   written on disk and whether it belongs in the sidecar (a regenerable artifact usually
   should be excluded from drift tracking — justify your choice).
5. **When is the compile enqueued?** At minimum, on import/commit of an item whose only
   printable is a `.scad` source with no existing mesh asset. Consider also a manual
   "Render preview" action on the item page. Wire the enqueue where import currently
   enqueues render/analyze (`backend/app/worker/tasks/`, `import_session.py` /
   `render.py` / `analysis.py`). Flag the enqueue-trigger + any UI affordance as a
   judgement call in your report; keep the first cut minimal.
6. **Config knobs** in `config.py`: enable/disable (default off or on — recommend and
   justify), max compile wall-clock seconds, max memory. Respect them in the subprocess.
7. **Tests:** the compile-step wrapper (mock/skip the binary), the fallback-on-failure
   path, the generated-asset linkage, and a **reconcile test proving the derived STL is
   NOT flagged as drift**. Follow existing worker-test patterns. Gate any test that needs
   the real `openscad` binary behind a skip-if-absent guard.

## Out of scope (first cut) — note as deferrals

- `include`/`use` of external libraries (BOSL2 etc.) — compile-what's-uploaded only.
- Customizer parameters (compile uses defaults).
- Refreshing an embedded slicer thumbnail; in-app `.scad` editing (pairs with #47).

## Conventions to honor

- Conventional-commit `feat:` prefix; **no `Co-authored-by:` trailer**.
- **Update `CHANGELOG.md` `[Unreleased]` in the SAME change.**
- Doc updates ship with the code: update `docs/architecture.md` (module map row + any new
  gotcha about the openscad subprocess isolation / image dep) and add a decisions entry.

## When done

1. Set this file's frontmatter: `status: done` (or `failed`), `completed: 2026-07-25`,
   `result:` one line.
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record non-obvious decisions (generated-asset shape, reconcile handling, enqueue
   trigger, default-on/off, image-dep tradeoff) in `docs/decisions.md`, newest at top.
4. **You are a spawned agent: do NOT commit, do NOT push, and do NOT run the full test
   gate.** Run only the fast DB-free checks (ruff on changed files; tsc/build if frontend
   touched), prepare the working tree, move the prompt, and **report back** to the
   orchestrator: exact file list, a proposed one-line `feat:` message including
   `closes #46`, the ruff/tsc result, the migration number used, the default
   enable/disable + enqueue-trigger decisions, the image-size impact, whether any tests
   require the real `openscad` binary (and how they're guarded to skip when it's absent),
   and what the owner must do to exercise it live (rebuild the dev worker image, `make
   worker-restart`, which item to test). **The orchestrator runs the authoritative
   `make verify`, then commits + pushes on `dev`.**
