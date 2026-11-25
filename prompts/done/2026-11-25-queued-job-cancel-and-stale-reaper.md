---
name: 2026-11-25-queued-job-cancel-and-stale-reaper
status: done
created: 2026-11-25
model: sonnet
completed: 2026-11-25
result: implemented; FE gates pass; backend pytest left to orchestrator
---

# Task: let admins cancel queued jobs, treat `superseded` as terminal in the Jobs UI, and auto-supersede stale queued rows

**Owner-reported:** orphaned `queued` `extract_archives` rows (bug fixed in v0.9.0 + migration 0027) could
not be removed from the Jobs page — a queued job has **no actions** at all. Also `superseded` rows (what 0027
produces) get no Archive/Delete and there's no `superseded` filter. Make stuck rows impossible to get wedged
on again.

## Before you start

- Read `CLAUDE.md`, `docs/architecture.md` (Jobs row + the `claim_or_create_job` gotcha),
  `backend/app/routers/jobs.py` (`cancel_job` ~L318 — only `running`; `_TERMINAL_STATUSES` includes
  `superseded`; `_ARCHIVABLE_STATUSES` excludes it; `delete_job`; `clear`), `backend/app/worker/job_tracker.py`
  (`claim_queued_job`, `claim_or_create_job`), `backend/app/services/item_helpers.py`
  (`_write_queued_row_and_enqueue` — self-assigned `arq_job_id`, `_defer_by`), `backend/app/worker/tasks/scheduled.py`
  (`_job_history_retention_core`), `backend/worker.py` (arq `allow_abort_jobs`? check), the arq pool helpers,
  `frontend/src/pages/admin/JobsPage.tsx` (`isTerminal`, `isRunning`, `STATUS_FILTERS`), its api client, and the
  existing job tests (`test_phase4_jobs.py`, `test_job_lifecycle.py`, `test_queued_visibility.py`, FE jobs tests).
- **No schema migration** (status is a string column). Don't run `make verify`/pytest — orchestrator does. Pinned
  ruff + `tsc -b --force && vite build && vitest run <your files> --no-file-parallelism` are fine. Don't edit
  `CHANGELOG.md`. Don't touch running containers.

## Working tree check

`git status --porcelain`; stop and report if a file you need is dirty.

## What to do

1. **Cancel queued jobs (backend).** `POST /api/jobs/{id}/cancel` accepts `queued` as well as `running`
   (409 for anything else, message updated). For queued: set `status='cancelled'`, `finished_at=now`, and
   best-effort abort the arq job by `arq_job_id` (same non-fatal pattern as running; arq can abort a deferred/queued
   job when `allow_abort_jobs` is on — verify the worker setting; if abort of not-yet-started jobs isn't supported,
   rely on step 2).
2. **Worker guard.** If the arq job still runs after its row was cancelled, it must NOT do the work or insert a
   fresh running row: make `claim_or_create_job` (or a small helper the four claiming tasks — render, analyze,
   scad_render, extract_archives — already call) detect "a row with this `arq_job_id` exists and is terminal" and
   signal skip (e.g. return `None` / raise a dedicated `JobAlreadyTerminal` the tasks catch and return early). Keep
   every existing caller's behavior for the normal paths; update the four tasks to honor the skip. Tests cover it.
3. **Superseded = terminal in the UI + archivable.** Add `superseded` to `_ARCHIVABLE_STATUSES` (single archive
   and `POST /api/jobs/clear?status=superseded`). Frontend: `isTerminal` includes `superseded` (Archive + Delete
   shown); add `superseded` to `STATUS_FILTERS`; show **Cancel** for `queued` rows (confirm dialog not needed —
   match the running Cancel button). If the "Clear failed"-style bulk clear UI lists statuses, include superseded.
4. **Stale-queued reaper.** In the daily `job_history_retention` cron (or a sibling step in the same task), first
   mark as `superseded` every Job with `status='queued'` and `created_at < now - STALE_QUEUED_JOB_HOURS` (new
   `config.py` setting, default **24**, documented in `.env.example` if other job settings are there), with
   `finished_at=now` and `error='stale queued row — never claimed by a worker; superseded by retention'`. Log the
   count. Then the existing retention deletes run as before (superseded rows age out after the failed window).
   Rationale to record: enqueue uses a small `_defer_by`; a genuinely queued job is claimed within seconds–minutes,
   so a day-old queued row is always an orphan.
5. **Tests:** cancel queued → cancelled + abort attempted; cancel succeeded → 409; worker skip when its row is
   already cancelled (one task is enough + unit test of the helper); superseded archivable (single + clear);
   reaper supersedes old queued rows only (fresh queued row untouched, running untouched); FE: Cancel shown for
   queued, Archive/Delete for superseded, superseded filter present.
6. Docs: `docs/architecture.md` Jobs gotcha line about the reaper + cancel-queued; `docs/decisions.md` entry.

## When done

1. Frontmatter; move this file (plain `mv`, untracked) to `prompts/done/` or `prompts/failed/`.
2. Do **not** commit. Report files changed, behavior summary, gate results, anything the orchestrator should check.
