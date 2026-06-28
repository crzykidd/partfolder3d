# Decisions

ADR-style log of non-obvious decisions, newest at top.

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
