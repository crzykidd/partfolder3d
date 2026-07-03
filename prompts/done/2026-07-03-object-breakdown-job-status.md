---
name: 2026-07-03-object-breakdown-job-status
status: done
created: 2026-07-03
model: sonnet
completed: 2026-07-03
result: >
  Added GET /api/items/{key}/jobs backend endpoint (ItemJobOut with progress+error;
  returns active + non-archived failed jobs). Added ItemJobSummary type + listItemJobs
  API fn. ItemPage polls jobs every 3s and threads into ObjectBreakdownSection.
  ObjectBreakdown now splits pending model files: 3MF → "read, not mesh-analyzed";
  mesh → correlates with analyze_item job (running/queued/failed/no-job). 5 backend
  pytest + 12 vitest + ruff + vite build all green. Pushed to feat/object-breakdown-jobs.
---

# Task: Make Object Breakdown "Analysis pending" tell the truth (job status + 3MF + failures)

On the item page, the **Object Breakdown** section shows a flat "Analysis pending — will
appear after the background worker runs." for any model file with no `object_analysis`.
That's misleading: **3MF files don't get mesh analysis at all**, and if the analyze job
**failed** or is **running**, the user has no signal. Make this section accurate and
actionable, committing to `dev`.

## Before you start
- Read `startnewsession.md` + `CLAUDE.md`. `dev` branch; conventional commits; changelog in
  the same commit; frontend = Tailwind + Radix + lucide + TanStack Query + apiFetch (NO
  Mantine/toast); verify frontend with `npm run build` + `npx vitest run`; backend lint
  `backend/.venv/bin/ruff check backend/` (pinned 0.8.4); backend tests on the ephemeral PG
  at `localhost:5433` (`partfolder3d/testpass/partfolder3d`), `alembic upgrade head` first.
- Stage ONLY your own files by explicit path — never `git add -A` (other untracked files
  exist in the tree). Do NOT run the full test suite (scoped only).

## Current state (traced)
- `frontend/src/pages/item/ObjectBreakdown.tsx` — `ObjectBreakdownSection`: `pendingFiles` =
  every `role === 'model'` file with `object_analysis == null`. The "Analysis pending"
  message (~line 255-261) shows whenever there are pending files but nothing analyzed/sliced.
  **3MF model files with no slice data fall into `pendingFiles` and show "pending" forever.**
- `backend/app/routers/items.py` `list_item_jobs` (`GET /api/items/{key}/jobs`) returns ONLY
  `status in (queued, running)` jobs, and `ItemJobOut` has NO `progress`/`error` fields.
- The `Job` model (`backend/app/models/job.py`) HAS `progress` (0–100 int), `error` (text),
  `type`, `status`, `payload`, `item_id`, `created_at/started_at/finished_at`, `archived_at`.
- `ItemPage.tsx` already polls `['item-jobs', key]` via `api.listItemJobs(key)` (type
  `ItemJobSummary` in `frontend/src/lib/api/items.ts`) — currently only passed to the file
  list for auto-refresh. Jobs monitor route = **`/admin/activity/jobs`**.
- Analyze work is enqueued as `analyze_item` (see `_enqueue_analyze` in
  `app/services/item_helpers.py`); confirm the exact `Job.type` string the analyze task
  records via `job_tracker` and match on it.

## What to do

### Backend
1. Extend `list_item_jobs` (`GET /api/items/{key}/jobs`) to ALSO include **recent failed
   jobs** for the item (in addition to queued/running), so the UI can show failures. Keep it
   bounded (e.g. non-archived `failed` jobs, or failed within the last ~24h — your judgment;
   keep it simple). Add **`progress`** and **`error`** to `ItemJobOut`. Don't break the
   existing auto-refresh consumer (it just checks for active jobs).
2. Update the frontend `ItemJobSummary` type (`lib/api/items.ts`) with `progress: number` and
   `error: string | null`.
3. Add a scoped backend test: the endpoint returns a failed analyze job with its `error` and
   `progress`, plus the existing active-job behavior.

### Frontend — `ObjectBreakdown.tsx`
Pass the item's jobs into `ObjectBreakdownSection` (thread from `ItemPage`, which already has
them). Then replace the single "Analysis pending" branch with accurate, per-cause messaging:

- **Split pending model files by type** using `is3mf` (`@/lib/file-tree`): `.3mf` vs mesh
  (`.stl/.obj/.ply`).
- **3MF files with no analysis** → do NOT say "pending". State plainly that **3MF files are
  read, not mesh-analyzed** — slice details (if any) appear inline in Files & Downloads above,
  and if there's no embedded thumbnail / slice data there's simply nothing more to show. (No
  implication that a job is coming.)
- **Mesh files (stl/obj/ply) still pending** → look for this item's `analyze_item` job among
  the jobs and message by state:
  - **running** → "Analyzing… {progress}%" with a small progress bar, + a link "View in Jobs"
    → `/admin/activity/jobs`.
  - **queued** → "Analysis queued" + the same link.
  - **failed** → "Analysis failed: {error}" (show the error text), + the link, + a hint to use
    **Rescan disk** (Files & Downloads) to re-queue it.
  - **no job found** → an honest "Analysis hasn't run yet — use **Rescan disk** to queue it"
    (not a promise that a worker will magically run).
- Keep the existing analyzed-files rendering and the sliced-3MF "shown inline" message intact.
- Use existing Aurora styles / lucide icons; no new deps. Add a light progress bar (a div with
  a width % is fine).

### Tests
- vitest for `ObjectBreakdownSection`: 3MF-only pending → the 3MF message (not "pending");
  mesh pending with a failed job → shows the error; with a running job → shows progress; with
  no job → the "run Rescan" message. Mock the jobs prop.
- Keep the suite green (`npm run build` + `npx vitest run`).

## When done
- Update `CHANGELOG.md [Unreleased]` (### Changed/Fixed) and record any non-obvious decision in
  `docs/decisions.md` (newest at top). Set this prompt's frontmatter + `git mv` to
  `prompts/done/`.
- Commit to `dev` (prefix `feat:` or `fix:`), one commit, staging only your files + the prompt.
  Do NOT push to main. Do NOT run the full suite.
- Report back: commit SHA + message, files changed, verification (ruff, scoped pytest, build,
  vitest counts), and a short bullet list of UI states to eyeball manually.
