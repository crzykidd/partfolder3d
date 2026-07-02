# Changelog

All notable changes to PartFolder 3D are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The version is stored bare (no `v` prefix) in `backend/app/version.py`; the `v`
prefix appears only on git tags and GitHub releases.

---

<!-- SKELETON — categories to use when adding entries:
### Added      new user-facing feature
### Changed    changed behaviour in an existing feature
### Fixed      bug fix
### Deprecated features removed in a future release
### Removed    features removed in this release
### Security   security-relevant fix or hardening
-->

## [Unreleased]

### Added

- **File-tree browser** — the flat file list in the "Files & Downloads" section
  is replaced with a collapsible folder hierarchy built client-side from each
  file's path. Folders expand/collapse with chevron controls; top-level folders
  default to expanded. Per-file row shows: role badge · file size · Download
  link. Image files show a small inline thumbnail.
- **In-browser 3D viewer** — clicking "View in 3D" on any `.stl`, `.obj`, or
  `.3mf` file (those with `preview_3d=true`) opens an interactive modal canvas
  powered by three.js + `@react-three/fiber`. Supports rotate/zoom/pan via
  OrbitControls; auto-fits the camera to the model bounding box on load; applies
  a two-light setup with a neutral material; background matches the active
  light/dark theme. Shows a loading-progress overlay while the mesh is fetching
  and a graceful error state if the file cannot be parsed. The viewer is
  lazy-loaded (`React.lazy` + Suspense) so three.js ships in its own async
  chunk and never inflates the initial page bundle. Over-cap files (where
  `preview_3d=false`) continue to show only the static thumbnail; no button is
  offered. ESC key or clicking outside the card closes the viewer.
- **3MF collapsible detail panel** — each `.3mf` file with a completed
  analysis shows a "Details" toggle in the file tree. The collapsed summary
  shows: Sliced/Unsliced badge · total print time · total filament weight ·
  plate count · filament count · embedded slicer thumbnail. Expanded view
  shows per-filament rows (color swatch · type · grams · meters), per-plate
  breakdown (index · time · weight), and the per-object/filament-slot list.
  Sliced data is clearly labelled "Real slicer data"; unsliced shows a
  volume-estimate warning.
- **"Slicer" badge on embedded thumbnails** — images with `source=embedded`
  (extracted from `.3mf` files by Phase A) now appear in the image carousel
  with a green "Slicer" badge, consistent with the "Rendered" badge for
  server-rendered images. The thumbnail strip also shows a small "S" indicator.
- **STL/OBJ Object Breakdown is now collapsible per-file** — the "Object
  Breakdown" section uses the same expand/collapse pattern as the 3MF panel,
  with each analyzed file starting collapsed. When all model files are sliced
  3MFs the section shows a note directing users to the inline panels above.

- **ZIP auto-extraction** — uploaded or imported ZIP files are automatically
  extracted into the item directory when the import is committed. Internal folder
  structure is preserved; a lone top-level wrapper folder is stripped; filenames
  that collide with existing files are renamed (`cover (1).png`, …). Zip-slip
  paths, `__MACOSX/`, `.DS_Store`, `Thumbs.db`, and `desktop.ini` entries are
  discarded. Nested archives (`.zip` inside `.zip`) are extracted as plain files
  (no recursion). Size/count caps (`ZIP_MAX_UNCOMPRESSED_MB` default 2048,
  `ZIP_MAX_FILES` default 10 000) and a zip-bomb ratio guard prevent runaway
  extractions. The original `.zip` is discarded after a successful extraction
  (it is reconstructable via the existing ZIP-bundle download). Extracted files
  flow through the normal inventory → analyze → render pipeline.
- **3MF embedded thumbnail extraction** — the analysis worker now reads the
  slicer-embedded thumbnail from `.3mf` files (`Metadata/plate_1.png` preferred)
  and creates a tracked `Image` row (`source=embedded`). Embedded thumbnails appear
  in the item image carousel and are used as the default image when no scraped or
  uploaded image exists.
- **3MF sliced metadata** — when a `.3mf` was sliced by Bambu Studio / OrcaSlicer,
  `analyze_item` reads `slice_info.config` (per-plate print time, filament grams/meters)
  and `project_settings.config` (filament colours, printer model) instead of the
  volume estimate. `est_method` is set to `"sliced"` in `object_analysis`, signalling
  that numbers come from the slicer (not a rough volume estimate).
- **`preview_3d` flag on `FileOut`** — `GET /api/items/{key}` now includes
  `preview_3d: bool` for each file. True when the file extension is `.stl`, `.obj`,
  or `.3mf` and the file size is ≤ `BROWSER_PREVIEW_MAX_MB` (default 50 MB).
  Used by Phase C/D frontend to decide whether to show the in-browser 3D viewer.
- **New config settings** — `RENDER_MAX_FILE_MB` (default 50), `RENDER_MAX_TRIANGLES`
  (default 1 000 000), `BROWSER_PREVIEW_MAX_MB` (default 50) in `config.py`.

### Changed

- **Server rendering bounded to STL/OBJ/PLY only** — `.3mf` files are never rendered
  server-side; embedded slicer thumbnails are used instead. STL/OBJ/PLY files over
  `RENDER_MAX_FILE_MB` or `RENDER_MAX_TRIANGLES` are skipped silently (no render, no
  error, no Image row).
- **Thumbnail priority chain enforced** — renders are only set as the default image when
  no scraped, uploaded, or embedded image exists. Previously renders could displace
  higher-priority images in the default slot.
- **Render stack collapsed to VTK-only** — `pyrender`, `PyOpenGL`, and the EGL/OSMesa
  detection/code paths removed. VTK's bundled Mesa software rasterizer is the sole render
  backend. `libegl1`, `libgbm1`, `libosmesa6`, `libxrender1`, and `libxi6` removed from
  the Dockerfile (no longer needed).
- **Embedded thumbnails excluded from sidecar** — like renders, embedded 3MF thumbnails
  are regenerated deterministically on scan and are not written to `sidecar.yaml`.
- **`ImageSource.embedded` added** — migration 0021 adds the new enum value to
  PostgreSQL via `ALTER TYPE … ADD VALUE` (outside the transaction, as required by PG).

### Fixed

- **README production-install guide** — `## Getting started` now documents the
  primary production path (pull published images, configure `.env` + library mounts,
  `docker compose up -d`) and prominently links the in-app **Quick Start** guide at
  `/quick-start` for guided first steps (add a library, load Starter Tags, enable AI,
  schedule backups). A "Build from source (dev)" subsection for contributors is kept as
  a collapsible secondary path.

### Changed

- **`docker-compose.yml` is now a production, image-based deploy** — `build:` blocks
  removed; `backend` and `worker` pull `ghcr.io/crzykidd/partfolder3d:latest`; `frontend`
  pulls `ghcr.io/crzykidd/partfolder3d-frontend:latest`. A version-pin comment (`:0.1.1`)
  is shown next to each image tag. Library mount placeholders are prominently commented
  for end-user editing; named volumes (`db_data`, `redis_data`, `frontend_dist`) are
  preserved for production durability. Header updated with a 5-step quick-start block.
- **`docker-compose.dev.yml` remains the build-from-source dev stack** — no changes;
  it continues to build all images locally with hot reload for contributors.

### Fixed

- **Sidebar over-highlighting** — a nav item is now highlighted only for its own route:
  selecting "API Keys" (`/settings/api-keys`) no longer also highlights the parent
  "Settings" (`/settings`). Section items still highlight across their sub-tabs.
- **Catalog / My Favorites highlighted together** — the sidebar now distinguishes the two
  by the `?favorited=true` query (they share the `/catalog` pathname), so selecting one no
  longer highlights both. Tolerant of other catalog query params (search/filters).
- **Quick Start "Import" and "Backups" steps never showed a Done badge** — added live
  status detection for both: the Import step flags done when `total > 0` items exist
  (universal, works for non-admin users); the Backups step flags done when at least one
  backup record exists (`GET /api/admin/backups`, admin-only). Both follow the existing
  best-effort pattern (badge hidden while loading or on error).
- **Import wizard showed library ID instead of name** — the Summary step now resolves
  `library_id` to the library name via `listLibraries()` (shared `['libraries']` cache
  key), falling back to `ID <n>` while loading and `'—'` when no library is set.

---

## [0.1.1] — 2026-07-01

> Render controls and reliability, complete job lifecycle management, per-type issue
> resolution, and catalog polish on top of the 0.1.0 baseline.

### Added

**Render controls**
- **Render mode setting** — a new instance setting (`Settings → Instance → Render mode`,
  or `RENDER_MODE` env var) controls when thumbnail rendering fires: *Render all models*
  (default), *Render only when a model has no images*, or *Disable rendering* entirely.
  The DB setting takes precedence over the env var. Lets image-heavy catalogs skip slow
  CPU renders without sacrificing scraped or uploaded images.
- **Subprocess isolation & safety** — each render now runs in a dedicated, killable
  subprocess with a configurable wall-clock timeout (`RENDER_TIMEOUT_S`, default 300 s)
  and a CPU-thread cap (`RENDER_CPU_THREADS`, default 2). A runaway or hung mesh can no
  longer block the worker indefinitely.
- **Render crash recovery** — render jobs still marked *running* when the worker
  restarts are automatically detected, marked failed, and re-queued so no render
  silently disappears after an unclean shutdown.

**Job lifecycle controls**
- **Cancel & restart** — running jobs can be cancelled from the job monitor
  (`/admin/activity/jobs`); failed or cancelled jobs can be restarted. A restart creates
  a new job that supersedes the original once it succeeds, keeping history clean.
- **Archive & retention** — jobs can be individually archived; the *Clear…* button
  archives all rows matching the active status filter (context-sensitive to the current
  view). Automatic retention prunes succeeded rows after 7 days and
  failed/cancelled/superseded rows after 30 days (configurable via
  `JOB_RETENTION_SUCCEEDED_DAYS` / `JOB_RETENTION_FAILED_DAYS`).
- **Archive view** — a dedicated archive tab on the job monitor surfaces historical
  records separately from the live queue.

**Issue resolution**
- **Per-type corrective actions** — the Issues page (`/admin/activity/issues`) now
  shows context-aware action buttons instead of a generic *Mark resolved*:
  - *Orphan* (directory + sidecar with no DB record) → **Import** (opens the import
    wizard prefilled from the sidecar) / **Delete to trash** / **Ignore**
  - *Conflict* → **Keep DB version** / **Keep sidecar version**
  - *Dead link* → **Clear source URL**
  - *Corruption* → **Accept new hash**
  - *Missing file* → **Remove file record**
  - *Sidecar error* → **Retry sync**
- **Issue deduplication** — once an issue is resolved or ignored the reconcile engine
  will not recreate the same issue on subsequent scans, preventing alert fatigue on
  recurring problems.

**Catalog polish**
- **Clickable stat tiles** — the home-page dashboard stat strip now links directly to
  the corresponding detail page (e.g. *Total items* → catalog, *Jobs* → job monitor).
- **Sortable Tags table** — the admin Tags table (`/admin/content/tags`) supports
  sorting by *Category* and *Uses* columns in addition to the existing name sort.

### Fixed

- **Scraped-image filename collision** — importing an asset from MakerWorld (and other
  sites where scraped images share a generic filename) no longer overwrites an existing
  image; filenames are deduplicated on import commit.
- **Tag-cloud font scaling** — the popularity-weighted tag-cloud font scale is now
  capped at ~14 px so a handful of very popular tags no longer visually dominate the
  cloud at the expense of readability.
- **Sidebar active-section highlight** — the admin sidebar now correctly highlights the
  active section when navigating between sub-tabs within a section (e.g. Content → Tags,
  Activity → Jobs); previously the highlight reset on sub-tab navigation.
- **Dark-theme native controls** — native `<select>` dropdowns and scrollbars now render
  dark in dark mode via explicit CSS overrides, matching the rest of the UI.

### Security

- **XSS in creator profile URL** — the import wizard no longer renders a live `<a href>` for a
  user-supplied profile URL unless it passes an `isSafeHttpUrl()` check (http/https only),
  blocking `javascript:` / `data:` and other dangerous schemes.
- **Path-traversal containment** — the file-serving endpoints in `downloads.py` and `shares.py`
  use an explicit `Path.is_relative_to()` boundary check so a requested path can never escape the
  item directory.
- **SSRF redirect hardening** — the remote share-link fetch passes `follow_redirects=False`, so a
  redirect cannot bypass the `assert_safe_url` SSRF guard applied to the initial URL.
- **Log-injection hardening** — user-supplied URLs are stripped of CR/LF before being written to
  logs in the SSRF guard and import paths.

---

## [0.1.0] — 2026-07-01

> First full-stack alpha release covering Phases 0–10 of the build plan.

### Added

**Scaffolding & infrastructure (Phase 0)**
- Docker Compose production stack: `backend` (FastAPI), `worker` (arq), `frontend`
  (React build artifact), `nginx` (reverse proxy, port 8973), `db` (PostgreSQL 16),
  `redis` (job queue + scheduler).
- Self-contained `docker-compose.dev.yml` for local development: hot-reload uvicorn
  + Vite dev server, host-visible bind-mounted data under `./private_data/data/`.
- Backend auto-migration on startup via `backend/docker-entrypoint.sh`
  (`RUN_MIGRATIONS=true` on the backend service; worker gates on backend health).
- GitHub Actions CI: `lint` (ruff + tsc), `config-validate`, `migration-check` (live
  Postgres), `compose-validate`, `image-build`, `test` (pytest + vitest).
- GitHub Actions publish workflow pushing to `ghcr.io/crzykidd/partfolder3d` and
  `ghcr.io/crzykidd/partfolder3d-frontend`; tags `:latest` on main/release, semver
  tags on release events.
- CodeQL analysis on Python and TypeScript/JavaScript.
- Artifact retention policy workflow.

**Identity & auth (Phase 1)**
- First-run setup wizard: admin account creation, instance name, external URL,
  time zone, and optional first library path.
- Session-cookie auth (httpOnly, Secure, server-stored in Postgres `user_sessions`).
- Argon2id password hashing via passlib; CSRF protection.
- Admin password-reset flow with tokenized links (7-day expiry, revocable).
- Tokenized invite links for new users (7-day expiry, revocable, with invite history).
- Per-user API keys (SHA-256 stored, once-only display at creation); Bearer token
  auth accepted on all API endpoints.
- User management: create, disable, role assignment (admin / regular user).
- Instance Fernet encryption key auto-generated into `DATA_DIR/config/secret.key`
  (0600); never stored in DB or repo. All in-DB secrets encrypted with this key.
- Settings page: display name, email, password change, theme preference, API keys,
  path-prefix rewrite.
- Dark / light / system-default theme, persisted per user (DB + localStorage).
- Full REST API for all identity operations; OpenAPI/Swagger docs auto-generated.

**Libraries & storage (Phase 2)**
- Library management: create, rename, enable/disable multiple library mounts.
- Sharded on-disk item directory layout (`/<library>/<shard>/<itemname>-<key>/`);
  shard = first 2 chars of 7-char lowercase base32 key.
- YAML sidecar (`<itemname>-<key>.yml`): full portable metadata mirror per item —
  no DB surrogate IDs, carries tags by name, files by name + SHA-256, creator
  descriptively. Schema version field for future migration.
- Atomic, all-or-nothing directory rename for item title changes: crash-safe
  filesystem journal at `/data/journal/<key>.json`, roll-forward recovery on
  startup and rescan.
- Item CRUD REST API: create, read, list, update, delete (soft-delete to trash).
- File inventory: automatic role inference (model, render, image, gcode, photo, zip)
  from subdirectory and extension; SHA-256 per-file hash; size tracking.
- Creator (designer attribution) entity: normalized, optional, best-effort; optional
  `user_id` FK to User for "my own design" toggle powering the "My Creations" view.

**Catalog, search & browse (Phase 3)**
- Full-text search via PostgreSQL application-maintained `TSVECTOR` column + GIN
  index; `websearch_to_tsquery` query parsing.
- Popularity-weighted tag cloud: linear font-size scale + weight tiers; clicking a
  tag filters the catalog (multiple tags stack as AND).
- Catalog list: **table** and **grid** views (TanStack Virtual row-virtualizer for
  large catalogs); per-user **favorites** (star, filter, sort); sort by newest,
  oldest, title A–Z/Z–A, or relevance.
- Item page: image carousel + default-image picker, full metadata, source link,
  license, SHA-256 file hashes, configurable **path-prefix rewrite** with copy
  button for host-filesystem navigation.
- Download individual files or a **ZIP bundle** (tracked in `download_bundles`
  table, invalidated automatically when files change, ~24 h expiry).
- Creator browse: "My Creations" view (items whose Creator is linked to the current
  user); browse-by-creator for external designers.
- Tag browse: filter by category namespace, sort by popularity or name.

**Worker jobs & rendering (Phase 4)**
- Headless CPU mesh rendering to PNG for **STL / 3MF / OBJ / PLY** using
  pyrender + OSMesa (EGL path tried first in Docker; OSMesa fallback; VTK
  detection via subprocess probe to avoid SIGABRT on missing EGL/OSMesa).
- Render cache keyed by file SHA-256; auto-re-rendered on file change.
- Background job model: UUID PK, type, status, progress, payload JSONB, log, error,
  optional `item_id` FK; `queued → running → succeeded | failed` lifecycle.
- Scheduled-job registry with per-job DB tracking (last run, status, next run,
  is-running); arq cron wrappers; "Run now" endpoint for on-demand triggers.
- Job monitor page (admin): live table of recent jobs with status, progress, log.
- Scheduled-job monitor page (admin): per-job status, last/next run, run-now button.

**Import & inbox wizard (Phase 5)**
- **"Add Asset" web wizard** (5-step): source URL → title confirm → tag selection →
  image selection → commit. Supported input: drag-drop upload or source URL only.
- **Inbox folder watcher**: detects new subdirectories under the configured inbox
  path (mtime-settle check prevents ingesting in-progress uploads); queues sessions
  automatically.
- **URL scraper**: `httpx` + `selectolax`; extracts Open Graph, meta-keywords,
  JSON-LD keywords; robots.txt pre-flight check; result cached per worker invocation.
- **Site capabilities** table: per-domain scrapeability flags (`can_scrape_metadata`,
  `can_scrape_images`, `requires_token`, `is_manual_only`); probed on first hit.
- **Tag reconciliation**: exact match → alias lookup → pending queue; pending tags
  created with `TagStatus.pending` and promoted via admin approval.
- Pending-tag approval queue and admin approval endpoint (`POST /api/tags/{id}/approve`).
- **Import from another instance's share link** (fetch assets + metadata, reconcile
  against local library and canonical tags).

**Reconcile engine (Phase 6)**
- **Bidirectional sidecar ⇄ DB sync**: three-way mtime comparison
  (`sidecar_written_at`, `sidecar_file_mtime`, `item.updated_at`) with 5 s tolerance.
- Detect new / removed / extra files; re-render on file change.
- **Issues** page: durably-recorded problems (conflict, dead_link, corruption, orphan,
  missing_file, extra_file, sidecar_error, other); filterable by type and status.
- **Change Log** page: append-only audit trail of all reconcile actions.
- **Review Queue** page: pending decisions for changes in `review` mode; approve /
  reject with actor tracking. Pending-count badge in the nav refreshed every 60 s.
- **Auto vs. Review modes** per behavior (`sidecar_sync`, `re_render`, `file_changes`);
  defaults: sidecar_sync=review, re_render=auto, file_changes=review. Stored in
  `settings` table; per-item rescan always uses auto.
- §8.5 isolated-per-item transactions in library scan: one bad item fails alone as
  an Issue, never blocking the rest of the scan.
- Per-item **"Rescan disk"** button for on-demand reconciliation.

**Print history & sharing (Phase 7)**
- Per-item **print records**: date, note, private/public visibility, structured slicer
  settings (printer, material, nozzle_diameter, layer_height, supports), logging user.
- **gcode parser** (best-effort, first 32 KB only): filament length, filament weight,
  estimated print time; binary `.bgcode` files skipped gracefully.
- **Aggregate print stats**: total prints, success rate, filament used, most-printed
  items.
- Per-design **tokenized share links** (256-bit entropy, `secrets.token_hex(32)`):
  public, read-only, optionally downloadable; configurable expiry, per-link override,
  and revocation.
- **Full-site share link** (admin): temporary anonymous catalog browse/download for
  guests.
- **Share audit log**: `ShareAuditEvent` rows on every view and download access;
  expiry events recorded by nightly cron.
- Public ZIP bundles: `requester_user_id=NULL`, `include_print_history=False` by
  default; `include_history` flag opt-in for share-link holders.

**AI tagging — optional (Phase 8)**
- Provider registry: **Anthropic Claude** (`claude-opus-4-8` default via `anthropic`
  SDK), **OpenAI** (via `openai` SDK), **local LLM / Ollama** (OpenAI-compatible
  endpoint).
- Provider API keys stored Fernet-encrypted in DB (`api_key_encrypted`); never
  returned in responses; test-connection endpoint does not persist to DB.
- **Tag suggestion**: structured JSON schema in system prompt; canonical tags matched
  against existing vocabulary; hallucination guard strips unknown canonicals; new
  suggestions capped at 5.
- **Description cleanup**: rewrite, extend, or summarize item description via AI.
- **Web-scrape summarization**: condense scraped metadata into a clean description.
- AI provider settings page (admin): add, test, remove providers; model override.
- **Manual-only always works** with zero AI configured; all AI paths degrade
  gracefully and never raise to the HTTP layer.

**Admin & backup (Phase 9)**
- **Scheduled DB backup**: in-process asyncpg dump of all table rows to
  `db.json.gz` inside a timestamped `.tar.gz` archive; bundles `config/secret.key`.
  Runs nightly at 04:00 UTC; configurable retention count (default 10); run-now-able.
- **Catalog JSON export** (`GET /api/admin/export/catalog`): full export of items,
  tags, aliases, creators, and print records as a downloadable JSON file.
- **Tag administration page**: list pending tags, approve/reject, set category,
  manage aliases, merge tags (repoints ItemTag + TagAlias rows, adds source as alias
  of target, idempotent).
- **Site capabilities admin**: full CRUD for site-capability entries and encrypted
  tokens; reprobe endpoint.
- **API key admin**: create, list, revoke per-user API keys.
- **API parity**: every UI action has a corresponding REST endpoint; Bearer API-key
  auth verified across all admin endpoints.

**Hardening (Phase 10a)**
- 8 database indexes added (migration 0010): `item_tags(tag_id)`, `items(creator_id)`,
  `items(created_at DESC)`, `items(updated_at DESC)`, `items(title)`,
  `share_links(created_by_id)`, `print_records(item_id, visibility)`,
  `download_bundles(item_id, status, expires_at)`.
- 31 hardening tests added: SSRF guard (unit + integration), path traversal guards,
  admin-only route enforcement, per-user write scoping, AI key masking, share-link
  public/private record separation, FTS injection resistance, index existence.

**Release machinery (Phase 10b)**
- `CHANGELOG.md` created (this file).
- `/release-prep` and `/release-cut` slash commands filled with project-specific
  values (version file, image registry, CI checks, docs-to-sync).
- CI `compose-validate` job corrected for the now-standalone dev compose.
- README version badge and `## What's New` section added.

### Changed

- **Tag browse:** replaced the planned hierarchical tag tree (PRD §5.2) with a
  popularity-weighted flat tag cloud. The tree was a holdover from an earlier
  on-disk-by-tag-directory design that was dropped; the cloud is simpler and
  equally powerful for navigation.
- **Dev compose:** `docker-compose.dev.yml` made self-contained (single file, run
  with `docker compose -f docker-compose.dev.yml up --build`) rather than an overlay
  on top of the production compose. Provides a uniform one-file/one-command dev
  workflow.
- **Reconcile modes UI:** placed on the Reviews page (not the Settings page) so
  the mode controls appear alongside the review queue they govern.

### Fixed

- `CREATE TYPE IF NOT EXISTS` is not valid PostgreSQL — migration 0006 corrected to
  use `DO $$ BEGIN ... EXCEPTION WHEN duplicate_object THEN null; END $$;` blocks.
- PyOpenGL platform module cache conflict: `_try_egl()` now clears `OpenGL.*` from
  `sys.modules` on failure so `_try_osmesa()` starts with a clean module state.
- VTK render detection changed from importability check to subprocess probe to
  prevent undetectable SIGABRT when VTK lacks EGL/OSMesa support.
- `from __future__ import annotations` + FastAPI 204 routes: `response_model=None`
  added explicitly on all 204 routes in files using PEP 563 annotations to avoid
  FastAPI assertion on `NoneType` response model.
- `python-multipart` added to `requirements.txt` (required for FastAPI Form/File
  endpoints; absence caused import-time crash on startup).

### Security

- **SSRF guard** (`app/storage/ssrf_guard.py`): DNS pre-flight resolution blocks all
  requests from the URL scraper and instance-import endpoints to RFC-1918 private
  ranges, loopback, link-local, and cloud-metadata addresses (e.g. 169.254.169.254).
  Applied to `scraper.scrape_url()`, `import_sessions.create_import_session()`, and
  `import_sessions.import_from_share_link()`.
- **Share-link private-data protection**: print records with `visibility="private"` are
  filtered at the SQL query level on every public share endpoint — private records are
  never fetched and then filtered in Python. A double-gate (endpoint + worker) ensures
  a programming mistake in one layer is caught by the other. Public ZIP bundles
  explicitly set `requester_user_id=NULL` and default `include_print_history=False`.

---

## Archived releases

_No archived releases yet. When v0.2.0 or later ships, the v0.1.x detail is moved to
[`docs/CHANGELOG-0.1.x.md`](docs/CHANGELOG-0.1.x.md) and a summary block replaces it
here. See Step 3 of [`/release-prep`](.claude/commands/release-prep.md) for the
archive trigger rules._
