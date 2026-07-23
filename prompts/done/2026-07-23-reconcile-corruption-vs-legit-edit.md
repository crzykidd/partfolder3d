---
name: 2026-07-23-reconcile-corruption-vs-legit-edit
status: done          # pending | in-progress | done | failed
created: 2026-07-23
model: sonnet            # coding
completed: 2026-07-23
result: >
  Unified integrity + re_render into one model-file classifier in
  worker/reconcile.py; added validate_model_file (render_mesh.py) and
  validate_3mf_structure (threemf.py); make verify-backend green, 919 passed.
---

# Task: Stop the reconcile scan from mislabeling legitimate in-place file edits as "corruption"

The owner's real workflow opens a model file (e.g. a 3MF) **in place** in a slicer and
saves an updated version back to the same path. Today that trips a **false `corruption`
issue at severity `critical`**, because `_behavior_integrity` flags *any* hash mismatch
as corruption with no regard for mtime — while `_behavior_re_render` treats the same hash
change as a legit "file updated → re-render." The two behaviors reach opposite conclusions
about the same change, and nothing ever adopts the new hash as the baseline, so the stale
`sha256` persists and the false alarm recurs.

Fix the classification: a hash mismatch is only **corruption** when it looks like
corruption (content changed **without** a legitimate write, or a write that produced an
unparseable file). A newer-mtime change that still parses is a **legitimate edit** —
adopt the new hash/mtime as the baseline and re-render, with **no** issue.

## Before you start

- Read `docs/architecture.md` (reconcile engine section + load-bearing gotchas) and
  `docs/decisions.md`. Read `CLAUDE.md` verify rules.
- The relevant code:
  - `backend/app/worker/reconcile.py` — `_behavior_integrity` (~line 603, raises the
    `corruption` `Issue`), `_behavior_re_render` (~line 489, detects mtime/size/hash drift
    and enqueues a render; note the cheap-first drift check at ~531–533 and the
    `_mtime_utc` / `hash_file_sha256` helpers it imports from `storage/inventory`).
  - `backend/app/models/issue.py` — `IssueType.corruption` ("file hash mismatch"),
    severities. **Do NOT add a new IssueType** — owner decision: reuse `corruption` for
    both silent bit-rot and unparseable-file cases.
  - `backend/app/worker/threemf.py` (zip open + `3D/3dmodel.model` parse — reuse for
    3MF validity) and `backend/app/worker/render_mesh.py` (`MESH_EXTENSIONS`, trimesh
    load — reuse for STL/other mesh validity).
  - `backend/app/config.py:147` — existing 3MF geometry-XML size cap (`ANALYZE_*` / 3MF
    limits) to respect when parsing for validation.
- **Verify discipline (`CLAUDE.md`): `make verify-backend` must pass** (ephemeral PG +
  pinned ruff 0.8.4 + alembic + `pytest -n auto`). **No migration is needed** — you are
  reusing existing columns (`sha256`, `last_seen_mtime`, `last_seen_size`, `mtime`) and
  the existing `corruption` IssueType. If you find yourself writing a migration, stop and
  reconsider.
- The dev **worker has no hot-reload** — irrelevant for the test gate, but if you
  live-test, `make worker-restart` after editing worker code.

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files this
plan touches. If any have uncommitted changes, list them and ask before touching. Surface
unrelated dirty files once; don't block. This prompt file is exempt.

## What to do

1. **Add a model-file validator.** A helper (e.g. `validate_model_file(path: Path) -> bool`
   or a small result carrying a reason) that returns whether a model/geometry file is
   structurally readable:
   - `.3mf` → opens as a zip (`zipfile.BadZipFile` ⇒ invalid) **and** its
     `3D/3dmodel.model` geometry part parses (reuse the threemf.py machinery; respect the
     geometry-size cap so a hostile/huge file can't OOM the worker).
   - Other `MESH_EXTENSIONS` (STL, OBJ, …) → trimesh loads it without raising (reuse the
     render_mesh path; keep it in the same subprocess-isolation spirit if that matters —
     match how analyze/render already sandbox trimesh).
   - Put it somewhere sensible (e.g. alongside the mesh/threemf helpers) and unit-test it
     against a valid fixture and a deliberately-truncated one.

2. **Unify the changed-file decision** so integrity and re_render no longer independently
   hash the same model files and disagree. For each model/geometry file whose current hash
   ≠ stored `sha256`, classify:
   - **Legitimate edit** — current mtime is newer than the stored baseline
     (`last_seen_mtime or mtime`) beyond the existing ~1s tolerance (mirror the drift
     check at ~531–533) **AND** `validate_model_file` passes →
     - **Adopt the new baseline** on the file row: update `sha256`, `last_seen_mtime`,
       `last_seen_size`, and `mtime` as appropriate.
     - Route the **re-render** through the existing re_render path, honoring
       `scan.re_render.mode` (auto → enqueue now + ChangeLog `render_enqueued`; review →
       queue the ReviewItem exactly as today).
     - Write a ChangeLog entry describing the adopted edit. **Do NOT create a corruption
       Issue.**
   - **Corruption (changed but unparseable)** — mtime newer but `validate_model_file`
     fails (truncated / incomplete / broken write) → raise the `corruption` `Issue`
     (critical). Make the `detail` distinguish this from silent bit-rot (e.g. "file
     changed but failed to parse — possible incomplete/interrupted write").
   - **Corruption (silent bit-rot)** — hash changed but mtime **not** newer (unchanged or
     older) → raise the `corruption` `Issue` as today.
   - **No change** — hash equal → nothing.
   Keep the `_issue_exists` dedup so a persisting condition doesn't pile up duplicate rows.

3. **Make sure the baseline actually advances** so a validated edit does not re-fire the
   corruption check or redundantly re-render on the next scan. This is the core of the
   bug — verify it with a test that runs the reconcile twice.

4. **Tests** (`backend/app/tests/…`, match existing reconcile test style). Cover at least:
   (a) newer mtime + valid file → hash/mtime adopted, **no** corruption issue, render
   enqueued (per mode); re-running the scan is a no-op. (b) newer mtime + unparseable
   file → corruption issue with the "failed to parse" detail. (c) hash changed + mtime
   unchanged → corruption issue (bit-rot). (d) no change → nothing. Include the validator
   unit tests from step 1.

5. **Changelog:** add a `### Fixed` (and/or `### Changed`) entry under `[Unreleased]` in
   `CHANGELOG.md`, in the SAME commit, describing that in-place model edits are no longer
   mis-flagged as corruption and that the integrity check now validates the file and only
   reports corruption for unchanged-mtime drift or unparseable writes.

## Conventions to honor

- Map, don't copy: reuse threemf.py / render_mesh helpers rather than re-implementing 3MF
  or mesh parsing.
- Backend tests **require `pytest -n auto`** (the verify script handles this). Lint with
  the pinned ruff 0.8.4 via the verify script — do not run an unpinned ruff.
- No `Co-authored-by:` trailers. Conventional-commit `fix:` (or `feat:`/`refactor:` if you
  judge it better) prefix.

## When done

1. Update this file's frontmatter: `status`, `completed` (2026-07-23), `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record non-obvious decisions (e.g. how you unified integrity vs re_render, where the
   validator lives, the mtime tolerance) in `docs/decisions.md`, newest at top.
4. **You are a spawned agent: do NOT commit.** Run `make verify-backend`, confirm it's
   green (report the test count), prepare the working tree, and report back to the
   orchestrator the exact file list + a proposed one-line `fix:`-prefixed commit message.
   Never `git add -A`, never push, never auto-commit.
