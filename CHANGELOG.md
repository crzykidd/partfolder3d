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

### Fixed

- **Import wizard AI buttons now use the typed-but-unsaved description** (issue
  #16) — clicking "Clean up (AI)" or "Summarize scrape (AI)" before advancing
  the step previously sent only the session ID; the backend cleaned the already-
  persisted `session.description`, which was empty/stale. Both cleanup and
  summarize endpoints now accept `description` and `title` in the request body
  and prefer those values over the persisted session. The wizard buttons pass the
  current component state so the AI always sees what is visible in the form.

- **AI provider calls no longer block the event loop** (issue #17) — `_dispatch`
  (and its callers `suggest_tags`, `cleanup_description`, `summarize_scrape`) is
  a synchronous function that was called inline inside async route handlers,
  freezing the single Uvicorn event loop for as long as the AI provider took to
  respond. All call sites now use `asyncio.to_thread` so a slow or stuck provider
  only stalls the one request that triggered it. An explicit timeout (10 s for the
  connectivity test, 60 s for inference calls) is passed to the SDK so the call
  fails fast rather than hanging indefinitely.

### Added

- **`render` preference on import-session commit paths** — `POST /api/import-sessions/{id}/commit`
  now accepts an optional JSON body (`CommitOptions`) with `render: "auto" | "off"` (default
  `"auto"`); `POST /api/import-sessions/bulk-commit` gains the same field on `BulkCommitRequest`.
  `"off"` suppresses server-side render enqueueing for the session/batch entirely — useful for
  scripted bulk migrations where renders are deferred or triggered later via browser capture.
  `"auto"` preserves existing behaviour (still gated by the instance `render.mode` setting).
  Omitting the body/field is fully backward-compatible. (Closes #15)

- **Bulk commit endpoint** (`POST /api/import-sessions/bulk-commit`) — commits
  multiple pending-wizard import sessions in one call.  Pass `session_ids` (list
  of UUIDs) or `null` to target all visible pending-wizard sessions.  An optional
  `library_id` override applies to every session in the batch.  Library resolution
  per session: (a) request override, (b) session's own `library_id`, (c) new
  `import.default_library_id` instance setting, (d) sole enabled library, (e) skip
  with reason.  Each session runs in its own isolated transaction — one failure does
  not roll back others.  Returns `{ total, committed, skipped, errors }` for
  full partial-success reporting.  (Issue #15)
- **Default import library setting** (`import.default_library_id`) — admin can
  configure a default library via Settings.  Used by bulk commit and the inbox
  scanner when a session has no explicit library set.  Validates that the referenced
  library exists and is enabled; accepts null to clear.
- **"Commit ready" button on `/imports`** — one-click bulk commit for all pending
  inbox sessions visible to the current user.  If multiple libraries exist and no
  default is configured, a library-picker modal appears before submitting.  Shows a
  partial-success summary (committed N/M; reasons for skips/errors).

## [0.2.5] — 2026-07-02

### Added

- **Confirm-password field on the setup wizard** — the first-run setup form now
  requires the admin to re-enter their password before proceeding. Mismatched
  passwords are caught client-side with an inline error; the confirm value is
  never sent to the backend (API contract unchanged).

### Fixed

- **First-run setup wizard now auto-logs in correctly** (issue #13) — completing
  the wizard previously dropped the user on the login screen instead of navigating
  into the app. Root cause: `SetupPage.onSuccess` called
  `queryClient.invalidateQueries({queryKey:['me']})` (fire-and-forget) then
  `navigate('/')` synchronously. `AuthGuard` rendered before the background
  refetch resolved (`user===null`, `isLoading===false`) and immediately redirected
  to `/login`. Fix: `onSuccess` is now `async` and `await`s
  `queryClient.refetchQueries({queryKey:['me']})` before calling `navigate`,
  ensuring `AuthContext.user` is populated before `AuthGuard` evaluates. Same
  fix applied to `LoginPage.onSuccess` (identical latent race). Belt-and-suspenders
  backend change: `run_setup` now calls `await db.commit()` explicitly before
  returning so the session row is guaranteed durable regardless of FastAPI
  version commit-ordering behaviour.

- Import wizard "set default image" not applied on commit (issue #14). PATCH
  `default_image_path` now syncs `ImportSessionImage.is_default` flags so the
  commit handler sees the correct default; a defensive fallback in
  `commit_import_session` handles the edge case where `default_image_path` is
  set before image rows are materialized.

### Security

- Sanitize CR/LF before logging the user-provided `default_image_path` in the
  import-session PATCH handler (CodeQL `py/log-injection`), matching the escaping
  already used elsewhere in the import-sessions package.

## [0.2.4] — 2026-07-02

> ⚠️ **nginx config changed** — if you are running a custom nginx config
> (the `./nginx/nginx.conf` bind-mount in `docker-compose.yml`), compare your
> copy against the updated `nginx/nginx.conf` in this release and reconcile any
> differences before upgrading.

### Added

- **Folder browser for library mount-path setup** — the Add Library form now
  includes a Browse button that opens a modal filesystem navigator. Operators
  can drill into the container filesystem (starting from the configured
  `FS_BROWSE_ROOTS`, default `/library`) and click "Select this folder" to fill
  the Mount path field instead of typing it. Manual text entry is preserved as
  a fallback. The backend endpoint (`GET /api/admin/fs/browse`) is admin-only
  and rejects any path that resolves outside the allowlist (prevents traversal
  to `/`, `/etc`, `/proc`, or arbitrary absolute paths). (Closes #8)

### Fixed

- **Native `<select>` dropdowns no longer render a white option list in dark mode**
  (fixes #6, #10) — the signup Timezone picker and the Add Asset Library selector
  showed a white popup because the aurora input background is semi-transparent
  (`rgba(255,255,255,0.06)`), which over a native option popup's own light base is
  effectively white, and `color-scheme: dark` alone doesn't reliably darken option
  lists (notably Chrome on Windows). Options now get an explicit opaque dark surface
  + light text in dark mode.

- **Disabled libraries no longer appear as import destinations** — soft-deleted
  (`enabled = false`) libraries were still offered in the Add Asset modal (both
  Upload and From-URL tabs), letting users target a library they had just
  "deleted." The destination pickers now filter to enabled libraries only; if all
  libraries are disabled a clear message is shown. The admin Libraries page is
  unaffected and continues to list all libraries. The backend already rejected
  disabled-library sessions at create time; the frontend now prevents the
  selection in the first place. (Fixes #9)

- **Corrected the settings location text on the version/landing page** — the
  info card said "Admin → Settings" but that nav item does not exist; library
  paths and configuration live under **Admin → Content**. The text now links
  directly to `/admin/content/libraries` using React Router `<Link>` so it
  cannot silently drift out of sync again. (Fixes #7)

- **Images and renders now display in production** (nginx no longer 404s
  `/api/…/*.png`) — the baked nginx config's static-asset regex
  (`location ~* \.(png|jpg|js|…)$`) matched *any* URL ending in an image
  extension, including proxied item images like
  `/api/items/<key>/files/renders/<sha>.png` and baked logos under `/img/`. Because
  regex locations are evaluated before plain prefixes, those requests were served
  from nginx's frontend root (where they don't exist) and returned 404 instead of
  being proxied to the backend — so thumbnails/renders never rendered. The `/api/`
  and `/img/` locations now use `^~` to take precedence over the regex.

- **Frontend "publish" container now logs a version banner and fails loudly** —
  previously it ran a bare `cp … && echo` and exited silently, so a failed asset
  copy (most often the `frontend_dist` volume not being writable by the
  configured `PUID`/`PGID`) blocked nginx with no explanation. It now logs
  `PartFolder 3D frontend vX.Y.Z — uid=… gid=…`, verifies the destination is
  writable (clear FATAL + remediation if not), reports how many files it
  published, and states that exit 0 is expected.

- **`ALLOWED_ORIGINS` no longer crashes the app when set as a comma-separated
  string** — `.env.example` documents the comma form
  (`ALLOWED_ORIGINS=https://a,https://b`), but pydantic-settings JSON-decodes
  list env vars, so a plain/empty value raised `SettingsError: error parsing
  value for field "ALLOWED_ORIGINS"` at boot (the app exited before serving). The
  setting now accepts a comma-separated string, a JSON array, or an empty value.

- **Backend startup now logs and fails loudly instead of hanging silently** — the
  container entrypoint previously printed only "applying database migrations…" and
  then went dark on any problem, so a bad DB host/credentials, an unwritable data
  volume (PUID/PGID mismatch), or a lock-blocked migration all looked identical: a
  stuck service with no logs. The entrypoint now (1) verifies the data dir is
  writable and prints a clear FATAL on a permissions problem, (2) waits for the
  database with a bounded timeout and logs the **actual** connection error
  (`ConnectionRefusedError`, `InvalidPasswordError`, …) on each attempt, and (3)
  runs migrations with a `lock_timeout`/`statement_timeout` **and** a hard
  `MIGRATION_TIMEOUT` (default 600s) so a blocked migration errors with a clear
  message naming the culprit instead of hanging forever. It also logs a startup
  banner — app **version**, uid/gid, the current DB revision before upgrading, and
  the `DATABASE_URL` **with the password redacted** — plus streams alembic's
  per-migration output live (`PYTHONUNBUFFERED`), so a user's log paste alone is
  enough to report an issue. Tunable via `DB_WAIT_TIMEOUT`, `DB_CONNECT_TIMEOUT`,
  `MIGRATION_LOCK_TIMEOUT_MS`, `MIGRATION_STATEMENT_TIMEOUT_MS`, `MIGRATION_TIMEOUT`.

## [0.2.3] — 2026-07-02

> ⚠️ **nginx config changed** — if you are running a custom nginx config
> (the `./nginx/nginx.conf` bind-mount in `docker-compose.yml`), compare your
> copy against the updated `nginx/nginx.conf` in this release and reconcile any
> differences before upgrading.

### Added

- **Published `partfolder3d-frontend` and `partfolder3d-nginx` images** — the
  publish workflow now builds and pushes all three images (`ghcr.io/crzykidd/partfolder3d`,
  `ghcr.io/crzykidd/partfolder3d-frontend`, `ghcr.io/crzykidd/partfolder3d-nginx`)
  on every push to `dev`/`main` and on release events, with the same tag scheme
  (`dev`, `sha-<short>`, `latest`, semver) applied to each.

### Fixed

- **Frontend production build (`npm run build`) now succeeds** — removed ~20 unused
  imports/variables flagged by `noUnusedLocals` under the strict project-reference
  tsconfig, and fixed 4 real type errors (`SideNavShell` functional-updater mismatch,
  `CatalogPage` `useMutation` generic types, `AiUsagePage` Lucide icon as `ReactNode`).
- **CI and release typecheck gates corrected** — both `ci.yml`/`dev-checks.yml` and
  `/release-prep` now run `npm run build` (`tsc -b`) instead of `npx tsc --noEmit`
  (root tsconfig, which skips strict project-reference settings and misses these errors).

### Changed

- **nginx config baked into the `partfolder3d-nginx` image** — the production
  nginx config (`client_max_body_size 1024m`, `/api/` proxy, `/health` proxy,
  `/img/` logo alias, SPA fallback) is now compiled into a dedicated nginx image
  (`nginx/Dockerfile`). The production `docker-compose.yml` no longer bind-mounts
  `./nginx/nginx.conf` or `./docs/images`; a commented-out optional override line
  is provided for operators running a custom config.
- **Logo images moved to `/img/` alias** — brand images (`docs/images/`) are baked
  into the nginx image at `/usr/share/nginx/img/` and served under `/img/` via an
  explicit `location /img/ { alias …; }` block, separate from the `frontend_dist`
  volume mount at `/usr/share/nginx/html`.
- **Production compose is now fully self-contained** — a fresh host running
  `docker compose up -d` with only `docker-compose.yml` + `.env` gets a fully
  working stack; no repo files (nginx config, logo images) are required on the host.

## [0.2.2] — 2026-07-02

### Added

- **Configurable `PUID`/`PGID` runtime user** — backend, worker, and frontend
  containers now run as the UID:GID set by `PUID`/`PGID` env vars (defaulting
  to `1000:1000`). This enables NFS-friendly file ownership so files written to
  library mounts and `/data` land with the correct host ownership. Set `PUID`
  and `PGID` in `.env` to match your NFS share owner. Operators upgrading should
  ensure their library mount(s) and `/data` volume are readable/writable by the
  configured `PUID:PGID`.

### Changed

- CI backend test suite now runs in parallel via `pytest-xdist -n auto` with
  per-worker Postgres databases; each xdist worker creates and migrates its own
  isolated DB at session start, eliminating shared-DB contention.
- CI now gates the `dev`→`main` PR on the `pull_request` event so the required
  status checks clear on their own (no more manual merge bypass); per-push `dev`
  feedback moved to a separate, non-required `Dev checks` workflow (fast jobs
  only, no heavy Test) so dev pushes stay cheap.

## [0.2.0] — 2026-07-01

### Added

- **Per-file 3MF thumbnails** — each `.3mf` file now carries its own thumbnail
  path in `File.object_analysis.thumbnail_path` (item-relative, written by the
  analysis worker). The 3MF collapsible panel displays the file's own embedded
  thumbnail instead of the first embedded image for the whole item, fixing the
  wrong-image bug when an item has two or more `.3mf` files. Existing cached
  analyses are backfilled on the next analysis run. The field is generic
  (`thumbnail_path`) so STL/OBJ server renders can populate it in the future.

### Fixed

- 3MF panels no longer share one thumbnail when an item has multiple `.3mf`
  files — each panel now shows the thumbnail extracted from its own file.

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
- **Render stack collapsed to a single headless VTK backend** — `pyrender`, `PyOpenGL`,
  and the EGL/OSMesa detection/code paths removed. The **`vtk-osmesa`** wheel (Kitware
  wheel index) is the sole render backend, doing true offscreen rendering with no X
  server. This **requires `libosmesa6`**; `libegl1`, `libgbm1`, `libxrender1`, and
  `libxi6` are removed from the Dockerfile. (The stock PyPI `vtk` wheel is X11-only and
  cannot render headless — see `docs/decisions.md` 2026-07-02.) **`networkx`** is now an
  explicit dependency (required by trimesh for scene-graph ops during analysis; it was
  previously pulled in transitively by `pyrender`).
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
