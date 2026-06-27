# Decisions

ADR-style log of non-obvious decisions, newest at top.

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
