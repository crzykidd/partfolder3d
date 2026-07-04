---
name: job-visibility-20-30
status: done
created: 2026-07-04
model: Sonnet
completed: 2026-07-04
result: >
  Queued Job rows are now written at enqueue time (status=queued) and the worker
  claims them (→running) via claim_or_create_job instead of duplicating; analyze_item
  wired into the same lifecycle (#30). Race handled with a short _defer_by on the
  enqueue plus an atomic queued→running UPDATE...RETURNING claim keyed on a
  self-assigned arq _job_id (the queued row FKs the not-yet-committed item, so it
  can't be pre-committed). No migration (columns already existed). Ruff clean; full
  suite 730 passed. No frontend change needed (queued already rendered). 10 new tests
  in tests/test_queued_visibility.py.
---

# Make queued + analyze jobs visible (closes #20, closes #30)

## Goal

Two related job-visibility gaps:

- **#20** — Queued worker jobs are invisible until a worker starts them. Jobs are enqueued to
  arq/Redis but no `Job` DB row exists until the worker *starts* the task, so a backlog of
  queued work (e.g. after a bulk import) shows nothing in the jobs UI.
- **#30** — `analyze_item` creates no `Job` row at all (only `render` and `extract_archives`
  do), so mesh-analysis work is invisible even while running — invisible CPU/RAM.

Fix both by writing a `Job` row at **enqueue** time (status `queued`) and having the worker
**claim** that row (→ `running`) instead of inserting a new one, and by wiring `analyze` into
the same job-tracker lifecycle.

## What's already in place (verified — do NOT re-derive)

- **No migration needed.** `backend/app/models/job.py` `Job` already has `status`
  (default `"queued"`; flow `queued → running → succeeded|failed|cancelled|superseded`) and an
  `arq_job_id` column. Use them.
- **Read side already tolerates `queued`.** `backend/app/routers/items/core.py` (the item jobs
  endpoint) and `backend/app/routers/jobs.py` filter on `status in ("queued","running")` — they
  will surface queued rows the moment we write them. Confirm this and do not regress it.
- **`job_tracker.create_job`** (`backend/app/worker/job_tracker.py`) currently inserts a row in
  status `"running"` with `arq_job_id=ctx.get("job_id")`. `finish_job` marks terminal states.
- **The enqueue helpers** (`backend/app/services/item_helpers.py`): `_enqueue_render`,
  `_enqueue_analyze`, `_enqueue_extract_archives` currently only call
  `pool.enqueue_job(<task>, item_id)` — **none take a `db` session**, so they can't write a row.
- **Worker tasks**: `tasks/render.py` and `tasks/archive.py` call `create_job`/`finish_job`;
  `tasks/analysis.py` (`analyze_item` / `_analyze_item_inner`) calls **neither** (that's #30).

## Required changes

1. **Write a `queued` Job row at enqueue.** Thread a `db: AsyncSession` into the three
   `_enqueue_*` helpers (and update every call site — grep `_enqueue_render` / `_enqueue_analyze`
   / `_enqueue_extract_archives`: routers/items/*, import_sessions/commit.py, worker/reconcile.py,
   worker/tasks/*). In each helper, after deciding to enqueue, create a `Job(type=..., status="queued",
   item_id=..., arq_job_id=<the enqueued job id>)`. Keep the existing "off"/all-3mf short-circuits
   (no row when we don't enqueue). Keep it fire-and-forget: a failure to write the row or enqueue
   must still never block item creation/rescan (log, don't raise).

2. **Worker claims the queued row instead of duplicating it.** Change `create_job` (or add a
   `claim_or_create_job`) so that when the task starts it looks up the existing `queued` row by
   `arq_job_id == ctx["job_id"]` and transitions it to `running` (set `started_at`, keep the same
   row id); only if none is found does it INSERT a running row (backward-compat for retries /
   scheduled / directly-enqueued jobs). Callers in render.py / archive.py keep working unchanged.

3. **Wire `analyze_item` into the tracker (#30).** Give `analyze_item` the same lifecycle as
   render/archive: claim-or-create a `Job(type="analyze")` at start, `finish_job` on
   success/failure, with the same guarded/try-finally shape the other tasks use. And
   `_enqueue_analyze` writes the queued row (task type `"analyze"`).

4. **RACE — handle it explicitly and document your choice.** The worker could pop the arq job
   *before* the caller's transaction that created the queued row commits, so `create_job` wouldn't
   find it and would insert a running row → a later commit of the queued row leaves a duplicate.
   Pick a race-safe, **migration-free** approach and write down why in the code + your report.
   Acceptable options (your call): (a) claim-or-create keyed on `arq_job_id` with an
   idempotency guard so at most one row per `arq_job_id` survives; (b) control the id via arq's
   `_job_id` and create+commit the queued row before `enqueue_job`; (c) a small `_defer_by` on
   these background jobs so the row is committed first. Do NOT prematurely commit a caller's
   open transaction, and do NOT add a DB migration. If a queued row can be orphaned (caller rolls
   back), the worker must fail that job gracefully (item missing → finish failed), not crash.

5. Use `closes #20` and `closes #30` in the CHANGELOG entry / eventual PR body. Add a
   `[Unreleased] ### Fixed` (or `### Changed`) CHANGELOG bullet describing the new
   queued-visibility + analyze-job-row behavior.

## Verify (ephemeral PG on :5433 — `pf3d-pg-v` is up; DATABASE_URL must point at it, DEBUG unset is fine since password is `testpass`)

- Pinned `backend/.venv/bin/ruff check backend/` clean.
- New/updated tests (put in the job-lifecycle / analyze test files): a `queued` row exists after
  enqueue and BEFORE any worker runs; the worker transitions it `queued → running` with **no
  duplicate** row for the same `arq_job_id`; `analyze_item` now creates and finishes a `Job` row;
  the item-jobs + jobs endpoints return queued rows. Cover the race path if feasible.
- `backend/.venv/bin/python -m pytest -n auto` @ :5433 — full suite green (was 720). The
  frontend already renders queued/running via the existing polling; check whether any frontend
  jobs view needs a label for `queued` (if the status is already handled, no FE change needed —
  report either way).

## Reporting

Prepare the working tree (do NOT git-commit). Report: files changed; the race approach you chose
+ why; whether any frontend change was needed; whether a queued Job needs a "cancel while queued"
path (note if out of scope); ruff + full-suite results; the proposed CHANGELOG bullet (with
`closes #20` `closes #30`) and commit message. Set this prompt's frontmatter
(`status: done`, `completed:`, `result:`) and `git mv` it to `prompts/done/` as part of the tree
you prepare.
