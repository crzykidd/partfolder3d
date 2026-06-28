---
name: 2026-06-27-phase-5b-frontend-wizard
status: pending
created: 2026-06-27
model: sonnet
completed:
result:
---

# Task: Phase 5b — Import wizard frontend

This is the **frontend half** of Phase 5 (import / inbox wizard).  The backend is fully
built (Phase 5a, committed alongside this handoff prompt).

## Before you start

- Read `docs/build-plan.md` **Phase 5**, `PRD.md` **§6**, and `docs/decisions.md`
  (especially the "Phase 5 import wizard decisions" section, newest at top).
- Read the Phase 5a backend code you will be calling:
  - `backend/app/routers/import_sessions.py` — all endpoints (create, list, get, patch,
    process, commit, cancel, upload files, site capabilities, share-link stub).
  - The `ImportSessionOut` and related schemas defined there.
  - `backend/app/routers/tags.py` — `POST /api/tags/{id}/approve` (pending-tag approval).
- Read the existing frontend files:
  - `frontend/src/App.tsx` — routing; add new routes here.
  - `frontend/src/components/AppShell.tsx` — nav bar; add links here.
  - `frontend/src/lib/api.ts` — typed fetch wrapper; add new API call functions here.
  - Existing admin pages in `frontend/src/pages/admin/` for patterns.
  - Existing catalog pages (`CatalogPage.tsx`, `ItemPage.tsx`) for UI patterns.

## Working tree check

`git status --porcelain` — the tree should have only Phase 5a changes staged/committed.
Surface any unexpected dirty files before proceeding.

## Scope

Build **only** the frontend pieces listed below.  Do NOT touch backend code.
Do NOT build Phase 6 (scan/reconcile), Phase 7 (share links), or Phase 8 (AI).

### 1. API client additions (`frontend/src/lib/api.ts`)

Add typed functions for every Phase 5a endpoint:
- `createImportSession(body)` → `ImportSession`
- `listImportSessions(params?)` → `PaginatedSessions`
- `getImportSession(id)` → `ImportSession`
- `patchImportSession(id, body)` → `ImportSession`
- `processImportSession(id)` → `ImportSession`
- `uploadSessionFiles(id, files)` → `ImportSession`  (multipart)
- `commitImportSession(id)` → `CommitResponse`
- `cancelImportSession(id)` → `void`
- `listSiteCapabilities()` → `SiteCapability[]`
- `getSiteCapability(domain)` → `SiteCapability`
- `patchSiteCapability(domain, body)` → `SiteCapability`
- `approvePendingTag(id)` → `TagApproveOut`

All interfaces typed to match the Pydantic schemas in `import_sessions.py` and `tags.py`.

### 2. "Add Asset" button + upload modal

- Add an **"Add Asset"** button to the AppShell nav bar (or to the CatalogPage toolbar).
- Clicking it opens a modal/dialog (shadcn/ui Dialog) with two tabs:
  - **Upload files**: drag-and-drop zone + file input (model files: .stl/.3mf/.obj/.ply
    etc.); optional source URL field; optional title field; library selector.
    Flow: create draft session → upload files → call /process → redirect to wizard.
  - **From URL**: source URL input; library selector.
    Flow: create URL session (status goes to processing automatically) → redirect to wizard.

### 3. Import wizard page (`frontend/src/pages/ImportWizardPage.tsx`)

Route: `/import/:sessionId`

A multi-step wizard for a session that is in `pending_wizard` (or `processing`) status.
Poll GET /api/import-sessions/{id} every 3 s while status=processing.

Steps (one step visible at a time; progress indicator at top):

1. **Title** — editable text field; pre-filled from `suggested_title`. Show the source URL
   if present. Confirm button → PATCH `confirmed_title`.

2. **Images** — horizontal scrollable image strip showing `images` from the session.
   Each image with a "Set as default" button (PATCH `default_image_path`).
   URL images show a preview via `<img src={image.path} />`.
   Upload additional images (optional).

3. **Tags** — two lists:
   - Confirmed tags (from `tag_state.confirmed`) — shown as removable chips.
   - Pending / suggested tags (from `tag_state.pending`) — shown with a "Accept" button
     that moves them to confirmed, or a "Reject" button to remove.
   - Manual tag entry: text input to add arbitrary tags (PATCH `confirmed_tags`).
   - Required-tag validation: if the item has zero tags, show a warning (but don't block).

4. **Creator** — toggle between:
   - "Attributed to: ..." (show `creator_name` from scrape/sidecar, editable).
   - "My own design" checkbox → sets `creator_is_own_design=true`.
   Show `creator_profile_url` as a link when present.

5. **Summary + Commit** — read-only review of title, tags, creator, library.
   "Commit" button → POST /api/import-sessions/{id}/commit → on success, redirect to
   `/items/<item_key>`.
   "Cancel" button → POST /api/import-sessions/{id}/cancel → redirect to catalog.

Error handling: if commit fails, show the error inline and allow retry.

### 4. Pending imports list (`frontend/src/pages/ImportsPage.tsx`)

Route: `/imports`

Admin page listing all pending import sessions (GET /api/import-sessions?all_users=true
for admins; own sessions for regular users).

Columns: status badge, source type, title/suggested title, created at, "Open wizard" link.
Status badges: draft (grey), processing (spinning), pending_wizard (yellow), failed (red).
Failed sessions show the `error` field.
"Open wizard" → `/import/:sessionId`.

### 5. Site-setup prompt (within wizard, not a standalone page)

On step 1 (Title) of the wizard: if `session.source_url` is set and there is a
`SiteCapability` for that domain with `is_manual_only=true` or `requires_token=true`:
- Show a banner: "This site requires manual file upload" or
  "This site requires a token — configure it in Site Setup below."
- Inline token form (PATCH /api/site-capabilities/{domain} with `token`) so the user can
  enter a token without leaving the wizard.

### 6. Pending tag approval (within admin Tags view or as a standalone section)

Add a "Pending Tags" section to the existing tag cloud or create a simple
`/admin/pending-tags` route that:
- Lists tags where `active_only=false` and `status=pending` (use GET /api/tags?active_only=false).
- For each pending tag: show name + "Approve" button → POST /api/tags/{id}/approve.

### 7. Navigation

Add to AppShell nav:
- **Imports** link → `/imports` (for all authenticated users; admin sees all sessions).
- Admin sub-menu: add **Pending Tags** link.

## Conventions

- TypeScript strict — no `any` unless absolutely necessary; `npx tsc --noEmit` must be clean.
- TanStack Query for all server state: `useQuery` / `useMutation`.
- shadcn/ui components (Dialog, Button, Badge, Input, Tabs, Progress, etc.).
- Tailwind for layout; match existing catalog page patterns.
- `vitest` for non-trivial logic (tag reconciliation display, wizard step navigation).
- CSRF: all mutations must include `X-CSRF-Token` header (use the `apiFetch` wrapper).

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. `git mv` into `prompts/done/` on success.
3. Add `docs/decisions.md` entries for any non-obvious UI decisions (wizard step layout,
   polling strategy, image preview approach, etc.).
4. **You are a spawned agent: do NOT commit, push, or change branch.**
5. Report back: complete file list; proposed `feat:` commit message; exact check results
   (`ruff` / `tsc` / `vitest`); any decisions or things you could not verify.
