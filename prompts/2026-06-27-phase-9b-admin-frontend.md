---
name: 2026-06-27-phase-9b-admin-frontend
status: pending          # pending | completed | failed
created: 2026-06-27
model: sonnet            # coding against a locked plan
completed:
result:
---

# Task: Phase 9b — Admin frontend (backup, export, reindex, tag admin, site caps, API keys)

Build the admin UI pages that surface the Phase 9a backend.  This is the frontend
half of Phase 9 (`prompts/done/2026-06-27-phase-9-admin-backup-export-api.md`).

## Before you start

- Read `CLAUDE.md` operating rules and `docs/decisions.md` (especially the Phase 9
  section at the top).
- Read `PRD.md` §13 (admin features) and §15 (API).
- Read `frontend/src/pages/admin/` to match existing page style (see
  `UsersPage.tsx`, `ScheduledJobsPage.tsx`, `PendingTagsPage.tsx`, `AiProvidersPage.tsx`
  as reference pages).
- Read `frontend/src/lib/api.ts` for the existing `apiFetch`/`apiFetchForm` helpers and
  endpoint patterns.
- Read `frontend/src/components/AppShell.tsx` to understand how admin nav items are
  added.
- The **backend API is complete** (Phase 9a). All endpoints below already exist and
  were tested. Do NOT add any backend code.

## Working tree check

Run `git status --porcelain`. Expect a clean tree on `dev` (only this prompt file
untracked). Surface anything unexpected and ask before proceeding.

## UI stack (MANDATORY)

**Tailwind + CSS-variable (shadcn-style) theme + minimal Radix (`react-dropdown-menu`
/ `react-slot` only) + `lucide-react` + TanStack Query + `apiFetch`/`apiFetchForm`
CSRF wrapper. NO Mantine. NO toast library. NO new external libraries.** Match the
existing page style exactly.

## What to do

### 1. Backups page (`frontend/src/pages/admin/BackupsPage.tsx`)

A new admin page at `/admin/backups`.

- **Loud callout banner** (prominent, not just a footnote): "Library files are NOT
  backed up. These backups contain only the database and config (encryption key). You
  are responsible for backing up your library files."  Use a warning color that
  matches the existing alert style.
- Table of backup records: filename, size (human-readable), status, created_at,
  download link (for `status=ready`), delete button.
- "Run Backup Now" button → `POST /api/admin/backups/run` (CSRF required).
- Retention count setting: show current value, allow update via
  `PUT /api/admin/backups/settings` (CSRF required). Inline form (no modal).
- Download: `GET /api/admin/backups/{id}/download` — anchor tag with `download` attr.
- Delete: `DELETE /api/admin/backups/{id}` (CSRF required) with a confirm step.
- Poll or invalidate on run to show updated list.

Backend endpoints:
- `GET    /api/admin/backups` → list
- `POST   /api/admin/backups/run` → trigger
- `GET    /api/admin/backups/settings` → retention count
- `PUT    /api/admin/backups/settings` → update retention count
- `GET    /api/admin/backups/{id}/download` → download archive
- `DELETE /api/admin/backups/{id}` → delete

### 2. Export page (`frontend/src/pages/admin/ExportPage.tsx`)

A minimal page at `/admin/export`.

- Brief description: "Download the full catalog as a JSON file (items, tags, creators,
  print records). Binary files are not included."
- "Download Catalog JSON" button → opens `GET /api/admin/export/catalog` in a new tab
  or triggers a download. (The endpoint streams a JSON attachment; a simple anchor
  `href="/api/admin/export/catalog"` download link is sufficient.)
- No polling/state needed; this is a one-shot download.

### 3. Reindex button on ScheduledJobsPage or a dedicated ReindexPage

Option A (preferred): Add a "Reindex Now" button directly on the existing
`ScheduledJobsPage.tsx` next to the `library_reconcile_scan` job entry. This reuses
the existing `POST /api/scheduled-jobs/{name}/run` endpoint that's already wired.
No new page needed.

Option B: A tiny `ReindexPage.tsx` at `/admin/reindex` if Option A is too invasive.

### 4. Tag administration page (`frontend/src/pages/admin/TagAdminPage.tsx`)

A new admin page at `/admin/tags`.

- **Pending tags tab/section**: list of pending tags from `GET /api/admin/tags/pending`.
  Per row: tag name, "Approve" button (→ `POST /api/admin/tags/{id}/approve` + CSRF),
  "Reject" button (→ `POST /api/admin/tags/{id}/reject` + CSRF, with confirm).
- **All tags table**: search/filter from the existing `GET /api/tags` (with
  `active_only=false`). Columns: name, category, popularity, status.
  Per row: "Set Category" (inline or popover input → `PATCH /api/admin/tags/{id}/category`),
  "View Aliases" (expand row → `GET /api/admin/tags/{id}/aliases` + add/delete inline),
  "Merge Into" (select target tag → `POST /api/admin/tags/{id}/merge-into/{target_id}`
  with confirm). The merge UI needs a tag picker for the target.

Backend endpoints used:
- `GET    /api/admin/tags/pending`
- `POST   /api/admin/tags/{id}/approve`
- `POST   /api/admin/tags/{id}/reject`
- `PATCH  /api/admin/tags/{id}/category`
- `GET    /api/admin/tags/{id}/aliases`
- `POST   /api/admin/tags/{id}/aliases`
- `DELETE /api/admin/tags/aliases/{alias_id}`
- `POST   /api/admin/tags/{id}/merge-into/{target_id}`
- `GET    /api/tags` (for the full tag list, with active_only=false)

### 5. Site capabilities page (`frontend/src/pages/admin/SiteCapabilitiesPage.tsx`)

A new admin page at `/admin/site-capabilities`.

- Table of all capability records: domain, can_scrape_metadata, can_scrape_images,
  requires_token (bool), is_manual_only (bool), last_probed_at, notes, has_token.
- Per row:
  - Toggle `is_manual_only` (inline checkbox or toggle → `PATCH` + CSRF).
  - Edit notes (inline editable text → `PATCH` + CSRF).
  - "Set Token" button → inline form for token input → `POST /{domain}/token` + CSRF.
  - "Clear Token" button (shown when `has_token=true`) → `DELETE /{domain}/token` +
    CSRF + confirm.
  - "Re-probe" button → `POST /{domain}/reprobe` + CSRF.
  - "Delete" button → `DELETE /{domain}` + CSRF + confirm.
- The token is NEVER shown back (the API never returns it). Only `has_token` flag
  is shown.

Backend endpoints:
- `GET    /api/admin/site-capabilities`
- `PATCH  /api/admin/site-capabilities/{domain}`
- `DELETE /api/admin/site-capabilities/{domain}`
- `POST   /api/admin/site-capabilities/{domain}/token`
- `DELETE /api/admin/site-capabilities/{domain}/token`
- `POST   /api/admin/site-capabilities/{domain}/reprobe`

### 6. API keys page (Settings → API Keys)

Check whether a per-user API keys page already exists. If not, create
`frontend/src/pages/ApiKeysPage.tsx` at `/settings/api-keys` (or integrate into an
existing settings page).

- List existing keys: `GET /api/api-keys` → table with label, last_used_at, active
  status, revoke button (→ `DELETE /api/api-keys/{id}` + CSRF + confirm).
- "Create API Key" form: label input → `POST /api/api-keys` + CSRF.
- On create: show the raw key in a one-time-display box with copy button and a
  "You will not see this again" warning. Key is NOT stored in state after modal close.

Backend endpoints:
- `GET    /api/api-keys`
- `POST   /api/api-keys`
- `DELETE /api/api-keys/{id}`

### 7. AppShell nav wiring

Add nav entries to `AppShell.tsx` (admin section):
- "Backups" → `/admin/backups`
- "Export" → `/admin/export`
- "Tag Admin" → `/admin/tags`
- "Site Capabilities" → `/admin/site-capabilities`

Add to user/settings section:
- "API Keys" → `/settings/api-keys` (or wherever the API keys page lives)

### 8. Router wiring (`App.tsx`)

Add `<Route path="/admin/backups" element={<BackupsPage />} />` etc. for every new page.

## Conventions to honor

- **UI stack** (mandatory): Tailwind + CSS-variable theme + minimal Radix
  (`react-dropdown-menu` / `react-slot` only) + `lucide-react` + TanStack Query +
  `apiFetch`/`apiFetchForm`. NO Mantine. NO toast library.
- Match the look of existing admin pages (same card/table/button classes).
- `npx tsc --noEmit` must be clean (zero errors).
- `vitest` for any non-trivial helpers (formatting, state logic). No need for
  component-level render tests.
- CSRF: all state-changing calls must pass the CSRF token (see how existing pages use
  `apiFetchForm` or the `x-csrf-token` header).
- No `git add -A`. No commit. No push. Prepare the tree and report back.

## Key backend API summary (for reference)

All routes are JSON unless noted. All admin routes require `require_admin`.
CSRF is required for all mutating (POST/PUT/PATCH/DELETE) calls.

```
# Backups
GET    /api/admin/backups
POST   /api/admin/backups/run
GET    /api/admin/backups/settings
PUT    /api/admin/backups/settings          body: {retention_count: int}
GET    /api/admin/backups/{id}/download     → binary download
DELETE /api/admin/backups/{id}

# Export
GET    /api/admin/export/catalog            → JSON download (streaming)

# Reindex
POST   /api/scheduled-jobs/library_reconcile_scan/run   → already wired in ScheduledJobsPage

# Tag admin
GET    /api/admin/tags/pending
POST   /api/admin/tags/{id}/approve
POST   /api/admin/tags/{id}/reject
PATCH  /api/admin/tags/{id}/category       body: {category: str | null}
GET    /api/admin/tags/{id}/aliases
POST   /api/admin/tags/{id}/aliases        body: {alias: str}
DELETE /api/admin/tags/aliases/{alias_id}
POST   /api/admin/tags/{id}/merge-into/{target_id}

# Site capabilities
GET    /api/admin/site-capabilities
GET    /api/admin/site-capabilities/{domain}
PATCH  /api/admin/site-capabilities/{domain}
DELETE /api/admin/site-capabilities/{domain}
POST   /api/admin/site-capabilities/{domain}/token   body: {token: str}
DELETE /api/admin/site-capabilities/{domain}/token
POST   /api/admin/site-capabilities/{domain}/reprobe

# API keys (per-user, not admin-only)
GET    /api/api-keys
POST   /api/api-keys                       body: {label: str}
DELETE /api/api-keys/{key_id}
```

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-27`, one-line
   `result`).
2. `git mv` into `prompts/done/`; create the dir if it doesn't exist.
3. Add `docs/decisions.md` entries (newest at top) for any non-obvious frontend
   decisions.
4. **Do NOT commit, push, or change branch.** Prepare the tree and report back with:
   - Complete file list (created/modified/moved).
   - Proposed one-line `feat:` commit message.
   - `npx tsc --noEmit` result.
   - `vitest` result.
   - Any decisions or limitations.
