---
name: 2026-06-28-feat-job-retry
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: >
  POST /api/jobs/{id}/retry endpoint added (admin+CSRF). Retry map: "render" →
  render_item(item_id). Non-failed → 409; non-retriable type → 400. Frontend:
  RotateCw Retry button on failed rows in JobsPage.tsx, useMutation + invalidate.
  api.ts: retryJob(). 5 new tests; 18/18 pass. ruff clean; tsc clean; 185 vitest
  pass; vite build success. No schema change. docs/decisions.md updated.
---

# Task: Manual "Retry" for failed jobs (re-enqueue the arq task)

Failed jobs are never auto-retried (the tasks catch their own errors and mark the Job row
`failed`, so arq sees success). Add a **manual retry**: a `POST /api/jobs/{job_id}/retry`
endpoint + a **Retry** button on failed jobs in the Jobs admin page. No schema change.

## Facts (already verified)
- `Job` model (`app/models/job.py`): `id` (uuid), `type` (str, e.g. `"render"`), `status`,
  `progress`, `payload` (JSONB — holds the task args, e.g. `{"item_id": N}`), `error`, `item_id`,
  timestamps. Jobs are created inside the arq tasks via the worker's `create_job`/`finish_job`
  helpers.
- Render is enqueued as `redis.enqueue_job("render_item", item_id)`. The Job `type` is `"render"`
  (NOT the same string as the arq task `"render_item"`), so retry needs an explicit
  **Job.type → (arq_task_name, args-from-payload)** mapping.
- Stack: FastAPI + SQLAlchemy async + arq/Redis. Frontend: Tailwind + Aurora + `@/components/ui` +
  TanStack Query + `apiFetch`. **NO new deps.** Don't touch `frontend/src/pages/examples/`.

## Working tree check
`git status --porcelain` clean on `dev`.

## What to build

### 1. Backend — retry endpoint
- `POST /api/jobs/{job_id}/retry` (admin-gated + CSRF, matching the other admin mutations).
- Load the job (404 if missing). Only allow retry when `status == "failed"` (return 409/400 with a
  clear message otherwise — don't retry a running/queued job).
- A **retry map** from `Job.type` → how to re-enqueue: at minimum `"render"` →
  `redis.enqueue_job("render_item", payload["item_id"])`. Inspect the worker for the other job
  `type` values created via `create_job` and add the ones that are **safely re-runnable** from
  their stored `payload` (e.g. import processing, zip bundle, backup, reconcile scan — include
  the ones whose task name + args you can determine confidently from the code). For any `type`
  not in the map, return a clear 400 ("This job type can't be retried automatically").
- Re-enqueue using the same Redis pool the routers already use to enqueue (`items.py`
  `_enqueue_render` shows the pattern). Return the same shape as the existing job endpoints (e.g.
  202 + a small `{queued: true}` or the new/updated job) — pick what fits the existing router
  style. Do NOT mutate the old failed row's history misleadingly; a fresh enqueue creating a new
  Job row (as the tasks already do) is fine — document the chosen behavior.

### 2. Frontend — Retry button
- In `admin/JobsPage.tsx`, add a **Retry** action (lucide `RotateCw`/`RefreshCw`) on rows whose
  `status === 'failed'` **and** whose `type` is retriable (gate on the same set the backend
  supports — expose it however is simplest: either always show on failed + handle the 400 with a
  message, or hardcode the retriable set; prefer showing on all failed rows and surfacing the
  backend's error message if not retriable). On click → call the endpoint, then invalidate the
  jobs query so the new/updated job appears. Use the existing `@/components/ui` `Button` +
  confirm/inline-status pattern already used on that page. Add `retryJob(jobId)` to `api.ts`.

## Rules
- No schema change, no migration. Frontend-only + one backend router (+ maybe a tiny worker
  helper if needed for the retry map). If you find you need a model/migration, STOP and report.
- Keep the best-effort contract: a retry just re-enqueues; it must not throw to the UI on a
  normal "can't retry this type" case (return a clean 4xx the UI shows).

## Verify
- Backend: `ruff check backend/`; **ephemeral Postgres** (no new migration, but tests need a DB):
  `docker run -d --name pf3d-test-pg -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p 5433:5432 postgres:16-alpine`,
  set `DATABASE_URL`, `alembic upgrade head`, `pytest`. Add tests: retrying a failed render job
  re-enqueues `render_item` (mock/patch the Redis enqueue and assert it's called with the item_id);
  retrying a non-failed job → 409/400; retrying a non-retriable type → 400. Recreate the scratchpad
  venv at the session path if gone; tear down the container after.
- Frontend: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite
  build` MUST succeed** (the real gate). Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: the retry map (which job types are retriable + why), and the re-enqueue
   behavior (new Job row vs reset).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; check results (ruff / pytest+count / tsc / vitest / **vite build**); which job
   types are retriable; confirmation no schema change; anything you could not verify.
