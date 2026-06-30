---
name: 2026-06-30-job-lifecycle-backend
status: completed
created: 2026-06-30
model: sonnet            # backend — migration + endpoints + cron
completed: 2026-06-30
result: >
  Migration 0019 (arq_job_id, retry_of_job_id FK, archived_at) + Job model updated.
  finish_job terminal guard; _supersede_ancestors chain on success.
  cancel/restart/archive/delete/clear-succeeded endpoints; allow_abort_jobs=True.
  job_history_retention cron (config + scheduled.py + worker.py).
  31 tests pass (test_job_lifecycle.py × 17 + test_phase4_jobs.py × 14).
  Alembic round-trip clean; ruff clean.
---

# Task: Job lifecycle backend — cancel/restart, retry-supersede, clear/archive, retention

Add full lifecycle management to the background-job system (backend only; the monitor UI
is a separate follow-up). Today `jobs` rows are render-only, created by the task itself,
never cancellable, retries are unlinked, and the table grows unbounded. This task adds:
cancel + restart of running jobs, retry that supersedes the old failed job once it
succeeds, clear/archive + an archive list, and a daily retention prune.

## Before you start

- Read `prompts/startnewsession.md` and `CLAUDE.md`. You are a spawned agent on `dev`:
  **do NOT commit, do NOT push** — prepare the tree and report back.
- Read these fully (the whole surface):
  - `backend/app/models/job.py` — the `Job` model. `status` is a free `String(16)`
    (today: queued/running/succeeded/failed); fields include `payload` (JSONB, holds
    `{"item_id": N}`), `item_id`, `created_at`, `started_at`, `finished_at`.
  - `backend/app/worker/job_tracker.py` — `create_job` (inserts row already in `running`),
    `finish_job` (the ONLY place a row leaves `running`), `update_job_progress`.
  - `backend/app/worker/tasks/render.py` — `render_item(ctx, item_id)`. It calls
    `create_job(...)` at the top (NOTE: this file was just hardened — keep its subprocess/
    timeout/`_job_finalized`/BaseException structure intact; only add what this task needs).
  - `backend/app/routers/jobs.py` — `list_jobs`, `get_job`, `retry_job` (failed+render
    only; `_enqueue_args_for` maps render→("render_item",[item_id])), `_VALID_STATUSES`.
  - `backend/worker.py` — `WorkerSettings` (`max_jobs=10`, `job_timeout=600`; does NOT set
    `allow_abort_jobs`), `SCHEDULED_JOB_REGISTRY`, `_SCHED_FUNCS`, cron_jobs, `startup()`.
  - `backend/app/worker/tasks/scheduled.py` — the scheduled-task impls + registry wiring
    (e.g. `expired_zip_cleanup`); mirror this pattern for the new retention task.
  - `backend/app/config.py` — `Settings`.
  - An existing alembic migration (e.g. `backend/alembic/versions/0018_*.py`) for the
    house style; the latest head is **0018**.

## Working tree check

`git status --porcelain` first. Expect a clean `dev` at commit `3a17711` or later. If any
file you need has unrelated uncommitted changes, list them and ask.

## What to do

### 1. Migration 0019 (single new migration; head is 0018)
Add to `jobs`:
- `arq_job_id VARCHAR(64) NULL` (indexed) — the arq job id, so a running job can be aborted.
- `retry_of_job_id UUID NULL` — FK → `jobs.id` `ON DELETE SET NULL` (indexed) — links a
  retry/restart to the job it replaces.
- `archived_at TIMESTAMPTZ NULL` (indexed) — set when a job is cleared/archived.
Provide a correct `downgrade()` (drop columns + indexes + FK). Verify up/down/up on ephemeral PG.
Update the `Job` model in `job.py` to match.

### 2. Status vocabulary
`status` stays a free string. Introduce two new terminal values: **`cancelled`** and
**`superseded`**. Update `_VALID_STATUSES` in `jobs.py` to
`{queued, running, succeeded, failed, cancelled, superseded}`. Define a small
`_TERMINAL_STATUSES = {succeeded, failed, cancelled, superseded}` helper where useful.

### 3. Capture the arq job id + make finish_job terminal-safe
- `create_job(...)`: accept an optional `arq_job_id: str | None` and persist it. In
  `render_item`, pass `ctx.get("job_id")` (arq sets this in the task context).
- `finish_job(...)`: **become a no-op if the row is already in a terminal status.** This is
  critical: when a user cancels a running render, the cancel endpoint sets status
  `cancelled`; the aborted task's `BaseException`/finalizer path will then call
  `finish_job(failed)` — it must NOT clobber `cancelled`. (Re-read the current status inside
  finish_job and return early if terminal.)

### 4. Enable abort + Cancel/Restart endpoints
- `WorkerSettings`: set **`allow_abort_jobs=True`** (without it, arq aborts are inert).
- `POST /api/jobs/{job_id}/cancel` (admin + CSRF): only `status == "running"` (else 409).
  Best-effort abort the arq job: if `arq_job_id` is set, build an arq `Job(arq_job_id,
  redis=<pool>)` and call `.abort()` (wrap in try/except — a failed abort must not block the
  status update). Set `status="cancelled"`, `finished_at=now`. Return the updated job.
  (Aborting cancels the coroutine → its `run_render_subprocess` `finally` kills the child
  process, and finish_job is now a no-op against the cancelled row — verify this reasoning.)
- `POST /api/jobs/{job_id}/restart` (admin + CSRF): allowed for any status. If currently
  `running`, do the cancel/abort first. Then re-enqueue the work linked to this job (see §5).
  Return 202.

### 5. Retry/Restart link + supersede-on-success
- `render_item` gains an optional `retry_of_job_id` (UUID/str) kwarg, threaded into
  `create_job` so the NEW row records `retry_of_job_id`. Retry/restart enqueue with it:
  `redis.enqueue_job("render_item", item_id, retry_of_job_id=<old_id>)`.
- Relax `retry_job` (`POST /api/jobs/{id}/retry`) to set the linkage; keep its existing
  guards (render-type only via `_enqueue_args_for`; item_id present). Restart reuses the same
  enqueue path.
- **Supersede on success:** when a job transitions to `succeeded` and it has a
  `retry_of_job_id`, walk the `retry_of_job_id` ancestor chain and set each ancestor's
  `status="superseded"`. Do this in `finish_job` (or a helper it calls) so it happens
  wherever a render succeeds. Net effect: a failed job whose retry later succeeds disappears
  from the default list. Guard against cycles (defensive max-depth).

### 6. Clear / archive + list filtering
- `POST /api/jobs/clear-succeeded` (admin + CSRF): set `archived_at=now` on all
  non-archived `succeeded` jobs. Return `{archived: <count>}`.
- `POST /api/jobs/{id}/archive` (admin + CSRF): set `archived_at=now` on one terminal job.
- `DELETE /api/jobs/{id}` (admin + CSRF): hard-delete one job row (204).
- `GET /api/jobs`: by **default exclude** `archived_at IS NOT NULL` AND exclude
  `status == "superseded"`. Add query params: `archived: bool=False` (when true, return ONLY
  archived rows — the archive list), and `include_superseded: bool=False`. Keep existing
  `status`/`type`/`page`/`per_page`. Update the response/schemas to include the new fields
  (`arq_job_id` may stay internal; DO expose `retry_of_job_id` and `archived_at`).

### 7. Retention cron
- Config (`config.py`): `JOB_RETENTION_SUCCEEDED_DAYS: int = 7`,
  `JOB_RETENTION_FAILED_DAYS: int = 30` (applies to failed/cancelled/superseded). Document in
  `.env.example`.
- New scheduled task `job_history_retention` (impl in `scheduled.py`, mirror
  `expired_zip_cleanup`): hard-delete jobs where
  `(status=succeeded AND finished_at < now - SUCCEEDED_DAYS)` OR
  `(status in {failed,cancelled,superseded} AND finished_at < now - FAILED_DAYS)`. Log the
  delete count. Wire into `SCHEDULED_JOB_REGISTRY` (human schedule "daily"), `_SCHED_FUNCS`,
  and `WorkerSettings.cron_jobs` (run once a day, e.g. 04:00). It must also create/finish a
  scheduled-job tracking row consistent with the other cron tasks.

## Conventions to honor
- No new dependencies. Match surrounding style + the lazy `# noqa: PLC0415` import pattern.
- Keep changes additive; do not regress the render hardening already in `render.py`/`worker.py`.
- Frontend is OUT OF SCOPE (separate prompt). Backend + tests only.

## Verification — CPU-CAPPED, NARROW (READ CAREFULLY)
A prior run buried the host CPU by running the full pytest suite. **Do NOT run the full
suite. Do NOT trigger any real render.** Specifically:
- `ruff check backend/` using **`backend/.venv/bin/ruff`** (it's pinned 0.8.4) run from the
  repo root. Ignore findings that only appear when you pass `--config` explicitly.
- Ephemeral PG: `docker run --rm --name pf3d-test-pg -e POSTGRES_USER=partfolder3d -e
  POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p 5433:5432 postgres:16-alpine`.
  Export `DATABASE_URL=postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d`.
- **Run pytest niced + thread-capped + only your new/relevant files:**
  `export OMP_NUM_THREADS=2 LP_NUM_THREADS=2 ; nice -n 19 backend/.venv/bin/pytest
  backend/tests/test_job_lifecycle.py backend/tests/test_phase4_jobs*.py -p no:cacheprovider -q`
  (only the job test files — NOT the whole suite). `alembic upgrade head` BEFORE pytest.
- Migration round-trip: `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head`.
- Add a new `backend/tests/test_job_lifecycle.py` covering (all mocked — NO real renders):
  cancel sets `cancelled` + subsequent `finish_job` is a no-op; retry links `retry_of_job_id`
  and a succeeded retry supersedes the ancestor chain; `clear-succeeded` archives; default
  list excludes archived + superseded while `archived=true` returns them; retention deletes
  by age (insert rows with old `finished_at`). Mock arq abort/enqueue (no live redis needed).
- **Tear down the ephemeral PG (`docker rm -f pf3d-test-pg`) when done.**
- Report exact pass counts + the alembic round-trip result.

## When done
1. Update this file's frontmatter (`status`, `completed: 2026-06-30`, `result`).
2. `git mv` it into `prompts/done/` (success) or `prompts/failed/` (failure).
3. **Do NOT edit `docs/decisions.md`** — include your decision note (status vocabulary,
   supersede-chain approach, finish_job terminal-guard, retention windows) in your report;
   the orchestrator records it.
4. **Do NOT commit, do NOT push.** Prepare the tree; report back: files changed, the
   decision note, a one-line `feat:`-prefixed commit message, ruff result, alembic round-trip
   result, and the exact capped pytest pass counts.
