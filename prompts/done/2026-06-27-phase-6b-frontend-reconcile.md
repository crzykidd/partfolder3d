---
name: 2026-06-27-phase-6b-frontend-reconcile
status: completed
created: 2026-06-27
model: sonnet
completed: 2026-06-27
result: Three admin pages (Issues, Change Log, Review Queue) + Reconcile Modes settings UI wired to Phase 6a backend; all 5 deliverables complete; tsc clean, 96/96 vitest passing.
---

# Task: Phase 6b — Reconciliation / Scan Engine Frontend

Wire up the three new Phase 6 backend APIs to the admin UI: **Issues**, **Change Log**,
and **Review Queue**. Phase 6a (backend) is **fully complete** — the APIs are live on
`dev` and all tests pass. This prompt covers the remaining frontend scope only.

## Context

Phase 6a delivered (all on `dev`):

- **Models**: `Issue`, `ChangeLog`, `ReviewItem` with typed enums in
  `backend/app/models/{issue,change_log,review_item}.py`
- **APIs**:
  - `GET /api/issues` — paginated list, filter by `status`, `issue_type`, `item_id`
  - `GET /api/issues/{id}` — detail
  - `POST /api/issues/{id}/resolve` — CSRF-protected
  - `POST /api/issues/{id}/ignore` — CSRF-protected
  - `GET /api/changes` — paginated list, filter by `behavior`, `item_id`
  - `GET /api/reviews` — paginated list, default `status=pending`
  - `POST /api/reviews/{id}/approve` — CSRF-protected; enqueues arq task
  - `POST /api/reviews/{id}/reject` — CSRF-protected
- **Scheduled scan**: `library_reconcile_scan` runs daily at 03:00 UTC (replaces
  `placeholder_reindex`).
- **Per-item rescan**: `POST /api/items/{key}/rescan` now uses the reconcile engine
  (auto mode for file_changes + sidecar_sync, preserving prior UX).

## Before you start

1. `git status --porcelain` — check for unrelated dirty files; list them, don't touch them.
2. Read [`standards.md`](../standards.md) sections relevant to frontend work.
3. Read existing admin pages for structural patterns:
   - `frontend/src/pages/admin/JobsPage.tsx` — job list with status badges, pagination
   - `frontend/src/pages/admin/ScheduledJobsPage.tsx` — scheduled job list
4. Read `frontend/src/lib/api.ts` to understand the API client conventions.
5. Read `frontend/src/components/AppShell.tsx` for nav link structure.

## Deliverables

### 1. API client additions (`frontend/src/lib/api.ts`)

Add typed functions for all six new endpoints:

```ts
// Issues
listIssues(params?: { status?: string; issue_type?: string; item_id?: number; page?: number }): Promise<PaginatedIssues>
getIssue(id: number): Promise<IssueOut>
resolveIssue(id: number): Promise<IssueOut>
ignoreIssue(id: number): Promise<IssueOut>

// Changes
listChanges(params?: { behavior?: string; item_id?: number; page?: number }): Promise<PaginatedChanges>

// Reviews
listReviews(params?: { status?: string; page?: number }): Promise<PaginatedReviews>
approveReview(id: number): Promise<ReviewItemOut>
rejectReview(id: number): Promise<ReviewItemOut>
```

Match the CSRF-header pattern already used by other POST calls in `api.ts`.

### 2. Three new admin pages

#### `frontend/src/pages/admin/IssuesPage.tsx`

- Table/list of issues (paginated, 50/page).
- Columns: severity badge (critical=red, warning=yellow, info=blue), type, status, item
  link (if `item_id` set), detail (truncated), created_at, actions.
- Status filter: All / Open / Resolved / Ignored (tab or dropdown).
- Issue type filter (dropdown).
- Row actions: **Resolve** / **Ignore** buttons (only on `open` issues).
- Clicking a row expands to show `detail`, `suggested_action`, `resolved_at`.

#### `frontend/src/pages/admin/ChangesPage.tsx`

- Read-only audit log; newest first.
- Columns: behavior badge, change_type, item link, summary, source, created_at.
- Behavior filter (dropdown): all, sidecar_sync, file_changes, re_render, integrity,
  orphan.
- No actions — purely informational.

#### `frontend/src/pages/admin/ReviewsPage.tsx`

- Queue of pending review items (default tab: Pending; tabs: All).
- Columns: behavior badge, change_type, item link, summary, created_at, actions.
- Row actions: **Approve** / **Reject** buttons (only on `pending` items).
- Expanding a row reveals `proposed_action` (formatted JSON or human-readable summary).
- After approve/reject, optimistically remove from Pending list or mark status.

### 3. Register routes and nav links

In the router config (likely `frontend/src/App.tsx`), add:

```
/admin/issues      → IssuesPage
/admin/changes     → ChangesPage
/admin/reviews     → ReviewsPage
```

In `AppShell.tsx`, add nav links in the **Admin** section:
- "Issues" → `/admin/issues`
- "Change Log" → `/admin/changes`
- "Review Queue" → `/admin/reviews` (add a pending-count badge if feasible)

### 4. TypeScript types

Define (or extend existing) types:

```ts
interface IssueOut {
  id: number;
  issue_type: string;
  severity: string;
  status: string;
  item_id: number | null;
  detail: string;
  suggested_action: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

interface ChangeLogOut {
  id: number;
  behavior: string;
  change_type: string;
  item_id: number | null;
  summary: string;
  before_state: unknown | null;
  after_state: unknown | null;
  source: string;
  actor: string;
  created_at: string;
}

interface ReviewItemOut {
  id: number;
  behavior: string;
  change_type: string;
  item_id: number | null;
  summary: string;
  proposed_action: Record<string, unknown>;
  status: string;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}
```

## Design guidance

- **Reuse existing component patterns** — don't introduce a new component library.
  Replicate the table/badge/pagination style from `JobsPage.tsx`.
- **Severity colors**: `critical` → red, `warning` → amber/yellow, `info` → blue.
  Match the severity to existing badge components if any.
- **Behavior badges**: consistent short labels — `sidecar_sync`, `file_changes`,
  `re_render`, `integrity`, `orphan`.
- **No new dependencies** unless trivially installed.
- **Admin-only**: All three pages are admin-gated. Redirect to `/` (or show 403) if not
  admin — look at how existing admin pages enforce this.

### 5. Auto/Review mode settings UI (PRD §8.2)

The reconcile engine reads three per-behavior mode settings (see
`backend/app/worker/reconcile.py`): `scan.sidecar_sync.mode`, `scan.re_render.mode`,
`scan.file_changes.mode`, each `"auto"` or `"review"` (defaults: sidecar_sync=review,
re_render=auto, file_changes=review). These are plain settings rows — **no new backend
endpoint is needed**; use the existing generic settings API:

- `GET /api/settings` → `[{ key, value }]` (find the `scan.*.mode` keys; a key absent means
  the engine default applies — show the default).
- `PUT /api/settings/{key}` with `{ value: "auto" | "review" }` (CSRF-protected) to change one.

Add this as a small **"Reconcile Modes"** section/card — either on a settings/admin page or as
a panel on the Issues or Reviews page (your call; match existing settings UI patterns). For each
of the three behaviors show a label + an Auto/Review toggle (or select) that reflects the
current value (falling back to the documented default) and PUTs on change. Add typed
`listSettings()` / `setSetting(key, value)` helpers to `api.ts` if not already present.

## Out of scope

- Bulk-resolve / bulk-reject actions.
- Real-time websocket push for new issues.
- Sorting columns (pagination + filter is sufficient).
- Item-level inline issue/review badges on the catalog page (Phase 7 if needed).

## Verification

```bash
# In frontend/
npm run build          # must succeed with no TypeScript errors
npm run lint           # must pass (no new warnings)
# Start dev server and manually visit:
#   /admin/issues   — list loads, filter works, resolve/ignore buttons work
#   /admin/changes  — list loads, behavior filter works
#   /admin/reviews  — list loads, approve/reject buttons work
```

If no issues/changes/reviews exist in the DB, the pages should show an empty state
(not an error). Seed via the test Postgres instance if needed:
`docker run -d --name pf3d-test-pg -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p 5433:5432 postgres:16-alpine`
then run `alembic upgrade head` and use the existing conftest fixtures.

## Commit

Prepare the working tree for a single commit. Do **not** commit or push yourself.
Report back:
- Files changed / created.
- Any decisions made (approach choices, rejected alternatives).
- Proposed commit message (conventional-commit style, `feat:` prefix).
- Any blockers or concerns.

The prompt file moves to `prompts/done/` as part of the commit bundle — update its
frontmatter (`status: completed`, `completed: <date>`, `result: <one-liner>`) before
reporting back.
