---
name: 2026-11-25-fix-extract-archives-orphan-queued
status: done
created: 2026-11-25
model: sonnet
completed: 2026-11-25
result: archive.py now claim_or_create_job; migration 0027; tests added; docs updated
---

# Task: fix `extract_archives` leaving an orphaned `queued` Job row forever (+ clean up existing ones)

**Owner-reported:** after importing items with ZIPs, extraction clearly ran, but an `extract_archives`
job stays **queued** forever in the Jobs page.

**Root cause (diagnosed by the orchestrator, verify it):** `_enqueue_extract_archives`
(`backend/app/services/item_helpers.py`) goes through `_write_queued_row_and_enqueue`, which writes a
`queued` Job row keyed on a self-assigned `arq_job_id`, and the worker is supposed to **claim** that row
(`claim_or_create_job` in `backend/app/worker/job_tracker.py`). `render.py`, `analysis.py` and
`scad_render.py` do; `backend/app/worker/tasks/archive.py::extract_archives` instead calls
**`create_job`**, which INSERTs a second (running→succeeded) row and never touches the queued one. The
worker startup recovery (`backend/worker.py` `_recover_orphaned_jobs`) intentionally skips `queued` rows,
so they never clear. Signatures of `create_job` and `claim_or_create_job` are identical.

## Before you start

- Read `CLAUDE.md`, `docs/architecture.md` (Jobs + gotchas), `backend/app/worker/job_tracker.py`,
  `backend/app/worker/tasks/archive.py`, `backend/app/services/item_helpers.py`
  (`_write_queued_row_and_enqueue`), `backend/worker.py` (`_recover_orphaned_jobs` docstring ~L161 — it
  claims "no code path writes [queued rows] today", which is stale since #20/#30; correct the comment only),
  `backend/app/models/job.py`, an existing data migration in `backend/alembic/versions/` for style, and the
  tests `test_archive.py`, `test_job_lifecycle.py`.
- **Migration number is `0027`** (latest is `0026_scad_generated_asset.py`). Name it
  `0027_supersede_orphaned_extract_archives_jobs.py`.
- **Do NOT run `make verify` / pytest** — the orchestrator runs the gate. Run pinned ruff only
  (`backend/.venv/bin/ruff check backend`). Don't edit `CHANGELOG.md`. Don't touch running containers.

## Working tree check

`git status --porcelain`; stop and report if a file you need is dirty.

## What to do

1. **Fix:** in `archive.py`, use `claim_or_create_job` instead of `create_job` (same args). Grep the rest of
   `backend/app/worker/tasks/` for any other task that is enqueued via `_write_queued_row_and_enqueue` but
   still calls `create_job`, and fix those too (orchestrator found only this one).
2. **Data migration `0027`** (upgrade only does data; downgrade is a no-op with a comment): mark as
   `superseded` every Job row with `type='extract_archives' AND status='queued'` for which a **later**
   `extract_archives` row exists for the same `item_id` (`created_at` greater) — those are provably
   orphaned by this bug. Set `finished_at` = now (if that column exists) and an `error`/note such as
   `"orphaned queued row (extract_archives claim bug) — superseded by migration 0027"`. Do NOT touch rows
   with no later sibling (could be genuinely pending). Use plain SQL via `op.execute` / `sa.text`; check
   actual column names in the model. Idempotent.
3. **Tests** (follow existing fixture style; new file `backend/tests/test_extract_archives_job_claim.py`
   or extend `test_archive.py`):
   - enqueue via `_write_queued_row_and_enqueue(..., task="extract_archives", job_type="extract_archives")`
     with a db, then run `extract_archives` with `ctx={"job_id": <that arq id>}` on an item with a zip →
     exactly ONE Job row for that item/type, status `succeeded`, same row id as the queued one.
   - item with no zips → the queued row is claimed and finished `succeeded` (no lingering queued row).
   - the migration's SQL logic: if there's an established way to test data migrations in this repo, use it;
     otherwise factor the UPDATE statement into a constant in the migration module and test it against the
     test DB directly (insert a queued+later succeeded pair, a lone queued row → only the paired one flips).
4. Fix the stale `_recover_orphaned_jobs` docstring comment.
5. `docs/decisions.md` entry (newest at top); `docs/architecture.md` gotcha one-liner: "every task enqueued
   via `_write_queued_row_and_enqueue` MUST use `claim_or_create_job`, not `create_job`, or its queued row is
   orphaned".

## When done

1. Frontmatter; move this file (plain `mv`, untracked) to `prompts/done/` or `prompts/failed/`.
2. Do **not** commit. Report files changed, the migration's exact SQL, and gate notes.
