---
name: 2026-06-30-job-monitor-ui
status: completed
created: 2026-06-30
model: sonnet            # frontend only
completed: 2026-06-30
result: Added cancelJob/restartJob/clearSucceededJobs/archiveJob/deleteJob to jobs.ts; extended JobOut with retry_of_job_id + archived_at; added archived?/include_superseded? to listJobs params. JobsPage gains per-row Cancel/Restart/Retry/Archive/Delete actions gated by status; top-bar Clear succeeded + archive toggle (view-archive / live-view); cancelled added to status filter pills. tsc clean, vitest 229/229 passed, vite build succeeded.
---

# Task: Job monitor UI — cancel/restart/clear/archive controls

Wire the new job-lifecycle backend endpoints into the admin job monitor so an operator can
cancel + restart running jobs, retry failed ones (already exists), clear/archive succeeded
jobs, and browse the archive. Frontend only — the backend (migration 0019 + endpoints) is
already committed.

## Before you start

- Read `prompts/startnewsession.md` and `CLAUDE.md` (you are a spawned agent on `dev`:
  do NOT commit, do NOT push — prepare the tree and report back).
- Frontend stack (state it, don't reintroduce wrong libs): Tailwind + CSS-var Aurora theme +
  minimal Radix + lucide-react + TanStack Query + the `apiFetch`/`apiFetchForm` CSRF wrapper.
  **No Mantine, no toast library.**
- Read these fully:
  - `frontend/src/lib/api/jobs.ts` — current client: `JobOut` interface, `listJobs`,
    `getJob`, `retryJob`. Extend it.
  - `frontend/src/pages/admin/JobsPage.tsx` — the monitor (route `/admin/activity/jobs`).
    Polls `listJobs` every 5s; status filter pills `['', running, queued, failed, succeeded]`;
    a `JobRow` with an Actions cell that today only shows "Retry" when `status==='failed'`.
  - `frontend/src/lib/widgets/panel/JobsMiniWidget.tsx` — dashboard widget (read-only; only
    touch if its `JobOut` typing needs the new fields).

## Backend API (already implemented — match these exactly)

- `GET /api/jobs` — query params: `status`, `type`, `page`, `per_page`, **`archived`** (bool;
  true = archive-only list), **`include_superseded`** (bool). Returns `PaginatedJobs
  {total,page,per_page,jobs[]}`. `JobOut` now also has **`retry_of_job_id: string|null`** and
  **`archived_at: string|null`**. Default view already excludes archived + superseded server-side.
- `POST /api/jobs/{id}/retry` → 202 `{queued: boolean}` (failed jobs only)
- `POST /api/jobs/{id}/cancel` → 200 `JobOut` (running jobs only; 409 otherwise)
- `POST /api/jobs/{id}/restart` → 202 `{queued: boolean}` (any status; cancels first if running)
- `POST /api/jobs/clear-succeeded` → 200 `{archived: number}`
- `POST /api/jobs/{id}/archive` → 200 `JobOut` (terminal jobs only; 409 otherwise)
- `DELETE /api/jobs/{id}` → 204
- New possible statuses to handle in the UI: **`cancelled`**, **`superseded`** (superseded is
  hidden by default; you generally won't show it unless the archive/superseded toggle is on).

## Working tree check

`git status --porcelain` first. Expect clean `dev` at `28f79a4` or later (a backend commit).
If `jobs.ts` / `JobsPage.tsx` have unrelated uncommitted changes, list them and ask.

## What to do

1. **`frontend/src/lib/api/jobs.ts`**: add `retry_of_job_id` + `archived_at` to `JobOut`; add
   `archived?`/`include_superseded?` to the `listJobs` params; add `cancelJob(id)`,
   `restartJob(id)`, `clearSucceededJobs()`, `archiveJob(id)`, `deleteJob(id)` using the same
   CSRF wrapper the existing `retryJob` uses (mutating calls need the CSRF token).

2. **`JobsPage.tsx` — per-row actions** in the Actions cell, gated by status:
   - `running` → **Cancel** + **Restart**
   - `failed` → **Retry** (existing) + **Restart** + **Archive** + **Delete**
   - `succeeded` / `cancelled` → **Archive** + **Delete**
   - Use lucide icons + the existing button styling. **Delete** must confirm (a simple
     `window.confirm` is fine — there's no toast/modal lib). After any action, invalidate the
     jobs query (or refetch) so the row updates; the 5s poll is the fallback.

3. **`JobsPage.tsx` — top controls:**
   - A **"Clear succeeded"** button → `clearSucceededJobs()` then refetch (confirm first; it
     archives all succeeded). Optionally show the returned count inline.
   - An **Archive view toggle** (e.g. a pill or button "Archived") that flips `listJobs` to
     `archived: true` so the table shows the archive list; toggling back returns to the live
     view. In the archive view, per-row actions reduce to **Delete** (and maybe Restart).
   - Add **`cancelled`** to the status filter pills. Leave `superseded` out of the normal pills
     (it's hidden by default); no need for an include_superseded toggle unless trivial.

4. Keep the existing polling, expand-row log/error display, pagination, and elapsed/created
   columns intact. Don't restyle the page beyond adding the controls.

## Conventions to honor
- Match the existing JobsPage styling (inline styles + CSS vars, lucide icons, the existing
  pill/button patterns). No new dependencies.
- Handle action errors gracefully (e.g. a 409 on cancel if the job already finished) — surface
  a brief inline message or just refetch; do not crash the page.

## Verification (light — frontend, no CPU concern)
- `npx tsc --noEmit` (typecheck).
- Relevant `npx vitest run` (any jobs/api tests).
- **`npx vite build`** — the real gate (tsc/vitest miss babel/esbuild parse errors).
Report all three results.

## When done
1. Update frontmatter (`status`, `completed: 2026-06-30`, `result`).
2. `git mv` into `prompts/done/` (success) or `prompts/failed/` (failure).
3. **Do NOT edit `docs/decisions.md`** — report any non-obvious choice back instead.
4. **Do NOT commit, do NOT push.** Prepare the tree; report back: files changed, any decision
   note, a one-line `feat:`-prefixed commit message, and the tsc/vitest/vite-build results.
