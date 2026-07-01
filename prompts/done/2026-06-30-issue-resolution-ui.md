---
name: 2026-06-30-issue-resolution-ui
status: done
created: 2026-06-30
model: sonnet            # frontend only
completed: 2026-06-30
result: >
  Added target_path + available_actions to IssueOut type; added ActionResponse + issueAction()
  to api/issues.ts. IssuesPage.tsx rewritten to drive action buttons from issue.available_actions
  (ignore/delete/import) with lucide icons, window.confirm for delete, and react-router
  navigate to /import/<id>?prefill=sidecar on import success. ImportWizardPage.tsx reads
  ?prefill=sidecar via useSearchParams and shows a dismissible teal banner. tsc/vitest/vite
  all clean.
---

# Task: Issue resolution actions UI (Phase 2, frontend)

Wire the new issue-resolution backend into the admin Issues page: each issue shows the actions
the backend says are available, and Import opens the import wizard prefilled from the folder's
existing sidecar. Frontend only — the backend (migration 0020, action framework, orphan
actions) is already committed.

## Before you start
- Read `prompts/startnewsession.md` and `CLAUDE.md` (spawned agent on `dev`: do NOT commit/
  push — prepare the tree, report back). Do NOT edit `docs/decisions.md` — report notes back.
- Frontend stack: Tailwind + CSS-var Aurora theme + minimal Radix + lucide-react + TanStack
  Query + `apiFetch`/`apiFetchForm` CSRF wrapper. No Mantine, no toast lib (use `window.confirm`).
- Read fully:
  - `frontend/src/pages/admin/IssuesPage.tsx` (route `/admin/activity/issues`) — current page;
    today it likely has plain Resolve/Ignore buttons.
  - `frontend/src/lib/api/issues.ts` (or wherever issues are fetched) — the `IssueOut` type +
    list/resolve/ignore calls.
  - The import wizard page + route (find it: likely `frontend/src/pages/ImportWizardPage.tsx`
    or `frontend/src/pages/import-wizard/*`, route like `/import` or `/import/:sessionId`) —
    to know how to open the wizard for a specific ImportSession id.

## Backend API (already implemented — match exactly)
- `GET`/list issues returns `IssueOut` now including **`target_path: string | null`** and
  **`available_actions: string[]`** (e.g. `["import","delete","ignore"]` for orphan issues;
  `["ignore"]` for most others).
- `POST /api/issues/{id}/action` (admin + CSRF), body `{ "action": "ignore" | "delete" | "import" }`:
  - `ignore` → marks the issue ignored (durably suppressed). Returns updated issue.
  - `delete` → moves the orphan directory to trash, marks issue resolved. Returns updated issue.
  - `import` → creates an ImportSession (pending_wizard) prefilled from the folder's sidecar and
    marks the issue resolved. Returns a payload containing the new import session id (confirm the
    exact field name by reading `backend/app/routers/issues.py` — likely `import_session_id`).
  - 422 if the action isn't in that issue's `available_actions`.
- The legacy `POST /api/issues/{id}/resolve` still exists but prefer the new `/action` endpoint.

## Working tree check
`git status --porcelain` first. Expect clean `dev` at `0299841` or later. If the files you need
have unrelated uncommitted changes, list them and ask.

## What to do
1. **`api/issues.ts`**: add `target_path` + `available_actions` to the `IssueOut` type; add
   `issueAction(id, action)` calling `POST /api/issues/{id}/action` with the CSRF wrapper.
   Type the import response (`{ import_session_id: string | number }` — match the backend).
2. **`IssuesPage.tsx`**: for each issue, render action buttons **driven by
   `issue.available_actions`** (not hardcoded), using lucide icons + existing button styling:
   - `ignore` → `issueAction(id,'ignore')` then refetch. (Label e.g. "Ignore".)
   - `delete` → `window.confirm('Move this directory to trash? …')` → `issueAction(id,'delete')`
     then refetch. (Label "Delete folder"; use a trash/danger affordance.)
   - `import` → `issueAction(id,'import')`; on success, **navigate to the import wizard** for the
     returned session id, adding a query flag so the wizard shows the sidecar-prefill note
     (e.g. `/import/<sessionId>?prefill=sidecar` — match the wizard's actual route/param).
   - Keep any existing status display; surface action errors inline (e.g. a 422) — don't crash.
3. **Import wizard prefill note**: when the wizard is opened with the `prefill=sidecar` flag
   (from step 2), show a small, dismissible banner near the top: e.g. **"Showing existing sidecar
   data — review and update before importing."** The wizard already renders the session's
   pre-populated fields; this just tells the user where the data came from. If the wizard route
   doesn't easily support the flag, use the cleanest equivalent signal and note what you did.

## Conventions to honor
- Match existing page/component styling (inline styles + CSS vars, lucide icons). No new deps.
- Use react-router navigation the way the app already does it.

## Verification (frontend — light, no CPU concern)
- `npx tsc --noEmit`
- relevant `npx vitest run`
- `npx vite build` (the real gate)
Report all three.

## When done
1. Update frontmatter (`status`, `completed: 2026-06-30`, `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`).
3. Do NOT edit `docs/decisions.md` — report any note back.
4. Do NOT commit/push. Report: files changed, note (esp. how you wired the wizard prefill flag),
   one-line `feat:`-prefixed commit message, and tsc/vitest/vite-build results.
