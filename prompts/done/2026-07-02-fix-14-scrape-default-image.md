---
name: 2026-07-02-fix-14-scrape-default-image
status: completed
created: 2026-07-02
model: sonnet            # coding fix
completed: 2026-07-02
result: >
  Fixed. PATCH handler now syncs ImportSessionImage.is_default flags when
  default_image_path is set; commit handler has a defensive fallback. Three
  regression tests added to test_import_management.py. Commit-flow test
  confirmed to FAIL without the fix (order=0 instead of order=1). All three
  new tests pass. CHANGELOG [Unreleased] and docs/decisions.md updated.
---

# Task: Fix #14 — import-wizard "set default image" not applied (scrape + upload)

When a user picks a non-first image as the default in the Import Wizard's Images step,
the finalized item's default image is **not** the one they selected. Reported for
URL/scrape imports; the same code path affects uploads. This fixes the persistence gap so
the chosen default is honored on commit.

GitHub issue: **#14**.

## Before you start

- Read `startnewsession.md` (current state) and the operating-model / verify rules in
  `CLAUDE.md`. This is a `dev`-branch fix; conventional-commit prefix `fix:`.
- **Changelog is mandatory in the same commit** — add an entry under `[Unreleased]` in
  `CHANGELOG.md` (see memory "Changelog every commit").
- **Verify discipline:** backend = `ruff check backend/` (pinned ruff **0.8.4** +
  `backend/pyproject.toml` config — do NOT use an unpinned ruff) + pytest against an
  **ephemeral Postgres** (you have no DB; bring one up: `docker run -d --name pf3d-pg-v
  -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e
  POSTGRES_DB=partfolder3d -p 5433:5432 postgres:16-alpine`, then run `alembic upgrade
  head` first — see the test config for the exact DSN/env the suite expects). Frontend
  (only if you touch it) = `npm run build` (NOT `npx tsc --noEmit`) + `npx vitest run`.

## Working tree check

Run `git status --porcelain` and cross-reference the files below. `dev` should be clean
(== `main`). If any target file has uncommitted changes, list them and stop. Surface
unrelated dirty files once as awareness; don't block. This prompt file is exempt.

## Root cause (already investigated — confirm, then fix)

The chain that breaks (all in `backend/app/routers/import_sessions/sessions.py` unless
noted):

1. Frontend `frontend/src/pages/import-wizard/ImagesStep.tsx` sets the default via
   `patchImportSession(session.id, { default_image_path: path })` — this part is correct.
2. **The bug:** `patch_import_session` (line **384**, specifically **423–424**) stores
   `session.default_image_path = body.default_image_path` but does **NOT** update the
   corresponding `ImportSessionImage.is_default` flags.
3. `commit_import_session` (line **459**) builds the final `Image` rows from
   `si.is_default` (lines **662** and **682**) — it never consults
   `session.default_image_path`. So the user's choice is dropped.
4. Reference pattern that already does it right: `delete_import_session_image`
   (lines **870–891**) sets `first_remaining.is_default = True` **and**
   `session.default_image_path = ...` together. The item-side set-default handler in
   `backend/app/routers/items.py:909–936` is the same clear-all-then-set-one pattern.

## What to do

1. **Primary fix — sync `is_default` in the PATCH handler.** In `patch_import_session`,
   when `body.default_image_path is not None`, in addition to setting
   `session.default_image_path`:
   - Load the session's `ImportSessionImage` rows (they may not be loaded on `session`
     yet — query them, e.g. `select(ImportSessionImage).where(...session_id...)`).
   - Clear `is_default` on all of them, then set `is_default = True` on the single row
     whose `path` equals `body.default_image_path`.
   - Match the existing clear-all-then-set-one style (see the two references above). Do
     it before the final `db.flush()` / re-query so the returned `ImportSessionOut`
     reflects it.
   - **Edge case:** if no image row matches the given path (e.g. path set before images
     materialized), don't crash — leave `default_image_path` stored (commit-side fallback
     in step 2 will cover it). Consider logging at debug.

2. **Defensive fallback in the commit handler.** In `commit_import_session`, when
   building the final images, if **no** `ImportSessionImage` has `is_default=True` but
   `session.default_image_path` is set, treat the image whose `path ==
   session.default_image_path` as the default (and ensure exactly one final `Image` ends
   up `is_default=True`; if none match and images exist, fall back to the first/lowest-
   order as today). This makes the outcome correct even if PATCH ordering ever races with
   image materialization. Keep it minimal — don't rewrite the commit loop.

3. **Do NOT edit the frontend** unless verification shows the frontend is also wrong.
   The `patchImportSession` call is correct; this is a backend persistence bug. If you do
   find a genuine frontend issue, note it but prefer the backend fix.

## Tests (required)

Add/extend backend tests (see `backend/tests/test_import_management.py` and
`test_phase5_import.py` for existing import-session test patterns and fixtures):

- PATCH `default_image_path` to a **non-first** image → the matching
  `ImportSessionImage.is_default` becomes `True` and others `False`.
- Full commit flow: create session with ≥2 images (URL/scrape-style rows), PATCH the
  default to the 2nd, **commit**, then assert the created `Item`'s default `Image`
  (`is_default=True` / the item's `default_image`) is the one the user selected — not the
  first. This is the actual #14 regression guard; make it fail without your fix.
- (If cheap) a test for the commit-side fallback: images present, none flagged
  `is_default`, `default_image_path` set → commit picks the matching image.

## Conventions to honor

- Match surrounding async SQLAlchemy style in `sessions.py` (`select(...)`, `db.execute`,
  `db.flush`). No raw cascades.
- `fix:` commit prefix. Doc/changelog updates ship **in the same commit**.
- Record the root cause + the "sync is_default in PATCH + commit fallback" decision in
  `docs/decisions.md` (newest at top), referencing issue #14.

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. `git mv` this file to `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record the decision in `docs/decisions.md`.
4. **You are a spawned agent — do NOT commit.** Prepare the working tree and report back
   to the orchestrator: the exact file list + a one-line `fix:` commit message + your
   verification results (ruff output, pytest pass count on the ephemeral PG, the new
   test names, and confirmation the new commit-flow test fails without the fix). The
   orchestrator auto-commits on `dev`.
