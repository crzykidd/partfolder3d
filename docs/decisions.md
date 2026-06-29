# Decisions

ADR-style log of non-obvious decisions, newest at top.

## 2026-06-29 — Phase 16: per-object static analysis (object_analysis)

### Volume-estimate formula and settings

Grams = `volume_cm3 × density_g_cm3 × (infill_pct / 100)`.  trimesh volumes are in mm³
for mm-unit meshes, so divide by 1000 to get cm³.  Two tuneable settings live in the
`settings` table: `estimate.filament_density_g_cm3` (default 1.24 g/cm³, typical PLA) and
`estimate.infill_pct` (default 15 %).  Field `est_method='volume'` is reserved so a future
slicing-based approach can be added without a schema change.

### Non-watertight mesh fallback

`_safe_volume_cm3` tries in order: (1) check `is_watertight` → use `abs(mesh.volume)/1000`;
(2) call `mesh.fill_holes()` and recheck; (3) use `mesh.convex_hull.volume/1000` as upper
bound; (4) return None.  Any result from steps 2–4 sets `low_confidence=True`.  The
`LOW CONF` badge on the frontend communicates this to the user.

### 3MF color parsing approach

Colors are extracted from `3D/3dmodel.model` inside the ZIP by lxml.  Priority:
- Per-triangle `p1` refs on `<triangle>` elements → collect distinct `displaycolor` hex
  values from the referenced material group.
- Per-object `pid`/`pindex` on `<object>` elements → single color per object.
- Bambu/Orca vendor paint (`paint_color`/`mmu_segmentation` attributes on triangles) →
  best-effort only; distinct non-zero `paint_color` values are counted as a proxy color
  count; actual per-segment decoding is not implemented (bitfield format is undocumented).

### Per-file SHA-256 cache key

`File.object_analysis` is a JSONB blob keyed by `source_hash` (the file's current sha256).
The worker skips re-analysis if the stored hash matches the current `File.sha256`.  This
piggybacks on the existing drift-check pipeline — no extra disk I/O on unchanged files.

### Object-to-color matching strategy (3MF)

trimesh may name Scene geometries as the original `<object id>` or as `'object_<id>'`.
The color map is keyed by id string.  Matching tries: (1) exact name match; (2) strip the
`object_` prefix; (3) positional fallback (XML order = Scene order).

## 2026-06-29 — Phase 15: local-modification tracking

### Baseline-diff approach

`source_baseline` is a JSONB map of `{ relative_path → sha256 }` for model-role files only,
captured at `commit_import_session` (only when the item has a `source_url`).  The reconcile
engine (behavior e) computes the same map from current DB File rows and compares; any
difference (path set or hash) sets `locally_modified=True`.  Comparison is done on DB-stored
hashes (already maintained by the re_render behavior), so baseline detection piggybacks on
the existing drift-check pipeline without extra disk reads.

### Effective-state rule (override vs auto)

`modified_override` takes precedence over `locally_modified`:
- `'modified'` → `is_modified = True` always
- `'original'` → `is_modified = False` always
- `null`        → `is_modified = locally_modified` (auto)

The override is persisted in the DB and written to the sidecar.  It is NOT reset when
the scan engine runs, so users can permanently mark an item as "original" even if future
scans would disagree (e.g. a deliberate, accepted customisation).

### What counts as "modified" (model files only)

Only files with `role=model` are included in the baseline and the comparison.  Renders,
thumbnails, sidecars, print photos, and gcode files are excluded.  Rationale: these are
either derived (renders), per-user (photos), or printing artefacts — none represent the
"design content" that was downloaded from the source.

### source_version: captured but unused

`source_version` (String nullable) is added to Item for the future type-2 upstream-update
check ("a newer version is available online").  The import session does not currently scrape
this field (scraper integration is best-effort; left for the future phase).  The column exists
so the future phase can add it without another migration.

### Sidecar: modified_state block (backward-compatible)

When `source_url` is present, `build_sidecar` writes a `modified_state` block:
```yaml
modified_state:
  locally_modified: <effective bool>
  modified_at: <ISO-8601 UTC or null>
  source: <source_url>
```
The reader ignores unknown keys, so old sidecars without the block parse cleanly with
`modified_state=None`.  The block is intentionally omitted for sourceless items (no
`source_url`) to keep the sidecar lightweight.

### Public share: no baseline hashes

The `PublicItemOut` schema includes `is_modified` (the effective boolean) and the existing
`source_url` / `source_site`.  The raw `source_baseline` dict (path→sha256 pairs) is NOT
exposed publicly — it reveals filesystem layout and is irrelevant to share consumers.

### Type-2 upstream-update check: out of scope

Checking whether a newer version is available at the source URL (type 2) is explicitly
excluded from this phase.  `source_version` is captured as a stub; the actual network
re-check requires a background job, per-site scraping logic, and user notification — all
left for a dedicated future phase.

---

## 2026-06-28 — Tag approval refresh fix; AI suggestion click-to-add UX; new tags created as pending

### Tag approval: two-screen approach (option a — keep both, make identical)

Two screens can approve pending tags: `/admin/pending-tags` (PendingTagsPage) and the
pending section of `/admin/tags` (TagAdminPage). The decision is to **keep both** (option a
from the prompt) and make their behavior and invalidation identical:

- Both screens now use `listAdminPendingTags()` via `GET /api/admin/tags/pending` (the
  admin endpoint that filters to `status=pending` only).
- Both use `queryKey: ['admin-tags-pending']` so cache invalidation is consistent.
- Both mutations (`adminApproveTag` / `adminRejectTag`) invalidate `['admin-tags-pending']`,
  `['admin-tags-all']`, and `['tags']` on success.
- PendingTagsPage previously used `listAllTags({ active_only: false })` with key
  `['tags', 'pending']` and invalidated `['tags']` — this meant the approved tag was never
  removed from the list (the endpoint returns all tags regardless of status). Fixed by
  switching to the pending-only endpoint.
- Cross-link from TagAdminPage's pending section → PendingTagsPage for the focused view.

The existing DuplicateDetectSection in PendingTagsPage is unchanged and keeps a separate
all-tags query (`['tags', 'all-for-dup-detect']`) for its fuzzy comparison.

### Import commit: new tags created as pending

Root cause: `_get_or_create_tag` in `routers/items.py` defaulted to `status=active` for
any newly-created tag. When `commit_import_session` called `_attach_tags(db, item, confirmed_tags)`,
any confirmed tag not yet in the database was created as `active`, bypassing the approval queue.

Fix: added a `status: TagStatus = TagStatus.active` parameter to `_get_or_create_tag` and a
corresponding `new_tag_status: TagStatus = TagStatus.active` parameter to `_attach_tags`.
The commit path in `import_sessions.py` now calls `_attach_tags(..., new_tag_status=TagStatus.pending)`.
Tags that already exist keep their current status unchanged; only brand-new tags created at
commit time become pending. Existing callers (`create_item`, `update_item`) are unaffected
since their defaults remain `active`.

### AI tag suggestion card: click-to-add with calm messaging

Previous UX: AI suggestions were presented as passive chips with a small `+` button; added
chips stayed visible in the suggestion box (only showing a checkmark); wording read "will need
admin approval after commit" which sounded like a blocker.

New UX in `ImportWizardPage.tsx` (Tags step):
- Suggestions are shown as interactive chips: clicking the entire chip adds it to Confirmed
  Tags AND removes it from the suggestion box (filtering by `!confirmed.includes(tag)`).
- Two labeled groups: **Matches your tags** (canonical, solid border) and
  **New suggestions** (dashed border).
- "Add all" button appears when each group has more than one chip.
- Calm note under "New suggestions": "Added now — your item gets tagged immediately. New tags
  are reviewed by an admin before joining the global tag cloud." This is accurate: the item
  gets the tag immediately (via `item_tags` link); only the Tag row is pending for the cloud.
- The "Suggested tags" section below (from session `tag_state.pending`) was relabeled from
  "need approval after commit" to "not yet in the catalog — accept or skip" for consistency.

## 2026-06-28 — Starter tag set + idempotent seed; cheap AI status probe; auto-suggest-once

### Starter tag set and idempotent seed

A curated vocabulary (57 tags, 7 categories: type, function, feature, theme, process,
audience, mechanical) lives in `backend/app/tags_defaults.py` as `(name, category)` pairs
in the project's canonical form (lowercase/slug). `POST /api/tags/load-defaults` (admin +
CSRF) inserts missing ones as `status=active` in one batch snapshot query, returning
`{added, skipped}`. It never touches existing tags — pure insert-if-absent — so it is safe
to call on a fresh instance or re-run at any time. Without active tags the AI suggest
endpoint's canonical-matching has nothing to match against; this seeds that set.

### Cheap `GET /api/ai/status` replaces billed probe

The import wizard's Title step previously called `POST .../ai/cleanup-description` on
mount just to detect whether a provider was available. That call spends real tokens and
writes an `ai_usage` row even if the user never clicks "Clean up (AI)". The new
`GET /api/ai/status` endpoint only calls `get_enabled_provider` — a single DB query with
no AI or network call — and records no usage. Both the Title step and the Tags step now
gate their AI buttons through this endpoint.

### Auto-suggest-once on the Tags step

When the wizard reaches the Tags step, `getAiStatus()` is called once (guarded by a
`useRef` so it never fires again on re-render). If a provider is available, `aiSuggestTags`
is automatically invoked, showing a loading state and populating the suggestions card on
success. The manual "✦ Suggest tags (AI)" button is preserved for re-running. Errors from
the auto-suggest are surfaced through the existing error state and auto-clear after 3 s;
they never block the manual tag flow.

## 2026-06-28 — Quick Start page

Quick Start (`/quick-start`) is a standalone page (not embedded in SettingsPage) with Aurora step cards linking to real routes; three steps carry live status badges via cheap existing queries (`listLibraries`, `getPathPrefix`, `listAiProviders`) — all best-effort with no badge on error; admin-only steps (libraries, AI, invites, backups, sharing) are role-filtered client-side.

## 2026-06-28 — Path style toggle (feat-path-style-toggle)

Explicit Windows (`\`) / Linux·macOS (`/`) path style toggle in Settings normalizes the saved prefix string's separators via `toPathStyle(path, style)` in `catalog-utils.ts`; `rewritePath`'s existing inference (checks whether the prefix contains `\`) is unchanged, so all previously saved prefixes continue to work without any backend or migration changes.

## 2026-06-28 — Tags step: pending-tag-on-Next confirmation

Chosen UX: **inline alertdialog panel** (not a modal) with three choices — "Add & continue", "Discard & continue", "Cancel" — shown only when the tag input has non-empty, non-duplicate text when Next is clicked; duplicates and empty inputs still advance silently. A `pendingTagNextAction` pure helper was added to `import-utils.ts` so the decision logic is unit-testable without rendering.

## 2026-06-28 — Phase 14: render Image reconcile, enum migration, upload storage, sidecar exclusion

### Render → Image reconcile approach

`render_item` (arq worker) now calls `_reconcile_render_images` after rendering. The
function is a **best-effort step** wrapped in try/except; a DB hiccup does not fail
the job. It:
- Scans `renders/*.png` on disk (the SHA-keyed cache) to build the current set
- Deletes `source=render` Image rows whose PNG no longer exists (and removes the orphaned
  PNG if present)
- Creates Image rows for new PNGs (no duplicates: match by `(item_id, source=render, path)`)
- Flushes before setting the default

### Default-image rule for renders

After reconcile: if the item has **no** `is_default` image at all, the first render row
(lowest order) is promoted to default, so the catalog grid shows a thumbnail. If a
curated (`scraped`/`uploaded`) image is already default, it is left untouched. Render
images sort after curated images (order > max curated order).

### `_reconcile_render_images` optional session parameter

The function accepts `_db: AsyncSession | None`. In production (`_db=None`) it opens and
commits its own `SessionLocal`; when an AsyncSession is injected (tests) it runs within
that session and flushes without committing. This lets unit tests call the function via
the test session's rollback-isolated transaction without a FK violation.

### Sidecar exclusion of render images

`_build_sidecar_data` (items router) already iterated `images_list` to build the sidecar.
It now filters with `if img.source != ImageSource.render`. Render rows are DB-only —
they are derived/regenerable from the on-disk PNGs; excluding them keeps the sidecar
portable and curated.

### Enum migration 0014: non-transactional ADD VALUE + no-op downgrade

`ALTER TYPE imagesource ADD VALUE 'render'` cannot run inside a Postgres transaction.
Migration 0014 uses `op.get_context().autocommit_block()` to issue the DDL outside any
surrounding transaction. The `DO $$ … END $$` block makes the upgrade idempotent
(checks `pg_enum` before adding). Downgrade is a documented no-op — Postgres cannot
remove enum values without recreating the type, and the extra value is harmless when
unused.

### Image upload storage location

Uploaded images are stored in `<item_dir>/images/<random_hex>.<ext>` (16-byte secrets
token, original extension). This mirrors where scraped images live. Path traversal is
prevented by validating content-type against an allowlist and generating the filename
server-side (never using the original upload filename in the path).

## 2026-06-28 — 3MF rendering needs lxml (trimesh optional extra)

Once the render backend worked, **3MF** renders failed with "No module named 'lxml'". trimesh's
3MF loader parses the zipped XML via `lxml.etree`, but `lxml` is an OPTIONAL trimesh extra not
pulled in by the base install (STL/OBJ/PLY parse without it). Added `lxml==6.1.1` to
requirements; needs an image rebuild. 3MF is a v1 format → required, not optional. Same lesson as
the render fix: exercise each format path against a real file in the actual image.

## 2026-06-28 — Job retry: retriable types and re-enqueue behaviour

### Retry map

`POST /api/jobs/{id}/retry` re-enqueues a failed job.  Only one job type is
currently retriable:

| `Job.type` | arq task | args extracted from payload |
|------------|----------|-----------------------------|
| `"render"` | `render_item` | `payload["item_id"]` (int) |

All other types return 400.  The rationale:

- **render** is the only type whose arq task (`render_item`) creates a `Job` row
  via `create_job()` in the production worker code.  Every failed render job will
  have a valid `{"item_id": N}` payload and can be safely re-submitted.
- **build_zip_bundle** / **exec_scheduled_job** / **process_import_session** /
  **apply_review_item** do NOT create `Job` rows — they use their own state models
  (`DownloadBundle`, `ScheduledJob`, `ImportSession`, `ReviewItem`).  No rows of
  those types should appear in the `jobs` table in production.
- A "zip_bundle" type was used in tests but has no production code path, so it is
  not added to the map.

### Re-enqueue behaviour

The old failed `Job` row is **left intact** (preserved as history).  The retry
re-enqueues the arq task; when that task runs it calls `create_job()` internally
and creates a **new** `Job` row.  This is consistent with normal first-run
behaviour, keeps the failure audit trail, and avoids any ambiguity about
timestamps or status transitions on the original row.

## 2026-06-28 — AI usage tracking: AiUsage model, AiCallResult refactor, summary API, cost estimates

### AiUsage model shape

`ai_usage` table (migration 0013): `id`, `created_at` (timestamptz, indexed), `provider`
(str), `model` (str | null), `action` (str: `suggest_tags` | `cleanup_description` |
`summarize` | `test`), `input_tokens` (int), `output_tokens` (int), `total_tokens` (int),
`user_id` (nullable FK → users, SET NULL on delete), `success` (bool).

The `created_at` index is the key: all windowed queries (24h/7d/30d) filter on it.

### AiCallResult refactor + str-normalization for the test seam

The real callers (`_call_anthropic_real`, `_call_openai_real`) were returning `str | None`.
They now return `AiCallResult | None` — a small dataclass carrying `text`, `input_tokens`,
`output_tokens`. This keeps token data coupled to the response without threading extra
parameters through every function.

The injectable test seam (`_anthropic_caller` / `_openai_caller` module-level vars) kept
backward-compat by normalizing in `_dispatch`: if the caller returns a `str`, it wraps it
as `AiCallResult(text=str_val, input_tokens=0, output_tokens=0)`. This means the 20+
existing Phase 8 tests that patch the callers to return plain strings continue to pass
unchanged. Only new tests that need to assert on token counts inject `AiCallResult` objects.

`AiTagResult` and `AiTextResult` grew `input_tokens: int = 0` and `output_tokens: int = 0`
fields so action endpoints can read them without touching the client layer. Defaults of 0
are backward-safe for error paths and test-seam paths.

### Record-failures-swallowed contract

Usage recording happens in `ai_actions.py` after each action call. The `_record_usage`
helper wraps its work in a `try/except` that logs and continues. Additionally, each
endpoint's call to `await _record_usage(...)` is wrapped in its own `try/except` as a
belt-and-suspenders outer guard — so even if `_record_usage` itself throws unexpectedly
(e.g., if mocked to raise in tests), the AI feature still returns HTTP 200.

The contract: AI usage recording **can never break or delay an AI feature**. Failures are
always logged and never surfaced to callers.

### Summary-window query approach

`GET /api/ai-usage/summary` runs three SQL queries (24h / 7d / 30d) over the indexed
`created_at` column. Each query aggregates `COUNT`, `SUM(input_tokens)`,
`SUM(output_tokens)`, `SUM(total_tokens)` per window. A per-provider-model query within
each window feeds the cost estimate. A 30d provider/model grouped query builds the
breakdown table.

### Estimated cost in USD

`backend/app/ai/pricing.py` holds a local pricing table keyed by `(provider, model)`.
Seeded with current Claude rates. Ollama is always $0. OpenAI models are deliberately
**not seeded** — rates change frequently and vary by model; unknown models yield `null`
cost (shown as "—" in the UI) rather than a misleading $0. The table is easy to extend.
A `claude-opus-*` wildcard fallback covers future Claude Opus variants not yet listed.
The API and UI label costs as **estimates**; actual billing may differ.

## 2026-06-28 — Headless render fix in the Docker image (X11 libs + PyOpenGL override)

Phase-4 render worked on the host but `get_backend()` returned `none` in the running container.
Two image-level causes, found by probing the live container:
- **`libXrender.so.1` (and libXi) missing** → `import pyrender` (via pyglet) and `import vtk`
  both crashed, so no backend could even import despite libGL/EGL/OSMesa being present. Fix: add
  `libxrender1` + `libxi6` to the Dockerfile apt set.
- **pyrender hard-pins `PyOpenGL==3.1.0`** (lacks `OSMesaCreateContextAttribs`, needs >=3.1.7);
  `PyOpenGL>=3.1.0` in requirements can't override the `==` pin, and `>=3.1.7` there would make
  pip conflict with pyrender. Fix: a separate `RUN pip install "PyOpenGL>=3.1.7"` AFTER the
  requirements install in the Dockerfile.
After both, a clean rebuilt image renders a real PNG (backend `egl`). Lesson: verify render in
the actual image, not a host venv.

## 2026-06-28 — UI B4 (final): Auth/public + remaining authenticated pages — Aurora revamp COMPLETE

### UI revamp complete

All real application pages are now on the Aurora aesthetic. The revamp series is done:
- **A1** — Shell (SideNavShell, TopNavShell, StatStrip, QuickImportRail)
- **B1** — Catalog + Item pages
- **B2** — Import wizard
- **B3a** — Admin ops (Jobs, ScheduledJobs, Issues, Changes, Reviews, ShareAudit, PrintStats, PendingTags, TagAdmin, SiteCapabilities)
- **B3b** — Admin settings (Users, Invites, PasswordReset, AiProviders, Backups, Export, Libraries, SettingsPage)
- **B4 (this pass)** — Auth/public pages + remaining authenticated pages

The `frontend/src/pages/examples/` directory is retained as a reference/prototype.

### Group 1 — standalone Aurora screens (public/auth, outside shell)

`LoginPage`, `SetupPage`, `InviteAcceptPage`, `ResetPasswordPage`, `PublicSharePage` all use
a full-viewport `linear-gradient(135deg, var(--aurora-bg-from), var(--aurora-bg-to))` background
with a centered glass card (`var(--aurora-card)`, `backdropFilter: blur(20px)`, `borderRadius: 16`).
A compact "PF" brand mark (teal accent square) appears above the card on auth pages.

`PublicSharePage` gets a top bar with the PF wordmark and a "Public Share" badge, making it
polished for first-impression public visitors.

**LoginPage/SetupPage logic preserved byte-for-byte**: `setQueryData(['setupStatus'], …)` and
`invalidateQueries({ queryKey: ['me'] })` calls are unchanged; only markup/styling changed.

### Group 2 — authenticated pages (inside shell, using @/components/ui primitives)

`ApiKeysPage` — `AdminPage + PageHeader + Card + DataTable/TableRow/Td + Button`. The copy-once
`KeyCreatedDialog` is restyled as an aurora glass overlay (no Radix, same pattern as B3b dialogs).

`CreatorPage` / `MyCreationsPage` — `AdminPage + PageHeader + EmptyState + Pagination`. Item cards
use the B1 aurora catalog card pattern (glass bg, teal hover glow) and are `<Link>` elements.

`VersionPage` — `AdminPage + PageHeader + Card + Card(accent)`. Displays the "PF" brand mark inline
and shows the backend version as a monospace teal-tinted pill.

### Tags and Favorites are CatalogPage routes (already done in B1)

Tags browse and Favorites filter are URL params on `/catalog` (not standalone pages), so they were
restyled as part of B1. No separate page needed.

### No new dependencies added

All pages use only the existing `@/components/ui` primitives, `lucide-react`, TanStack Query,
and React Router. No Mantine, no toast, no new packages.

## 2026-06-28 — UI B3b: Remaining admin/settings pages Aurora restyle

### One new primitive: `AuroraToggle`

Added `AuroraToggle` to `frontend/src/components/ui/Button.tsx` (exported from `index.ts`) because
two pages (`AiProvidersPage`, `SiteCapabilitiesPage`) need a visual boolean toggle for "enabled" /
"is_manual_only" states. The `AuroraToggle` is a `role="switch"` button that uses `--aurora-accent`
when checked and `--aurora-glass` when unchecked, matching the overall aurora theme. It replaces the
original CSS-class-based Tailwind toggle pattern.

### Dialogs styled inline (no Radix)

`InvitesPage` and `PasswordResetPage` both use a `CopyUrlDialog` overlay. Styled with CARD_STYLE
inline — no Radix `Dialog`, no external dep. The overlay + card approach matches the existing
site-capabilities token panel pattern.

### `@tanstack/react-table` removed from `UsersPage`

The original `UsersPage` used `@tanstack/react-table` for its table, which was unnecessary
given the `DataTable`/`TableRow`/`Td` primitives from B3a. B3b removes the `react-table` usage
and renders the 5-column user table directly via the shared primitives.

### `BackupsPage` warning callout: custom amber inline style (not Card accent)

The `Card accent` variant is teal-tinted (for info callouts). The backup warning requires amber/
orange to convey danger. Used a custom inline style with `rgba(245,158,11,…)` amber tones + a
border width of 2px (slightly thicker than normal 1px cards) to ensure the callout stays visually
loud. The `AlertTriangle` (lucide) icon reinforces urgency.

### `SettingsPage`: section headers as plain divs (not `SectionHeader`)

The `SectionHeader` primitive is designed for within-card section labels (small uppercase, 11px).
The settings page uses larger section groupings that sit above cards (like h2). These are styled
as plain 15px/700-weight divs to match the B3a `IssuesPage` / `ShareAuditPage` page-level
section approach, keeping `SectionHeader` for inside-card use only.

## 2026-06-28 — UI B3a: Operations admin pages Aurora restyle + shared primitives

### Shared Aurora admin primitives introduced (reuse in B3b)

Seven files created under `frontend/src/components/ui/` and exported from `index.ts`:

| Export(s) | File | Purpose |
|---|---|---|
| `AdminPage`, `PageHeader` | `AdminPage.tsx` | Page wrapper (flex-col) + header (title, description, meta, actions slot) |
| `Card`, `SectionHeader`, `CARD_STYLE`, `CARD_ACCENT_STYLE` | `Card.tsx` | Aurora glass card/panel; `accent=true` for teal-tinted callouts |
| `Badge`, `BadgeVariant` + 5 variant helpers | `Badge.tsx` | Status/severity/behavior badge; semantic colors via Tailwind `dark:` variants; `muted`/`accent` via inline aurora vars |
| `Button`, `FilterPill` | `Button.tsx` | `primary`/`ghost`/`danger` buttons; `FilterPill` for toggleable filter pills (active = aurora accent) |
| `DataTable`, `TableRow`, `Td`, `Pagination` | `DataTable.tsx` | Aurora card table wrapper with thead/loading/empty; hover rows; `Pagination` component |
| `EmptyState` | `EmptyState.tsx` | Icon + title + description empty state |
| `Field`, `AuroraInput`, `AuroraSelect` | `Field.tsx` | Form field with uppercase label; aurora-styled input/select with onFocus/onBlur focus ring |

B3b should `import { … } from '@/components/ui'` for all the above.

### Style approach: mixed Tailwind layout + inline aurora vars

B3a uses Tailwind classes for layout/spacing (`flex`, `gap-*`, `grid`, etc.) and
inline `style={{ ... }}` with `var(--aurora-*)` CSS vars for theming (color,
background, border, shadow). This matches the shell pattern and is slightly more
class-based than B1/B2's pure-inline approach, improving maintainability for the
table and form primitives repeated across many pages. The `Badge` component uses
Tailwind `dark:` variants for semantic colors (green/red/amber/blue/violet/orange)
— the cleanest approach for a fixed variant set.

### DataTable: zero deps, composable children

`DataTable` accepts `columns: string[]` for `<thead>` and `children` for `<tbody>`.
Loading and empty states render as colspan rows; `TableRow`/`Td` helpers add hover
states and consistent padding. `Pagination` is a separate component so pages can
place it independently. No virtual scrolling added — all pages use server-side
pagination at ≤ 50 rows per page.

### Pages restyled (feature parity, no backend changes)

`JobsPage`, `ScheduledJobsPage`, `IssuesPage`, `ChangesPage`, `ReviewsPage`,
`PrintStatsPage`, `ShareAuditPage` — all behavior, endpoints, routes, query keys,
and polling intervals preserved. `ReconcileModesCard` in ReviewsPage uses `Card`
and `FilterPill` for the Auto/Review toggles (same UX, aurora-styled).

### Untouched

Shell, B1 (Catalog/Item), B2 (Import), auth/public pages, examples, and all B3b
admin pages (Users, Invites, PasswordReset, AiProviders, SiteCapabilities, Backups,
Export, TagAdmin, PendingTags, Settings) are untouched.

---

## 2026-06-28 — UI B2: import flow Aurora restyle

### Inline-style-first approach (matching B1 pattern)

All three B2 files (`ImportWizardPage.tsx`, `ImportsPage.tsx`, `AddAssetModal.tsx`) adopt
the same inline-style + `var(--aurora-*)` approach established in B1's
`CatalogPage.tsx` / `ItemPage.tsx`. Tailwind utility classes are kept only for
animation (`animate-spin`, `animate-pulse`) and accessibility (`sr-only`) — everything
else is inline CSS using the Aurora design tokens defined in `index.css`. This matches
B1 exactly and avoids class-name drift.

### Aurora stepper with labels below circles

The `StepProgress` component uses a `flex` row with alternating circle columns and
connector lines. Connector `marginTop: 15` centres it at the midpoint of the 32 px
circles (half-height minus 1 for border). Step labels sit below each circle inside the
column div, keeping the connector anchored to the circle center while labels extend
downward. Completed steps show a `Check` icon (from lucide-react — already a dep).

### Focus handling on aurora inputs

Each Aurora-styled `<input>`, `<textarea>`, and `<select>` element has inline `onFocus`
/ `onBlur` handlers that set `borderColor` and `boxShadow` to aurora pill values.
This gives a visible keyboard-focus ring without a CSS class or index.css change, and
matches the approach used in CatalogPage's search wrapper.

### AI-assist buttons use ✦ text glyph

The "Clean up (AI)" and "Suggest tags (AI)" buttons use a `✦` glyph prefix instead of
importing a Sparkles icon. The glyph keeps the aurora teal text colour from the
ghost-button style, avoids adding a new icon to the import set, and is semantically
neutral (no screenreader issues since the button label carries the meaning).

### AddAssetModal drop-zone accessibility

The drop-zone `<div>` has `role="button"`, `tabIndex={0}`, and `onKeyDown` handling for
Enter/Space so keyboard users can open the file picker. Previously it was only
click-accessible.

### ImportsPage session table — no `<tbody>` row border on first row

Aurora table rows use `borderTop` (not `borderBottom`) on each `<tr>` so the header
bottom line is provided by the `thead` glass background's natural bottom edge.
The first row in `<tbody>` gets a `borderTop` matching `--aurora-divider`; this avoids
a doubled line where header meets body.

---

## 2026-06-28 — Libraries management + dev library mount

### Dev library mount convention

`./private_data/data/library` is bind-mounted to `/library` in both the backend
and worker containers in `docker-compose.dev.yml`. The path is gitignored (under
`private_data/`). This gives every fresh dev instance a ready-to-use library
root: after first login, go to Admin → Libraries, add Name="Main Library" and
Mount path="/library". The prod compose adds only commented examples — operators
mount their own volumes.

### Libraries management page

Added `frontend/src/pages/admin/LibrariesPage.tsx` (Aurora-styled) providing
list / add / disable flows. Uses TanStack Query + `api.createLibrary` /
`api.disableLibrary` — no new dependencies. Added to the Admin nav group in
`navConfig.ts` at the top (highest-priority admin setup action). Route
`/admin/libraries` added to `App.tsx` under `<AdminGuard>`.

### Catalog empty-state CTA

`CatalogPage.tsx` now shows a CTA when no filters are active and total === 0.
Admins see a "No libraries configured yet" state with a direct link to
`/admin/libraries`; non-admins see a "ask an admin" message. The CTA is
suppressed when any filter (q, tags, favorited, creator_id) is active — those
cases fall through to the grid/table's existing "No items found." text. The
libraries query is a separate TanStack Query call (staleTime 5 min) so it does
not interfere with the catalog items query.

### Item-create mkdir-p path

`items.py`'s `create_item` already calls `item_dir.mkdir(parents=True,
exist_ok=True)`. The library root does NOT need to be pre-created by the app —
it must already exist on disk (the container mount creates it). A fresh
`./private_data/data/library/` dir is pre-created in the repo so the dev bind
mount succeeds on first `docker compose up`.

## 2026-06-28 — UI revamp B1: CatalogPage + ItemPage Aurora restyle

### Styling approach: inline CSS vars, not Tailwind tokens

The shell (SideNavShell/TopNavShell) uses inline `style={{ ... }}` with
`var(--aurora-*)` CSS variables throughout. Pages in B1 follow the same
pattern for color/background/border/shadow properties, keeping Tailwind only
for non-visual layout helpers (`sr-only`, responsive grid). This avoids
a parallel Tailwind theme layer and keeps aurora colors consistent with the
shell at zero extra config cost.

### local style constant objects

Rather than repeating `var(--aurora-*)` strings inline at every element, each
file defines a small set of `const AURORA_*: React.CSSProperties` objects at
the top (`AURORA_CARD`, `AURORA_INPUT`, `AURORA_BTN_PRIMARY`, `AURORA_BTN_GHOST`
in ItemPage; `CARD_STYLE`, `INPUT_STYLE` in CatalogPage). These are spread with
`{ ...CONSTANT, overrideKey: value }` where needed. No new shared module was
created — the constants are file-local.

### `AuroraSection` local primitive (ItemPage only)

A small `AuroraSection({ title, children })` component wraps each ItemPage section
in a glass card with the aurora uppercase section header pattern. It is defined
locally in ItemPage.tsx (not extracted to a shared file) since ItemPage is its
only consumer.

### Virtualized grid: row height unchanged

`ROW_HEIGHT_PX = 280` and `VIRTUAL_CONTAINER_HEIGHT = 640` are unchanged.
The aurora card image area is 160 px (down from the conceptual 86 px of
Example3 which used a tighter grid) to maintain good visual proportion at
the 3-col layout. The virtualizer `estimateSize` is unchanged.

### lucide-react icons added to CatalogPage + ItemPage

CatalogPage imports: `Box`, `LayoutGrid`, `List`, `Search`, `Star`, `X`.
ItemPage imports: `Check`, `Copy`, `Download`, `X as XIcon`.
These replace the custom `StarIcon` SVG in CatalogPage and add icon affordances
to search, view toggle, copy/download/close controls. No new dependencies —
`lucide-react` was already in `package.json`.

### `getTagFontWeight` Tailwind class usage preserved

`catalog-utils.ts`'s `getTagFontWeight()` returns Tailwind font-weight class
strings (`'font-bold'` etc.). In the aurora tag cloud these are kept as
`className={weight}` on the button alongside `style={{...}}` aurora colors.
This avoids changing catalog-utils or adding a numeric weight mapping.

## 2026-06-28 — UI revamp A2: customizable widget framework

### Widget registry design: typed metadata + region-keyed, single file to add

All dashboard widgets are defined in `frontend/src/lib/widgets/registry.ts` — the single
place to add a widget. The registry exports `WIDGET_REGISTRY: WidgetDef[]` (a flat array)
plus three helpers: `getWidgets(region, isAdmin)`, `getWidgetById(id)`, and
`resolveWidgets(ids, region, isAdmin)`. Two discriminated union types:

- **`StatWidgetDef`** (region `'stat'`) — metadata + `color` (CSS var or literal) +
  `getValue(cache: StatDataCache): string`. No React component; value derivation is
  pure so it is unit-testable without a DOM.
- **`PanelWidgetDef`** (region `'panel'`) — metadata + `component: React.ComponentType`.
  Larger components live in `frontend/src/lib/widgets/panel/`.

`StatDataCache` is a bag of pre-fetched data shared across all active stat tiles so
TanStack Query's caching means shared queries (e.g. print-stats drives three tiles:
prints-done, filament-used, success-rate) are fetched once, not per-tile.

### Dashboard layout shape: JSON blob on `users.dashboard_layout`

`users.dashboard_layout` (nullable `TEXT`, migration 0012) holds a JSON blob:
```json
{
  "stats":  { "density": "comfortable|compact", "tiles": ["id", ...] },
  "rail":   { "collapsed": false, "widgets": ["id", ...] }
}
```
`NULL` resolved to role-based default at API time in `_resolve_dashboard_layout()`.
Admin default: compact density + 8 admin-default tiles (including pending-reviews,
open-issues, pending-tags). User default: comfortable density + 5 basic tiles.
Both defaults include quick-import in the rail.

### Reorder without drag-and-drop: move-up / move-down buttons

No drag-and-drop library was added (prompt requirement). Reordering uses ChevronUp /
ChevronDown icon buttons visible in edit mode, disabled at array boundaries.
Covers the 90% use case with zero additional JS weight. HTML5 native drag is a future
optional enhancement.

### Density approach: CSS flex-wrap, compact tiles shrink via padding + font-size

Both densities use `display: flex; flex-wrap: wrap`. Comfortable = `padding: 10px 14px;
font-size: 20px`; compact = `padding: 6px 10px; font-size: 15px`. With compact + 8+
tiles, tiles naturally wrap to 2 rows via `flex: 1 1 120px`.

### `useDashboardLayout` hook: server → localStorage → role default

Mirrors `useNavLayout`. Graceful fallback if GET /api/me/dashboard errors (migration
0012 not yet applied). Optimistic update: localStorage+cache then fire-and-forget PUT.
Collapsed rail state migrated from `useLocalStorage('aurora-rail-collapsed')` into
`layout.rail.collapsed`.

**Migration-restart note:** containers running before migration 0012 is applied need
`docker compose up -d --force-recreate` or `alembic upgrade head`. The frontend falls
back gracefully to role defaults until then.

### Storage Used tile: graceful permanent dash (no backend endpoint)

`storage-used` is registered (user-addable) but `getValue` always returns `'—'`.
When a `/api/admin/storage` endpoint is added, only the registry entry needs updating.

## 2026-06-28 — UI revamp A1: Aurora AppShell

### Aesthetic locked: Aurora (Example3) with CSS variable tokens

The owner selected the Aurora prototype (`frontend/src/pages/examples/Example3.tsx`) as
the real app's look. Aurora tokens (`--aurora-*`) are now declared in `index.css` for
both light and dark modes; the shell components reference them via `var()` in inline
styles. `frontend/src/pages/examples/` is kept untouched as the reference prototype.

### Two shells, one navConfig source of truth

All authenticated navigation is defined in `frontend/src/lib/navConfig.ts` (groups →
items with real App.tsx routes and lucide icons, role-gated). Two shells consume it:

- **SideNavShell** — collapsible glass sidebar (full ↔ icon-rail), grouped with animated
  collapse, pill active state with teal glow, version + release notes in the footer.
- **TopNavShell** — sticky top bar, Radix `react-dropdown-menu` per group, Aurora skin.

Both include the stat strip and the collapsible Quick Import right rail.

### nav_layout: per-user server preference, role default, graceful fallback

`users.nav_layout` (nullable `VARCHAR(16)`, migration 0011) holds `'top'` or `'side'`.
Resolution order: server value → localStorage (`partfolder3d-nav-layout`) → role default
(admin → `side`, user → `top`). The `useNavLayout()` hook wraps this; errors on
`GET/PUT /api/me/nav-layout` are swallowed so the app never hard-breaks when the
migration is not yet applied on a running container (graceful degradation to
localStorage + role default). The user-menu toggle in both shells calls `setLayout()`
which updates optimistically and PUTs to the server fire-and-forget.

**Migration-restart note:** containers running before migration 0011 is applied need
recreation (`docker compose up -d --force-recreate`) or an alembic upgrade to pick up
the column. The frontend falls back gracefully until then.

### Stat strip: real data, fixed tile set for A1

Five tiles fetch real data (items count, prints done, filament weight, success rate,
jobs running) via TanStack Query. Graceful dash shown on any error. The tile set is
fixed for A1; A2 will make it customizable.

### Quick Import rail: wraps real AddAssetModal

The collapsible right rail contains the production `AddAssetModal` (upload + URL tabs →
`/import/:sessionId` flow). No mock. Collapsed state persisted to localStorage.

### `AuroraShell` router component

`AuroraShell` (mounted in App.tsx where `AppShell` was) calls `useNavLayout()` and
renders `SideNavShell` or `TopNavShell` accordingly. The old `AppShell.tsx` is kept but
not wired into any route. All existing routes, `AuthGuard`, `AdminGuard`, and public
routes are unchanged.

## 2026-06-28 — Phase 10b release machinery decisions

### Version source-of-truth: `backend/app/version.py` (already existed from Phase 0)

The version source-of-truth file was locked at scaffolding (Phase 0 decision:
`backend/app/version.py` → `__version__ = "0.1.0"`). Phase 10b formalizes this
in the release commands: `frontend/package.json` `"version"` must be kept in sync
by `/release-prep` (same bare semver), and `GET /api/version` reads
`backend/app/version.py` at runtime. No additional version file introduced.

### Release command placeholders filled

All `<PLACEHOLDER>` tokens in `.claude/commands/release-prep.md` and
`.claude/commands/release-cut.md` replaced with project-specific values:
- Version file: `backend/app/version.py` (+ `frontend/package.json` sync)
- Image registry: `ghcr.io/crzykidd/partfolder3d` + `…-frontend`
- Publish workflow: `Build and publish Docker images`
- Release image tags: `:latest`, `:<semver>`, `:<major>`
- Local checks: ruff, tsc, vitest, compose-validate (pytest/alembic flagged as
  needing live Postgres — CI covers them; the commands note when to skip locally)
- Docs to sync: `CLAUDE.md` Status line
- Changelog archive dir: `docs/`
- README badge pattern: `version-<current>-0FA4AB` (brand teal)

The top HTML-comment placeholder guide was removed from both command files now that
the values are filled.

### CI `compose-validate` step corrected: standalone dev compose

The `Validate dev compose overlay` step in `.github/workflows/ci.yml` ran
`docker compose -f docker-compose.yml -f docker-compose.dev.yml config` — the old
overlay invocation. The dev compose was made self-contained in Phase 0 (a decision
recorded in the 2026-06-27 deployment-readiness entry below), but the CI step
was never updated. Corrected to `docker compose -f docker-compose.dev.yml config --quiet`
and renamed to `Validate dev compose`. Production compose step unchanged.

## 2026-06-28 — Phase 10a hardening decisions

### SSRF guard: DNS pre-flight block (new module `app/storage/ssrf_guard.py`)

**Problem:** The URL scraper (`scraper.py`) and instance share-link importer
(`routers/import_sessions.py`) fetched arbitrary user-supplied URLs without
checking whether the destination resolved to an internal/private address. This
allowed SSRF attacks to reach cloud-metadata endpoints (169.254.169.254),
RFC-1918 private networks, loopback, link-local, etc.

**Fix:** New module `app/storage/ssrf_guard.py` provides `assert_safe_url(url)`
which resolves the hostname via `socket.getaddrinfo` and rejects any address in
the blocked ranges before a connection is opened. The guard is applied in:
- `scraper.scrape_url()` — returns `ScrapeResult(blocked=True)` for internal URLs.
- `import_sessions.create_import_session()` — raises HTTP 422 for internal targets.
- `import_sessions.import_from_share_link()` — raises HTTP 422 for internal targets.

**Deferred:** DNS rebinding (where DNS returns a public IP on lookup but routes
to a private IP at connection time) is not mitigated. Full mitigation requires
binding to the resolved IP explicitly (httpx supports this via custom transports)
— deferred as a Phase 10b hardening item since it requires more invasive httpx
plumbing and is a lower-likelihood threat model for a self-hosted app.

### Performance indexes: migration 0010

Added 8 missing indexes identified by static query path analysis:
1. `item_tags(tag_id)` — tag browse queries filter by tag_id; the PK (item_id, tag_id) index doesn't cover this.
2. `items(creator_id)` — creator-filter browse.
3. `items(created_at DESC)` — default catalog sort; was doing full seq-scan + sort.
4. `items(updated_at DESC)` — `sort=updated_at_desc`.
5. `items(title)` — `sort=title_asc/desc`.
6. `share_links(created_by_id)` — listing/revoking per-owner links.
7. `print_records(item_id, visibility)` — compound index for public share view.
8. `download_bundles(item_id, status, expires_at)` — bundle reuse + expiry cleanup.

### Coverage: 61% → 63% after adding 31 hardening tests

The hardening test file covers SSRF guard (unit + integration through 2 fetch paths),
path traversal on authenticated and public share file-download endpoints, admin-only
route enforcement, per-user write scoping, AI provider key masking, share link public/
private record separation, FTS injection resistance, and migration 0010 index existence.

### 100k-scale load testing: deferred to Phase 10b

A real load test (100k items, pagination, tag-filter, FTS, favorites, concurrent
reads) requires a seeding harness (bulk-insert script + arq-driven image/sidecar
generation) that would take 30-60 min to seed and dedicated DB server time. This
was intentionally out of scope for 10a. The Phase 10b recommendation is:
- Write a `scripts/seed_100k.py` that uses `COPY FROM STDIN` for fast bulk-insert.
- Run the seeder against a staging Postgres instance (not the test container).
- Use `pgbench` + `explain analyze` on the hot catalog queries.
- Measure p95 latency on `/api/items?sort=created_at_desc` and tag-filter queries.
- Pay special attention to the FTS GIN index scan cost on `search_vector`.

### N+1 analysis: no critical N+1s found

The catalog list endpoint batch-loads images and tags in two follow-up queries
(not N+1). Item detail loads are single-object fetches and use `selectinload`
for the creator. No obvious N+1 patterns found in hot paths. The one area worth
revisiting is `tag_admin.py` merge (loads all item_tags for the source tag in a
loop) but that endpoint is low-frequency admin-only.

## 2026-06-27 — Phase 9b admin frontend decisions

### API keys page already existed — no duplicate created

`frontend/src/pages/settings/ApiKeysPage.tsx` was created as part of Phase 9a
(the backend commit already landed it). `App.tsx` and `AppShell.tsx` already had
the route and nav entry wired. Phase 9b confirmed it complete and did not modify it.

### New admin API functions added to api.ts (not a separate file)

All new Phase 9 API helpers (backup, export, tag admin, admin site capabilities)
were appended to the existing `frontend/src/lib/api.ts` rather than split into
separate modules. Rationale: the existing pattern is one flat file; splitting now
would require touching all import sites for no immediate benefit. The file is
getting long (~1700 lines) — if it grows further a module-per-domain split is the
right next step.

### Admin site capabilities use a separate `AdminSiteCapabilityOut` type

The Phase 5 `SiteCapability` interface (used by the Phase 5 import wizard) lacks
`created_at` / `updated_at`. The Phase 9a admin router returns `SiteCapabilityOut`
with those fields. Rather than mutate the Phase 5 type and risk breaking the import
wizard, a separate `AdminSiteCapabilityOut` interface was added to `api.ts`.

### TagAdminPage: merge target loaded via a separate all-tags query (up to 500)

The "Merge Into" dropdown in `TagAdminPage` needs a list of all tags as merge
targets. Rather than reuse the paginated view (which shows only the current 50),
a dedicated query (`['admin-tags-merge-list']`) loads up to 500 tags when the page
mounts. For catalogs with > 500 tags, the user should search-narrow first. This
is an acceptable trade-off for an admin tool.

### TagAdminPage: separate admin endpoints, not the existing PendingTagsPage path

The existing `PendingTagsPage` calls `/api/tags/{id}/approve` (the public tags
router). `TagAdminPage` calls `/api/admin/tags/{id}/approve` (the Phase 9a admin
router). Both exist in the backend; this separation preserves the existing page
and avoids a regression.

### Reindex: ScheduledJobsPage already has "Run now" per job

The `ScheduledJobsPage` already exposes a "Run now" button for every scheduled job,
including `library_reconcile_scan`. Option A from the prompt (no new page, reuse
existing) applies — no ReindexPage was created.

### Backup download uses plain anchor with `download` attribute

The `GET /api/admin/backups/{id}/download` endpoint returns a `FileResponse`
(Content-Disposition: attachment). The UI uses a plain `<a href="..." download>`
anchor rather than a fetch + Blob URL. This avoids holding the full archive in
memory and is the correct pattern for file downloads.

## 2026-06-27 — UI prototype examples (`/examples`, `/example1..3`)

Three standalone mock-data prototypes added under `frontend/src/pages/examples/` for
the owner to pick a design direction from. All routes are registered outside `<AuthGuard>`
(siblings of `/share/:token`) so they render with no backend. Delete the losers after a
direction is selected.

- **`/example1` — "Mission Control":** Collapsible left rail, dark navy (#091D35) +
  teal (#0FA4AB), dense compact spacing à la Linear/Vercel, icon-only rail mode,
  grouped nav, stats bar, tabbed catalog + jobs + tags panel, inline import wizard.
- **`/example2` — "Atelier":** Top nav with `@radix-ui/react-dropdown-menu` grouped
  dropdowns, light-first warm neutrals, rounded cards with soft shadows, large generous
  whitespace, stepped import wizard card, creator directory + tag cloud.
- **`/example3` — "Aurora":** Deep gradient canvas, frosted-glass sidebar with
  backdrop-filter blur + animated `max-height` group collapse, pill nav items with
  teal glow, fully functional `⌘K` command palette overlay (keyboard: Ctrl/Cmd+K,
  arrow keys, Enter to select, Esc to close), glass catalog cards.

All three share `mockData.ts` (16 items, rich stats, jobs, creators, tag cloud) and
`useLocalStorage.ts` (sidebar collapsed/expanded + group open/closed states persisted
per-browser). `tsc --noEmit` clean; all 131 tests green.

## 2026-06-27 — Phase 9a backend decisions (backup, export, tag admin, site-caps, API parity)

### Backup: in-process JSON dump (no pg_dump)

Chose `asyncpg`-based in-process table dump over `pg_dump` for deployment safety.
`pg_dump` is not in `python:3.12-slim`; adding it from the PGDG apt repo requires
pinning the major version (Debian default is v15, may refuse to dump a v16 server),
adds ~15 MB to the image, and introduces a subprocess call with shell-injection risk.
The in-process approach uses the same `asyncpg` driver already in the image, exports
all table rows as gzip-compressed JSON (`db.json.gz`), and bundles the instance
`secret.key`. Trade-off: restore requires `alembic upgrade head` first, then a future
`restore` tool to re-import the JSON. Acceptable for a personal/team asset manager;
a large-scale SaaS would prefer binary pg_dump. Decision recorded in
`backend/app/worker/backup.py` docstring.

### Backup archive format: `.tar.gz` with `metadata.json + db.json.gz + config/secret.key`

Timestamped archive: `backup_YYYY-MM-DDTHH-MM-SS.tar.gz`. Contents:
- `metadata.json` — timestamp, app version, table list, "library files not included" note
- `db.json.gz` — gzip-compressed JSON of all table rows (dict of {table: [rows]})
- `config/secret.key` — instance Fernet key (critical for decrypting secrets at restore)

Library binary files (STL, OBJ, images) are explicitly NOT included. A loud callout
in the admin UI (Phase 9b) will make this clear to the admin.

### Backup retention: DB setting `backup.retention_count` (default 10)

Retention count is stored in the `settings` table (key `backup.retention_count`) so
admins can change it without redeploying. Pruning happens at the end of each successful
backup run; `BackupRecord` rows + archive files are both deleted.

### Backup scheduling: `db_backup` at 04:00 UTC

Registered in `SCHEDULED_JOB_REGISTRY` and `_SCHED_FUNCS` alongside the existing four
scheduled jobs. Runs via `exec_scheduled_job("db_backup")` so it's also run-now-able
from the admin UI / API.

### JSON catalog export: in-memory collection, non-streaming

`GET /api/admin/export/catalog` loads all items (with eager-loaded tags, files, images,
creator), tags, aliases, creators, and print records into memory, serializes to JSON,
and returns a single `StreamingResponse`. For a personal/team library (hundreds to low
thousands of items) this is well within memory limits. For very large catalogs a proper
chunked streaming approach would be needed. A `StreamingResponse` is used so
Content-Disposition is honored and the file downloads correctly in browsers.

### Tag administration: new router `/api/admin/tags/*`

Public tag browsing + Phase-5 approval (`POST /api/tags/{id}/approve`) remain in
`routers/tags.py`. Phase 9 admin operations (list pending, approve, reject, set
category, alias CRUD, merge) live in `routers/tag_admin.py` at `/api/admin/tags/*`
to keep the public-API router uncluttered.

Tag merge semantics: (1) repoint ItemTag rows from source → target using SQLAlchemy
UPDATE + handle ON CONFLICT via pre-filtering; (2) repoint TagAlias rows; (3) add
source.name as a new alias of target so old alias lookups keep resolving; (4) add
source.popularity_count to target; (5) DELETE source. Idempotent on alias creation.

### Site capabilities admin: `/api/admin/site-capabilities/*`

Phase 5 created the `SiteCapability` + `SiteToken` models but only populated them
from the import-session scraper — no admin API existed. Phase 9 adds full CRUD.
Tokens are stored Fernet-encrypted (existing `crypto.encrypt`); the admin endpoint
accepts a plaintext token over HTTPS and encrypts it. The `has_token` flag in the
response indicates existence without exposing the value.

### `from __future__ import annotations` + FastAPI 204 routes

FastAPI's `APIRoute.__init__` asserts `response_model is None` for 204 status codes.
With `from __future__ import annotations` (PEP 563), `-> None:` is stored as the
string `"None"` and resolved to `NoneType` (the class) by
`get_typed_return_annotation`. `bool(NoneType)` is `True`, so FastAPI sees a non-None
response model and the assertion fires. Fix: pass `response_model=None` explicitly on
all 204 routes in files that use `from __future__ import annotations`. This is a
known FastAPI footgun documented as an edge case in their migration guide.

### API-parity audit result

All UI-facing actions now have REST endpoints:
- Backup: list / trigger / settings / download / delete (`/api/admin/backups/*`)
- Export: catalog JSON (`/api/admin/export/catalog`)
- Reindex: via existing `POST /api/scheduled-jobs/library_reconcile_scan/run`
- Tag admin: pending list / approve / reject / category / aliases / merge (`/api/admin/tags/*`)
- Site capabilities: list / get / patch / delete / token / reprobe (`/api/admin/site-capabilities/*`)
- API keys: create / list / revoke (existing `/api/api-keys/*`)
- Bearer API-key auth: confirmed working across all admin endpoints (test `test_api_key_bearer_auth_on_admin_endpoint` passes)

### Reindex: no new code

`library_reconcile_scan` is already a scheduled job with a run-now endpoint
(`POST /api/scheduled-jobs/library_reconcile_scan/run`). The frontend 9b handoff
will add a "Reindex" button that calls this existing endpoint — no backend changes
needed.

## 2026-06-27 — Auto-migration via entrypoint + self-contained dev compose + host-visible dev storage (deployment readiness)

A scaffolding gap carried since Phase 0: nothing ran `alembic upgrade head` on
startup — neither the Dockerfile `CMD` (plain `uvicorn`) nor the FastAPI `lifespan`
(which only does `ensure_key()` + journal recovery) — so a fresh stack came up
against an empty database and the first-run wizard failed.

**Migrations are bundled into service startup via the image entrypoint**
(`backend/docker-entrypoint.sh`): when `RUN_MIGRATIONS=true` (set only on the
`backend` service) it runs `alembic upgrade head`, then `exec "$@"`. A *one-shot
`migrate` service was rejected* — it shows as an "exited" container in
`docker ps`/Portainer and reads as a broken stack. To avoid a double-run race
(backend + worker share the image), only the backend migrates; the **worker (and
nginx) gate on `backend: condition: service_healthy`**, and the backend has a
healthcheck hitting `GET /health`. So migrations run exactly once, before anything
that touches the DB. `alembic/env.py` already prefers the `DATABASE_URL` env var.

**`docker-compose.dev.yml` is self-contained** — all services + build in one file,
run with a single `docker compose -f docker-compose.dev.yml up --build` (no
base+overlay, no two `-f` flags). Rationale: a uniform one-file/one-command dev
workflow across projects on the same machine.

**Dev storage is host-visible:** the dev stack bind-mounts ALL data under
`./private_data/data/{postgres,redis,app}` instead of named volumes, so every
file is inspectable on the host without entering containers. `./private_data/` is
gitignored. Production (`docker-compose.yml`) keeps managed named volumes
(`db_data`/`redis_data`/`frontend_dist`).

## 2026-06-27 — Phase 8b AI tagging frontend decisions

### Description editing added to TitleStep (not a new wizard step)

The handoff prompt described a "description step" for the AI cleanup/summarize
buttons, but the existing wizard has no description-editing step and adding one
would break all existing step-navigation vitest tests (nextStep/prevStep/stepIndex
assertions hardcode the 5-step sequence). Adding description editing to the
existing TitleStep was the minimal-impact choice: it preserves all step tests,
keeps title and description together as primary text metadata, and satisfies the
spec (AI buttons appear where users edit the description). The TitleStep now saves
both `confirmed_title` and `description` in a single PATCH on "Next →".

### AI availability probe fires on TitleStep mount (description path only)

The spec says "probe by calling the endpoint once on fresh page load". The probe
calls `aiCleanupDescription` (POST) in a `useEffect` with an empty dependency
array so it fires exactly once per mount. It only fires if the session already
has a non-empty description (to avoid making an AI call when there is nothing to
clean). The response `provider_available` field is cached in component state.
If the probe itself triggers an AI call (provider configured, description exists),
the returned text is intentionally discarded — the probe is only for availability
detection; the user still explicitly clicks "Clean up" or "Summarize" to get a
usable preview. Buttons remain enabled when provider state is null (unknown) and
become disabled only after confirmed `provider_available: false`.

### Surface 3 (PendingTagsPage): client-side fuzzy matching, not an AI call

The prompt noted that the AI suggest-tags endpoint requires an import session ID,
which is not available on PendingTagsPage. The implemented feature is therefore
a client-side Levenshtein fuzzy match (≤ 3 edits, case-insensitive) using a new
`fuzzyMatchTags` function in `import-utils.ts`. Tags with `popularity_count > 0`
are treated as canonical; tags with `popularity_count === 0` are treated as
potentially pending. This heuristic is consistent with the comment already in
the existing PendingTagsPage code. The textarea pre-populated with pending tag
names lets the admin refine the list before running the client-side match.

### Levenshtein implementation: row-only DP (O(n) space)

`levenshtein(a, b)` in import-utils.ts uses two 1D arrays (`prev`/`curr`) instead
of a 2D matrix to keep memory O(n). This is the standard optimization for cases
where only the final distance is needed (not the edit path). Correctness is
verified by 7 unit tests; edge cases (empty string, same string, no common chars)
are all covered.

## 2026-06-27 — Phase 8a AI tagging backend decisions

### Provider dispatch: anthropic SDK for Claude; openai SDK for OpenAI + Ollama

Two SDKs are used, not one.  Claude requires `anthropic.Anthropic(api_key=...).messages.create(...)` — the official Anthropic SDK, which is the only supported path for claude-opus-4-8 and its extended context / system-prompt features.  OpenAI and Ollama both use `openai.OpenAI(api_key=..., base_url=...).chat.completions.create(...)`.  Ollama exposes an OpenAI-compatible REST API at its configured endpoint, so `base_url` is set to `AiProvider.endpoint` (e.g. `http://localhost:11434/v1`) and the key is a placeholder.  A single generic "LLM SDK" was rejected because no single open-source client covers all three provider flavors with their distinct auth and API shapes.

### Default Claude model: `claude-opus-4-8` (exact string, no date suffix)

When `AiProvider.model` is NULL the dispatcher falls back to `"claude-opus-4-8"`.  This is the exact model ID; the `anthropic` SDK does not accept a date suffix.  `temperature`, `top_p`, `top_k`, and `thinking={type:"enabled", budget_tokens:…}` are intentionally omitted — they return HTTP 400 on claude-opus-4-8.  Thinking is off by default; the prompt is structured (system + user message) using `messages.create`.

### Tag suggestion: structured JSON schema via prompt-level enforcement (not SDK schema binding)

The tag-suggestion prompt embeds the JSON schema (`_TAG_SCHEMA`) in the system message and instructs the model to output only a valid JSON object.  The dispatcher's `suggest_tags` function then JSON-parses the raw text and post-filters the result: `canonical` entries that don't appear in `existing_tags` are stripped (hallucination guard); `new_suggestions` is capped at `MAX_NEW_SUGGESTIONS` (5) regardless of what the model returns.  This approach works for all three providers (including Ollama, which does not support structured-output parameters).  SDK-level `response_format` / `output_config` was rejected: it's anthropic-SDK-only and not available on the openai SDK for all model versions.

### Best-effort / degrade-gracefully contract

Every public AI function (`suggest_tags`, `cleanup_description`, `summarize_scrape`) catches all exceptions and returns a sentinel result (`AiTagResult(error=...)` / `AiTextResult(error=...)`).  AI failure **never** re-raises to the HTTP handler.  All three action endpoints (`suggest-tags`, `cleanup-description`, `summarize`) return HTTP 200 in all non-authentication failure cases — including no provider configured (`provider_available=False`) and provider call failure (`error != None`).  The headline contract: with zero AI providers configured, the manual import path (item create, wizard commit, tag approval) is completely unaffected — no code path on the critical import/commit flow touches the AI layer.

### Key-encryption reuse: Fernet via `crypto.encrypt` / `crypto.decrypt`

`AiProvider.api_key_encrypted` is a Fernet-encrypted ciphertext using the same instance key as Phase 1 API-key and site-token encryption.  Keys are decrypted only inside `_dispatch` at call time and never logged or returned in responses.  The provider CRUD endpoint returns `has_key: bool` (not the ciphertext or plaintext).  The test-connection endpoint (`POST /api/ai-providers/test`) encrypts ephemerally, passes through `_dispatch`, and never writes to the DB.  Key rotation (a later utility) requires only replacing `api_key_encrypted` on the relevant provider row.

### Phase 8 split: backend (8a) complete; frontend (8b) deferred

The backend (AI client layer, provider CRUD, three action endpoints, 37 new tests) is complete.  The frontend (AI-provider settings page, wizard AI-action buttons, tag-admin AI suggestions) is deferred to `prompts/2026-06-27-phase-8b-ai-frontend.md` so each agent gets a focused scope.  The backend is fully usable without the frontend (e.g. via API or future CLI).

## 2026-06-27 — Phase 7b frontend decisions

### print-utils.ts extracted as standalone module (not inlined in pages)

`formatPrintTime`, `formatFilamentLength`, `formatFilamentWeight`, and `renderStars`
live in `src/lib/print-utils.ts` rather than being inlined in `ItemPage.tsx` or
`PublicSharePage.tsx`. Rationale: both pages need the same helpers; extracting them
makes them independently unit-testable with vitest without any DOM/React setup.

### PublicSharePage: 400 "full-site" disambiguation via error message substring

The backend returns HTTP 400 with a body containing "full-site" when a full_site share
token is passed to `/api/public/share/{token}` (which only handles item_design). The
frontend detects this specific 400 by substring-matching `error.message.includes('full-site')`
to activate the catalog view. This is fragile against backend message changes, but the
alternative (a separate probe endpoint) adds a round-trip. If the backend ever adds a
scope field to the 400 response, switch to that instead.

### ShareSection (ItemPage): "copy on mint" using clipboard API (no toast library)

When a share link is minted, the new URL is immediately copied to clipboard and a
transient inline "✓ Copied!" label appears on the row for 3 seconds. This matches
the existing inline feedback pattern (copy-path button on PathDisplay). No toast
library was added — the project stack explicitly has no global toast system.

### DownloadsSection: includeHistory checkbox resets ZIP state on toggle

When the user toggles "Include print history", any in-flight or ready bundle is
discarded (state reset to idle) so the next click starts a fresh ZIP request with
the correct `include_history` param. Reusing an old bundle id after the flag changes
would silently serve a stale ZIP without the expected content.

### queueZip API: include_history passed as query param (not body)

The backend `POST /api/items/{key}/zip` accepts `include_history` as a query param
(FastAPI `Query(...)`), not in the JSON body. The `apiFetch` wrapper used for this
endpoint sets `Content-Type: application/json` only when body is present, so we
append `?include_history=true` to the URL string.

## 2026-06-27 — Phase 7 print history + sharing decisions

### PrintRecord shape: normalized with structured settings fields

`PrintRecord` stores both structured slicer settings (printer, material, nozzle_diameter,
layer_height, supports) and gcode-parsed metrics (filament_length_mm, filament_weight_g,
estimated_print_time_s) as first-class columns rather than JSONB blobs. Rationale: SQL
aggregation for stats (`SUM(filament_length_mm)`, `AVG(rating)`, `COUNT(success=True)`)
is far simpler on typed columns; schema evolution is explicit. The `note` field and
`visibility` column let owners keep private remarks that never leak to public endpoints.

### ShareLink token: secrets.token_hex(32) stored as-is (not hashed)

Share tokens use `secrets.token_hex(32)` — 64 hex chars, 256-bit entropy. Stored in
cleartext in the DB so public endpoints can do O(1) lookup by token. Not hashed because
share tokens are not passwords: they are already the access credential, bearer-token
style. Revocation + expiry are enforced server-side on every request. Rejected: UUID4
(only 122 bits, lower collision safety for a publicly guessable surface); HMAC-signed
tokens (adds server-secret dependency, no benefit for revocable links).

### gcode parser: best-effort, pure, first-32 KB only

`parse_gcode_file` / `parse_gcode_text` read only the first 32 KB of gcode. All slicer
dialects write their summary comments at the top; parsing the full file would be O(MB)
for no gain. The function is pure (no I/O in the text variant) so unit tests don't need
temp files. Errors are accumulated in `parse_errors` list; the result is always
returned (never raises). Binary `.bgcode` files are detected by magic bytes and skipped
gracefully — returning empty metadata rather than crashing.

### Public/private separation: filter at query time + never pass through

Every public share endpoint explicitly filters `PrintRecord.visibility == "public"` in
the SQL query. Private records are never fetched and then filtered in Python — the DB
never returns them. Public ZIP bundles set `requester_user_id=None`; the worker checks
this flag and only includes public records. This double-gate (endpoint + worker) means a
programming mistake in one layer is caught by the other.

### Audit events: written on every public access (not just first)

`ShareAuditEvent` rows are inserted for every `accessed_view` and `accessed_download`
event, not just the first access. This gives admins a full access log for abuse
investigation. Expiry events (`expired`) are written idempotently by the daily cron job
(skips links that already have an expired event).

### include-history ZIP: flag on DownloadBundle + null requester_user_id for anonymous

`DownloadBundle` gained two new columns: `include_print_history` (bool, default False)
and `requester_user_id` (nullable int, no FK so user deletes don't cascade). Public
share ZIP bundles set both to their anonymous defaults (`False`, `NULL`). The worker
reads these flags to decide what to include. This design keeps the existing ZIP path
unchanged (old bundles continue to work) and avoids passing user context into the worker.

### Instance import: _share_link_fetcher module-level mock seam

`import_sessions.py` exposes a module-level `_share_link_fetcher` variable. In
production it is `None` and the code falls through to `httpx.AsyncClient`. In tests,
`monkeypatch.setattr(import_sessions_mod, "_share_link_fetcher", ...)` replaces it with
a sync function returning mock data. This avoids the need for a live instance, respawning
a test server, or a complex fixture chain. Rejected: dependency injection via FastAPI
`Depends` (makes the endpoint signature more complex without benefit in production).

## 2026-06-27 — Phase 6b reconcile engine frontend decisions

### Reconcile Modes card placed on ReviewsPage (not SettingsPage)

The "Reconcile Modes" settings UI (Deliverable 5) is rendered as a card at the top of
`/admin/reviews` rather than in `/settings`.  Rationale: the three mode toggles
(`sidecar_sync`, `re_render`, `file_changes`) directly control what ends up in the
review queue — placing the controls on the same page as the queue makes the
cause-and-effect relationship immediately visible to the admin.  The SettingsPage
hosts instance-level operational settings (name, external URL, timezone); the reconcile
modes are more operational than configurational.

### Pending-count badge in AppShell via per-minute background query

The "Review Queue" nav link shows a red badge with the count of pending review items.
This is implemented as a `useQuery` in `AppShell` with `refetchInterval: 60_000` and
`staleTime: 30_000`, fetching `GET /api/reviews?status=pending&per_page=1` (one-row
page — only the `total` field is used).  Enabled only when `isAdmin`.  Rejected:
WebSocket push (out of scope per prompt); a Context-based approach that requires
threading query results through the tree; polling on every page vs. once at shell level.
The 60s interval is a deliberate trade-off between freshness and request volume.

### Issue type filter uses backend IssueType enum values verbatim

The dropdown in IssuesPage lists all `IssueType` enum values defined in
`backend/app/models/issue.py` (conflict, dead_link, corruption, orphan, missing_file,
extra_file, sidecar_error, other).  The backend filter is a plain string match on the
`issue_type` column so the list is fixed to known values.  Future issue types added to
the backend enum would need a corresponding frontend update.

### Behavior badge colors consistent across ChangesPage and ReviewsPage

`sidecar_sync` → violet, `file_changes` → orange, `re_render` → blue,
`integrity`/`orphan` → muted/red (fallbacks for log entries with non-standard
behaviors).  Colors are chosen to be distinct at a glance without requiring a legend.

### reconcile-utils extracted to lib for testability

`getReconcileMode`, `reconcileSettingKey`, and `RECONCILE_DEFAULTS` are extracted
to `frontend/src/lib/reconcile-utils.ts` as pure functions so they can be unit-tested
without rendering a React tree.  The default-fallback logic (absent key → documented
default) is non-trivial and must match the backend's `DEFAULT_MODES`; tests assert
this contract explicitly.

## 2026-06-27 — Phase 6a reconcile engine decisions

### Issue / ChangeLog / ReviewItem shapes

Three new models represent distinct concerns: `Issue` is a durably-recorded problem
(survives until resolved/ignored, FK to item nullable for library-level orphans).
`ChangeLog` is an append-only audit trail (no update path, only created_at).
`ReviewItem` is a pending decision record (status: pending → approved/rejected,
resolved_by_id for actor tracking).  A single combined table was rejected because the
three have incompatible lifecycles.

### Sidecar sync direction: three-way mtime comparison

Three timestamps are compared to determine sync direction: `sidecar_written_at`
(from `sidecar.updated_at` field — when the app last wrote the file),
`sidecar_file_mtime` (OS mtime), and `item.updated_at` (DB last-modified).
`sidecar_externally_edited` = sidecar_file_mtime moved >5 s past sidecar_written_at.
`db_changed_since_sync` = item.updated_at moved >5 s past sidecar_written_at.
Both true → conflict Issue.  Only DB newer → push DB to sidecar (always auto).
Only sidecar newer → pull to DB or ReviewItem (per mode).  The 5 s tolerance
(`SIDECAR_SYNC_TOLERANCE_SECONDS`) guards against filesystem timestamp resolution.

### Default reconcile modes are conservative

`sidecar_sync="review"` and `file_changes="review"` by default: the nightly library
scan creates ReviewItems rather than auto-applying changes, protecting against
unexpected sidecar edits or stray files silently mutating the catalog.  Only
`re_render="auto"` because a re-render has no data-loss risk.  Modes are stored as
`settings` table entries (`scan.*`) and can be changed per-installation.

### Per-item rescan uses "auto" modes regardless of DB settings

`POST /api/items/{key}/rescan` overrides `file_changes` and `sidecar_sync` to "auto"
after loading DB settings.  The user explicitly requested a rescan of that item, so
changes should apply immediately — matching pre-Phase-6 behavior.  The conservative
DB defaults apply only to the unattended nightly library scan.

### Reconcile engine isolated from routers (circular import prevention)

`backend/app/worker/reconcile.py` cannot import from `app.routers.items` (routers are
at a higher layer).  The sidecar-write helper `_write_sidecar_for_item` is duplicated
in `reconcile.py` using the same `build_sidecar` + `write_sidecar` primitives.  This
is intentional duplication to preserve layer boundaries; the sidecar write logic is
stable and small.

### §8.5 isolated-per-item transactions in library scan

`reconcile_library_scan` opens a fresh `SessionLocal()` for every item.  If one item's
reconcile transaction fails, the exception is caught, a best-effort Issue is recorded
in a second transaction, and the scan continues.  This matches the §8.5 PRD contract:
"one bad item → Issue, never blocks rest."

## 2026-06-27 — Phase 5b import wizard frontend decisions

### No @radix-ui/react-dialog: custom Tailwind overlay modal
`@radix-ui/react-dialog` is not in `package.json` (only `react-dropdown-menu` and `react-slot` are).  Rather than adding a new dependency, `AddAssetModal` uses a plain `div` with `fixed inset-0 z-50 bg-black/60` backdrop and a centered panel.  Escape-key and backdrop-click close it via `useEffect` + event listener.  This matches the existing pattern in the codebase where shadcn/ui component packages are not installed — only the Tailwind + CSS variable theme is used.

### Wizard step state in local React state (not URL)
Step navigation in `ImportWizardPage` is stored in `useState<WizardStep>` rather than a URL param.  The session ID is the durable param (`/import/:sessionId`); step position is transient UI state.  If the user refreshes on step 3, they restart at step 1 — this is acceptable because PATCH calls on each step persist the data, so no work is lost.  URL-based steps would require back/forward browser nav to be handled, adding complexity with no material benefit for a linear wizard.

### Polling strategy: refetchInterval as a function of session status
TanStack Query's `refetchInterval` is passed a function (`(query) => ...`) rather than a static value.  While `status === 'processing'`, the function returns 3000 (ms); otherwise it returns `false` (no polling).  This eliminates a separate `useInterval` and keeps the polling lifecycle tied to the query data state.  The ImportsPage uses 5s polling when any session on the page is processing.

### Local staged images: no preview until committed
`ImportSessionImage.is_url` is `true` for scraped/URL images (the `path` field is the full remote URL).  For uploaded local files, `is_url` is `false` and `path` is an absolute staging filesystem path.  There is no public API endpoint to serve staged files (by design — they're in `/data/staging/`, outside the item tree).  The wizard shows a placeholder for local images ("preview after commit") rather than constructing a broken URL.  After commit, images are moved into the item directory and served via `/api/items/{key}/files/{path}`.

### PendingTagsPage shows all-tags from active_only=false (no status filter in TagSummary)
`GET /api/tags?active_only=false` returns all tags (active + pending) but the backend's `TagSummary` Pydantic schema does not include a `status` field.  This means the client cannot distinguish pending from active tags in the list response.  The PendingTagsPage therefore shows ALL tags and the Approve button is safe to call on already-active tags (the backend is idempotent: `POST /api/tags/{id}/approve` on an already-active tag returns 200 with no change).  Adding `status` to `TagSummary` would require a backend change; deferred to a future cleanup.

### AddAssetModal: library selector queries /api/libraries
A `useQuery(['libraries'])` fetches `GET /api/libraries` (all-users endpoint, no auth restriction in that router) to populate the library dropdown in both upload and URL tabs.  The query is enabled only when the modal is open (`enabled: open`) so it does not load on every page render.  `staleTime: 60_000` avoids refetching on repeated modal open/close within a minute.

### Custom tab bar without @radix-ui/react-tabs
The two-tab "Upload / From URL" switcher in `AddAssetModal` uses `useState<TabId>` + bottom-border `border-b-2 border-primary` styling on the active tab.  No Radix Tabs, no WAI-ARIA `role="tabpanel"` — simple enough for a 2-tab modal that doesn't need keyboard tab-panel navigation.

### Commit redirect uses item_key from CommitResponse
`POST /api/import-sessions/{id}/commit` returns `{ item_key, item_id, session_id }`.  The wizard `onSuccess` navigates to `/items/{item_key}` (the human-readable key used by `ItemPage`), not the integer `item_id`.  If a user navigates directly to a committed session URL, the wizard shows a "already committed" message with a link to `/catalog` (since there's no `GET /api/items/by-id/{id}` endpoint to look up the key from the integer ID).

## 2026-06-27 — Phase 5a verification fixes (orchestrator, post-agent)

Two bugs were caught by the orchestrator running the migration round-trip + full test
suite against an ephemeral Postgres (the executing agent had no DB and could only run the
6 pure-unit tests):

- **`CREATE TYPE IF NOT EXISTS` is not valid Postgres** — Postgres has no `IF NOT EXISTS`
  for `CREATE TYPE`. Migration `0006` now guards each enum type in a
  `DO $$ BEGIN ... EXCEPTION WHEN duplicate_object THEN null; END $$;` block, which keeps it
  re-runnable and matches the `DROP TYPE IF EXISTS` already in `downgrade()`. Verified
  upgrade→downgrade→upgrade ends at `0006 (head)`.
- **`python-multipart` was missing from `requirements.txt`** — FastAPI raises at import
  time when an endpoint uses `Form`/`File` (the Add Asset multipart upload) without it, so
  the app would not boot. Added `python-multipart==0.0.20`. With it installed, the full
  suite is **189 passed** (167 prior + 22 new Phase 5).

## 2026-06-27 — Phase 5 import wizard decisions

### Import-session model shape: staging entity, not job-payload JSON

An `ImportSession` table (not a JSON blob inside a `jobs.payload`) was chosen as the
staging entity.  Rationale: sessions need to be efficiently listed, paginated, filtered by
status, and patched independently of the background job that processes them.  A job-payload
approach would require loading the full jobs table and deserializing JSON for every list
query.  The ImportSession has a nullable `job_id FK → jobs.id` to track the async processing
step, and a nullable `item_id FK → items.id` to record the committed result.  The Job row is
created by the `process_import_session` arq task; the ImportSession is the durable,
user-facing record.

### Item directory is NOT created until commit

The staging entity holds a `staging_dir` (uploaded files) or `inbox_folder` (inbox files)
reference.  The actual item directory (named from the confirmed title) is created only at
commit time by the commit endpoint.  This means a corrected title always yields the right
path the first time, and there are no half-named dirs to clean up on cancel/failure.

### Commit reuses the create_item helper path

The `POST /api/import-sessions/{id}/commit` endpoint calls the same module-level helpers
used by `create_item` — `_attach_tags`, `_write_item_sidecar`, `_update_search_vector`,
`_enqueue_render` — imported from `routers/items.py`.  Files are moved (via `Path.replace()`,
falling back to `shutil.copy2 + unlink` on cross-device) into the item dir, then
`inventory_item()` walks the result to create File rows.  A committed import is
indistinguishable from a normal item.

### Inbox scan safety: mtime-settle check

The inbox scanner skips any subfolder whose `mtime` is newer than
`INBOX_MTIME_SETTLE_SECONDS` (default 30 s).  This prevents ingesting a folder that is
still being written (e.g. a large network copy).  inotify was considered for real-time
detection but deferred: a periodic scan (daily by default, run-now-able) is sufficient for
Phase 5 and avoids the complexity of inotify kernel subscription lifecycle.

### Scrape library: httpx + selectolax

`httpx` (already in `requirements.txt`) handles HTTP.  `selectolax` (added at 0.4.10)
handles HTML parsing via a fast CSS-selector API.  `beautifulsoup4` was considered but
`selectolax` is significantly lighter and faster for the Open-Graph / meta-tag extraction
pattern used here.  The scraper extracts `og:title`, `og:description`, `og:image`,
`og:site_name`, `meta[name=keywords]`, and JSON-LD `keywords`.

### Robots.txt stance: check before every scrape, cache per session

`urllib.robotparser.RobotFileParser` is used (stdlib, no extra dep).  The result is cached
in-process for the duration of a worker invocation (not persisted to DB — a per-deploy
memory cache is sufficient given the low scrape frequency).  The scraper uses the
user-agent string `PartFolder3D/1 (+https://github.com/crzykidd/partfolder3d)`.  Scrape
failures (timeout, non-200, robots block) degrade gracefully: the session remains in
`pending_wizard` but with empty scraped fields; the user fills them manually.

### Site-capabilities table: probed on first hit, stored per domain

A `site_capabilities` row is created or updated the first time a domain is scraped.
`can_scrape_metadata` and `can_scrape_images` are set from the observed scrape result.
`requires_token` and `is_manual_only` are user-settable overrides.  Tokens are stored in
a separate `site_tokens` table, encrypted with the instance Fernet key (same as API-key
encryption from Phase 1).  Plaintext tokens are never persisted to the DB.

### Tag reconciliation / pending-tag approval flow

Phase 5 wires the existing `TagAlias` schema (already in DB from Phase 2) into the import
wizard:
  1. Exact name match → confirmed (active or pending tag both OK).
  2. Alias lookup → map to canonical name → confirmed.
  3. Unknown → goes to `pending` list in `tag_state JSONB`.
At commit time, pending tags are created with `TagStatus.pending` (not yet canonical) and
attached to the item.  Admins promote them via `POST /api/tags/{id}/approve`.  The manual
path (user types/selects tags directly via PATCH on the session) always works; tag
reconciliation is best-effort pre-fill.

### Share-link import: stub only (Phase 7)

`POST /api/import-sessions/from-share-link` returns HTTP 501 with a clear message.  The
full instance-to-instance import flow is deferred to Phase 7.

### Phase 5 split: backend (5a) complete; frontend (5b) deferred

The backend (models, migration 0006, scraper, reconciliation, import sessions + site
capabilities endpoints, inbox scan + process_import_session worker tasks, tag approval
endpoint) is complete.  The frontend wizard UI (Add Asset modal, import wizard step
component, inbox/pending list, site-setup prompt) is deferred to the
`prompts/2026-06-27-phase-5b-frontend-wizard.md` handoff so each agent gets a clean,
focused scope.

## 2026-06-27 — Phase 4 worker + rendering decisions

### Render backend that actually works: pyrender + OSMesa (not VTK)
The build plan said "VTK offscreen — Mesa software rasterizer built into the VTK wheel;
always works on a CPU-only host." This was **incorrect**: the PyPI `vtk==9.3.1` wheel on
Linux uses `vtkXOpenGLRenderWindow` which calls `Abort()` (SIGABRT) when there is no X11
display and no EGL. It does not ship with a true software (OSMesa) rasterizer. The crash
is not catchable by Python's exception system.

The working path on this host (and expected in Docker) is **pyrender + OSMesa**: the
system has `libosmesa6` (Mesa 25.1.7) which provides `OSMesaCreateContextAttribs`, and
`PyOpenGL>=3.1.7` exposes that function. `pyrender` 0.1.45 uses it via its
`OSMesaPlatform`. A real 256×256 PNG was rendered from a test STL using this path.

EGL (`pyrender+EGL`) is the preferred path when EGL libraries are present (faster, same
pyrender code path). This host has no EGL; Docker with `libegl1`+`libgbm1` is expected
to try EGL first.

### VTK detection fixed: subprocess probe, not just importability
The original `_try_vtk()` returned `True` if `import vtk` succeeded, but `import vtk`
succeeds even when VTK offscreen rendering will SIGABRT. Fixed to run a minimal
offscreen render probe in a subprocess (returncode 0 = confirmed; any other code = False).
The VTK backend remains in the detection chain as a fallback for environments where VTK
is built with EGL/OSMesa support (e.g. certain CI images).

### OpenGL platform module cache: _try_egl() clears OpenGL on failure
PyOpenGL initialises a global platform singleton (EGL, OSMesa, X11) on first import.
If `_try_egl()` fails after importing OpenGL, the singleton is stuck as `EGLPlatform`,
causing `_try_osmesa()` to fail with `AttributeError: 'EGLPlatform' has no attribute
'OSMesa'`. Fixed: `_try_egl()` now removes all `OpenGL.*` entries from `sys.modules`
in its except block so that `_try_osmesa()` starts with a clean module state.

### PyOpenGL version pin relaxed to >=3.1.0
`requirements.txt` originally pinned `PyOpenGL==3.1.0`. `OSMesaCreateContextAttribs` is
only exposed by PyOpenGL ≥ 3.1.7. `pyrender 0.1.45` declares `==3.1.0` in its own
metadata but is functionally compatible with 3.1.x; we tested 3.1.10. Changed to
`PyOpenGL>=3.1.0`.

### Dockerfile GL libs added (Phase 4)
The root `Dockerfile` now installs (in the `deps` stage):
  - `libgl1` — Mesa OpenGL (required by pyrender's GL context)
  - `libegl1`, `libgbm1` — EGL (pyrender+EGL path, tried first in Docker)
  - `libosmesa6` — Mesa OSMesa (pyrender+OSMesa fallback)
  - `libglib2.0-0`, `libfreetype6` — Mesa transitive deps
CPU-only; no GPU drivers.

### Job model shape
`jobs` table: UUID PK (`gen_random_uuid()`), `type VARCHAR(64)` (e.g. "render",
"zip_bundle"), `status VARCHAR(16)` (`queued → running → succeeded | failed`),
`progress INTEGER` (0–100), `payload JSONB`, `log TEXT`, `error TEXT`, optional
`item_id FK → items.id (ON DELETE SET NULL)`, timestamps `created_at / started_at /
finished_at`. Worker tasks call `create_job` (→ "running") then `finish_job`
(→ succeeded/failed) from `app.worker.job_tracker`.

### Scheduled-jobs mechanism
`scheduled_jobs` table: `name VARCHAR(64) PK` (matches a registry key in `worker.py`),
`description`, `schedule` (human-readable string), `last_run_at / last_run_status /
last_run_error / next_run_at`, `is_running BOOL`. The worker's `on_startup` hook seeds
one row per entry in `SCHEDULED_JOB_REGISTRY`. arq cron wrappers (one per job) call
`exec_scheduled_job(name)` which dispatches the real function and updates the row.
`POST /api/scheduled-jobs/{name}/run` enqueues `exec_scheduled_job` immediately for
on-demand "run now" outside the normal schedule.

### Render cache key: file SHA-256 hex
Rendered thumbnails are stored at `<item_dir>/renders/<sha256>.png` where `<sha256>` is
the SHA-256 hex digest of the mesh file. The worker uses the cached `File.sha256` column
when available (set at inventory time) and recomputes it only when the column is NULL.
A file whose hash changes (edited, replaced) gets a different cache key and is
automatically re-rendered on the next render job.

## 2026-06-27 — Phase 3b frontend implementation decisions

### Tag-tree endpoint removed from backend (Phase 3b section 0)
`GET /api/tags/tree`, the `TagTree`/`TagTreeNode` Pydantic schemas, the
`_get_tag_tree_depth` / `_build_tree` helpers, the `TAG_TREE_DEPTH_KEY` /
`TAG_TREE_DEPTH_DEFAULT` constants, and the `json` + `Setting` imports that
served only the tree were deleted from `backend/app/routers/tags.py`.  The
two corresponding tests (`test_tag_tree`, `test_tag_tree_depth_override`) were
removed from `test_phase3_catalog.py`.  `GET /api/tags` (popularity) is kept
and now drives the cloud exclusively.  Rationale: see "Tag tree dropped →
popularity tag cloud" entry below.

### Virtualized grid: TanStack Virtual row-at-a-time in a fixed-height container
`useVirtualizer` from `@tanstack/react-virtual` v3 is applied to *rows* of 3
items (not individual items) so the grid layout is kept in CSS (`grid-cols-3`).
The virtual container uses a fixed height of 640 px with `overflow-y: auto`.
Window-level scroll was rejected because TanStack Virtual requires a scrollable
element with a known height.  Row height is estimated at 296 px (card 280 px +
16 px gap); actual measurement uses `measureElement` ref for accuracy.
Dynamic class name `grid-cols-${COLS}` was replaced with the static
`grid-cols-3` to ensure Tailwind v4's scanner includes the class.

### ZIP download polling: useEffect + setInterval, window.open for stream
The ZIP download flow (POST /zip → poll GET /zip/{id} every 2 s → GET
/zip/{id}?download=true) uses a `setInterval` managed inside a `useEffect`.
The interval is stored in a ref to avoid stale closure issues; cleanup happens
on unmount and on status reaching a terminal state.  When status is `ready`,
`window.open(zipDownloadUrl(...))` triggers the browser's native file download.
Rejected: a custom streaming `fetch()` into a Blob — adds complexity with no
benefit; the backend streams via nginx/starlette `FileResponse` so a plain
navigation URL is sufficient.

### Tag-cloud weighting: min-max linear scale across 8 font-size steps
Font size is linearly interpolated between `TAG_SIZE_SCALE = [0.75, 0.875,
1.0, 1.125, 1.25, 1.5, 1.75, 2.0]` rem values using
`Math.round(normalised × (n−1))` to pick a bucket.  Font weight is mapped to
4 Tailwind classes (`font-normal / font-medium / font-semibold / font-bold`)
based on 4 quartile thresholds.  When all tags have the same count (min ===
max), everything renders at 1 rem / font-normal — no division-by-zero.
Pure utility functions (`getTagFontSize`, `getTagFontWeight`) extracted to
`frontend/src/lib/catalog-utils.ts` for unit-testing.

### URL as single source of truth for catalog filter state
All catalog filter params (q, tags, creator_id, favorited, sort, view, page)
live in the URL via React Router's `useSearchParams`.  This makes the catalog
fully deep-linkable.  The search input uses local state updated on every
keystroke, with a 300 ms `setTimeout` debounce writing back to URL (to avoid
racing requests on every character).  `view` is additionally persisted to
`localStorage` so the user's grid/table preference survives navigation.
Rejected: Zustand/Context for filter state — URL is simpler, free, and shareable.

### Path prefix: pure `rewritePath` function, no server-side rewrite
The dir path displayed on the item page is rewritten client-side by
`rewritePath(dirPath, prefix)` from `catalog-utils.ts`.  The function detects
Windows-style prefixes by checking for `\\`, converts internal separators, and
ensures a trailing separator.  The server always stores and returns the raw
Unix-style path.  Rejected: server-side formatted path — would require a
per-user query param on every item request or a dedicated endpoint; client-side
is cheaper and instantly reactive to prefix changes.

### Popularity sort for items not yet in the backend
The sort dropdown in CatalogPage omits a "Most popular" item sort because the
backend `GET /api/items` does not have a popularity/favorites-count sort option
in Phase 3a (`_VALID_SORTS`).  The available options (newest, oldest, title
A–Z, title Z–A, relevance) match exactly what the backend supports.  A
favorites-count sort is a Phase 4/9 enhancement.

### Phase 7 placeholders: clearly labelled dashed-border sections
The ItemPage renders two dashed-border placeholder sections ("Print History —
Coming in Phase 7" and "Sharing — Coming in Phase 7") with no interactivity.
This matches the PRD constraint that Phase 7 features must not ship in Phase 3b
but must be visually represented.

## 2026-06-27 — Tag tree dropped → popularity tag cloud

**Reversal of the §5.2 "virtual tag-browse tree."** The N-levels-deep tag hierarchy was a
holdover from an early design where objects were stored under a **tag-name directory
structure on disk**. That disk layout was dropped long ago (locked decision: files are
**never** organized by tags on disk — tags are a pure DB/UI construct, §3.2), which removed
the only reason the hierarchy mattered.

**Decision:** no tag hierarchy. Tags drive browse via a **popularity-weighted tag cloud** +
a sortable tag list; clicking a tag filters (multiple stack as AND); popularity also a sort
option. Built off the existing `GET /api/tags` (popularity counts).

**Consequences:** the Phase 3a `GET /api/tags/tree` endpoint (category-namespace tree) and
the `catalog.tag_tree_depth` setting are **obsolete and removed in Phase 3b**. Categories
on tags (§5.1) remain only as an optional **filter facet**, not a tree driver. PRD §5.2/§12
and `docs/build-plan.md` Phase 3 updated.

## 2026-06-27 — Phase 3a backend implementation decisions

### Full-text search via application-maintained TSVECTOR column
`items.search_vector TSVECTOR` + GIN index; updated via raw SQL (`to_tsvector('english', ...)`)
after every create/update in `_update_search_vector()`.  Queried with `websearch_to_tsquery('english', ...)`.
Rejected: DB trigger (harder to test, more migration ceremony); generated column (not
supported by asyncpg in SQLAlchemy's async DDL path without extensive hacks); real-time
document indexing per-request (too slow).  The application-side update means the vector
is always current as of the last successful write; an async task would add latency and
complexity for no material gain at Phase 3 scale.

### TSVECTOR mapped as `Mapped[Any]` in SQLAlchemy ORM
SQLAlchemy 2.0 has no built-in `TSVECTOR` type for the `Mapped[...]` annotation.  Rather
than defining a custom `TypeDecorator`, the column is declared `Mapped[Any]` with
`TSVECTOR` from `sqlalchemy.dialects.postgresql` as the underlying column type.  All
reads and writes go through raw `sa.text()` calls so the type is only needed for DDL
generation; the `Any` annotation satisfies mypy without confusion.

### Tag tree derived at request time from category namespace
The virtual tag tree (PRD §5.2) is computed in `GET /api/tags/tree` by grouping active
tags by the namespace part of `tag.category` (e.g. `"type:keychain"` → namespace `"type"`
→ leaf label `"keychain"`).  No `TagNode` table is maintained.  Rationale: the tree
changes only when tags are added/renamed/recategorized, which is infrequent; generating
it per-request on the active tag set is cheap and always consistent.  Rejected: storing a
precomputed tree in the DB (extra table, cache-invalidation complexity for negligible
gain); reading the category hierarchy from a static config file (out of sync with the DB
Tag table).

### ZIP bundle tracking via DownloadBundle table + inventory hash invalidation
`download_bundles` tracks arq-built ZIPs (UUID PK, `status`, `bundle_path`,
`inventory_hash`, `expires_at`).  On `POST /zip`, a fresh inventory hash is computed from
the sorted `path:sha256:size` fingerprint of all `File` rows.  A non-expired `pending`
bundle is reused (the client just polls the existing ID).  A `ready` bundle is reused if
and only if its `inventory_hash` matches the current hash — files changing invalidates it
automatically without a background watcher.  Expiry is ~24 h.  Rejected: storing the ZIP
on the item path (clutters the asset directory, confuses the file scanner); perpetual
bundles (user expects fresh downloads after file edits); Redis-only tracking (not durable
across worker restarts).

### Download streaming via starlette FileResponse (no aiofiles)
`GET /api/items/{key}/files/{path}` and `GET /api/items/{key}/zip/{id}?download=true`
use starlette's built-in `FileResponse`, which streams via its own async file reader.
`aiofiles` was not added to `requirements.txt` — starlette's own streaming is the
idiomatic approach and avoids an extra dependency.  Path traversal is blocked by
`Path.resolve()` + `relative_to()` in the handler.

### Per-user `path_prefix` stored as a nullable VARCHAR on the User row
PRD §3.3 requires a user-configurable prefix that is prepended to the displayed
`dir_path` so paths match the user's local mount.  Stored as `users.path_prefix
VARCHAR(1024)` rather than a Setting row keyed by user id.  Rationale: it is a
per-user attribute (not an instance setting); direct FK-free column avoids joins;
max 1024 chars covers any realistic filesystem path.

### Phase 3a/3b split — backend only this pass
The full phase (§1–§9 in the handoff) requires TanStack Virtual (not yet in
`package.json`), a virtualized catalog grid with item cards, an image carousel,
ZIP-download polling state machine, and vitest tests for complex client state.
After completing all backend endpoints with 157 passing tests, the frontend is deferred
to a dedicated 3b handoff (`prompts/2026-06-27-phase-3b-catalog-ui.md`) on Sonnet.

### Test fix: `test_my_creations_with_linked_creator` uses shared test session
The test patches `Creator.user_id` to link a creator to the current user.  The initial
implementation used a fresh `SessionLocal()` that committed independently of the
rolled-back test transaction.  Because the test's Creator row only exists within the
test's in-progress transaction (NullPool, rolled-back at teardown), the independent
`SessionLocal` UPDATE would target a row that does not exist in the committed DB state.
Fixed by accepting `db_session: AsyncSession` as a fixture parameter and doing the
UPDATE within the same transaction; `db_session.expire_all()` is called before the GET
so SQLAlchemy re-reads from the DB instead of returning the cached pre-update state.

### `_batch_enrich` avoids ORM relationship access to prevent async lazy-load errors
In SQLAlchemy 2.0 async, accessing a relationship attribute (`item.creator`) triggers a
lazy SQL load.  Lazy loads are disallowed in an async context (they require a greenlet)
unless the relationship was eagerly loaded.  `_batch_enrich` (in `me.py`) was refactored
to batch-query creator names via `Creator.id.in_(creator_ids)` instead of accessing
`item.creator` — this is correct in any async route and requires no `selectinload`
annotation on the calling query.

## 2026-06-27 — Phase 2 implementation decisions

### Key alphabet and length
7-character lowercase base32 (4 random bytes → `base64.b32encode` → strip `=` padding →
`lower()` → first 7 chars). This yields 32^7 ≈ 34 billion possible keys — more than
enough for any foreseeable library size. Lowercase-only avoids case-folding surprises in
URLs and on case-insensitive filesystems. Recorded: `backend/app/storage/keys.py`.

### Shard derivation
`key[:2]` — the first two characters of the key, giving 1024 possible shards (32² since
the alphabet is 32 chars). This keeps directory fan-out bounded and predictable. Matches
the §2 spec's "first N chars" approach without hard-coding a shard depth that would be
awkward to change later.

### Slugify library: python-slugify 8.0.4 + text-unidecode 1.3
`python-slugify` with `text-unidecode` (LGPL) performs NFKD-then-ASCII transliteration
at the Python level without a system-level `libunicode` dependency. Rejected:
`awesome-slugify` (heavier, GPL), hand-rolled unicodedata normalization (error-prone edge
cases). CJK text (Japanese, Chinese) is transliterated to Latin by `text-unidecode` (e.g.
`日本語タイトル` → `ri-ben-yu-taitoru`); only content that transliterates to empty (pure
emoji, lone punctuation) falls back to `"item"`.

### YAML library: PyYAML 6.0.2
`yaml.safe_dump` / `yaml.safe_load` — already widely used in the Python ecosystem, no
extra dependencies. Sidecar is always regenerated on write so round-trip comment
preservation is not needed. Rejected: `ruamel.yaml` (preserves comments, heavier).

### Delete = move to trash, not hard delete
Item delete moves `item_dir` to `/data/trash/<timestamp>-<key>/` rather than `rm -rf`.
Conforms to the PRD's "never lose data" principle: accidental deletes are recoverable by
the admin. Trash is out-of-scope for automated cleanup in Phase 2; a retention/purge
policy is Phase 9.

### File role inference from subdirectory and extension
Top-level file role is inferred in priority order: `renders/` → render, `images/` → image,
`prints/` + photo extension → photo, `prints/` + gcode extension → gcode; extension alone
→ model (3mf/stl/obj/ply), zip → zip, fallback → other. Recorded in
`backend/app/storage/inventory.py`. This heuristic is intentionally simple and overridable
via future tag-based rules.

### COOKIE_SECURE=False in test conftest
Tests run against `http://test` via httpx's `ASGITransport`. The `Secure` cookie flag
causes httpx to silently drop session/CSRF cookies on non-HTTPS URLs, breaking all
authenticated requests in tests. Fixed by adding
`monkeypatch.setattr("app.config.settings.COOKIE_SECURE", False)` to the
`isolated_data_dir` fixture. Production deployments (HTTPS) must keep `COOKIE_SECURE=True`
(the default).

### Directory fsync via os.open(O_RDONLY)
`Path.open("rb")` raises `IsADirectoryError` on Linux when called on a directory.
fsync'ing a directory (to durably persist a rename into the directory entry) requires
`os.open(str(dir), os.O_RDONLY)` → `os.fsync(fd)` → `os.close(fd)`. Applied in both
`backend/app/storage/journal.py` and `backend/app/storage/sidecar.py`.

## 2026-06-27 — Atomic move / move-journal approach (settled pre-Phase-2)

Full spec: [`docs/atomic-moves.md`](atomic-moves.md). Settled the §8.5 journaled-rename
mechanism before Phase 2 builds it. Driving goal (owner): **never leave the library in a
half-applied mess** — the Manyfold-style failure where a locked file mid-bulk-op corrupts
everything.

- **Atomic `os.replace()` is the commit point.** A title rename keeps `<key>`/`<shard>`
  invariant, so old/new dirs share a parent → the move is a single same-volume atomic
  rename, not a copy. Cross-device (`EXDEV`) → **abort**, never copy.
- **Locked-file protection = ordering.** The atomic rename is the *first* mutating step;
  a locked/in-use dir makes it raise with **nothing changed** → clean abort + clear error.
- **Roll-forward (chosen over strict rollback).** Pre-commit failures change nothing;
  **post-commit** failures (sidecar/DB) **complete forward** (idempotent), and a failed
  sidecar write self-heals via the scheduled Sync job. Rejected strict "reverse the rename
  on any failure" — undoing a successful atomic op can itself fail. Slightly amends §8.5's
  literal "roll back on any failure" wording.
- **Journal on the filesystem** (`/data/journal/<key>.json`, fsync'd) — NOT a DB table,
  since the DB is one of the coordinated resources and may be the inconsistent one.
  Recovery sweep at worker startup (+ scan/Rescan): finish-forward if new dir exists, roll
  back if old dir exists, raise an Issue if ambiguous (never guess).
- **Bulk = N isolated per-item transactions** (no global batch lock). A bad item fails
  alone as an Issue; committed/pending siblings are untouched. This is the core anti-mess
  guarantee.

## 2026-06-27 — Sidecar schema & title sanitization (settled pre-Phase-2)

Full spec: [`docs/sidecar-schema.md`](sidecar-schema.md). Settled the on-disk formats
before Phase 2 builds them (changing either after items exist on disk is costly).

- **Portability rule:** the sidecar carries **no instance-specific surrogate IDs** (no DB
  `id`, no `user_id`). Identity travels via the stable `key`; tags by name, files by
  name + hash, creator descriptively. (`creator.is_original` does **not** auto-bind to the
  importing user on transfer — it becomes an external named Creator.)
- **`schema_version`:** integer starting at **1**; bumped only on breaking changes
  (additive keys don't bump it; readers ignore unknown keys).
- **File hashing: SHA-256** (lowercase hex). Cheap-first drift check on `size`+`mtime`;
  full hash recomputed only when those change or on an explicit integrity/Rescan pass —
  keeps hashing off the hot path for large libraries.
- **Tags in the sidecar: flat canonical names.** Category/namespace lives in the instance
  Tag vocabulary and is re-derived on import (rejected: per-item structured tag objects,
  which risk drift vs. the canonical Tag table).
- **Title → on-disk name:** one sanitized form for **both** the dir and the URL slug.
  NFKD → **ASCII transliteration** → lowercase → `[a-z0-9]`-only with `-` separators →
  empty falls back to `item` → **80-char cap**. Collisions impossible by construction via
  the invariant `-<key>` suffix, which also defuses Windows reserved names and dot/space
  traps. (Rejected: preserving Unicode in the slug — NAS/SMB/Windows/zip edge cases.)

## 2026-06-27 — Phase 1b frontend identity UI decisions

### ThemeProvider context wrapping for server-side theme sync
`ThemeProvider` exports its `ThemeProviderContext` so that `AuthProvider` (which lives
inside `ThemeProvider` in the provider chain) can re-provide it with a server-aware
`setTheme` wrapper. When the user is authenticated, `setTheme` calls `PUT /api/me/theme`
(fire-and-forget) in addition to updating `localStorage` and the DOM class. When not
authenticated the original localStorage-only behavior is preserved. This avoids circular
context dependencies and requires no changes to `ThemeToggle` — components call
`useTheme()` and get the server-aware version transparently once `AuthProvider` wraps
the context.

Rejected alternative: pass an `onThemeChange` prop down from App.tsx. This required
threading auth state up above `AuthProvider`, which cannot work because `AuthProvider`
needs `QueryClientProvider` as an ancestor.

### Password-reset history uses local session state (no backend list endpoint)
`GET /api/password-reset` (a list of active tokens) is not implemented in Phase 1a.
The admin password-reset page tracks tokens created in the current browser session in
local React state. Per-session tracking is adequate for Phase 1 (single admin,
short-lived resets). A full audit list is a Phase 9 item.

### TanStack Table for admin users page only
`@tanstack/react-table` is installed and used for the `/admin/users` table as specified
in the prompt. The invites and password-reset admin pages use plain `<table>` HTML
because their structures are simple and the table library offers no material benefit
over styled HTML for these two pages.

### `input-base` CSS component class
A shared `input-base` Tailwind component class is defined in `src/index.css` using
`@layer components`. This gives all form inputs a consistent look without adding
a shadcn `<Input>` component. The style is consistent with the Phase 0 new-york/slate
theme (same border-radius variable, border color, focus ring).

### jsdom `window.matchMedia` stub added to test setup
`ThemeProvider` calls `window.matchMedia('(prefers-color-scheme: dark)')` in a
`useEffect`. jsdom does not implement `matchMedia`, causing all auth tests to fail.
Added a minimal stub in `src/test/setup.ts` (matches=false) so tests run without
importing the whole platform polyfill.

### No new frontend environment variables
All API calls use relative URLs (`/api/…`) that nginx proxies to the backend. No
`VITE_*` vars are needed for Phase 1b. `.env.example` is unchanged.

## 2026-06-27 — Creator / designer attribution model

The PRD originally had **no creator field** — only `source URL` / `source site` / `license`
on an Item — so "who designed this" was unrepresentable. Closed before Phase 2 builds the
Item model.

**Decision:** model the designer as a **normalized `Creator` entity** (like Tag), not a
plain string. `Creator` = name, optional `profile_url`, optional `source_site`, and an
**optional `user_id` FK to User**. It is **optional and best-effort** on an Item (never
required): auto-filled from **scraped** source metadata when available, else manual or
blank, and deduped/mergeable across sites.

**Self-designed = per-user.** A "this is my own design" toggle binds the Item's Creator to
the **importing user's** account (rejected: a single instance-wide "self" identity). This
directly powers the headline requirement the user asked for — **"show me everything I have
created"** = Items whose Creator is linked to the current user — and gives browse-by-creator
for external designers for free.

**Phasing:** `Creator` model + `Item.creator` + sidecar field in **Phase 2**;
browse-by-creator + the **"My Creations"** view in **Phase 3**; creator scrape + self-toggle
in **Phase 5** (import). A dedicated public **maker-profile page is out of scope for v1**
(PRD §17). Recorded in `PRD.md` (§4/§6/§12/§17) and `docs/build-plan.md` (Phases 2/3/5).

## 2026-06-27 — Phase 1 identity layer decisions

### API-key storage scheme
Per-user API keys are stored as a **SHA-256 hex digest** of the raw key only (no
Fernet-encrypted copy).  Rationale: the PRD specifies "encrypted at rest" and
"once-only display" (the user sees the raw key once at creation; the app never
re-shows it).  Storing only a hash satisfies "never cleartext in DB" and is
strictly more secure than encryption — the raw key is irrecoverable even if the
instance key is leaked, because SHA-256 is one-way.  Storing an encrypted copy
would enable re-display (security regression vs. the once-only model) for no
functional gain.  The deviation from "encrypted" → "hashed" for this one field is
documented here and in `backend/app/models/api_key.py`.

### Session store choice (DB vs Redis)
Server-side sessions are stored in the **`user_sessions` Postgres table** rather
than Redis.  Redis is already present for the arq job queue but introducing a
Redis dependency for session management adds operational cost (one more
service to crash, back up, and monitor) with minimal benefit at Phase 1 scale.
DB-backed sessions have known good performance for ≤hundreds of concurrent users,
and a `TIMESTAMPTZ expires_at` column + a periodic cleanup job (Phase 9) keep the
table small.  The session module is self-contained; if Redis sessions are needed
later, only `auth/sessions.py` changes.

### Cookie-Secure dev toggle
`COOKIE_SECURE` (default `True`) controls the `Secure` flag on both the session
and CSRF cookies.  Set it to `False` in `.env` when running over plain
`http://` locally (the Docker dev stack).  Must be `True` in any TLS deployment.
Without this toggle, browsers silently discard cookies on `http://` origins, making
local dev non-functional.  The toggle is documented in `.env.example`.

### Argon2id parameters
`passlib.CryptContext` with `argon2__type="ID"`, `time_cost=2`,
`memory_cost=65536` (64 MiB), `parallelism=2`, `hash_len=32`, `salt_len=16`.
These are moderate defaults that balance security and latency for a personal/team
server.  They meet or exceed the OWASP-recommended minimums for argon2id.
Passlib's `needs_update()` path allows transparent re-hash if params are raised
in a future version.  All hashing/verification goes through
`backend/app/auth/password.py` — no direct passlib calls elsewhere.

### Encryption-key handling
The Fernet instance key is auto-generated at first run into
`DATA_DIR/config/secret.key` (mode 0600) and **never stored in the DB or repo**.
`crypto.ensure_key()` is called once in the FastAPI lifespan so the key always
exists before the first request.  Tests patch `DATA_DIR` to a per-test temp dir
and reset the `lru_cache` so each test gets its own isolated key.
**Key rotation is a later utility** — `crypto.py` leaves a clear seam:
`encrypt()`/`decrypt()` callers never touch the key directly, so a future
`rotate()` can swap `_get_fernet()` transparently.
Losing the key means re-entering all encrypted secrets in the DB (AI provider
keys, etc.) — no key escrow is provided (per PRD §18).

### Alembic migration: raw SQL to avoid SQLAlchemy enum auto-create
Phase 1's migration (`0002_phase1_identity.py`) uses `op.execute(sa.text(...))`
throughout rather than the usual `op.create_table(...)` with `sa.Enum(...)`.
Reason: SQLAlchemy 2.x + asyncpg's `named_types` machinery attempts to issue
`CREATE TYPE` even when `create_type=False` is passed to `sa.Enum(...)` inside
`op.create_table`.  Postgres `DO $$ BEGIN CREATE TYPE ... EXCEPTION WHEN
duplicate_object THEN null; END $$` blocks in the migration are idempotent and
unambiguous.  The ORM models still use the proper `sa.Enum(...)` types; the
divergence is migration-only.

### alembic.ini: script_location uses %(here)s
Changed `script_location = alembic` to `script_location = %(here)s/alembic` so
alembic can be invoked from any working directory (e.g. the session scratchpad)
without resolving the scripts path relative to the CWD.  Also added an explicit
`sys.path` insertion in `alembic/env.py` pointing to the `backend/` root so
`from app.models import Base` works regardless of invocation directory, without
relying on `PYTHONPATH` (which would shadow the local `alembic/` package).

### Phase 1 split: backend-only (1a); frontend deferred to 1b
Implemented sections 1–7 (backend identity layer) fully with 54 passing tests.
Section 8 (frontend identity UI: login page, setup wizard, admin area, API-key UI,
theme server-persistence) is deferred to a Phase 1b handoff prompt
(`prompts/2026-06-27-phase-1b-frontend.md`).  Rationale: the backend is
security-sensitive and needed clean, well-tested implementation as a foundation.
The frontend is substantial (multiple new pages + TanStack Query wiring) and
cleaner in a dedicated pass.

## 2026-06-27 — Phase 0 scaffolding decisions

### Dockerfile layout (backend+worker)
Single root `Dockerfile` with three stages: `base` → `deps` (pip install) → `runtime`
(app source). The `deps` stage is a separate cached layer so dep changes don't
invalidate the source copy. Worker uses the same image, CMD overridden in compose.
CPU-only; no GPU/EGL at this stage (Phase 4 render spike will address headless GL).

### Frontend build / nginx serving (volume-based)
Chose a volume-based handoff between the `frontend` build service and the `nginx`
service rather than a nginx Dockerfile multi-stage build. Rationale: keeps the root
`Dockerfile` focused on the backend (per spec), makes the nginx service use stock
`nginx:1.27-alpine`, and decouples frontend and nginx builds cleanly. The `frontend`
service builds via `frontend/Dockerfile` (prod target), copies dist to the named volume
`frontend_dist`, and exits (code 0). nginx depends on `service_completed_successfully`.

Rejected alternative: a `nginx/Dockerfile` that bakes frontend into the nginx image.
Adds coupling and means the nginx image must be rebuilt on every frontend change;
the volume approach makes each concern independently buildable.

### Logo images — nginx volume mount
Logo PNGs live in `docs/images/` (checked into the repo). Rather than copying binary
blobs into `frontend/public/` (awkward with the Write tool) or into the Dockerfile,
nginx mounts `./docs/images` directly at `/usr/share/nginx/html/img/`. Frontend code
references logos as `/img/logo-horizontal-{light,dark}.png`. In dev mode, logos are
also available through the same nginx volume mount in `docker-compose.dev.yml`.

### Dev compose design (hot reload)
`docker-compose.dev.yml` overrides three services:
- `backend`: `uvicorn --reload`, bind-mounts `./backend:/app`
- `frontend`: builds `dev` target of `frontend/Dockerfile` (runs Vite dev server on
  port 5173), bind-mounts source files; node_modules stay in the image via the anonymous
  volume trick (`- /app/node_modules`)
- `nginx`: switches to `nginx.dev.conf` (proxies / → frontend:5173 with websocket
  upgrade for HMR) instead of serving static dist

Intended local dev command: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`

### CI: Postgres service added to migration-check and test jobs
`alembic upgrade head` and `pytest` both need a live Postgres. Added `services: postgres:16-alpine`
with a healthcheck to both jobs. The test job includes a Postgres service even though
Phase 0 tests don't actually touch the DB — this is pre-wired for Phase 1+ tests so the
job structure doesn't need to change.

### Alembic async engine setup
Used `async_engine_from_config` + `asyncio.run()` in `alembic/env.py` so migrations
run through asyncpg (consistent with the app's async engine). `DATABASE_URL` env var
overrides the ini-file placeholder. `poolclass=NullPool` prevents connection leaks
during migration runs.

### shadcn/ui with Tailwind v4
Used Tailwind CSS v4 (`@tailwindcss/vite` plugin, no `tailwind.config.ts`, CSS uses
`@import "tailwindcss"`). This is the current canonical shadcn/ui setup. CSS variables
for theming are defined in `src/index.css` using `@layer base`. The `@/` path alias is
configured in both `vite.config.ts` and `tsconfig.app.json`.

## 2026-06-27 — Phased build plan + locked build-time technical decisions

- Wrote [`docs/build-plan.md`](build-plan.md): 11 phases (0–10), each a shippable
  increment with exit criteria, plus the dependency shape. Phase 0 = scaffolding.
- **Locked build-time tech choices** (PRD intentionally left these open; filling them so
  the build session doesn't re-litigate):
  - Backend: FastAPI + **SQLAlchemy 2.0 async** (asyncpg) + Pydantic v2 + **Alembic**;
    deps in `backend/requirements.txt`. Job queue: **arq**. DB: **Postgres 16**.
  - **UI auth:** httpOnly secure **session cookie** (server-stored opaque token) + CSRF;
    **argon2id** password hashing; programmatic API via **per-user API keys**; auth behind
    a provider interface so **SSO** slots in later.
  - **Secrets at rest:** **Fernet**; instance key auto-generated at first run into
    `/data/config/secret.key` (0600), never in DB; rotation = re-encrypt-all (later).
  - **Version file:** `backend/app/version.py` `__version__ = "0.1.0"` (bare); frontend
    reads `/api/version`. Start at **0.1.0**.
  - Frontend: Vite + React 18 + TS + Tailwind + shadcn/ui; TanStack Query/Table/Virtual +
    React Router; theme = system→light/dark, persisted.
  - **Mesh render:** `trimesh` parse + **pyrender/EGL** (headless GL) with **VTK offscreen**
    fallback; headless GL in a container is the known risk → Phase 4 opens with a spike.
  - Image: root `Dockerfile` = backend+worker (`ghcr.io/crzykidd/partfolder3d`); nginx
    serves the built frontend; CPU-only.
- These are veto-able before Phase 0; recorded in `docs/build-plan.md` too.

## 2026-06-27 — CI workflows added with tolerant-bootstrap guards; main required-checks wired

- Added four GitHub Actions workflows (`.github/workflows/ci.yml`, `codeql.yml`,
  `publish.yml`, `retention.yml`) modeled on the `filament-bridge` project's proven
  `code-checkin-and-pr` implementation.
- **Tolerant-bootstrap decision:** every job in `ci.yml` guards its real commands
  behind file/directory existence checks so the workflow passes cleanly on the current
  empty repo. Each guard is a placeholder to be removed per-job as scaffolding adds the
  corresponding piece (`backend/`, `frontend/`, `docker-compose.yml`, `Dockerfile`,
  alembic, etc.). The `publish.yml` Dockerfile guard works the same way.
- **Required-status-checks wired (post-first-run):** after the first `dev` push CI run
  passed green, `main` branch protection was set (non-strict) to require the **6 CI
  checks**: `CI / Lint`, `CI / Config validation`, `CI / Migration check`,
  `CI / Compose validation`, `CI / Image build`, `CI / Test`.
- **CodeQL required-checks deferred to scaffolding:** `CodeQL / Analyze (python)` and
  `CodeQL / Analyze (javascript-typescript)` are intentionally **not** required yet —
  CodeQL errors with "no source code seen" on an empty tree, which would block an early
  PR to `main`. They get added to required checks once real backend + frontend source
  exists. CodeQL still runs on `main` PR/push from now on (just not gating).

## 2026-06-27 — Adopt three engineering standards; skip sandbox; autonomous dispatch model

- Adopted `code-checkin-and-pr` (1.2.0), `handoff-prompt-workflow` (2.0.0), and
  `release-prep-and-cut` (1.1.0). See [`standards.md`](../standards.md).
- **Skipped `repo-sandbox-permissions`**: this environment is not sandbox-provisioned, so
  the standard would be inert (it falls back to prompts with no friction reduction).
- **Operating model:** a central **Opus** planning session writes handoff prompts and
  dispatches autonomous **Sonnet** subagents. **Deviation from the standards'
  ask-before-commit rule:** the orchestrator **auto-commits on `dev`** with no per-step
  y/n — the user explicitly opted out of babysitting. `main` is never direct-pushed;
  everything reaches it via PR, and releases via `/release-prep` → merge → `/release-cut`.
- **`release-prep-and-cut` parked:** the slash-command templates are copied but their
  `<PLACEHOLDER>` values stay unfilled until a version file + CI exist (scaffolding).
- This adoption is the **final commit on `main`**; subsequent work moves to `dev`.
