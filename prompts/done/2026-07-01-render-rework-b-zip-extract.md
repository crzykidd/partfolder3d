---
name: 2026-07-01-render-rework-b-zip-extract
status: done
created: 2026-07-01
model: sonnet
completed: 2026-07-01
result: >
  All deliverables implemented and verified. New files: backend/app/storage/archive.py
  (safe extractor with zip-slip, junk filter, caps, lone-wrapper strip, collision rename),
  backend/app/worker/tasks/archive.py (extract_archives worker task),
  backend/tests/test_archive.py (22 pure-Python unit tests, all pass). Modified:
  backend/app/config.py (ZIP_MAX_UNCOMPRESSED_MB, ZIP_MAX_FILES), backend/app/services/
  item_helpers.py (_enqueue_extract_archives), backend/worker.py (extract_archives in
  functions list), backend/app/routers/import_sessions/sessions.py (enqueue on commit),
  CHANGELOG.md (Added entry), docs/decisions.md (Phase B impl details).
  Verification: ruff clean, 22/22 archive unit tests pass, 582/582 full suite pass
  (17:59), alembic at head (no new migration needed).
---

# Task: Backend — auto-extract uploaded/imported ZIPs into the item directory

Today ZIPs are stored as an opaque blob. Extract them into the item dir preserving internal
folder structure, so their contents become first-class files (browsable, downloadable, and
thumbnailed/analyzed like any other file). Phase B of the four-phase rework; assumes Phase A
is committed on `dev`.

## Before you start

- Read `docs/decisions.md` top entry (**2026-07-01 — Asset-detail / 3D-preview rework**) for
  the locked extraction rules, and `prompts/startnewsession.md` for verify discipline.
- Relevant code (verify current state):
  - `backend/app/routers/import_sessions/sessions.py` — file upload + commit (files are moved
    into the item dir as-is around the commit phase).
  - `backend/app/storage/inventory.py` — file discovery + role inference (rescan picks up
    on-disk files).
  - `backend/app/storage/paths.py` — item dir layout.
  - `backend/app/worker/worker.py` — arq task registry; `services/item_helpers.py` — enqueue
    helpers (`_enqueue_analyze`, `_enqueue_render`).
- **Do NOT** touch the renderer, 3MF reader (Phase A), or the frontend.

## Working tree check

`git status --porcelain`; cross-reference the files below; ask before touching anything
already dirty. Sibling prompts C/D untracked is expected.

## What to do

1. **Safe extractor** — new `backend/app/storage/archive.py`:
   - `extract_zip(zip_path, dest_dir, *, existing_paths) -> ExtractResult`.
   - **Reject zip-slip**: resolve each entry against `dest_dir`; skip/abort any entry that
     escapes (`..`, absolute paths, drive letters).
   - **Skip junk**: `__MACOSX/`, `.DS_Store`, `Thumbs.db`, `desktop.ini`.
   - **Do not recurse** into nested archives — a nested `.zip` is extracted as a plain file.
   - **Caps** (new config): `ZIP_MAX_UNCOMPRESSED_MB` (default 2048), `ZIP_MAX_FILES`
     (default 10000), and a per-entry sanity cap. Also guard the compression ratio (zip-bomb)
     — bail if uncompressed/compressed exceeds a sane multiple. Over cap → fail cleanly with a
     clear error (don't partially litter the item dir; clean up on failure).
   - **Strip a lone top-level wrapper folder**: if every entry shares one top-level dir,
     drop that prefix so contents land at the item root.
   - **Rename on collision** against `existing_paths` (and within the archive): `name.ext` →
     `name (1).ext`, `name (2).ext`, … Never overwrite.
   - Preserve all other internal folder structure verbatim.
2. **Extraction task** — `extract_archives(ctx, item_id)` (in `worker/tasks/`), registered in
   `worker.py`'s `functions` list. For each `role=zip` file in the item: extract, then on
   success **discard the original `.zip`** (whole-item ZIP is reconstructable via
   `build_zip_bundle`). Then trigger an inventory rescan and enqueue `analyze_item` +
   `render_item` so extracted STL/OBJ/3MF get metadata/thumbnails.
3. **Enqueue on commit**: in the import-session commit path, after files are moved into the
   item dir, enqueue `extract_archives(item_id)` when the item contains any zip. Keep it
   best-effort — a bad archive must not fail the whole import (record an error, leave the zip
   in place).

## Conventions to honor

- **Changelog:** `CHANGELOG.md [Unreleased]` (Added: ZIP auto-extraction) in this same change.
- **Verify:** `ruff check backend/`; unit-test `archive.py` thoroughly with crafted in-memory
  zips — structure preserved, lone-wrapper stripped, collision-renamed, zip-slip rejected,
  junk skipped, caps enforced, nested zip left as a file. These are pure-Python (no DB). Run
  the full pytest + `alembic upgrade head` on ephemeral PG if available; if not, say so.
- Never-crash / best-effort on malformed archives.

## When done

1. Frontmatter (`status`/`completed`/`result`), then `git mv` into `prompts/done/` or
   `prompts/failed/`.
2. Record non-obvious decisions in `docs/decisions.md`.
3. **Spawned agent: do NOT commit/push.** Prepare the tree, verify, and report back the paths
   to stage, a one-line conventional-commit message, and verification results (flag anything
   unverifiable locally). Orchestrator auto-commits on `dev`. Never `git add -A`.
