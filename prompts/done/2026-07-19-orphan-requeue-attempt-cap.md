---
name: 2026-07-19-orphan-requeue-attempt-cap
status: done             # pending | in-progress | done | failed
created: 2026-07-19
model: sonnet            # opus = research/planning, sonnet = coding
completed: 2026-07-19
result: Capped orphan-requeue at 3 attempts/6h in _recover_orphaned_jobs; 3 new tests; make verify-backend green (855 passed).
---

# Task: Cap orphan-requeue attempts so a crash-looping job fails terminally (issue #37, fix #1)

A job that OOM-kills / hard-crashes the worker is left `running`, then re-queued on the
next worker startup by `_recover_orphaned_jobs`. There is **no attempt cap**, so a "poison"
job (repro: analyzing a 1.3M-vertex mesh that exceeds the worker's memory cap) loops
`crash → restart → re-queue` forever (observed: 31 restarts). This task caps the
re-queue: after **3** orphan-failures of the same job for the same item within a recent
window, mark it terminally `failed` and stop re-enqueuing.

**Scope: proposed-fix #1 of issue #37 ONLY** — the retry cap. Do **NOT** attempt the other
three proposals (subprocess-isolate analyze, dedup concurrent analyze jobs, guard huge
meshes); they remain open follow-ups on #37. Keep this change small and surgical.

## Before you start

- Read `CLAUDE.md` (verify-before-commit gates), and skim `docs/architecture.md` for the
  worker/jobs area. This is a `dev`-branch autonomous run.
- Read the target function `_recover_orphaned_jobs` in `backend/worker.py` (currently
  ~line 133) and its existing tests in `backend/tests/test_render_reliability.py`
  (the `_recover_orphaned_render_jobs` tests, ~line 227 — note the `AsyncMock` redis +
  `_db=db_session` harness pattern; reuse it).
- **No migration** — this is a query/logic change only. Do not add an Alembic migration
  or touch the `Job` model schema.
- **No task-signature changes** — do NOT add params to `analyze_item` / `render_item` /
  `extract_archives`. The entire change lives in `_recover_orphaned_jobs`.

## Working tree check

Before editing, run `git status --porcelain`. The tree should be clean (the dev stack
runs from committed images). If `backend/worker.py` or
`backend/tests/test_render_reliability.py` have uncommitted changes, list them and stop.
Unrelated dirty files: surface once, don't block. This prompt file is exempt.

## Background — how the loop works (so you implement the cap correctly)

- Each orphan re-enqueue creates a **new** `Job` row on the next run (the task calls
  `claim_or_create_job` and inserts a fresh row). So there is no single row to bump —
  attempts are distinct rows linked only by `(type, item_id)`.
- Orphaned rows are marked `failed` with `error = "orphaned by worker restart — re-queued"`
  and `finished_at = now`. That marker string is the signal we count on.
- Real `analyze` jobs set BOTH the `item_id` FK column and `payload["item_id"]`. But the
  re-enqueue keys off `payload["item_id"]` (the FK can be NULL — see the render test seeds
  that pass `item_id=None`). **Count by `payload["item_id"]`** so the count matches exactly
  what we key the re-enqueue on. In Postgres JSONB: `Job.payload["item_id"].astext == str(item_id)`.

## What to do

1. **Add three module-level constants** near the top of `backend/worker.py` (by
   `_IDEMPOTENT_JOB_TASKS`):
   - `_ORPHAN_REQUEUE_MARKER = "orphaned by worker restart"` — the shared marker prefix.
   - `_MAX_ORPHAN_REQUEUE_ATTEMPTS = 3` — the cap ("3 tries then fail").
   - `_ORPHAN_REQUEUE_WINDOW_HOURS = 6` — recency window that scopes the count to an active
     crash-loop storm (a loop re-queues within seconds; this comfortably contains it while
     ignoring stale rows from unrelated past restarts).
   - Update the existing `job.error = "orphaned by worker restart — re-queued"` line to be
     built from `_ORPHAN_REQUEUE_MARKER` (e.g. `f"{_ORPHAN_REQUEUE_MARKER} — re-queued"`)
     so the marker isn't duplicated.

2. **In `_recover_orphaned_jobs._do_recover`**, restructure the idempotent branch so the
   re-enqueue is gated by the attempt count:
   - Keep marking every orphan `failed` + `finished_at = now` as today. While doing so,
     for idempotent orphans track a map `item_jobs: dict[(task_name, item_id)] -> list[Job]`
     of the rows marked **this pass** (you'll need it to write the terminal message), in
     addition to the existing `to_enqueue` dedup.
   - `await db.flush()` (as today) so the just-marked rows are visible to the count query.
   - For each candidate `(task_name, item_id)` in `to_enqueue`, run a COUNT over `Job`:
     `type == <the orphan job.type>`, `status == "failed"`,
     `Job.error.like(_ORPHAN_REQUEUE_MARKER + "%")`,
     `Job.payload["item_id"].astext == str(item_id)`, and
     `finished_at >= now - timedelta(hours=_ORPHAN_REQUEUE_WINDOW_HOURS)`.
     (Use the orphan's own `job.type` for the type filter — you have it in `item_jobs`;
     `task_name` is the arq function name, `job.type` is the DB type string, e.g. type
     `"analyze"` → task `"analyze_item"`. Don't mix them up.)
   - **If count ≥ `_MAX_ORPHAN_REQUEUE_ATTEMPTS`:** do NOT add to the final enqueue list.
     Overwrite the `error` on the rows marked this pass for that item (from `item_jobs`)
     with a terminal message, e.g.:
     `f"{job.type} left orphaned {_MAX_ORPHAN_REQUEUE_ATTEMPTS}× by worker restarts within "
     f"{_ORPHAN_REQUEUE_WINDOW_HOURS}h — not retried automatically (possible crash-loop; see issue #37)"`.
     `log.error(...)` it so the storm is loud in the worker log.
   - **Else:** enqueue as today.
   - Preserve all existing behavior for the common case (a single restart with one orphan
     and no recent priors → count == 1 → re-enqueue exactly as before). Non-idempotent
     orphans are unchanged.

3. **Tests** in `backend/tests/test_render_reliability.py` (reuse the existing harness:
   `AsyncMock()` redis, `ctx = {"redis": mock_redis}`, `_recover_orphaned_jobs(ctx, _db=db_session)`).
   Use a job type that IS idempotent (`analyze` or `render`) and unique high item_ids to
   avoid cross-test collisions. Add:
   - **Capped after max attempts:** seed 2 already-`failed` orphan rows for the item with
     `error = _ORPHAN_REQUEUE_MARKER + " — re-queued"` and recent `finished_at`, plus 1
     `running` orphan. Run recovery → the running one is marked failed → count == 3 →
     `mock_redis.enqueue_job` is **NOT** called for that item, and the just-failed row's
     `error` contains "not retried" / "issue #37".
   - **Below cap still re-enqueues:** 1 prior recent `failed` orphan + 1 `running` →
     count == 2 → re-enqueued once.
   - **Stale history ignored:** 3 prior `failed` orphans with `finished_at` older than the
     window (e.g. `now - timedelta(hours=_ORPHAN_REQUEUE_WINDOW_HOURS + 1)`) + 1 `running`
     → still re-enqueued (window excludes stale rows).
   - Confirm the existing recovery tests still pass unchanged.

4. **CHANGELOG.md** — add a `### Fixed` bullet under `[Unreleased]` (create the section if
   absent) in the SAME commit, e.g.:
   `- Worker no longer crash-loops on a job that repeatedly kills it: orphaned jobs are
   re-queued at most 3× within 6h, then marked terminally failed (issue #37).`

## Verify (gate before reporting the commit)

- Run the backend gate: `make verify-backend` (ephemeral PG on :5433 → pinned ruff 0.8.4
  → alembic → `pytest -n auto`). It MUST be green. No frontend changes, so `verify-frontend`
  is not required — but run `make verify` if in doubt.
- The worker is not exercised by this change at runtime (recovery only runs at worker
  startup), so no `make worker-restart` is needed for tests. Do not restart prod-like services.

## Conventions to honor

- Match the surrounding style in `worker.py` (inline `# noqa: PLC0415` imports inside the
  function, `log.warning/error` phrasing, the `# type: ignore[union-attr]` annotations on
  the dynamically-typed `db`/`job`).
- Conventional-commit prefix `fix:`. Use `closes #37`? **No — this only implements fix #1 of
  4; do NOT close #37.** Reference it as `(issue #37)` instead so it stays open for the
  remaining proposals.
- No `Co-authored-by:` trailers. Docs/changelog ship in the same commit.

## When done

1. Update this file's frontmatter: `status`, `completed`, `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record the non-obvious decision (count-by-payload-item_id + recency-window heuristic,
   and why no migration / no task-signature change) at the top of `docs/decisions.md`.
4. **You are a spawned agent: do NOT commit and do NOT push.** Prepare the working tree,
   then report back to the orchestrator: the exact file list, a one-line `fix:` commit
   message, and the `make verify-backend` result. The orchestrator auto-commits on `dev`
   (project operating model) and pushes.
