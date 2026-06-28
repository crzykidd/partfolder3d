---
name: 2026-06-27-phase-7b-frontend
status: completed
created: 2026-06-27
model: sonnet            # coding
completed: 2026-06-27
result: All Phase 7b frontend work implemented: api.ts Phase 7 types+functions, ItemPage print history + share controls + include-history ZIP checkbox, PublicSharePage (outside AuthGuard), PrintStatsPage, ShareAuditPage, ImportsPage from-share-link panel, App.tsx + AppShell.tsx routes/nav; tsc clean; 109 vitest tests pass (13 new).
---

# Task: Phase 7b — Print history + sharing frontend

Add all frontend work that Phase 7a (backend) deferred. The backend is fully
implemented and tested; this prompt builds the matching UI. Covers PRD §9 (print
history UI on ItemPage + stats), §10 (share controls, public share page, audit),
§11 (include-print-history checkbox on ZIP download), and the from-share-link step
in the import wizard.

**Exit criteria:** owner can log a print (with gcode/photo upload) and see stats;
mint a share link from the item page, open it logged-out and browse/download; audit
log shows accesses; admin can revoke; import wizard accepts a share URL and presents
choices; TypeScript compiles clean (`npx tsc --noEmit`); vitest passes.

## Before you start

- Read `docs/decisions.md` (Phase 7 section, newest at top) for architecture choices.
- Read `PRD.md` §9, §10, §11.
- Read `CLAUDE.md` operating rules.
- Study the existing frontend conventions to match them exactly:
  - `frontend/src/lib/api.ts` — all API functions live here; match naming and pattern.
  - `frontend/src/pages/ItemPage.tsx` — this is the primary page to extend.
  - `frontend/src/pages/admin/` — admin pages for share management + audit.
  - `frontend/src/pages/ImportsPage.tsx` + `ImportWizardPage.tsx` — extend the import
    wizard with the from-share-link entry point.
  - `frontend/src/components/AppShell.tsx` — nav links; add "Print Stats" if appropriate.
  - `frontend/src/App.tsx` — route registration; add public share route + admin pages.
- **Backend endpoints already exist** (no backend changes needed unless you find a bug):
  - `GET /api/items/{key}/print-records` → list records
  - `POST /api/items/{key}/print-records` → create
  - `PATCH /api/items/{key}/print-records/{id}` → update
  - `DELETE /api/items/{key}/print-records/{id}` → delete
  - `POST /api/items/{key}/print-records/{id}/gcode` → upload gcode (multipart)
  - `POST /api/items/{key}/print-records/{id}/photo` → upload photo (multipart)
  - `GET /api/print-stats` → aggregate stats (totals, success rate, filament, most-printed)
  - `POST /api/items/{key}/shares` → mint per-design share link (body: `{label?, expires_in_days?}`)
  - `GET /api/items/{key}/shares` → list share links for item
  - `POST /api/admin/shares/site` → mint full-site share link (admin only)
  - `GET /api/admin/shares/site` → list full-site share links
  - `POST /api/shares/{share_id}/revoke` → revoke a link
  - `GET /api/shares/{share_id}/audit` → audit events for a link
  - `GET /api/public/share/{token}` → public item view (no auth required)
  - `GET /api/public/share/{token}/files/{path}` → public file stream
  - `GET /api/public/share/{token}/zip` → queue public ZIP (no auth)
  - `GET /api/public/share/{token}/catalog` → full-site catalog browse (no auth)
  - `GET /api/items/{key}/zip?include_history=true` → ZIP with print history (existing, extended)
  - `POST /api/import-sessions/from-share-link` → create import session from share URL
    Body: `{share_url, library_id, include_public_notes?, include_gcode?, include_photos?, include_settings?}`

## Working tree check

Run `git status --porcelain` before editing. The tree should be clean on `dev` (Phase 7a
was committed by the orchestrator). Surface any unexpected dirty files before touching them.

## What to do

### 1. api.ts — add Phase 7 API functions

In `frontend/src/lib/api.ts`, add:
- `PrintRecord` interface (id, item_key, note, visibility, date, printer, material,
  filament_color, nozzle_diameter, layer_height, supports, success, rating,
  filament_length_mm, filament_weight_g, estimated_print_time_s, gcode_file_path,
  print_photo_path, logged_by_id, created_at, updated_at)
- `PrintStats` interface (total_prints, successful_prints, failed_prints, success_rate,
  total_filament_mm, total_filament_g, avg_print_time_s, most_printed — top items list)
- `ShareLink` interface (id, token, scope, item_id, label, expires_at, revoked,
  revoked_at, created_by_id, created_at)
- `ShareAuditEvent` interface (id, share_link_id, event_type, ip_address, user_agent,
  created_at)
- `PrintRecordIn` / `PrintRecordPatch` interfaces matching backend schemas
- API functions: `listPrintRecords`, `createPrintRecord`, `updatePrintRecord`,
  `deletePrintRecord`, `uploadGcode`, `uploadPrintPhoto`, `getPrintStats`
- Share functions: `mintItemShare`, `listItemShares`, `mintSiteShare`, `listSiteShares`,
  `revokeShare`, `getShareAudit`
- Public functions: `getPublicShare`, `getPublicCatalog`
- Import: `importFromShareLink(body: ShareLinkImportRequest): Promise<ImportSession>`
- Update `queueZip` to accept `{ includeHistory?: boolean }` and pass
  `?include_history=true` when set

### 2. ItemPage — print history section

In `frontend/src/pages/ItemPage.tsx`, add a collapsible **Print History** section below
the files section:
- List print records: public/private badge (green/gray), date, success/fail chip, rating
  (1–5 stars display), parsed filament + time if available, note snippet
- **Add Record** button → inline form or modal: visibility, date, printer, material,
  nozzle_diameter, layer_height, supports, success, rating, note; then optionally upload
  gcode and/or photo
- After record created: show gcode upload button → file input → `POST …/gcode`;
  show photo upload button → file input → `POST …/photo`
- Parsed gcode stats (filament, time) appear on the record card after upload
- Edit + delete for each record (owner/admin only)
- Empty state: "No print records yet. Log your first print above."

### 3. Share controls on ItemPage

In `ItemPage.tsx`, add a **Share** section (owner/admin only):
- List existing share links: label, token (first 8 chars + "…"), expiry countdown,
  revoked badge, copy-link button (`/share/{token}` URL)
- **Mint share link** button → small form: optional label, optional expiry (days; blank =
  instance default). On success, copy the new link to clipboard automatically and show a
  toast.
- Revoke button per link (confirm dialog)

### 4. Public share page

Add `frontend/src/pages/PublicSharePage.tsx` — **no AuthGuard**, unauthenticated route:
- `GET /api/public/share/{token}` → show design: title, description, tags, images,
  **public** print records only (badge shows "public"), files list
- Download buttons: single file `GET /api/public/share/{token}/files/{path}` (direct URL),
  ZIP `POST /api/public/share/{token}/zip` → poll → download (same pattern as ItemPage
  ZIP flow but using the public endpoints)
- If the response scope is "full_site", show the shared catalog instead:
  `GET /api/public/share/{token}/catalog` → item grid (read-only, same components as
  CatalogPage but no auth, no favorite/edit controls)
- Expired/revoked links → show a friendly "This link is no longer available" message (do
  NOT show error details)
- The page intentionally shows NO authenticated controls (no edit, no admin)

Register this route **outside** `<AuthGuard>`:
```tsx
<Route path="/share/:token" element={<PublicSharePage />} />
```

### 5. Print stats page (admin)

Add `frontend/src/pages/admin/PrintStatsPage.tsx`:
- Call `GET /api/print-stats`
- Show stat cards: Total Prints, Success Rate %, Total Filament (m), Avg Print Time
- "Most printed" table: item title + key (link to ItemPage) + print count
- Add to `AppShell` admin nav and register route `/admin/print-stats`

### 6. Share audit page (admin)

Add `frontend/src/pages/admin/ShareAuditPage.tsx` (or a panel on a "site shares" page):
- Admin view: list all full-site share links (`GET /api/admin/shares/site`), revoke each
- Click a link → show its audit events: type, timestamp, IP, user-agent table
- Register route `/admin/shares`

### 7. Download ZIP — include-print-history checkbox

On `ItemPage.tsx`, the existing ZIP download flow should gain a checkbox:
- "Include print history" (default OFF). When checked, calls
  `queueZip(key, { includeHistory: true })`.
- Tooltip: "Adds a print-history.json to the ZIP. Public records always included;
  private records included only for your own download."

### 8. Import wizard — from-share-link step

In `frontend/src/pages/ImportsPage.tsx` (or a new entry point if the page lists
sessions), add a **"From share link"** button/section:
- Input: share URL text field
- Library selector (reuse existing library select from import wizard)
- Checkboxes: "Include public notes" (default on), "Include gcode files" (default off),
  "Include print photos" (default on), "Include structured settings" (default on)
- Submit → `POST /api/import-sessions/from-share-link` → on 201, redirect to
  `/import/{sessionId}` (the existing wizard picks up from there)

### 9. TypeScript + tests

- `npx tsc --noEmit` must pass clean — no `any` escapes, type all API responses.
- Vitest: add tests for non-trivial logic: time-formatting helper (seconds → "2h 3m"),
  filament formatting (mm → "1.23 m"), public share page shows "no longer available"
  for a 403 response.

## Conventions to honor

> **IMPORTANT — the stack is NOT Mantine.** This project uses **Tailwind CSS + a
> CSS-variable theme** (the shadcn-style `bg-primary`/`text-muted-foreground` etc. tokens),
> minimal Radix (`@radix-ui/react-dropdown-menu`, `@radix-ui/react-slot` only — no Dialog/
> Tabs packages), and **`lucide-react`** icons. **Do not add Mantine or any new UI library.**
> Read existing pages (`ItemPage.tsx`, the `pages/admin/*` pages, `AddAssetModal.tsx`) and
> replicate their exact patterns — custom Tailwind overlay modals, tab bars, badges, tables.

- TanStack Query (`useQuery` / `useMutation`) for all server state.
- **All requests go through the `apiFetch` wrapper from `api.ts`** (and `apiFetchForm` for
  multipart) — it already injects the `X-CSRF-Token` header. Do **not** invent a `useCsrf()`
  hook or `getCsrfToken()`; follow how existing mutations call `apiFetch`/`apiFetchForm`.
- Admin routes follow the existing `<AdminGuard>` pattern in `App.tsx`; protected routes use
  `<AuthGuard>`. **Public pages are registered OUTSIDE both guards.**
- **No toast library exists** (`notifications.show` is NOT available). For user feedback after
  an action (e.g. copy-link), use the lightweight inline pattern already used in the codebase
  (e.g. the ZIP-download/copy-path feedback on existing pages) — a transient inline message /
  button-label swap — rather than a global toast. Match what the item/catalog pages already do.
- **No hardcoded colors** — use the existing Tailwind theme tokens / CSS variables.
- The public share page must NOT import anything that would trigger auth redirects (no
  AuthGuard, no calls to authenticated-only endpoints, no auth-context dependency).

## When done

1. Update this file's frontmatter: `status: completed`, `completed: 2026-06-27`,
   one-line `result`.
2. `git mv` this file into `prompts/done/`.
3. Add any non-obvious frontend decisions to `docs/decisions.md` (newest at top).
4. **You are a spawned agent: do NOT commit, push, or change branch.** Prepare the
   tree and report back with:
   - Complete file list (new + modified)
   - Proposed commit message: `feat: Phase 7b — print history + sharing frontend`
   - TypeScript check result (`npx tsc --noEmit`)
   - Vitest result
   - Anything you could not finish + why
