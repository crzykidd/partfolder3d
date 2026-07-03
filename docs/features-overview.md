# PartFolder 3D — Features Overview

**As-built feature catalog — current as of v0.3.0.** This is the living "what exists
now" reference for shipped functionality (kept current with each release); the
[`PRD.md`](../PRD.md) holds product intent, and [`CHANGELOG.md`](../CHANGELOG.md) holds
the per-release history. Each entry notes the admin section/route where the feature is
configured (where applicable). When a feature ships or changes, update the relevant
entry here in the same commit.

---

## AgentQL fallback scraper

The built-in static scraper cannot reach Cloudflare-gated sites (e.g. MakerWorld).
When enabled, **AgentQL** is called as a cloud-browser fallback *only* when the static
scraper returns a blocked result — ordinary sites are never billed. Requires a BYO
AgentQL API key. Budget controls: **free-only** mode (counts calls against a free
allowance, default 50/month) or **cap** mode (stops when estimated cost exceeds a
monthly $ limit). Reset day is the 1st of each month.

Configure: **AI & Scraping** → `/admin/ai/sites` (Site Capabilities tab).

---

## AI usage tracking and cost estimates

Every AI call (tag suggestions, description cleanup, summarization) is recorded in an
`ai_usage` table with provider, model, input/output token counts, action, and success
flag. The **AI Usage** page aggregates totals for 24 h / 7 d / 30 d windows and shows
per-provider estimated cost in USD using a local pricing table (Ollama is always $0;
unknown OpenAI models show "—" rather than a misleading $0). Costs are labeled as
estimates; the provider's billing dashboard is authoritative.

View: **AI & Scraping** → `/admin/ai/usage`.

---

## Asset analysis (filament estimate + color count)

For **STL, 3MF, OBJ, and PLY** files (`MESH_ANALYSIS_EXTENSIONS`), the background worker
computes per-object **estimated filament grams** (volume × density × infill %) and
**color count**. For mesh files (STL/OBJ/PLY) the estimate comes from mesh volume; for
`.3mf` the worker prefers **real slicer data** (per-plate print time, filament
grams/meters, colors) embedded by Bambu Studio / OrcaSlicer and only falls back to a
volume estimate when the file is unsliced (`est_method` records which was used).
Results appear in an "Object Breakdown" section on the item page. Meshes that are not
watertight are flagged with a **LOW CONF** badge. Two site-wide settings control the
volume estimate: `estimate.filament_density_g_cm3` (default 1.24 g/cm³, typical PLA)
and `estimate.infill_pct` (default 15 %). Analysis is cached per file SHA-256 and
re-runs automatically when a file changes.

No admin configuration needed; runs automatically on import/rescan.

---

## Modification tracking

When an item is imported from a source URL, the model-file SHA-256s are captured as a
**baseline**. The reconciliation engine compares current file hashes to the baseline on
each scan; any difference (added/removed/changed model file) sets `locally_modified =
true`. A **"modified copy"** notice appears on the item's public share page when this
flag is set. Users can override the auto-detection per item (force "modified" or force
"original") from the item page; the override survives future scans.

No admin configuration needed; runs as part of the reconciliation scan.

---

## Per-library × per-OS local path prefixes

Each library stores independent path prefixes for **Windows** (`\` separators) and
**Linux/macOS** (`/` separators). The browser auto-detects the visitor's OS via
`navigator.userAgentData` and picks the right prefix when displaying the full local
path on an item page. Users can force a specific OS style (or "auto") via a
**Settings** toggle. A `pf3d_os_override` value in `localStorage` persists the choice
per browser.

Configure: **Settings** → `/settings` (Path Prefix section, per library).

---

## Image management: renders, upload, delete, and delete-to-trash

- **Renders as gallery images** — after a mesh is rendered, the PNG is recorded as an
  `Image` row (`source=render`) and appears in the item carousel alongside scraped and
  manually uploaded images.
- **Per-item image upload** — admins and item owners can upload additional images from
  the item page; stored in `<item_dir>/images/`.
- **Per-item image delete** — any curated image can be removed; if the deleted image
  was the default, the next image by order is promoted automatically.
- **Delete to trash** — deleting an item moves its directory to
  `DATA_DIR/trash/<itemkey>` rather than permanently removing it; recoverable by
  moving it back into the library.

No admin configuration needed; actions are available on the item page.

---

## Item file management (upload, rename, delete, rescan)

Owners and admins can maintain an item's on-disk files directly from the **Files &
Downloads** panel on the item page — no full re-scan required:

- **Upload file** — accepts model files, archives, G-code, and documents. The backend
  sanitizes the filename, resolves collisions with a counter suffix (`part (1).stl`),
  infers the file role from its extension, and enqueues the standard analyze + render
  pipeline. ZIP uploads auto-extract (see below).
- **Rename file** — inline edit (Enter to confirm, Escape to cancel); path-traversal and
  collision guarded.
- **Delete file** — two-step trash-can confirm; best-effort removal on disk.
- **Rescan disk** — re-inventories the item's folder and resyncs the sidecar via the
  reconcile engine, then refreshes the page. Per-item rescans always apply changes
  automatically (no review queue), so out-of-band edits show up immediately.

All three file operations sync the item sidecar. The panel is collapsible/scrollable,
shows a file count, sorts model files (stl/obj/3mf/ply) to the top of each folder, and
starts the `images/` folder collapsed.

No admin configuration needed; actions are on the item page (owner-gated).

---

## In-browser 3D viewer and view capture

Clicking **View in 3D** on any `.stl`, `.obj`, or `.3mf` file whose size is within
`BROWSER_PREVIEW_MAX_MB` (default 50 MB; exposed as `preview_3d` on each file) opens an
interactive viewer powered by three.js + `@react-three/fiber`:

- Rotate / **zoom-to-cursor** / pan via OrbitControls; the camera auto-fits the model
  bounding box; background follows the active light/dark theme.
- The viewer renders through a portal as a **centered overlay** with an
  **expand-to-full-window** toggle; ESC / backdrop / **X** close it.
- The three.js bundle is **lazy-loaded** (`React.lazy` + Suspense) so it never inflates
  the initial page load. Over-cap files show only the static thumbnail (no button).
- **Save view (capture)** — owners get a camera-icon button that snapshots the current
  WebGL frame and saves it as a new item image (`source=captured`, migration 0022).
  Multiple captures are supported and any can be promoted to the default thumbnail.
  Especially useful for `.3mf`, which has no server-side render.

No admin configuration needed; available on the item page.

---

## ZIP auto-extraction

Uploaded or imported `.zip` files are **automatically extracted** into the item
directory on import commit (or on upload from the item page). Internal folder structure
is preserved; a lone top-level wrapper folder is stripped; filenames that collide are
renamed (`cover (1).png`). Zip-slip paths and junk entries (`__MACOSX/`, `.DS_Store`,
`Thumbs.db`, `desktop.ini`) are discarded; nested archives are kept as plain files (no
recursion). Guards: `ZIP_MAX_UNCOMPRESSED_MB` (default 2048), `ZIP_MAX_FILES` (default
10 000), and a zip-bomb ratio check. The original `.zip` is discarded after successful
extraction (reconstructable via the ZIP-bundle download). Extracted files flow through
the normal inventory → analyze → render pipeline. An `extract_archives` Job row tracks
progress so the item page updates when extraction finishes.

No admin configuration needed; runs on import/upload.

---

## Tag improvements: delete, autocomplete, starter tags, and sort

- **Tag delete** (`DELETE /api/admin/tags/{id}`) — removes a tag and untags all items
  that use it; items themselves are never deleted. Safe to run on active or pending
  tags. Returns `{ deleted: true, items_untagged: N }`.
- **Typeahead autocomplete** in the import-wizard Tags step — debounced prefix search
  (`?search=`) on existing active tags; results appear in a keyboard-navigable dropdown;
  selecting an existing tag adds it directly to confirmed tags without going through the
  new-tag approval path.
- **Starter-tags loader** — `POST /api/tags/load-defaults` (idempotent) seeds a
  curated 57-tag vocabulary across 7 categories (type, function, feature, theme,
  process, audience, mechanical); skips tags that already exist.
- **Tag-cloud sort** — compact "A–Z / #" toggle on the catalog tag cloud; Number mode
  (default) sorts by `item_count` desc; Alpha mode sorts A–Z. Choice persists in
  `localStorage`. **In-use-only** filter (`?in_use_only=true`) hides tags with zero
  items.
- **Sortable Tags table** — the admin Tags table (`/admin/content/tags`) supports
  click-to-sort on the **Category** and **Uses** columns (ascending / descending /
  clear cycling).
- **Dark-mode native dropdowns** — sort-control `<select>` elements on the catalog
  page set `color-scheme` to match the active theme so the browser's native dropdown
  renders correctly in dark mode.

Configure: **Content** → `/admin/content` (Tags tab) for tag management.

---

## Import management

Operators can manage in-progress import sessions without needing database access:

- **Delete import session** — removes the session record and cleans up the staging
  directory (safety-checked: only paths inside `DATA_DIR` are removed).
- **Delete staged image** — removes one image from a pending session; promotes the
  next image to default if the deleted image was the default.
- **Clear inbox folder** — removes a detected-but-unprocessed inbox directory.

Access: **Imports** page → `/import` (active import session list).

---

## Bulk import commit

Instead of committing pending import sessions one wizard at a time, the **Commit ready**
button on `/imports` commits many at once (`POST /api/import-sessions/bulk-commit`). Pass
a list of session IDs or `null` to target all visible pending-wizard sessions; an
optional `library_id` override applies to the whole batch. Library resolution per
session falls back through: request override → the session's own `library_id` → the
`import.default_library_id` instance setting → the sole enabled library → skip-with-
reason. **Each session commits in its own isolated transaction**, so one failure never
rolls back the others, and the call returns `{ total, committed, skipped, errors }` for a
partial-success summary. Both the per-session commit and bulk-commit accept a
`render: "auto" | "off"` option to defer server renders (e.g. for scripted migrations).

Configure the default target library: **Settings** (admin) → `import.default_library_id`.
Access: **Imports** page → `/imports` (Commit ready button; a library picker appears when
multiple libraries exist and no default is set).

---

## Job monitor / lifecycle

The admin job monitor (`/admin/activity/jobs`) covers the full job lifecycle:

- **Cancel** — abort a running job (sets status to `cancelled`; best-effort aborts the
  arq task via `allow_abort_jobs=True`).
- **Restart** — re-enqueue a job of any status; if currently running, cancels it first.
- **Retry** — re-enqueue a failed job. The original failed `Job` row is preserved as
  history; the new job links back via `retry_of_job_id`. When the new run succeeds, the
  old row is automatically marked `superseded`. Currently supported type: `render`.
- **Clear… button** — context-sensitive to the active status filter: archives all
  `succeeded`, `failed`, or `cancelled` rows in one click; hidden when the filter is
  `running` or `queued`.
- **Archive view** — toggle to a history list of archived (cleared) rows; restarting or
  hard-deleting individual archived rows is available from this view.
- **Retention** — a daily prune hard-deletes old rows: succeeded after 7 days,
  failed / cancelled / superseded after 30 days. Both thresholds are configurable via
  `JOB_RETENTION_SUCCEEDED_DAYS` / `JOB_RETENTION_FAILED_DAYS`.

Access: **Jobs & Activity** → `/admin/activity/jobs`.

---

## Render reliability and controls

Mesh renders run in an **isolated subprocess** so the worker event loop is never
blocked. Each subprocess has:

- A **wall-clock kill timeout** — the child is `SIGTERM`'d then `SIGKILL`'d after
  `RENDER_TIMEOUT_S` seconds (default 300). Raises `RenderTimeout`; the `Job` row is
  marked failed.
- A **CPU-thread cap** — `OMP_NUM_THREADS`, `LP_NUM_THREADS`, and related vars are set
  to `RENDER_CPU_THREADS` (default 2), limiting saturation on shared hosts.

**Render mode** controls when items are auto-rendered:

| Value | Behavior |
|---|---|
| `all` (default) | Render every mesh item. |
| `no_images` | Only render items that have no images (render as fallback thumbnail; skip items that already have real images). |
| `off` | Never auto-render. |

Set via the `RENDER_MODE` env var or the **Settings → Instance settings** admin control
(`render.mode` DB key). The DB value takes precedence over the env var.

On **worker restart**, any jobs still in `running` status (orphaned by a previous crash)
are automatically detected, marked `failed`, and re-enqueued — one re-enqueue per unique
`item_id` — so no render silently disappears.

Configure: `RENDER_TIMEOUT_S`, `RENDER_CPU_THREADS`, `RENDER_MODE` in `.env`; or
**Settings** → `/settings` (Instance settings section, admin only).

---

## Worker resource limits

The background worker no longer runs a fixed pool, so a bulk import (or a large startup
backlog) can't overrun a small host. Two layers bound it:

- **Concurrency limits** (env): `WORKER_MAX_JOBS` (default 2, total jobs at once),
  `RENDER_CONCURRENCY` (default 1 — renders are the heaviest job, each a mesh +
  vtk-osmesa subprocess), and `ANALYZE_CONCURRENCY` (default 2, mesh analysis loads whole
  meshes into RAM).
- **Hard container caps** (docker-compose, the backstop): `WORKER_CPUS` (default 2) and
  `WORKER_MEM_LIMIT` (default 3g) confine the worker container so it gets CPU-/OOM-limited
  instead of taking down the whole box.

Each setting carries a per-setting risk note in `.env.example`. Start small and raise
carefully on constrained hosts.

Configure: `WORKER_MAX_JOBS`, `RENDER_CONCURRENCY`, `ANALYZE_CONCURRENCY`, `WORKER_CPUS`,
`WORKER_MEM_LIMIT` in `.env`.

---

## Issue resolution (per-type actions)

The admin Issues page (`/admin/activity/issues`) provides actionable, context-aware
resolution via `POST /api/issues/{id}/action`. Available actions are computed from the
issue type and whether an item DB row exists:

| Issue type | Available actions |
|---|---|
| `orphan` (no DB row) | `import` — opens the import wizard prefilled from the folder's sidecar · `delete` — moves directory to trash · `ignore` |
| `orphan` (DB row, directory gone) | `delete_item` — removes the DB item record · `ignore` |
| `conflict` | `keep_db` — rewrites sidecar from DB state · `keep_sidecar` — applies on-disk sidecar fields to DB · `ignore` |
| `dead_link` | `clear_source` — clears `item.source_url` · `ignore` |
| `corruption` | `accept` — recomputes SHA-256 from disk and accepts the new hash · `ignore` |
| `missing_file` | `remove_record` — deletes the `File` DB row · `ignore` |
| `sidecar_error` | `retry` — re-runs reconcile for the item; resolves if clean · `ignore` |

Resolved and ignored issues **stick**: the reconciliation scanner deduplicates by
`(issue_type, target_path)` and does not re-create an issue that already exists in
`open` or `ignored` status. The `import` action returns an `import_session_id`; the UI
navigates directly into the import wizard.

Access: **Jobs & Activity** → `/admin/activity/issues`.

---

## Aurora UI: switchable nav, widget dashboard, Quick Start, and 5-section admin nav

- **Switchable navigation** — each user can choose **top-bar** or **side navigation**
  in Settings; choice persists per-user.
- **Customizable widget dashboard** — the home page shows a configurable set of
  stat/shortcut widgets; layout persists per-user. Each stat tile with a `linkTo`
  value is **clickable** and navigates to its corresponding detail page (e.g. Total
  Assets → catalog, Jobs Running → job monitor, Open Issues → issues page, Open
  Reviews → reviews page).
- **Quick Start page** (`/quick-start`) — step-by-step onboarding with live status
  badges for library, path prefix, AI provider, and invite setup.
- **5-section admin nav** — the 17+ old admin menu entries are consolidated into five
  tabbed sections (see [nav-architecture.md](nav-architecture.md) for the full route
  map). Old `/admin/*` paths redirect automatically.
