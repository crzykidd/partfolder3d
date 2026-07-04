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

### Security

- **Data-safety hardening: ZIP runtime byte budget, 3MF XXE-hardened parser, and backup-at-rest
  permissions.** ZIP extraction (`storage/archive.py`) now enforces a *running* byte budget while
  decompressing — counting real bytes per entry and across the archive — so a crafted ZIP that
  under-declares its central-directory sizes to slip past the pre-scan caps is aborted mid-extraction
  (all in-flight files are written to a temp dir and only moved into place once every entry is within
  budget, so nothing partial is left behind). Untrusted `.3mf` XML (`worker/threemf.py`) is now parsed
  with an explicit hardened lxml parser (`resolve_entities=False`, `no_network=True`, `load_dtd=False`,
  `dtd_validation=False`, `huge_tree=False`) at every parse site, making XXE/entity-expansion
  mitigation explicit and fail-closed. Backup archives (`worker/backup.py`) — which bundle the Fernet
  key with all encrypted secrets — are now written `0600` in a `0700` `/data/backups` directory so
  other local host users can't read them; the sensitivity note in `docs/backup-restore.md` documents
  the enforced permissions.
- **Error responses no longer leak raw exception text; added a global exception handler.**
  A catch-all handler now turns any *unhandled* server error into a fixed generic
  `500 {"detail": "Internal server error"}` and logs the full traceback server-side, so
  internal detail can't leak into the HTTP body (as FastAPI's default handler can with debug
  on). ~12 endpoint sites that interpolated the raw exception into `detail=` (job
  retry/restart, scheduled-job + backup enqueue, import-session commit, item rename/delete +
  file rename, issue trash, remote share-link fetch) now log the real error and return a
  generic action message with the same status code. The **SSRF-block message** on
  import-session create and share-link import is scrubbed to a generic `"URL is not allowed."`
  (the resolved internal IP / block reason is logged, not returned), so importers can't probe
  internal network topology. A best-effort `updated_at` bump in the commit path now logs at
  debug instead of a silent `except: pass`.
- **SSRF hardening on the scrape/import fetch path** — every user-influenced outbound fetch
  (URL metadata scrape, `robots.txt`, and the commit-time download of scraped/AgentQL images)
  now goes through one guarded helper that rejects non-`http(s)` schemes, re-validates **every
  redirect hop** against the internal-IP block-list (no silent auto-follow into `169.254.169.254`
  or RFC1918), **streams with a size cap** instead of buffering unbounded response bodies,
  enforces `image/*` on scraped images, and sanitizes URLs before logging. New caps
  `SCRAPE_IMAGE_MAX_MB` (25) and `SCRAPE_HTML_MAX_MB` (5).
- **`javascript:`-scheme XSS blocked on `source_url` / creator `profile_url`** — these
  user-set/scraped fields are rendered into anchor `href`s (including the unauthenticated
  public share page), so a `javascript:`/`data:`/`vbscript:` value was a one-click
  authenticated request forgery (the CSRF cookie is JS-readable). Defense in depth: the
  backend now rejects non-`http(s)` URLs at the API schema boundary (item create/PATCH,
  import-session create/PATCH → **422**) and silently drops them on scraper/share-import
  ingestion; the frontend gained a `safeHref()` helper applied to every external link so a
  stored bad value still can't navigate.
- **Authorization hardening on print records, first-run setup, sessions, and login.**
  Print-record **edit / delete / gcode / photo** endpoints now require the record's owner or
  an admin — previously any authenticated user could modify another member's records
  (→ **403**); read access stays shared within the household. First-run **setup** serializes
  its check-then-insert with a Postgres advisory lock, closing a TOCTOU window in which two
  concurrent requests could each mint an admin. Consuming a **password-reset** token now
  deactivates all of that user's existing sessions. **Login** runs a dummy argon2 verify on
  unknown emails so a missing account no longer responds measurably faster (removes the
  user-enumeration timing oracle).
- **Redis now requires a password** — the broker runs with `--requirepass` and both the
  backend and worker authenticate via `REDIS_URL` (`redis://:<pw>@redis:6379/0`), injected by
  compose from the new `REDIS_PASSWORD` env var. arq deserializes job bodies, so queue write
  access is code execution in the worker; this is defense-in-depth even though Redis is not
  network-published. Set a strong `REDIS_PASSWORD` in `.env` for production.
- **arq jobs are JSON-serialized, not pickled** — the worker previously used arq's default
  `pickle` (de)serializer for job bodies, so any write to the Redis queue key was arbitrary
  code execution in the worker (which can write the whole library + `secret.key`). Both the
  enqueue side (the API's shared pool) and the dequeue side (`WorkerSettings`) now use a JSON
  (de)serializer; all job args are ints/strings. The worker's `REDIS_URL` fallback also now
  comes from the same password-bearing `settings.REDIS_URL` default as the API instead of a
  bare `redis://localhost:6379`, so a bare-metal worker run can't silently bypass Redis auth.
  **Upgrade note:** any pickled jobs still sitting in the Redis queue at upgrade time will
  fail to deserialize under JSON — **drain the worker queue across this upgrade** (jobs are
  short-lived and the queue is normally empty, so this is a non-event in practice).
- **nginx sends security headers** — the reverse proxy now emits `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and a conservative
  `Content-Security-Policy` (`default-src 'self'`; same-origin scripts, no `eval`; `data:`/
  `blob:` images; inline styles only) on the served SPA — mitigating clickjacking and
  MIME-sniffing. Don't assume the outer TLS proxy adds these.
- **Fail-fast on the default DB password** — the backend refuses to start if `DATABASE_URL`
  still uses the placeholder `changeme` password while `DEBUG` is not `true`, so a production
  deploy can't silently run with the weak default (dev keeps working with `DEBUG=true`).
- **CORS wildcard rejected with credentials** — `ALLOWED_ORIGINS` now raises a clear startup
  error if set to `*`, since the API sends credentials and browsers reject a wildcard CORS
  origin when credentials are enabled (previously it produced a silently broken config).
- **CI/CD supply-chain hardening** — all third-party GitHub Actions are pinned to a full
  commit SHA (checkout, setup-python/node, docker/*, codeql-action), and `ci.yml` /
  `dev-checks.yml` gained a top-level least-privilege `permissions: contents: read` block.

### Added

- **Auto-approve tags — skip the pending review queue (`tags.auto_approve` setting) + bulk
  "Approve all".** A new admin setting on the Tag Administration page lets new tags minted during an
  import commit land `active` immediately instead of queuing as `pending` for manual approval; when
  off (the default), the review workflow is unchanged. The setting only affects tags created *after*
  it is enabled — it does not retroactively approve the existing queue. For that backlog, a new
  `POST /api/admin/tags/approve-all` endpoint (and an "Approve all" button on the pending list)
  promotes every pending tag to active in one idempotent call. (closes #31)

- **Daily disk-reclamation sweep (`orphan_cleanup` cron, 05:00 UTC)** — a new scheduled job
  reclaims space that previously accumulated forever. It **purges soft-deleted items** under
  `/data/trash` older than `TRASH_RETENTION_DAYS` (default **30**; set `0` to disable), logging
  every deletion (path + age) and a summary (entries purged, bytes reclaimed). It also finds
  **orphaned print files** under items' `prints/` dirs — gcode/photos left behind because
  deleting a print record intentionally keeps its files — and, by default, **reports them only**
  (count + sample paths + bytes; nothing deleted) so you can review first. Set
  `ORPHAN_PRINTS_DELETE=true` to have it delete an orphan only when it is both unreferenced and
  older than `TRASH_RETENTION_DAYS`, with per-file logging. Both knobs are in `.env.example`
  with risk notes. (audit §E)

### Changed

- **Startup crash recovery now covers every job type, not just renders** — when the worker
  restarts, any job left `running` by the previous (crashed) worker is reaped instead of only
  `render` rows. Idempotent types (`render`, `analyze`, `extract_archives`) are marked failed and
  **re-enqueued** (deduped per item); non-idempotent/side-effecting types are marked failed **only**
  (with a clear error) so a half-finished job is surfaced rather than silently re-run. `queued`
  rows are intentionally left untouched. (audit §E)
- **One shared arq Redis pool instead of ~32 per-request pools** — routers and services that
  enqueue background jobs (render, analyze, extract-archives, ZIP bundle, import-session,
  review-apply, scheduled-job run, backup, job retry/cancel/restart) used to open a fresh
  `create_pool()` and `aclose()` it per request; if `enqueue_job()` raised, the `aclose()` was
  skipped and the connection leaked. The API now creates a single pool at app startup
  (`app.state.arq_pool`) and injects it via a `get_arq_pool` dependency, closing it once at
  shutdown; job names and args are unchanged. The two worker-internal enqueue sites still open
  a short-lived pool but now wrap it in `try/finally`. (audit §A / §E)

### Fixed

- **Import wizard: existing tags render immediately + zero-file commits are flagged**
  (partial #27). Existing catalog tags now render right away on the Tags step as a
  "Popular tags" quick-pick, independent of the AI suggest-tags call, so a slow or unconfigured
  AI provider no longer stalls the step. The Review & Commit step now shows a **Files** row that
  flags zero-file (metadata-only) commits with a warning note, so a URL import that attached no
  model file is no longer silent.
- **URL-import scraper: full-resolution images, cleaned title/description, and creator
  pre-fill** (closes #28; partial #27 — backend scraper parts). `_extract_images` now ranks
  candidates by likely resolution — largest-width `<img srcset>` / `<source srcset>` first,
  then lazy-loaded `data-src`/`data-original`/`data-full`, with the `og:image` social card
  demoted to a fallback and plain `<img src>` last — so the stored/default image is the
  full-res gallery photo instead of the ~1200x630 share card (still stored verbatim, no
  resize). `scrape_url` now strips SEO boilerplate that aggregator sites (Printables/MakerWorld/
  Thingiverse) bake into their OG tags: titles are cut at the first ` | ` (plus a trailing
  ` - <Site>.com` suffix) and descriptions at the first ` | `, so e.g. `NeilMed Sinus Rinse
  holder by Fuu | Download free STL model | Printables.com` becomes `NeilMed Sinus Rinse holder
  by Fuu`. Creator pre-fill is fixed too: `creator_name` now falls back to the `<name> by
  <Creator>` title pattern when no author meta exists (Printables exposes none), and the
  previously-dead `creator_profile_url` field is now populated from `rel="author"`
  links/anchors or a URL-valued `article:author`. All values flow through `process_session`
  into the wizard's Creator/Title steps.
- **Queued and analyze jobs are now visible in the Jobs monitor** (closes #20, closes #30).
  Background work was previously invisible until a worker *started* it: a `Job` row was only
  written when the task began, so a backlog of enqueued work (e.g. right after a bulk import)
  showed nothing, and mesh-analysis (`analyze_item`) created no `Job` row at all — invisible
  CPU/RAM even while running. A `Job` row is now written at **enqueue** time with status
  `queued`, and the worker **claims** that same row (→ `running`) instead of inserting a
  duplicate, keyed on the arq job id. `analyze_item` is wired into the same job-tracker
  lifecycle (claim-or-create at start, finished on success/failure). To avoid a race where the
  worker pops the job before the caller's transaction commits the queued row, background jobs
  are enqueued with a short defer and the claim is atomic (`queued → running` in one
  `UPDATE … RETURNING`), so at most one running row survives per job. The existing item-jobs
  and admin jobs endpoints already surface `queued` rows, so the backlog is now visible before
  any worker starts.
- **Catalog pagination bounced back to page 1.** Selecting page 2 (or any page) in the catalog
  briefly showed that page then reverted to page 1: the search-input debounce effect ran on
  mount and on every render and unconditionally cleared the `page` URL param. It now rewrites the
  URL only when the search text actually changed, so pagination sticks.
- **Scraped/uploaded images missing from an item's file list after import.** They appeared in
  the thumbnail gallery but not in the Files & Downloads list until a manual (or daily) rescan,
  because the commit inventoried the folder *before* downloading the images. The commit now
  re-inventories after writing images and adds the File rows immediately — matching what a rescan
  produces, so no rescan is needed.

## [0.3.0] — 2026-07-03

### Added

- **Worker resource limits (env-configurable, small defaults)** — the background worker no
  longer runs a fixed 10 jobs at once, so a bulk import (or a big startup backlog) can't
  overrun the host. New settings bound how hard it hits the machine: `WORKER_MAX_JOBS`
  (default **2**), `RENDER_CONCURRENCY` (default **1** — renders are the heaviest job, mesh +
  vtk-osmesa subprocess), `ANALYZE_CONCURRENCY` (default **2**), plus **hard docker-compose
  caps** `WORKER_CPUS` (default 2) and `WORKER_MEM_LIMIT` (default 3g) that confine the worker
  container so it gets OOM-/CPU-limited instead of taking down the whole box. All documented
  with per-setting risk notes in `.env.example`. (Closes #29)
- **Item page uses more of a wide screen** — the detail page cap widened from 900px to
  `min(1280px, 94vw)` so the image + metadata columns scale up on larger displays.
- **Long descriptions no longer dominate the item page** — a long description is shown in a
  capped, scrollable box with an **Expand** button that opens the full text in a modal.
- **Responsive catalog grid** — the grid column count now adapts to the window width
  (ResizeObserver): narrowing removes columns, widening adds them (min card width 220px
  compact / 340px full), instead of a hardcoded 3 columns.
- **Compact / Full catalog grid mode** — a toggle in the catalog toolbar (grid view). Compact
  is the dense cropped layout; Full shows uncropped images (~260px, contain fit). Persisted to
  localStorage (`pf3d-catalog-grid-mode`).
- **Configurable catalog page size** — a "Per page: 20 / 40 / 60 / 100" selector replaces the
  hardcoded 20; changing it resets to page 1. Persisted to localStorage (`pf3d-catalog-per-page`).
- **Image carousel "Renders" filter** — when an item has a mix of images, a **Renders**
  toggle next to the image counter filters the carousel to app-generated renders
  (`source === 'render'`) so you can quickly page through just the renders.
- **3D viewer "expand to full window"** — a maximize button (top-right, next to Close) grows
  the "View in 3D" viewer to fill the whole browser window; the same button restores it.
- **Files & Downloads is collapsible + scrollable** — the section header now toggles the
  panel open/closed, and the collapsed state is remembered in the browser (localStorage) so
  it stays that way across item pages until you change it. The file list also scrolls
  (capped height) so items with many files no longer run off the section. The header shows
  the **file count**, model files (**stl/obj/3mf/ply**) sort to the **top** of each folder,
  and the **`images` folder starts collapsed** (its contents already show in the carousel).
- **"Rescan disk" button on the item page** — the Files & Downloads panel now has a Rescan
  button (owner-only) that re-inventories the item's folder on disk and resyncs the sidecar
  via the reconcile engine, then refreshes the page. Per-item rescans always apply changes
  automatically (no review queue), so on-disk edits show up immediately without waiting for
  the daily scan.
- **App-wide error boundary** — a component crash now shows a readable "Something went wrong"
  screen (with Reload and "Reset app data & reload" actions) instead of blanking the entire
  app. Also fixed a crash where the release-notes popup shared a React Query cache key with the
  version page (object vs string), which blanked the app on load after an upgrade.
- **Hard-delete empty library + re-enable disabled library** (issue #11) — two new admin
  actions fill the soft-delete gap.  A disabled library row in the admin Libraries page now
  shows **Re-enable** (restores `enabled = true` instantly) and **Delete permanently**.
  Delete permanently is guarded: if the library still has assets the UI shows the count and
  a message directing the user to issue #25 (move-assets-between-libraries, coming later);
  if the library is empty a confirmation dialog is shown and the row is hard-deleted from
  the database.  The `GET /api/libraries` response now includes `item_count` per library
  so the frontend always knows the count without an extra fetch.
  New endpoints: `POST /api/libraries/{id}/enable` (re-enable) and
  `DELETE /api/libraries/{id}/purge` (hard-delete, guarded).

- **Release-notes popup** (issue #24) — after an upgrade, authenticated users
  see a dismissible "What's New" modal once on their first app load at the new
  version.  The modal is skipped on first-ever use (no prior seen-version) and
  does not reappear until the next upgrade.  The last-seen version is stored in
  browser localStorage (`partfolder3d-seen-version`).  Release blurbs live in
  `frontend/src/lib/releaseNotes.ts`; the release-prep process should add a
  new entry there when bumping the version.  The modal includes a "View full
  release notes" link to the GitHub release page.
- **3D viewer capture** — owners can now save a snapshot of the current 3D viewer
  viewpoint as an item image.  A camera-icon "Save view" button appears in the top-left
  of the viewer overlay (gated on ownership); each click captures the WebGL canvas frame
  and saves it as a new `Image` row with `source=captured` — multiple captures per item
  are supported, and any can be promoted to the default thumbnail via the existing
  set-default flow.  Especially useful for 3MF files, which have no server-side render and
  may lack an embedded thumbnail.  A new `ImageSource.captured` enum value and Alembic
  migration 0022 back the provenance.  (Closes #21)
- **Item file management** — owners can now upload, rename, and delete individual files
  from the "Files & Downloads" panel on any item page without a full re-scan.  Each file
  row gains a rename button (inline edit, Enter to confirm, Escape to cancel) and a
  two-step trash-can delete.  An "Upload file" control at the bottom of the panel accepts
  model files, archives, G-code, and documents; the backend sanitizes the filename,
  resolves collisions with a counter suffix, infers file role from the extension, and
  enqueues the standard analyze + render pipeline.  PATCH enforces path-traversal and
  collision guards; DELETE is best-effort on disk.  All three operations sync the item
  sidecar.  (Closes #19, part of #18)
- **Extraction progress reflected without a manual reload** — `extract_archives` now
  creates a Job row at the start of the task (type `"extract_archives"`, linked to the
  item) and marks it succeeded or failed when done.  The item page polls
  `GET /api/items/{key}/jobs` and auto-invalidates the item query when active jobs
  drop to zero, so the file list updates as soon as extraction finishes.  (Part of #18)
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

### Changed

- `GET /api/items/{key}/jobs` (new endpoint) returns active (queued/running) plus
  non-archived failed jobs for an item. `ItemJobOut` includes `progress` and `error`.
  `ItemPage` polls this endpoint every 3 s and threads the results into
  `ObjectBreakdownSection`.

### Fixed

- **3D viewer overlay, sizing, close, and zoom** — the "View in 3D" window now
  renders through a portal to `document.body`, so it's a true centered overlay
  instead of being trapped inline at the bottom of the page by an Aurora card's
  `backdrop-filter` (which also pushed its top controls under the nav bar). It's
  capped (`min(90vw,1100px)` × `min(82vh,760px)`) so it no longer dominates large
  displays, the close control is a clear **X** (top-right; Esc/backdrop also close),
  and OrbitControls now uses **zoom-to-cursor** + faster pan so you can zoom in on
  one side/object to frame a clean capture. Owner-only **Save view** is unchanged.
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
- **Object Breakdown reports real analysis status instead of a blanket "Analysis
  pending."** 3MF files are read, not mesh-analyzed, so they now say so plainly (slice
  details appear inline in Files & Downloads) rather than implying a job is coming. For
  mesh files (STL/OBJ/PLY) awaiting analysis the section shows the actual job state:
  *Running* ("Analyzing… N%" with a progress bar + "View in Jobs" link), *Queued*,
  *Failed* (with the error text + a hint to use Rescan disk), or *No job* ("hasn't run
  yet — use Rescan disk to queue it").

### Security

- Sanitize CR/LF before logging the user-provided session id in the bulk-commit handler
  (CodeQL `py/log-injection`), matching the escaping used elsewhere in the import-sessions
  package.

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
- **`docker-compose.yml` is now a production, image-based deploy** — `build:` blocks
  removed; `backend` and `worker` pull `ghcr.io/crzykidd/partfolder3d:latest`; `frontend`
  pulls `ghcr.io/crzykidd/partfolder3d-frontend:latest`. A version-pin comment (`:0.1.1`)
  is shown next to each image tag. Library mount placeholders are prominently commented
  for end-user editing; named volumes (`db_data`, `redis_data`, `frontend_dist`) are
  preserved for production durability. Header updated with a 5-step quick-start block.
- **`docker-compose.dev.yml` remains the build-from-source dev stack** — no changes;
  it continues to build all images locally with hot reload for contributors.

### Fixed

- 3MF panels no longer share one thumbnail when an item has multiple `.3mf`
  files — each panel now shows the thumbnail extracted from its own file.
- **README production-install guide** — `## Getting started` now documents the
  primary production path (pull published images, configure `.env` + library mounts,
  `docker compose up -d`) and prominently links the in-app **Quick Start** guide at
  `/quick-start` for guided first steps (add a library, load Starter Tags, enable AI,
  schedule backups). A "Build from source (dev)" subsection for contributors is kept as
  a collapsible secondary path.
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

> **Shipped untagged** — no `v0.1.0` git tag or GitHub release was ever cut; the first
> published tag is **v0.1.1**, which superseded it the same day. This entry is retained
> for the full feature record.
>
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

## Release history policy

This is a **single living changelog** — old release series are **not** archived or split
out into separate files. Every release, from the oldest to the newest, stays in full
detail in this one file. (An earlier plan to archive closed minor series into
`docs/CHANGELOG-<minor>.x.md` was dropped; there is no archive file to look for.)

<!-- Reference links: comparison ranges per release. v0.1.0 shipped untagged, so the
     earliest tag is v0.1.1 (no v0.2.1 was ever tagged). -->

[Unreleased]: https://github.com/crzykidd/partfolder3d/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/crzykidd/partfolder3d/compare/v0.2.5...v0.3.0
[0.2.5]: https://github.com/crzykidd/partfolder3d/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/crzykidd/partfolder3d/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/crzykidd/partfolder3d/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/crzykidd/partfolder3d/compare/v0.2.0...v0.2.2
[0.2.0]: https://github.com/crzykidd/partfolder3d/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/crzykidd/partfolder3d/releases/tag/v0.1.1
[0.1.0]: https://github.com/crzykidd/partfolder3d/releases/tag/v0.1.1
