# Decisions

ADR-style log of non-obvious decisions, newest at top.

## 2026-07-03 — Catalog grid: responsive cols, compact/full mode, page-size selector

- **Column count** = `floor((W + gap) / (minCard + gap))` (N cards + N−1 gaps in width W),
  extracted as `computeCols` in `catalog-utils.ts` + unit-tested. Min card widths 220px
  (compact) / 340px (full).
- **Virtual scroll container height** changed from a fixed 640px to `calc(100vh - 320px)`
  clamped 480–900px — fixed height under/over-shot on different screens; viewport-relative
  self-adjusts (320px accounts for the chrome above the grid).
- **`gridMode` + `perPage` stored in localStorage, not URL** — they're UI-density
  preferences, not navigation state; keeping them out of the URL avoids polluting
  shared/bookmarked links (URL still carries q/tags/sort/page/view).

## 2026-07-03 — Black-screen on load: React Query key collision (#24 popup)

The #24 release-notes hook used `useQuery({ queryKey: ['version'] })` returning a **bare
string**, but `VersionPage` and both nav shells already use `['version']` returning a
`{ version }` **object**. React Query shares one cache entry per key, so the hook's
`currentVersion` (and the value it wrote to `localStorage`) could be an object. On the next
load `compareSemver` did `v.split(...)` on that object → `TypeError` thrown inside
`AuroraShell` (a shell-level component) with **no error boundary** → the whole React tree
unmounted → blank/black page after ~1s (once `/api/version` resolved). **Fix:** gave the hook
a distinct key `['release-notes-version']`, and guarded both `currentVersion` and `lastSeen`
to strings (so an already-poisoned localStorage value self-heals instead of crashing), plus
made `compareSemver` never throw on a non-string. **Lessons:** (1) never reuse a React Query
key with a different result shape; (2) the app has NO top-level error boundary — a follow-up
should add one so a single component crash can't blank the entire app.

## 2026-07-03 — v0.3.0 full-suite gate: one real regression + a test-hermeticity fix

Running the full backend suite after the overnight batch surfaced two issues:

1. **Real regression (fixed):** the issue-#14 commit-side default-image fallback (honor
   `session.default_image_path` when no `ImportSessionImage.is_default` is set) was **dropped**
   when `commit_import_session` was refactored into `_commit_session_inner` (by the bulk-import
   work, then the render-param change). The agents that touched the commit path only ran
   `test_bulk_import`/`test_phase5_import`, not `test_import_management`, so the #14 test never
   re-ran — the full suite is what caught it. Restored the fallback just before the image loop in
   `_commit_session_inner`. **Lesson:** when refactoring a shared function, run the tests of ALL
   callers/features that depend on it, not just the new feature's tests.

2. **Test hermeticity (fixed):** `test_clear_jobs_by_status_{succeeded,failed,cancelled}` asserted
   an EXACT global archived count (`== 2`). Under xdist, other tests in the same worker DB leave
   committed `Job` rows (notably #18's `extract_archives`, which now commits a Job row via
   `job_tracker` outside the per-test rollback), so the global "clear all of status X" endpoint
   correctly archives more than 2. Relaxed to `>= 2`; the per-job assertions already prove only the
   right jobs are touched. The endpoint is correct — the test over-specified.

Also noted: the local serial `:5433` test DB is NOT reset by conftest between runs (only xdist
workers drop+create), so a long-lived container accumulates committed rows and produces spurious
count failures in serial runs. Validate with xdist (`-n N`, fresh per-worker DBs) — that's how CI runs.

## 2026-07-03 — #11 library purge: no on-disk directory removal

`DELETE /api/libraries/{id}/purge` hard-deletes the `libraries` row but does not remove
the on-disk directory.  The existing `disable_library` endpoint never touched the
filesystem either, so there is no existing directory-management pattern to follow.
The library directory is a host-mounted volume; deleting it from inside the container
would be destructive and surprising.  Operators who want to reclaim the disk space can
unmount and remove the volume on the host after deleting the library through the UI.

## 2026-07-03 — #11 library purge: item_count added to LibraryOut (not a separate endpoint)

The frontend needs the asset count before deciding whether to show the delete-blocked
message.  Two options: (a) a separate count endpoint called on demand, or (b) include
`item_count` in the `GET /api/libraries` list response.  Chose (b): the count is a
correlated subquery on an indexed FK column — cheap at small library counts — and it
eliminates a round-trip on every library page load.  The field defaults to `0` so
callers that don't use it are unaffected.

## 2026-07-03 — #11 purge endpoint: allow purge of enabled library

The purge endpoint (`DELETE /api/libraries/{id}/purge`) does not require the library to
be disabled first.  An operator might want to create-and-immediately-delete an empty
library without the extra disable step.  The only guard is the item count check.

## 2026-07-03 — #24 release-notes popup: localStorage over per-user DB column

The issue proposed two options for persisting last-seen version: a `last_seen_version`
DB column (syncs across devices) or the existing `useLocalStorage` hook (per-browser).

Chose **localStorage** for v1:
- Zero backend changes — no migration, no PATCH endpoint, no round-trip latency.
- The app is already using localStorage for theme and nav-layout preferences.
- The modal's "once per upgrade" goal is satisfied per browser; the per-device gap is
  an acceptable v1 trade-off (worst case: user sees the modal again on a second device,
  which is harmless).
- Promoted to DB storage if per-device annoyance proves significant in practice.

## 2026-07-03 — #24 release-notes popup: frontend blurb module over served CHANGELOG

The CHANGELOG.md is not bundled into the frontend build or served by the backend.
Parsing it would require either:
(a) a new backend endpoint that slices the file, or
(b) bundling a markdown renderer + the full changelog into the frontend.

Chose a **small frontend module** (`frontend/src/lib/releaseNotes.ts`) that maps
version strings to curated "What's New" bullet arrays.  This is:
- Dependency-free (no markdown renderer)
- Bundle-minimal (one TS module, a few hundred bytes)
- Author-friendly: the release-prep process already writes README "What's New" and
  CHANGELOG entries; adding a `releaseNotes.ts` entry is one more step of the same kind.

The release-prep skill/process should update `releaseNotes.ts` alongside the version
bump (noted in decisions.md as a reminder and in the CHANGELOG entry).

## 2026-07-03 — #21 viewer capture: ImageSource.captured as native PG enum value

`ImageSource` is a native PG enum (`Enum(ImageSource, name="imagesource")`). Added
`captured` via migration 0022 using `ALTER TYPE imagesource ADD VALUE IF NOT EXISTS 'captured'`
outside a transaction (`autocommit_block()`), matching the existing 0021 pattern for
`embedded`.

The `POST /api/items/{key}/images` endpoint gains a `?source=captured` query param
(default: `"uploaded"`). The frontend passes `source=captured` when uploading a canvas
screenshot so captured images carry distinct provenance in the DB and sidecar.

Filenames use a `capture_` prefix (vs. `upload_`) to make the origin visible on disk.

## 2026-07-03 — #21 viewer capture: wizard ImagesStep capture deferred

The issue owner requested a "Try to render file" action in the import wizard
(`ImagesStep.tsx`) that captures a browser render during import. During the wizard, items
don't exist yet — images are `ImportSessionImage` rows — so the upload path is different.
This is more involved and was deferred as a follow-up rather than risk rework of the
wizard flow. The item-page capture (the core request) ships in this commit.

## 2026-07-03 — #18/#19 file management: upload extension allowlist, rename-in-dir-only

`upload_file` (`POST /api/items/{key}/files`) rejects extensions not in
`_ALLOWED_FILE_EXTENSIONS`. The allowlist is explicit rather than a blocklist — unknown
extensions from future formats won't silently pass through. Extensions match those already
handled by `infer_role` / `inventory_item`.

`rename_file` (`PATCH /api/items/{key}/files/{file_id}`) accepts a `name` (basename only)
and keeps the file in its current directory. Cross-directory moves are not supported: the
rename target is always `parent(current_path) / new_name`. The path traversal guard
(`resolve().relative_to(item_dir.resolve())`) runs after deriving the target to catch any
edge cases the `/../` check misses.

Role is re-inferred on every rename via `infer_role(new_rel)` — if the extension changes
(e.g. `.stl` → `.gcode`) the role column is updated to match.

## 2026-07-03 — #18 extract_archives Job row: separate session, failure-safe

`extract_archives` now creates a Job row at task start using its own `async with
SessionLocal()` block (not the caller's) so that if the job creation itself fails the task
still proceeds — the log warns but extraction continues. The `_finish` helper follows the
same pattern: a fresh session that commits independently. This means Job lifecycle is
best-effort: if the DB is unavailable during a task, the task result (files extracted) is
still preserved.

`arq_job_id` is set from `ctx.get("job_id")` — present when arq calls the task but `None`
in tests / CLI invocations.

## 2026-07-03 — #15 render preference: caller-side gate vs. instance-side gate

The `render` parameter (`"auto"` | `"off"`) is a **caller-side gate**: when `"off"`,
`_enqueue_render` is never called at all. This is layered on top of the existing
**instance-side gate** inside `_enqueue_render` (`settings.RENDER_MODE == "off"`),
which already short-circuits when the operator has disabled rendering globally.

The two are intentionally independent:
- Instance `render.mode = "off"` means the server can't render at all (no worker, no GPU).
- Request `render = "off"` means the caller doesn't want a render now (e.g. bulk migration
  deferred to browser capture later), even if the server is capable.

Neither gate can be used to *force* rendering past the other: `render="auto"` still
goes through the instance check; `render.mode="off"` still blocks even if `render="auto"`.

`"auto"` was chosen as the default (not `"on"`) so the value is meaningful as "use the
instance default policy" rather than "always render", keeping the option additive.

## 2026-07-03 — #17 asyncio.to_thread placement and timeout strategy

**Why `asyncio.to_thread` at the router level, not inside client.py:** the public
functions `suggest_tags`, `cleanup_description`, `summarize_scrape` are designed to be
pure sync (they never raise). Making them async internally would couple client.py to the
event loop and complicate unit tests that call them directly. Wrapping at the call site
in routers keeps concerns separated — client.py stays sync and testable in isolation,
routers own the async offload.

**Injectable test callers do NOT receive the timeout argument** even though `_dispatch`
now accepts one. Existing test lambdas use `lambda *a: "text"` which absorbs extra args,
but the injectable caller is only for tests — it makes no real network call and needs no
timeout. Keeping the injectable signature stable meant zero test changes were required
for #17.

**Timeout values chosen:** 10 s for `test_ai_connection` (explicitly a connectivity
ping; a provider that can't respond in 10 s is broken), 60 s default for all inference
calls (generous for slow local Ollama models; still protects the event loop from a
permanently-hung provider).

## 2026-07-03 — #16 body-override approach (not auto-save on blur)

Issue #16 offered two fix options: (1) auto-save on blur before the AI button fires,
or (2) pass current values in the request body. Chose option 2 because it requires no
extra PATCH round-trip, works even for a brand-new session (session id just created,
no title/description ever saved), and keeps the "save only on Next" contract intact.
The body fields are all optional so existing call sites that send no body continue to
work (the backend falls back to session values).
## 2026-07-03 — Object Breakdown job-status fix (feat/object-breakdown-jobs)

**"Recent failed jobs" scope for `GET /api/items/{key}/jobs`:** The endpoint returns
non-archived failed jobs with no time cap (i.e., any non-archived failed row).
Alternatives considered: (a) last-24h cap — rejected because a job that failed yesterday
and hasn't been retried is still actionable; (b) all failed rows ever — same as chosen
since archiving is the explicit cleanup action. The safe minimal choice is: failed +
non-archived = still needs attention.

**3MF files are excluded from "pending mesh analysis":** A 3MF file with no
`object_analysis` is NOT pending mesh analysis — it may have embedded slice metadata
(shown in the ThreeMfPanel) or nothing at all. Saying "Analysis pending" implies a worker
will run and produce results, which is false for 3MF. The new message correctly states
"read, not mesh-analyzed."

**Job polling in ItemPage (3 s interval):** The `['item-jobs', key]` query polls every
3 s. This matches the DownloadsSection ZIP poll cadence and is short enough to feel
responsive while the analyze job runs. The endpoint is cheap (a single indexed SELECT on
`item_id` + `status` + `archived_at`). A future optimization could use server-sent events
or WebSockets, but polling is sufficient at this scale.

## 2026-07-02 — CodeQL log-injection fix in import-session PATCH (v0.2.5 PR)

CodeQL (`py/log-injection`, Medium) flagged the #14 code on the v0.2.5 release PR:
`patch_import_session` logged the user-provided `default_image_path` raw in the
"no matching image row" debug line. **Fixed (not dismissed)** — this is a real,
if low-severity, log-forging vector. Escaped CR/LF before logging
(`.replace("\r", "\\r").replace("\n", "\\n")`), matching the existing pattern in
`import_sessions/__init__.py:258` and `storage/ssrf_guard.py` (and consistent with the
earlier `fs_browse` CR/LF fix). Not the strip-style used in `fs_browse.py:161` — escaping
preserves the value for debugging while neutralizing newlines. CodeQL is not a required
check on `main`, but the finding was fixed pre-merge rather than carried into the release.

## 2026-07-02 — Bulk commit design (issue #15)

**Deferred**: CLI option (issue #15 option 3) was explicitly excluded from scope;
only the endpoint + UI button were shipped.

**Per-session isolated transactions**: `bulk_commit_import_sessions` creates a new
`SessionLocal()` per session so a failure in one session's commit does not roll back
others.  The request-scoped `db` is used only to enumerate target session IDs; all
actual commit work runs in isolated connections.

**Library resolution order** (decided with owner, baked into both bulk-commit and
inbox-scan): (a) request body `library_id` override, (b) session's own `library_id`,
(c) `import.default_library_id` instance setting, (d) sole enabled library, (e) skip
with `no_library` reason.  The same helper `_resolve_import_library` is used by all
code paths.

**`bool` rejected from `import.default_library_id`**: Python's `bool` is a subclass of
`int`, so `isinstance(True, int)` is `True`.  Added an explicit `isinstance(body.value,
bool)` guard to prevent `true`/`false` from being accepted as library IDs.

**No migration needed**: `import.default_library_id` is stored in the existing `Settings`
generic key-value table.  No schema change required.

**Monkeypatch approach for bulk-commit tests**: the bulk-commit endpoint creates
`SessionLocal()` per session (a new DB connection) which cannot see uncommitted test
transaction data.  Tests that exercise the commit path monkeypatch `app.db.SessionLocal`
to return a context manager yielding the test's `db_session` (backed by the outer
transaction).  Since `db_session` uses `bind=conn` with `expire_on_commit=False`, the
`session.commit()` call within the inner context manager uses savepoint semantics and
does not escape the test transaction.

## 2026-07-02 — Auto-login race fix and confirm-password field (issue #13)

**Root cause confirmed: Suspect B (frontend navigation race).**

Two suspects were analysed before fixing:

**Suspect A — backend commit ordering:** `run_setup` only called `db.flush()` before
returning; the real `COMMIT` happened in `get_db`'s post-yield cleanup. FastAPI
0.115.6 routing (see `fastapi/routing.py` line 290) exits the `AsyncExitStack` — and
thus runs all `yield`-dependency teardown including `await session.commit()` — **before**
the response object is returned to Starlette for byte transmission. So the commit lands
before the `Set-Cookie` response bytes reach the client. **Suspect A was ruled out as
the primary cause for FastAPI 0.115.6.** Belt-and-suspenders: an explicit
`await db.commit()` was added to `run_setup` after `create_session` so the behaviour
is robust across FastAPI version changes and the intent is self-documenting. A redundant
commit on an already-committed SQLAlchemy async session is a harmless no-op.

**Suspect B — frontend navigation race (confirmed primary cause):** `SetupPage.onSuccess`
called `queryClient.invalidateQueries({queryKey:['me']})` (fire-and-forget, not awaited)
then `navigate('/', {replace:true})` synchronously. When `AuthGuard` rendered at `/`:
- `user` was still `null` (stale cached value)
- `isLoading` was `false` (background refetch triggered by `invalidateQueries` does
  **not** set `isLoading=true` when the query already has data; only `isFetching`
  becomes true, which `AuthGuard` does not check)
- Result: `AuthGuard` immediately rendered `<Navigate to="/login" />` before the
  background refetch could update `user`.

**Fix:** `SetupPage.onSuccess` and `LoginPage.onSuccess` are now `async` and call
`await queryClient.refetchQueries({queryKey:['me']})` before `navigate`, guaranteeing
`AuthContext.user` is non-null before `AuthGuard` evaluates the route.
- `SetupPage`: falls back to `/login` on refetch error (session cookie is set; normal
  login flow can proceed).
- `LoginPage`: navigates to `from` regardless of refetch outcome (session is set; a
  re-fetch will happen on the next `AuthGuard` render).
- A local `isNavigating` state keeps the Finish Setup button disabled/loading during
  the async post-mutation refetch window.

**Confirm-password field** added to `SetupPage` step 1 as an owner request riding in
the same commit. The field is local UI state only; `admin_confirm_password` is never
sent to the API. Backend `SetupRequest` schema is unchanged.

## 2026-07-02 — Fix import-wizard default image not applied on commit (issue #14)

**Root cause:** `patch_import_session` stored `session.default_image_path` but did
not sync `ImportSessionImage.is_default` flags. `commit_import_session` builds final
`Image` rows solely from `si.is_default` (never reading `session.default_image_path`),
so the user's wizard selection was silently dropped.

**Fix (two parts):**

1. **Primary — sync `is_default` in the PATCH handler.** When
   `body.default_image_path` is set, query all `ImportSessionImage` rows for the
   session, clear `is_default` on all, then set `is_default = True` on the row whose
   `path` matches. Matches the clear-all-then-set-one pattern already used in
   `delete_import_session_image` and `items.py:set_default_image`. No match (path set
   before images materialised) → log debug and leave `default_image_path` stored;
   fallback below covers it.

2. **Defensive fallback — commit handler.** Before the image-building loop, if
   `session.default_image_path` is set but no `ImportSessionImage` has
   `is_default=True`, scan the list for the matching path and set it; if no path
   matches and images exist, fall back to the lowest-order image. This makes the
   outcome correct even if PATCH ordering ever races with image materialisation.

**Tests added** in `backend/tests/test_import_management.py`:
- `test_patch_default_image_path_syncs_is_default` — PATCH syncs DB flags
- `test_commit_honors_patched_default_image` — full commit flow regression guard
  (confirmed FAILs without the fix: first image is default instead of second)
- `test_commit_fallback_honors_default_image_path` — commit-side fallback

## 2026-07-02 — CodeQL triage for the FS browser endpoint (issue #8, PR #12)

CodeQL flagged 5 alerts on `backend/app/routers/fs_browse.py`:

- **`py/log-injection` (1)** — **fixed in code.** The `except OSError` handler logged the
  resolved (user-influenced) path via `%s`; a directory name can technically contain
  CR/LF. Now strips `\r`/`\n` before logging.
- **`py/path-injection` (4)** — **dismissed as false positives** (won't-fix). The endpoint
  is admin-only (`require_admin`) and every request path is `Path(path).resolve()`-d and
  then containment-checked against the `FS_BROWSE_ROOTS` allowlist via `is_relative_to`
  before any filesystem access; paths outside all roots are rejected with 400. CodeQL does
  not recognise the multi-root allowlist helper (`_inside_any_root`, an `any(...)` over
  `is_relative_to`) as a taint barrier, so it reports the constrained `resolve()`/`scandir`
  calls. Traversal to `/`, `/etc`, `/proc`, `..`, and symlink escapes is prevented and
  covered by 14 tests in `tests/test_fs_browse.py`. Dismissed via the code-scanning API
  with this justification. (Same precedent as the earlier `downloads.py` path triage.)

## 2026-07-02 — FS browser allowlist-root design (issue #8)

**Problem:** The library mount-path field is free text, forcing operators to guess
the absolute container path. Adding a filesystem browser requires tight security because
the API is running inside the container and must not expose arbitrary paths like `/`,
`/etc`, or `/proc` to any caller — even admins.

**Design: operator-configured allowlist (`FS_BROWSE_ROOTS`)**

A new config setting `FS_BROWSE_ROOTS` (env var; comma-separated or JSON array; default
`["/library"]`) defines the only roots the browser may expose. Every request path is:

1. Checked to be absolute (reject relative paths immediately).
2. Resolved via `Path(path).resolve()` — this normalises `..` components and follows
   symlinks, so `/library/../etc` resolves to `/etc` before the check runs.
3. Checked with `is_relative_to()` against every configured root. If the resolved path
   is not inside *any* root, the request is rejected with HTTP 400.

**Why resolved path + is_relative_to, not a string prefix check:** `Path.is_relative_to`
works on normalised Path objects, so it is immune to tricks like extra slashes, `.`, or
`..` that fool naive string prefix matching (e.g. `/libraryfoo` would falsely pass a
`str.startswith("/library")` check but correctly fails `is_relative_to(Path("/library"))`).

**Why allowlist instead of a read-only flag:** A simple "read-only browse" flag would
still allow admins to enumerate `/etc/passwd`, `/proc/*/environ`, etc. — information that
should not leak even to admins in a shared-hosting context. The allowlist gates what paths
the container exposes via the HTTP API entirely independently of filesystem permissions.

**Parent navigation stops at the root boundary:** The `parent` field in the response is
set to `None` when the parent directory is outside all configured roots, preventing
up-navigation above the allowlist boundary.

**Symlinks in directory entries are excluded:** `os.scandir` entries are filtered with
`is_dir(follow_symlinks=False)` so symlinked directories are not shown to the user.
(The *roots themselves* may be symlinks; whether to resolve them is the operator's
responsibility when configuring `FS_BROWSE_ROOTS`.)

## 2026-07-02 — Frontend typecheck gate is `npm run build`, not `npx tsc --noEmit`

**Problem:** The frontend production image (`frontend/Dockerfile --target prod`) runs
`npm run build` (`tsc -b && vite build`). The `tsc -b` mode compiles project references
(`tsconfig.app.json` / `tsconfig.node.json`), which set `noUnusedLocals: true` and
`noUnusedParameters: true`. The root `tsconfig.json` is a references-only file with none
of those strict settings. `npx tsc --noEmit` always reads the root tsconfig, so it
silently passes with zero errors even when the real prod build has ~24 errors. CI and
`/release-prep` were both using `npx tsc --noEmit`, meaning the frontend prod image had
never successfully built.

**Fix:** Changed the `frontend` job step in `ci.yml` and `dev-checks.yml` from
`npx tsc --noEmit` to `npm run build`. Updated `/release-prep` to use `npm run build`
as the frontend validation gate. The correct rule: **always use `npm run build` to
validate the frontend; never `npx tsc --noEmit`**.

**Type fixes required:** 24 errors were present — ~20 TS6133 unused-import/variable
removals (automatic JSX runtime makes bare `import React` unnecessary in all non-class
files that don't reference `React.*`), plus 4 real type errors:
- `SideNavShell.tsx`: `useLocalStorage` setter only accepts `T`, not a functional
  updater — fixed by using the already-captured `collapsedGroups` state directly.
- `CatalogPage.tsx`: `favMutation` needed explicit generics
  `useMutation<FavoriteOut | void, Error, ...>` because `favoriteItem` returns
  `Promise<FavoriteOut>` and `unfavoriteItem` returns `Promise<void>`.
- `AiUsagePage.tsx`: `icon={Activity}` passed a Lucide component constructor where
  `ReactNode` was expected — fixed to `icon={<Activity size={32} />}`.

## 2026-07-02 — Baked nginx image: dedicated Dockerfile, `/img/` alias, release-note callout rule

**Problem (why a dedicated nginx image):** `publish.yml` originally built only the backend
image. The `nginx` compose service used the stock `nginx:1.27-alpine` image with two
required bind-mounts: `./nginx/nginx.conf` (the proxy config) and `./docs/images` (logo
assets). A pull-images-only production host without the repo clone would get nginx falling
back to its built-in empty config: no `/api/` proxy (API 404s), no SPA fallback (deep
links broken on refresh), and the stock 1 MB upload cap (model uploads rejected with 413).
This silently defeats the "zero repo files needed" promise of the production compose.

**Decision: bake config + logos into `nginx/Dockerfile`:**
- `FROM nginx:1.27-alpine`; `COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf` bakes
  the proxy config (1024m upload cap, `/api/` proxy, `/health` proxy, SPA fallback).
- `COPY docs/images/ /usr/share/nginx/img/` bakes the brand assets at a path *outside*
  the `frontend_dist` volume mount (`/usr/share/nginx/html`), so logos are always present
  regardless of whether the volume has been populated.
- `RUN nginx -t` in the build validates the baked config at build time — a bad conf fails
  the Docker build immediately rather than silently at runtime.

**`/img/` alias (not `/img/` under html root):** mounting `frontend_dist` at
`/usr/share/nginx/html` at runtime would shadow anything baked at `.../html/img/`.
Instead the logos live at `/usr/share/nginx/img/` and a dedicated `location /img/ { alias
/usr/share/nginx/img/; }` block serves them. The `frontend_dist` volume only covers
`/usr/share/nginx/html` so there is no mount-shadow conflict.

**Optional operator override:** operators running a custom nginx config (e.g. with TLS
termination) can uncomment the single bind-mount line in `docker-compose.yml`. The
bind-mount takes precedence over the baked config at runtime, preserving the full
override path without requiring a custom image build.

**Release-note callout rule:** because operators may run a custom config, `release-prep.md`
now includes a Step 6b that diffs `nginx/nginx.conf` against the previous release tag. If
the config changed, it prepends a `⚠️ nginx config changed` callout to the release notes
so operators know to reconcile their copy. This is the least-surprise upgrade path for
overriding operators while keeping the baked default zero-friction for everyone else.

**publish.yml matrix:** expanded from a single `build-push` job to a 3-entry matrix
(backend / frontend / nginx), each with its own `docker/metadata-action` `images:` and
`build-push-action` params. GHA cache scopes are keyed by `matrix.name` to prevent
cross-image cache pollution. The same tag scheme (`dev` / `sha-<short>` / `latest` /
semver) applies to all three.

## 2026-07-02 — Fixed the perpetual release-PR bypass: required checks bind by BARE job name

Every `dev`→`main` release PR (v0.1.0 through v0.2.1) had to be merged with "bypass rules"
because the required CI checks sat forever at **"Expected — Waiting for status to be reported,"**
even though the checks ran and passed. Long misdiagnosed as CodeQL, push-vs-pull_request, or the
review rule. **Actual root cause:** `main` branch protection listed the required contexts as
**`CI / Lint`, `CI / Test`, …** (workflow-prefixed), but **GitHub Actions binds required status
checks by the bare check-run/job name** (`Lint`, `Test`, …), not `workflow / job`. The prefixed
contexts matched no check → the required slots never bound → permanent block → bypass.

**Fix (instant, verified — PR #4 went `mergeStateStatus: CLEAN` and merged with a normal button):**
set `main`'s `required_status_checks.contexts` to the **bare job names**:
`["Lint","Config validation","Migration check","Compose validation","Image build","Test"]`
(via `gh api -X PATCH …/branches/main/protection/required_status_checks`). No workflow change was
actually required for this — the earlier `ci.yml` edits (push→pull_request, then single-trigger)
were red herrings for the binding, though pull_request-only is kept because it's the correct PR-gate
shape (post-merge `main` builds are handled by `publish.yml`; `ci.yml` no longer runs on `main`).

**Consequences / guardrails:**
- **Job names are now load-bearing.** The six `ci.yml` job names ARE the required-check contexts —
  renaming a job silently breaks the gate (back to "Expected — Waiting"). Keep them stable/unique.
- `dev-checks.yml` (non-required per-push dev feedback) shares four job names with `ci.yml`
  (`Lint`, `Config validation`, …). With bare-name matching that risked a required slot binding to
  the dev-feedback run, so every `dev-checks.yml` job was **suffixed "(dev)"** to keep its check-run
  name distinct.
- Lesson: when a required check is stuck "Expected — Waiting" while the same-named check passes, the
  contexts are mis-registered — set them to the exact bare check-run names, not `workflow / job`.

## 2026-07-02 — PUID/PGID runtime user: /data chmod 0777, dev-compose left commented

**Problem:** The backend/worker write to `/data` (named volume in prod) and to library
NFS mounts. Running as root works locally but causes ownership mismatches on NFS shares
where files must be owned by the host's service UID.

**Decision:** Use compose `user: "${PUID:-1000}:${PGID:-1000}"` on backend, worker, and
frontend (prod only). No hardcoded `USER` in the Dockerfile — the UID is chosen at
runtime by the operator.

**`/data` chmod 0777 rationale:** Docker initialises a new named volume by copying the
image directory's contents and *permissions* to the host-side mount point. Without 0777,
the directory is created as `root:root 0755`; the first container to start as a non-root
UID then cannot write it. Setting `chmod 0777` in the Dockerfile ensures any UID can
write `/data` on first mount. The same logic applies to `/dist` in the frontend image.

**`HOME=/tmp` + `XDG_CACHE_HOME=/tmp`:** Arbitrary UIDs have no passwd entry, so
`$HOME` would expand to `/` or remain as the build-time root home. Libraries like
fontconfig and matplotlib try to create cache dirs under `$HOME`; forcing it to `/tmp`
(world-writable) prevents start-up errors for non-root UIDs.

**dev-compose choice:** `user:` is added as a comment (disabled) in
`docker-compose.dev.yml` for all three services:
- *backend/worker*: dev bind-mounts `./private_data/data/app` (host-owned). Setting
  `user:` would only be safe if `PUID` exactly matches the host developer's UID. Forcing
  it on by default would break dev setups where the host UID differs from 1000. The
  operator can uncomment if their UID matches.
- *frontend*: the dev target uses an anonymous `/app/node_modules` volume installed
  during build as root. A non-root UID cannot read it, so `npm run dev` would fail
  immediately with permission errors.

## 2026-07-02 — pytest-xdist: per-worker databases, DATABASE_URL set before app imports

**Problem:** Enabling `pytest-xdist -n auto` on a single shared Postgres DB causes
transaction-rollback isolation to break — workers contend on the same DB and
transactions from different tests interleave or block each other.

**Decision:** At the top of `conftest.py` (before any `from app import ...`), detect
`PYTEST_XDIST_WORKER` and rewrite `os.environ["DATABASE_URL"]` to a per-worker DB name
(e.g. `partfolder3d_gw0`).  A session-scoped `autouse` fixture then drops and recreates
that DB and runs `alembic upgrade head` against it.  Serial runs (`PYTEST_XDIST_WORKER`
unset) are left entirely unaffected.

**Why top-of-file env override matters:** `app.config.Settings()` is instantiated at
module load time; `app.db` creates its engine at import time from `settings.DATABASE_URL`.
If the env var is set after those modules are imported, the engine silently points at the
wrong DB.  Setting it at the top of conftest — before any test file imports `app.*` — is
the only reliable way to ensure both the fixture engine *and* the app's `SessionLocal` use
the same per-worker URL.

**Alembic invocation:** Uses `subprocess.run([venv/bin/alembic, "upgrade", "head"])` from a
synchronous session fixture.  The programmatic API (`alembic.command.upgrade`) was attempted
first but fails because `backend/alembic/__init__.py` exists (alembic stores its migration
scripts as a package), which shadows the installed `alembic` distribution on `sys.path` when
`backend/` is on the path.  The subprocess call uses the venv's alembic binary directly,
bypassing the naming conflict entirely.  DB creation still uses `asyncio.run()` + SQLAlchemy
async engine (fine since no event loop is active at session fixture setup time).

**CI postgres superuser:** `POSTGRES_USER: partfolder3d` in the GitHub Actions service
container creates a superuser by the postgres image convention, so workers can `CREATE DATABASE`.

## 2026-07-02 — Per-file 3MF thumbnail path stored in `object_analysis`

**Problem:** `_reconcile_embedded_thumbnail` wrote the thumbnail to disk and
created an item-level `Image` row but returned nothing. `analyze_item` had no
per-file record of which thumbnail came from which `.3mf`, so the UI had to
fall back to "first embedded image for the item" — wrong when there are two or
more `.3mf` files.

**Decision:** Have `_reconcile_embedded_thumbnail` return the item-relative path
(`thumbs/embedded/<sha256>.png`) on success, `None` on disk write failure.
`analyze_item` injects that path as `thumbnail_path` into the `object_analysis`
dict before writing it to `File.object_analysis` (JSONB). No migration needed.

**Alternatives rejected:**
- Adding a `thumbnail_image_id` FK on `File` — requires a migration and adds
  coupling between File and Image models; JSONB field is simpler and consistent
  with the existing analysis result schema.
- Storing the path as a separate `File` column — same migration cost, no gain.

**Backfill:** Cached analyses missing `thumbnail_path` are updated in-place on
the next `analyze_item` run (sha still matches → skip full analysis, but
reconcile thumbnail and write `thumbnail_path` into the cached dict).

**Frontend:** `ThreeMfPanel` reads `analysis.thumbnail_path` directly (via
`fileDownloadUrl`) rather than receiving an `embeddedThumbnail: ImageOut` prop
threaded from the parent. Removed the Phase-C "first embedded image" fallback
(`firstEmbeddedImage`) from `DownloadsPanel` entirely.

## 2026-07-02 — Render backend fix: `vtk-osmesa` wheel (the "VTK bundles Mesa" assumption was wrong)

Testing render-rework-A against a freshly built `:dev` image exposed a shipping-blocker: **no
render backend worked**. `get_backend()` returned `none`, so STL/OBJ thumbnails silently didn't
generate. Two compounding mistakes in Phase A's stack-slim:

1. The Dockerfile dropped `libxrender1`, but the **stock PyPI `vtk` wheel links libXrender** — so
   `import vtk` failed with `libXrender.so.1: cannot open shared object file` (ironically, Phase A's
   own *deleted* comment warned of exactly this).
2. Even with libXrender restored, the stock `vtk` wheel ships **only `vtkXOpenGLRenderWindow`** (no
   `vtkOSOpenGLRenderWindow`/`vtkEGLRenderWindow`) — it renders through X11/GLX and **cannot render
   headless**. Offscreen render aborted with `bad X server connection. DISPLAY=` (the SIGABRT the
   old Phase-4 note predicted). "VTK bundles its own Mesa software rasterizer, no libs needed" was
   simply false for the PyPI wheel.

Verified two working fixes empirically in containers built from the same image:
- **Xvfb + stock `vtk`** — works, but needs a virtual X server (xvfb + xauth + libgl1 + libxrender1)
  running alongside the worker.
- **`vtk-osmesa` wheel + `libosmesa6`** — true offscreen (default window becomes
  `vtkOSOpenGLRenderWindow`), **no X server**, identical PNG output. Chosen: it keeps the VTK-only
  single-backend architecture, needs no runtime X server, and is a two-file change.

**Fix:** `backend/requirements.txt` → `vtk-osmesa==9.3.1` (+ `--extra-index-url
https://wheels.vtk.org`, Kitware's wheel index); `Dockerfile` → add `libosmesa6`. No code change —
`render_mesh._try_vtk()` now passes because offscreen works. Lesson: render-backend viability is
**not** locally verifiable without a built image + headless probe; always run `get_backend()` + a
real render inside the actual image before trusting a stack change.

## 2026-07-01 — Asset-detail / 3D-preview rework: read-don't-render, browser viewer, ZIP extraction

The server-side mesh renderer (pyrender EGL→OSMesa→VTK fallback chain) was overloading the
worker — sliced 3MF files are huge (multi-plate, multi-object, often 2–3 per item) and CPU
software-rasterizing them per item was the main cost. Reworking the whole asset-detail /
file-preview experience around a **"read, don't render whenever the file already carries the
answer"** principle. Locked decisions:

- **Never server-render 3MF.** Sliced 3MF already embeds a slicer thumbnail
  (`Metadata/plate_1.png` / `thumbnail.png`) and real metadata (`slice_info.config` →
  grams/meters/print-time per filament; `project_settings.config` → filament hex colors, types,
  printer/slicer). We extract that (`zipfile` + lxml/JSON, no GL) instead of rendering. Real slice
  numbers flip `est_method` `"volume"`→`"sliced"`; unsliced 3MF falls back to today's volume
  estimate.
- **Server render becomes a bounded fallback for raw STL/OBJ only** — used only when the item has
  no higher-priority image and the mesh is under a size/triangle cap (over cap → skip, not an
  error). **Thumbnail priority chain:** user-default > curated (scraped/uploaded) > embedded 3MF
  thumbnail > STL/OBJ render > placeholder icon.
- **Render stack collapsed to VTK-only.** VTK bundles Mesa and runs headless with no GL system
  libs; drops `pyrender`, `PyOpenGL`, OSMesa/EGL code paths and the `libegl1`/`libgbm1`/`libosmesa6`
  apt packages. Kept: `trimesh` (STL/OBJ metadata + mesh load), subprocess isolation, timeout,
  SHA-cache, crash recovery. (Image-build + render smoke test is a CI/Docker follow-up — not
  locally verifiable, consistent with prior render work.)
- **In-browser viewer** via `@react-three/fiber` + `drei` (three.js STL/OBJ/3MF loaders), **lazy
  loaded / code-split** so it stays out of the catalog bundle. Loads the raw file from the existing
  `/api/items/{key}/files/{path}` endpoint — no server conversion. Gated by a configurable
  ~50 MB cap (`preview_3d` flag on `FileOut`); over cap → static thumbnail only.
- **ZIP uploads are auto-extracted** into the item dir preserving internal folders — **strip a lone
  top-level wrapper folder**, **rename on collision** (`cover (1).png`), reject zip-slip, skip
  `__MACOSX`/`.DS_Store`/`Thumbs.db`, enforce uncompressed-size/file-count caps, don't recurse into
  nested archives. Original `.zip` **discarded** after success (whole-item ZIP is reconstructable
  via `build_zip_bundle`). Extracted files flow through the normal inventory→analyze→render path.
- **UI:** flat `DownloadsPanel` becomes a **folder tree** (built client-side from the `path` field,
  no API change). 3MF detail is a **collapsible per-file element** — collapsed summary shows totals
  (sliced badge · print time · filament g · objects · plates · thumb); expanded shows filament rows
  (color swatch · type · g · m), per-plate breakdown, per-object list.
- **New `ImageSource.embedded`** for extracted 3MF thumbnails (migration 0021, PG `ALTER TYPE ADD
  VALUE` — must run outside the alembic transaction). Embedded thumbnails are **excluded from the
  sidecar** (like renders) — regenerated deterministically from the portable 3MF on scan.

Sequenced as four handoff prompts: **A** backend (read-don't-render foundation + 3MF read + stack
slim + migration), **B** backend (ZIP extraction), **C** frontend (file tree + 3MF collapsible),
**D** frontend (browser viewer). Dispatched sequentially — B/C/D branch off A's committed state to
avoid migration/config/worker-registry conflicts.

### Phase D implementation details (2026-07-01)

- **`@react-three/fiber@8.18.0` (not 9.x) — React 18 constraint.** fiber 9.x
  requires React `>=19 <19.3`. This project uses React `^18.3.1`. Pinned to fiber
  8.18.0 (latest 8.x, peer requires `>=18 <19`) + drei 9.121.5 (peer `^18` +
  `@react-three/fiber ^8`) + three 0.177.0 + @types/three 0.177.0 (three 0.177.x
  ships no bundled `.d.ts` files; @types/three provides the declarations including
  `examples/jsm/loaders`).
- **Code-split via `React.lazy` at module scope in `DownloadsPanel.tsx`.**
  `const LazyModelViewer = React.lazy(() => import('@/components/viewer/ModelViewer'))`
  placed at module scope (not inside a component) so Vite sees the dynamic import
  at build time and splits `ModelViewer.tsx` and all its transitive deps (three,
  fiber, drei) into `ModelViewer-*.js`. Confirmed: entry chunk `index-*.js`
  (≈800 kB) does not include three.js; lazy chunk `ModelViewer-*.js` (≈902 kB)
  contains three.js + fiber + drei.
- **Viewer state lives in `DownloadsSection`, not in `FileRow`.** Holding
  `viewerFile` at the panel level means only one viewer modal is ever open;
  passing `onOpenViewer` down through `TreeNodes` → `FolderNode` → `FileRow` is
  shallow (2 levels) and avoids the complexity of a global modal registry.
- **No per-geometry `dispose()` on the lazy-cached STL/OBJ/3MF resources.**
  `useLoader` in r3f caches loaded resources by URL. Calling `geometry.dispose()`
  in a cleanup effect would corrupt the cache for subsequent opens. The material
  (created via `useMemo` and not cached by r3f) IS explicitly disposed on unmount.
  WebGL GPU memory is freed by the `Canvas` renderer's `gl.dispose()` call (r3f
  triggers this when the Canvas unmounts). JS heap is GC'd. For this modal-based
  viewer this is acceptable.
- **`ThreeMFLoader` cast via `unknown`.** The `ThreeMFLoader` from
  `three/examples/jsm/loaders/3MFLoader.js` returns `THREE.Group` but r3f's
  `useLoader` generic uses `new () => THREE.Loader<T>` which ThreeMFLoader's
  declared type doesn't exactly satisfy. Cast `ThreeMFLoader as unknown as
  new () => THREE.Loader<THREE.Group>` to satisfy TypeScript without a `@ts-ignore`.
- **Background via `SceneBackground` component (not Canvas `style`).** Setting
  `style.background` on the `<Canvas>` div has no effect on the WebGL clear colour.
  Instead, a `SceneBackground` component uses `useThree()` to access `scene` and
  sets `scene.background = new THREE.Color(...)`, restoring the prior value on
  unmount. Theme detection uses `window.matchMedia('(prefers-color-scheme: dark)')`.
- **`ViewIn3DButton.onView` simplified to `() => void`.** Phase C declared
  `onView?: (filePath: string, fileId: number) => void`. Phase D simplifies to
  `onView?: () => void` since the button no longer needs to know its own path —
  `FileRow` closes over `file.path` and passes a bound handler. The `filePath` and
  `fileId` props (unused in Phase C's onclick) are removed from the interface.

### Phase C implementation details (2026-07-01)

- **Embedded thumbnail matching is best-effort in Phase C** — the backend stores
  embedded 3MF thumbnails as `Image` rows with `source=embedded`, but there is no
  `file_id` FK linking an image to its source 3MF file. Phase C shows the first
  `source=embedded` image from `item.images` as the thumbnail in all 3MF collapsed
  panels. When an item has multiple 3MF files with distinct thumbnails this will show
  the wrong thumbnail for all but the first. Deferred to Phase D (or a future schema
  addition of `file_id` on `Image`) to do per-file correlation.
- **3MF Detail toggle is a separate button, not integrated into the folder expand.**
  The file row has a "Details" button that independently opens the inline ThreeMfPanel.
  Opening Details auto-passes `defaultExpanded=true` to the panel so no second click
  is needed. This keeps the Download and View-in-3D affordances always visible without
  requiring the user to expand the 3MF analysis first.
- **STL/OBJ ObjectBreakdown section now filters out sliced 3MF files** — it only
  shows files with `est_method !== 'sliced'`. When every model file is a sliced 3MF
  the section renders an explanatory redirect note. This avoids duplicating data between
  the inline 3MF panels (in the file tree) and the Object Breakdown section.
- **"View in 3D" button is a disabled stub** — Phase C renders the button for every
  file with `preview_3d=true`, but it is always disabled (opacity 0.45, cursor
  not-allowed, tooltip "coming in the next update"). The `ViewIn3DButton` component
  accepts an optional `onView` prop; Phase D passes the real viewer handler there
  without restructuring the file row.
- **Top-level folder nodes default to expanded; deeper nodes default collapsed** —
  `FolderNode` receives `defaultExpanded` from its parent. `TreeNodes` at `depth=0`
  passes `defaultExpanded={true}`; at `depth>0` it passes nothing (defaults false).
  This heuristic keeps short item directories fully visible while preventing deep
  hierarchies from overwhelming the panel.

### Phase B implementation details (2026-07-01)

- **Cap failures are pre-scan only** — file-count, total-uncompressed-size, and zip-bomb ratio
  caps are all computable from the ZIP central directory (no decompression needed). All cap checks
  happen before any bytes are written to the item directory, so `ArchiveError` from a cap failure
  leaves `dest_dir` completely untouched.
- **Temp dir for in-flight safety** — extraction writes to a sibling temp dir then moves files
  to `dest_dir` one-by-one. The `finally` block rmtrees the temp dir so a mid-extraction crash
  or per-file I/O error can never leave half-written files in the item directory. Per-entry
  errors are recorded in `ExtractResult.errors` (non-fatal) — extraction of other entries
  continues.
- **Inventory resync via focused diff** — after extraction the task calls `inventory_item()`
  then diffs against current File rows (delete rows whose path is gone from disk, add rows for
  newly found paths). The full `reconcile_one_item()` engine is intentionally not used here:
  it generates Issues/ChangeLogs which are inappropriate for an automated extraction event.
- **`_FileRole` import is inline in sessions.py** — `FileRole` was already imported inline in
  section 6b of `commit_import_session`. Section 14 (the new enqueue step) follows the same
  inline-import pattern (`# noqa: PLC0415`) to keep the outer function dependency surface narrow.
- **No new DB migration** — Phase B is purely logic (new task, new helper, new config keys).
  No schema changes needed.

### Phase A implementation details (2026-07-01)

- **`threemf.py` is GL-free and trimesh-free** — uses only `zipfile` + `lxml` + `json`. No
  geometry loading: thumbnails are raw PNG/JPG bytes, slice metadata comes from Bambu/Orca XML/JSON
  config files. Unsliced 3MF still falls through to the existing trimesh `_analyze_3mf()` for
  the volume estimate.
- **`RenderCapSkip` is not an error** — a new exception class signals "file is over cap, skip
  silently" vs `RenderError` which marks the Job failed. Propagated through the subprocess
  boundary via a `__CAP_SKIP__:` prefix in the err-file, checked before `RenderError` in
  `run_render_subprocess`. Callers add to `skipped[]` not `errors[]`.
- **Size cap checked in parent, triangle cap in subprocess** — file size is a single `stat()` call
  in `render_item` (no trimesh load); triangle count requires loading the mesh, so it's checked
  inside `render_mesh_file()` after `_load_as_trimesh()` returns. This avoids a double-load in
  the parent while still giving a clean skip signal.
- **Thumbnail SHA is of the raw PNG bytes, not the 3MF file** — so the same slicer thumbnail
  re-used across 3MF revisions stays a cache-hit even when the geometry changes. Stored in
  `thumbs/embedded/<thumb_sha>.png` inside the item dir.
- **`model_validator(mode='after')` computes `preview_3d`** in `FileOut` from `path` and `size`
  fields already populated from the ORM. Avoids building `FileOut` objects manually and
  keeps the schema self-contained. Settings read lazily inside the validator.
- **Embedded images excluded from sidecar alongside renders** — `_build_sidecar_data` now
  excludes both `ImageSource.render` and `ImageSource.embedded` via a `_SIDECAR_EXCLUDED` set.
- **`_enqueue_render` accepts optional `model_extensions`** — callers who know the file types
  (post-inventory) can pass `model_extensions=['.3mf']` to skip the Redis enqueue entirely for
  3MF-only items. Callers that don't know pass `None` and `render_item` handles the per-file skip.

## 2026-07-01 — CodeQL triage on the first release PR (v0.1.1): 12 fixed, 24 dismissed

The first-ever CodeQL run (release PR #1) raised 36 alerts (1 critical, 20 high, 15 medium) —
because `main` was empty, it scanned the whole codebase at once. Disposition: **12 fixed in
code**, **24 dismissed as verified false positives** (via the code-scanning API, with per-alert
justifications).

- **Path-injection (downloads.py, shares.py):** switched the containment check from a
  `try: relative_to()` to an explicit `Path.is_relative_to()` boolean guard — functionally
  equivalent but **CodeQL's taint analysis recognizes it as a barrier**, so the alerts clear on
  re-scan rather than needing a dismissal. journal.py / sidecar.py path alerts were **dismissed**:
  those paths are built from `item.dir_path` (DB) + sanitized slug + 7-char base32 key, never from
  request input.
- **Critical SSRF (`_fetch_remote_share`):** already guarded by `assert_safe_url` on the exact URL
  fetched; added explicit **`follow_redirects=False`** to make the guard's assumption airtight,
  then dismissed the alert (CodeQL doesn't recognize the custom guard as a sanitizer).
- **XSS (creator profile URL):** real — added `isSafeHttpUrl()` (allow only http/https) and only
  render the `<a href>` when it passes (new `frontend/src/lib/utils.ts` + 8 tests).
- **Log-injection (15):** sanitized CR/LF at the request-derived sites (ssrf_guard, import);
  dismissed the rest where the logged value is app-controlled (UUIDs, ints, or `%r`-escaped names).

CodeQL is a **required release gate** — these had to be cleared (fixed or justifiably dismissed)
before PR #1 could merge.

## 2026-06-30 — Issue resolution Phase 3 (backend): context-aware corrective actions for all types

Extended the action framework to every issue type (no schema change). `available_actions` is now
computed by `actions_for(issue)` (type + item_id), not a static type map — so the two `orphan`
sub-cases differ: **item_id NULL** (dir, no item) → import/delete/ignore; **item_id SET** (item's
dir missing) → `delete_item`/ignore. New handlers, each doing the real fix then resolving:
`delete_item` (drop the DB item + child rows; dir already gone, no trash move), `remove_record`
(missing_file → delete the File row), `accept` (corruption → recompute + store the on-disk sha),
`clear_source` (dead_link → clear source_url), `keep_db`/`keep_sidecar` (conflict), `retry`
(sidecar_error). Notable choices: **`keep_sidecar`** applies the sidecar's description/source
fields to the DB then re-stamps the sidecar via `_write_item_sidecar` (skips title renames — those
need the atomic-rename flow); **`retry`** re-runs `reconcile_one_item(auto)` and resolves only if
no errors remain, else updates the issue detail. Verified capped: 61 pytest, ruff clean.

## 2026-06-30 — Issue resolution framework, Phase 1 (backend): dedup + actionable resolve (migration 0020)

Reconcile Issues couldn't be truly resolved — `resolve`/`ignore` only flipped status and the
scan had no dedup, so issues reappeared on the next run. Phase 1 backend foundation:

- **Schema (0020):** `issues.target_path VARCHAR(4096) NULL` — the most specific resolvable
  identifier per issue (dir path for orphan/conflict/sidecar_error, file path for
  missing_file/corruption, source URL for dead_link) — plus a covering index
  `(issue_type, target_path, status)`.
- **Dedup / durable suppression:** `_issue_exists(db, type, target_path)` returns true when an
  **open or ignored** issue already exists for that pair; every one of the 8 detector sites
  now skips creation when it does. Effect: no duplicate open issues, and **ignore now sticks**
  (an ignored issue is never re-created). A `resolved` issue does NOT suppress — a genuinely
  recurring condition raises a fresh issue (actionable resolve removes the condition, so this
  is rare).
- **Action framework:** `ISSUE_ACTIONS: dict[IssueType, list[str]]` (only `orphan` exposes
  `["import","delete","ignore"]` this phase; all others `["ignore"]`); `available_actions`
  computed on `IssueOut`; `POST /api/issues/{id}/action` validates against it (422 otherwise).
  Legacy `/resolve` + `/ignore` endpoints preserved.
- **Orphan-directory actions:** `delete` moves `target_path` to trash via the same
  `move_to_trash` helper item-delete uses, guarded to stay inside a known library mount, then
  marks the issue resolved. `import` creates an `ImportSession` (pending_wizard) prefilled from
  the folder's sidecar (`read_sidecar()` then raw-YAML fallback) and marks the issue
  **resolved immediately** — if the user abandons the wizard, `resolved` doesn't suppress, so
  the next scan re-detects the orphan (no dangling open issue while the wizard is active).

Phase 2 = the Issues-page actions UI (import → wizard showing existing sidecar data); Phase 3 =
corrective actions for the other issue types. Verified capped: 43 pytest (21 new + 22 reconcile),
ruff clean, 0020 round-trip clean.

## 2026-06-30 — RENDER_MODE promoted to admin-editable DB setting (`render.mode`)

`RENDER_MODE` (all / no_images / off) is now an admin-editable server setting, not env-only.
Stored as the generic `Setting` key `render.mode` (values `all` / `no_images` / `off`).
**Precedence:** the DB row wins; if absent or malformed JSON, fall back to the `RENDER_MODE`
env/config value (itself defaulted to `all`). `render_item` reads the setting inside its
existing gate session and remains the **single authoritative gate** (enforced before a Job
row is created). The `_enqueue_render` "off" short-circuit deliberately still reads only the
env value — opening a DB session there for a fire-and-forget optimization isn't worth the
complexity, and correctness is preserved because `render_item` always re-checks the DB setting.
The settings router validates `render.mode` against the allowed set via a per-key
`_KEY_ALLOWED_VALUES` map (422 on invalid). Admin UI: a select in SettingsPage (Instance
settings card, admin-gated) — "Render all models" / "Render only when a model has no images"
/ "Disable rendering". No migration (Setting is generic key/value).

## 2026-06-30 — Job lifecycle: cancel/restart, retry-supersede, archive, retention (migration 0019)

Backend lifecycle management for the `jobs` table (UI is a separate follow-up). Migration
0019 adds `arq_job_id` (so a running job can be aborted), `retry_of_job_id` (FK→jobs.id,
links a retry/restart to the job it replaces), and `archived_at`.

- **Status vocabulary** extended with two terminal values, `cancelled` and `superseded`
  (status stays a free `String`, so no enum migration). `_VALID_STATUSES`/`_TERMINAL_STATUSES`
  updated in both `jobs.py` and `job_tracker.py`.
- **Cancel race closed:** `finish_job` is now a **no-op if the row is already terminal**. The
  cancel endpoint sets `cancelled` FIRST, then best-effort arq-aborts; the aborted task's
  `BaseException` finalizer calls `finish_job(failed)` which the terminal guard ignores —
  so an explicit cancel is never clobbered. Abort requires `allow_abort_jobs=True` (now set).
- **Supersede on success:** when a job succeeds and has a `retry_of_job_id`, `finish_job` walks
  the ancestor chain (`_supersede_ancestors`, depth-20 cycle guard) marking each `superseded`,
  so a failed job whose retry later succeeds drops out of the default list.
- **List filtering:** default `GET /api/jobs` excludes `archived_at IS NOT NULL` AND
  `status='superseded'`; `?archived=true` → archive-only list; `?include_superseded=true`
  reveals superseded in the default view.
- **New endpoints:** `POST /{id}/cancel`, `POST /{id}/restart`, `POST /clear-succeeded`
  (archive all succeeded), `POST /{id}/archive`, `DELETE /{id}`. `/clear-succeeded` is declared
  before `/{job_id}` so it isn't captured by the path param.
- **Retention cron** `job_history_retention` (daily 04:30): hard-deletes succeeded jobs older
  than `JOB_RETENTION_SUCCEEDED_DAYS` (7) and failed/cancelled/superseded older than
  `JOB_RETENTION_FAILED_DAYS` (30); both configurable.

Verified capped (no full suite, mocked renders): 31 pytest (17 new + 14 existing), ruff clean,
alembic 0019 up/down/up clean.

## 2026-06-30 — Render reliability: subprocess offload, timeout, crash recovery, RENDER_MODE

**Problem:** renders pegged 100% CPU and got stuck in "running" forever. Root cause: the
render was a synchronous blocking C call (`trimesh` + pyrender/OSMesa/VTK) run directly in
the worker's asyncio event loop. No thread caps → every core saturated; arq's cooperative
`job_timeout` could not interrupt blocking C code → hung renders never timed out; and
`asyncio.CancelledError` (a `BaseException`) bypassed the `except Exception`, leaking the
"running" row.

**Fix:**
- New `backend/app/worker/render_subprocess.py`: runs `render_mesh_file` in a fresh
  `multiprocessing` **spawn** child (not fork — GL/Mesa global state makes fork unsafe),
  awaited via `asyncio.to_thread` so the loop stays free. On `RENDER_TIMEOUT_S` (default
  300s) the child is SIGTERM'd then SIGKILL'd → a real wall-clock kill.
- Thread caps (`RENDER_CPU_THREADS`, default 2) set as `OMP_/OPENBLAS_/MKL_/VECLIB_/
  NUMEXPR_NUM_THREADS` + **`LP_NUM_THREADS`** (llvmpipe/Mesa — the one that caps OSMesa)
  in Dockerfile ENV, both compose worker services, and defensively in `worker.startup()`.
- `render_item` finalizes the Job row on every path: content failures (RenderError/
  RenderTimeout/unexpected) mark it `failed` and **return normally** so arq does NOT
  auto-retry (which would spawn duplicate Job rows — chosen over tweaking WorkerSettings
  `max_tries` globally, which would affect zip/import tasks too); `BaseException`
  (cancel/shutdown) finalizes best-effort via a fresh session, then re-raises.
- Crash recovery: `worker.startup()` runs `_recover_orphaned_render_jobs` — marks any
  pre-existing `running` render jobs `failed` and **re-enqueues** `render_item` (deduped by
  item_id). Renders are idempotent (sha-cache), so completed ones just cache-hit.

**RENDER_MODE (background-render config):** new setting `all` (default) | `no_images` (only
render items with zero images — render-as-fallback-thumbnail) | `off` (never auto-render).
Gated at the top of `render_item` before the Job row is created; `off` also short-circuits
`_enqueue_render`. `render_item` is the single source of truth (reconcile.py enqueues bypass
the helper).

**Verification (light, CPU-capped — orchestrator ran this, not a heavy host suite):** live
render smoke inside the worker container (tiny cube → valid PNG; garbage file → RenderError,
no hang), plus 7 mocked/capped pytest (timeout→failed, error→no-dup-rows, orphan recovery +
dedup + no-op, and the two RENDER_MODE gate cases).

## 2026-06-30 — Clickable stat-strip tiles

Made the global `WidgetStatStrip` tiles navigate to their detail pages. Added an optional
`linkTo` to the tile registry; `StatTileBase` renders as a react-router `<Link>` only when
`linkTo` is set AND the strip is not in edit mode (edit mode keeps tiles draggable/removable).
Two tiles intentionally have no `linkTo`: `creators` (only a `/creators/:id` detail route
exists, no list page) and `storage-used` (backend not implemented; shows `—`). `favorites`
links to `/catalog?favorited=true` — `CatalogPage` already honors that query param.

## 2026-06-30 — Fix scraped-image filename collision on import commit

**Root cause:** the URL-image download loop derived `img_name` from `Path(si.path).name`, so every MakerWorld CDN URL ending in `.../image/format,webp` resolved to the filename `format,webp` — each successive image overwrote the previous one, leaving N `Image` rows all pointing to the same single file.

**Fix:** moved the httpx fetch before filename construction; added `_scraped_image_ext(url, content_type)` helper that prefers `Content-Type` (reliable), falls back to the URL path suffix (good for normal CDNs), then falls back to `.jpg`; renamed every downloaded file `scraped_{order:02d}{ext}` to guarantee uniqueness within a commit. The non-URL (staged/inbox) branch is unchanged.

**Recovery:** the already-imported Dahlia item (`private_data/data/library/ey/dahlia-eymipoa`) is corrupted on disk (1 file, 9 `Image` rows all pointing to it). It must be deleted and re-imported after this fix lands.

## 2026-06-30 — Docs refresh: README features + getting-started, .env.example, build-plan, + new features-overview/nav-architecture

Updated README features section (8 post-Phase-10 feature groups: AgentQL fallback, AI usage/cost, asset analysis, modification tracking, per-library/OS path prefixes, image management, tag improvements, import management, Aurora UI) and rewrote Getting Started to the real dev-stack flow; replaced stale "Admin → Libraries" wording in `.env.example`; updated `docs/build-plan.md` status; added `docs/features-overview.md` (per-feature reference with admin routes) and `docs/nav-architecture.md` (5-section IA, tab/route table, back-compat redirects).

## 2026-06-29 — Admin nav reorg: 17-item menu → 5 tabbed sections

**Problem:** The admin sidebar/dropdown had two groups (Operations + Admin) totalling 17 entries —
too many for quick scanning.

**Decision:** Collapse into **5 themed sections**, each a single route with a tab bar
(`AdminSectionLayout`) hosting the existing admin page components unchanged.

**Route map (new):**

| Nav entry | Base route | Tabs → component |
|---|---|---|
| Content | `/admin/content` | libraries→`LibrariesPage`, tags→`TagAdminPage`, print-stats→`PrintStatsPage` |
| Users & Access | `/admin/access` | users→`UsersPage`, invites→`InvitesPage`, password-resets→`PasswordResetPage` |
| AI & Scraping | `/admin/ai` | providers→`AiProvidersPage`, usage→`AiUsagePage`, sites→`SiteCapabilitiesPage` |
| Jobs & Activity | `/admin/activity` | jobs→`JobsPage`, scheduled→`ScheduledJobsPage`, reviews→`ReviewsPage`, issues→`IssuesPage`, changes→`ChangesPage` |
| Data & Backups | `/admin/data` | backups→`BackupsPage`, export→`ExportPage`, shares→`ShareAuditPage` |

**Back-compat redirects** (`<Navigate replace>`) from every old `/admin/*` path to its new location
so bookmarks, QuickStart links, and cross-links never 404:

- `/admin/libraries` → `/admin/content/libraries`
- `/admin/tags` → `/admin/content/tags`
- `/admin/pending-tags` → `/admin/content/tags` (PendingTagsPage merged into TagAdminPage nav entry)
- `/admin/print-stats` → `/admin/content/print-stats`
- `/admin/users` → `/admin/access/users`
- `/admin/invites` → `/admin/access/invites`
- `/admin/password-reset` → `/admin/access/password-resets`
- `/admin/ai-providers` → `/admin/ai/providers`
- `/admin/ai-usage` → `/admin/ai/usage`
- `/admin/site-capabilities` → `/admin/ai/sites`
- `/admin/jobs` → `/admin/activity/jobs`
- `/admin/scheduled-jobs` → `/admin/activity/scheduled`
- `/admin/reviews` → `/admin/activity/reviews`
- `/admin/issues` → `/admin/activity/issues`
- `/admin/changes` → `/admin/activity/changes`
- `/admin/backups` → `/admin/data/backups`
- `/admin/export` → `/admin/data/export`
- `/admin/shares` → `/admin/data/shares`

**Implementation notes:**
- `AdminSectionLayout` (`frontend/src/components/admin/AdminSectionLayout.tsx`): Aurora underline
  tab bar with `NavLink` isActive detection + `<Outlet />`. Zero new deps.
- `navConfig.ts`: Replaced `operations` + `admin` groups with a single `admin` group of 5 items.
  Both SideNavShell and TopNavShell render the 5 sections (they both read navConfig).
- Pending reviews badge moved to "Jobs & Activity" nav item (path `/admin/activity/jobs`).
- `QuickStartPage.tsx` deep links updated to new paths.
- `PendingTagsPage` component retained but removed from nav and its old route is redirected.
  `TagAdminPage` already contained the pending section.
- `PasswordResetPage` added to nav for the first time (was routed but not linked).

## 2026-06-29 — Split backend monoliths: worker.py → tasks/, items.py → services/, import_sessions.py → package

Three backend monoliths extracted into smaller modules — pure token-efficiency refactor, no behavior change.

**worker.py** (1,741 → thin entrypoint ≈ 110 lines): Task functions moved to `app/worker/tasks/` package:
`render.py` (`render_item`, `_reconcile_render_images`), `analysis.py` (`analyze_item`),
`bundles.py` (`build_zip_bundle`, `_cleanup_expired_bundles_core`), `backup.py` (`_db_backup_core`),
`import_session.py` (`process_import_session`, `_try_agentql_fallback`), `reviews.py` (`apply_review_item`),
`scheduled.py` (`exec_scheduled_job`, cron wrappers, `_sj_start`/`_sj_finish`, `_inbox_scan_core`,
`_library_reconcile_scan_core`, `_share_link_expiry_cleanup_core`).
arq task names are registered by function `__name__`; they were not renamed. Two symbols
(`_try_agentql_fallback`, `_reconcile_render_images`) are re-exported from `worker.py` with `# noqa: F401`
for test backward-compat (`from worker import _try_agentql_fallback`).

**items.py** (1,350 → ≈ 1,100 lines): Seven cross-imported helpers extracted to `app/services/item_helpers.py`:
`_get_or_create_tag`, `_attach_tags`, `_update_search_vector`, `_build_sidecar_data`,
`_write_item_sidecar`, `_enqueue_render`, `_enqueue_analyze`.
`_effective_is_modified` STAYS in items.py (test imports it from `app.routers.items`).
All import sites in `import_sessions.py` and task modules updated to `from ..services.item_helpers import …`.

**import_sessions.py** (1,648 → package): Converted to `app/routers/import_sessions/` package:
`schemas.py` (Pydantic models), `helpers.py` (`reconcile_tags`, `_session_out`, `_load_session`,
`_ensure_creator`, `_get_staging_dir`, `_enqueue_import_job`), `sessions.py` (10 CRUD endpoints),
`site_caps.py` (3 site-cap endpoints), `__init__.py` (combined router + `_share_link_fetcher` module-level
variable + `_get_fetcher` + `import_from_share_link` + re-export of `reconcile_tags`).
`_share_link_fetcher` kept at package `__init__` scope so `import app.routers.import_sessions as m; m._share_link_fetcher = mock` still works.
`reconcile_tags` re-exported from `__init__` for `from app.routers.import_sessions import reconcile_tags`.

## 2026-06-29 — Split ImportWizardPage.tsx into import-wizard/* step components

`frontend/src/pages/ImportWizardPage.tsx` (2,389 lines) split into per-step component files
under `frontend/src/pages/import-wizard/` — pure token-efficiency refactor, no behavior change.

Files extracted: `styles.ts` (Aurora style constants + focus/blur handlers, JSX-free),
`StepProgress.tsx` (Aurora stepper indicator), `SiteSetupBanner.tsx` (site API token banner),
`AiTextPreview.tsx` (AI text suggestion preview panel), `TitleStep.tsx` (confirmed title +
description + AI cleanup/summarize + source URL + site-setup token banner), `ImagesStep.tsx`
(scrollable strip + set-default + remove-image ✕ + upload), `TagsStep.tsx` (confirmed chips +
reconcile accept/reject chips + AI suggestions click-to-add box + typeahead autocomplete +
pending-tag-on-Next prompt), `CreatorStep.tsx` (own-design toggle + attributed creator),
`SummaryStep.tsx` (read-only review table + commit/cancel + SummaryRow helper),
`ProcessingOverlay.tsx` (spinner shown while status=processing).

`ImportWizardPage.tsx` now 289 lines — owns the session query + 3s polling, step state machine
(`useState<WizardStep>` + `nextStep`/`prevStep` lambdas), all terminal states
(committed/cancelled/failed/processing), scrape_note banner, and composes step components via
props. All query keys, polling logic, per-step PATCH mutations, AI-assist calls, tag
autocomplete debounce, pending-tag-on-Next flow, and commit/cancel navigation preserved exactly.

## 2026-06-29 — Split ItemPage.tsx into item/* subcomponents

`frontend/src/pages/ItemPage.tsx` (2,589 lines) split into 8 subcomponent files under
`frontend/src/pages/item/` — pure token-efficiency refactor, no behavior change.

Subcomponents extracted: `styles.ts` (aurora constants + formatters), `AuroraSection.tsx`
(section wrapper), `ImageCarousel.tsx` (carousel + pager/thumbs/lightbox),
`PathDisplay.tsx` (path rewrite + OS override), `DownloadsPanel.tsx` (single files + ZIP
queue/poll + include-history), `PrintHistory.tsx` (PrintRecordForm + PrintRecordCard +
PrintHistorySection), `ObjectBreakdown.tsx` (ColorSwatch + ObjectBreakdownSection),
`ShareControls.tsx` (mint/list/revoke/copy), `ItemMetadata.tsx` (title, creator, tags,
source/license, modified badge + override, description, timestamps).

`ItemPage.tsx` now 300 lines — owns the top-level query, image mutations (set-default,
upload, delete), delete-to-trash, breadcrumb, and layout. `overrideMutation` lives in
`ItemMetadata` since it updates the same `['item', key]` query key. All TanStack query
keys, mutations, carousel paging, upload/delete/set-default, print-history forms, share
flow, ZIP poll, and object breakdown behavior preserved verbatim.

`AuroraSection` was initially placed in `styles.ts` (.ts extension); build failed because
esbuild does not parse JSX in `.ts` files. Fixed by extracting to `AuroraSection.tsx`.

## 2026-06-29 — Split api.ts into per-domain modules under lib/api/

`frontend/src/lib/api.ts` (2,011 lines) split into 22 domain modules under
`frontend/src/lib/api/` with a barrel `api/index.ts` that re-exports everything.
The old `api.ts` was deleted; `@/lib/api` now resolves to the barrel. No consumer
changes required — pure token-efficiency refactor, zero behavior change.

Modules created: `core`, `setup`, `auth`, `users`, `invites`, `password-reset`,
`settings`, `me`, `api-keys`, `items`, `libraries`, `import`, `print-records`,
`shares`, `jobs`, `scheduled-jobs`, `issues`, `changes`, `reviews`, `ai`,
`backups`, `export`, `tag-admin`, `agentql`. `shares.ts` imports `BundleOut`
type-only from `items.ts` (single cross-module dep).

## 2026-06-29 — Import management: delete-session-image semantics + SQLAlchemy identity-map caveat

### Staged-file cleanup safety check

Both the delete-session (`DELETE /api/import-sessions/{id}`) and delete-session-image
(`DELETE /api/import-sessions/{id}/images/{image_id}`) endpoints remove local files
best-effort. To prevent path-traversal bugs, every removal is gated by
`Path.relative_to(...)`:

- Delete session: `staging_path.relative_to(Path(settings.DATA_DIR))` before `shutil.rmtree`
- Delete image: `file_path.relative_to(staging_path)` before `file_path.unlink()`

If either check raises `ValueError` (path is outside the expected root), the removal is
silently skipped (logged as a warning). Committed Items/library files are never touched.

### Default-image reassignment on delete

When the deleted image had `is_default=True`, the endpoint queries remaining images
`ORDER BY order ASC LIMIT 1` and promotes that image (`is_default = True`,
`session.default_image_path = first_remaining.path`). If no images remain,
`default_image_path` is cleared to `None`. This avoids dangling default pointers while
keeping the reassignment deterministic (lowest `order` wins).

### SQLAlchemy async identity-map cache bust before response reload

After `await db.delete(img)` + `await db.flush()`, a follow-up
`select(ImportSession).options(selectinload(images))` can return the stale in-memory
collection when the parent session object is already in the ORM identity map with the
`images` attribute loaded (e.g. from `_load_session`). The fix is
`db.expire(session, ["images", "files"])` before the reload; this marks those
attributes as expired so the next `selectinload` re-fetches from the DB.

The scalar `id` attribute must be captured into a local variable _before_ expiring
the object, because `expire()` marks it stale and accessing it later triggers a
lazy-load (which raises `MissingGreenlet` in an async context).

### Inbox dir auto-creation at startup

`INBOX_DIR` (default `/data/inbox`) is created in the FastAPI lifespan hook next to the
existing journal-recovery logic. `mkdir(parents=True, exist_ok=True)` is wrapped in a
broad `except` so any permission or FS error produces a warning rather than crashing
startup. The scanner skips a missing inbox but now the directory is guaranteed present.

## 2026-06-29 — Tag Admin: real item_count via join (popularity_count unmaintained)

The Tag Admin page ("Pending tags" section and "All tags" table) was showing 0 uses for
every tag because it displayed `popularity_count`, a denormalized field that is never
updated in any write path.

Fix: `GET /api/admin/tags/pending` now computes `item_count` via an outer join
`COUNT(item_tags.item_id)` per tag (same approach as the public `/api/tags` endpoint /
tag cloud). `item_count: int = 0` is added to `TagAdminOut`; the "Uses" column in both
the pending section and the all-tags table (and the merge dropdown) now shows `item_count`
instead of `popularity_count`.

`popularity_count` is deliberately **not** backfilled or maintained; it is superseded by
the computed join count for display purposes and would require write-path hooks to keep
in sync (out of scope). It remains in the schema for historical compatibility.

## 2026-06-29 — Catalog: tag-cloud log scale, Alpha/Number sort toggle, dark-mode select fix

### Tag cloud font sizing — log scale, capped max

The previous `getTagFontSize` used a linear step-bucket scale with a max of 2 rem (32 px).
With a typical collection where a handful of tags dominate by count, even 2–3 items on a
single tag pushed it into the top bucket, making the cloud look chaotic.

Fix: replaced the step buckets with a **log-normalised continuous scale** (`logNorm =
log(count − min + 1) / log(max − min + 1)`) clamped between **0.75 rem (~12 px)** and
**1.375 rem (~22 px)**. The log curve compresses high-count outliers so they scale
proportionally without exploding. Min stays at 12 px (readable), max stays at 22 px
(prominent but not enormous). All existing tests updated; a new log-scale monotonicity
assertion (`midVal > (minVal + maxVal) / 2`) is added to verify the curve direction.

### Tag cloud Alpha / Number sort toggle

Added a compact segmented toggle ("A–Z" | "#") at the top of the tag-cloud card. Default
is Number (`item_count` desc, ties → name A→Z) which matches prior behaviour; Alpha sorts
A→Z by name. The toggle is rendered inside `TagCloud` (inline with the "Browse by tag"
label) to keep all tag-cloud UI self-contained. Choice is persisted in `localStorage`
(`pf3d-tag-sort`). Sorting is client-side via `sortTags<T>(tags, mode)` in
`catalog-utils.ts` (pure, immutable, unit-tested with 7 new tests).

### Dark-mode native `<select>` fix — `colorScheme` style property

The catalog sort `<select>` rendered with OS-default white dropdown options in dark mode
because no `color-scheme` hint was provided to the browser. Fix: read the active theme
via `useTheme()`, compute `isDark` (handles `'system'` by querying `matchMedia`), and
set `colorScheme: isDark ? 'dark' : 'light'` as an inline style on the select element.
This instructs the browser to render native controls (including the dropdown list) in the
matching OS colour scheme. No global CSS changes, no new dependencies; `colorScheme` is a
standard `React.CSSProperties` key.

## 2026-06-30 — Delete-to-trash must be cross-device safe

`move_to_trash` used `Path.replace` (os.replace), which is atomic but raises EXDEV across
filesystems. Items live under a **library mount** (e.g. `/library`) while trash is under
`DATA_DIR` (`/data`) — usually separate devices — so every real item delete 500'd. Fixed: try
`os.replace` first (fast, same-device), fall back to `shutil.move` (copy+delete) on `OSError`.

## 2026-06-29 — Import wizard Tags step: tag typeahead autocomplete

### `GET /api/tags?search=<prefix>` — new param alongside existing `?q=`

The existing `?q=` param does a substring match (`ILIKE '%q%'`) for the tag
cloud / admin browse.  A second `?search=` param was added for the autocomplete
typeahead: it does a prefix match (`ILIKE 'search%'`) and respects the existing
`active_only=true` default.  No per-page cap is enforced server-side; the
frontend requests `per_page=10` when calling as a typeahead.

Chose a separate `?search=` param (rather than reusing `?q=`) so the two call
sites remain independent: the cloud uses substring-everywhere; the autocomplete
wants prefix-anchored results (users type from the start of a tag name).

### Autocomplete in `ImportWizardPage.tsx` — debounced, keyboard accessible

A 200 ms debounced search fires on every keystroke in the tag input.  Results
are shown in an absolute-positioned dropdown attached to the input container
(click-outside closes it).  The dropdown lists:

- **Matching existing active tags** (click or Enter on highlighted item → adds
  directly to `confirmed`, skipping the new-tag → pending path since the tag
  already exists).
- **"Create new tag: '<typed>'"** when the typed text is non-empty and does not
  exactly match any result (selecting it goes through the existing `handleAddTag`
  new-tag path).

All existing Tags-step behaviors are preserved: AI suggestions card, manual
Enter-to-add, the pending-tag-on-Next confirmation prompt, and the
pending-from-session accept/reject chips.  `onMouseDown` + `e.preventDefault()`
on each dropdown item prevents input blur before selection fires.

## 2026-06-29 — Item page: carousel layout + controlled thumbnail strip

### Fixed-height main image (300 px, no aspect-ratio)

The previous main-image container used `aspectRatio: '16/9'` + `minHeight: 200`.
On a 900 px max-width page the 1fr column is ~440 px wide, so 16:9 = ~247 px — fine
by itself, but the unbounded thumbnail strip below (rendering all 16+ thumbnails with
`overflow: auto`) pushed the image block to dominate the hero.  Fix: fixed `height: 300`
with no aspect-ratio.  The image inside uses `objectFit: contain` so any shape fits
without cropping.

### Controlled thumbnail strip: THUMBS_VISIBLE = 6 + scroll arrows + page jump nav

Instead of rendering all images as a scrollable `overflowX: auto` row, the new strip:
- Shows exactly `THUMBS_VISIBLE = 6` thumbnails at a time (flex-equal-width slots,
  with empty spacer divs to keep the strip width stable when fewer than 6 remain).
- ‹ / › buttons scroll the window by 1 thumbnail (`thumbOffset` state).
- A `useEffect` on `clampedIdx` calls `setThumbOffset` (functional updater) to
  auto-scroll the strip whenever the active image moves outside the visible window —
  no `thumbOffset` in the effect dep array, avoiding infinite loop.
- Jump nav below the strip: `buildCarouselPagerItems(currentPage, totalPages)` returns
  0-based page indices and `'ellipsis'` markers.  Clicking a page number jumps `activeIdx`
  to the first image on that page and snaps the strip to show it.

### Responsive hero grid: auto-fit minmax(320 px, 1fr)

Changed from `gridTemplateColumns: '1fr 1fr'` (always two columns, details column gets
squished) to `repeat(auto-fit, minmax(320px, 1fr))`.  When the viewport is narrower than
~680 px (2 × 320 + 16 gap + margins) the grid auto-stacks to a single column with the
image above the details — pure CSS, no media query, no Tailwind class needed.

### buildCarouselPagerItems extracted to carousel-utils.ts

The pager math is a pure function (no DOM, no React), so it lives in
`frontend/src/lib/carousel-utils.ts` and is covered by 7 unit tests in
`frontend/src/test/carousel.test.ts`.  This keeps the component clean and
the boundary logic verifiable without spinning up a browser.

## 2026-06-29 — Phase 18: AgentQL optional BYO-key fallback scraper

### AgentQL as REST-only fallback (no Playwright/SDK, no Chromium)

The built-in static scraper (`scraper.py`) cannot reach Cloudflare-gated pages
(MakerWorld returns a 403 JS-challenge).  AgentQL's cloud browser service can
(proven: POST `/v1/query-data` with `browser_profile=stealth` + `proxy.type=tetra`
returns HTTP 200 with title + description + 12 images in ~21s).

Design choices:
- **REST API only** (`POST https://api.agentql.com/v1/query-data`).  No Playwright,
  no Chromium in the Docker image.  The REST endpoint is sufficient and avoids
  adding a multi-GB browser dependency.
- **Fallback only**.  AgentQL is called _only_ when `scrape_url` returns
  `blocked=True`.  Sites that scrape fine (Printables, Thingiverse) never
  incur an AgentQL call.
- **Off by default**.  `agentql_enabled` defaults to `false`.  The admin must
  explicitly enable it and paste their BYO key.
- **Stealth + Tetra proxy as configurable defaults**.  These are the params
  confirmed to defeat Cloudflare; they're configurable (proxy can be disabled)
  but default to the working combination.
- **Sync HTTP client** (`httpx.Client` with 120 s timeout) run via
  `asyncio.run_in_executor` from the arq worker — same pattern as the static
  scraper.

### Local usage tracking (no AgentQL usage API)

AgentQL's REST API has no `/usage` or `/quota` endpoint (verified as of 2026-06).
We count our own calls in the `scraper_usage` table (one row per call) and use
that count for budget enforcement.  Our key is the sole consumer, so our count
≈ real usage; the AgentQL dashboard remains authoritative for billing.

### Fixed reset day (1st of month) — not yet in UI

The budget window resets on the 1st of each month.  This is stored as
`AGENTQL_RESET_DAY = 1` in both `app/routers/agentql.py` and `worker.py`.
It is deliberately NOT exposed as a UI field yet; it can be promoted to a
settings field later without a migration.

### Budget modes: free_only / cap

- `free_only` (default): counts calls; stops when `window_calls >= free_allowance`
  (default 50 — the AgentQL Starter free tier).
- `cap`: stops when `window_cost + per_call_usd > monthly_cap_usd`.
  Requires setting `monthly_cap_usd`.
Both modes use the `per_call_usd` rate (default $0.02) for cost estimation.

### scrape_note on import_sessions

A new nullable `scrape_note` column on `import_sessions` (migration 0018)
communicates the scrape source to the frontend wizard:
- "Fetched via AgentQL" — agentql fallback succeeded.
- Human-readable blocked/budget reason — both static + agentql were blocked.
- `null` — standard static scrape (no special annotation needed).
Shown as a subtle banner in the import wizard.

## 2026-06-29 — Tag delete semantics + cloud real-count join

### Delete tag untags items; never deletes them

`DELETE /api/admin/tags/{id}` removes any tag regardless of status.  Semantics:

1. Count the `ItemTag` rows for the tag (= items that will be untagged).
2. Delete all `ItemTag` rows (unlinks tag from items; items themselves are unaffected).
3. Delete all `TagAlias` rows for the tag.
4. Delete the `Tag` row itself.
5. Return `{ deleted: true, items_untagged: <count> }`.

The existing `reject` endpoint is kept (pending-only, 409 on active); the existing
`merge-into` endpoint is kept.  The new delete is the only way to hard-delete an
active tag without a merge target.

### Cloud uses real join count, not popularity_count

`popularity_count` on `Tag` is a denormalized counter that can drift (e.g. if an
import session is cancelled after tagging).  The tag cloud in `CatalogPage` and
the `in_use_only` filter both need accurate counts, so `GET /api/tags` now computes
`item_count` via a `COUNT(item_tags.item_id)` outer-join subquery grouped by
`tag_id`.  `popularity_count` is still returned for callers that rely on it, and
is still used for popularity-ordering in the response.

`in_use_only=true` (default: false) lets the cloud request only tags with
`item_count > 0`, hiding zero-item tags without a schema change or migration.

## 2026-06-29 — Phase 17: per-library × per-OS local path prefixes

### Model: per-user JSONB map keyed by library ID and OS

The single `users.path_prefix` string was replaced by `users.path_prefixes`
(JSONB, migration 0017) — a map `{ "<library_id>": { "windows": str|null,
"posix": str|null } }`.  Keys are library IDs as strings (JSON requires string
keys).  This handles two use cases the old single field could not:
- Multiple libraries at different mount points (e.g. `/library/main` and
  `/library/archive`) each need an independent local mapping.
- The same user on a Windows PC and a Mac needs separate `C:\prints\` and
  `/mnt/nas/` prefixes stored simultaneously; the browser picks the right one.

`path_prefix` is kept (deprecated) so the downgrade is trivially safe.

### Browser OS detection + manual override

`detectOS(platformHint?)` in `catalog-utils.ts` checks
`navigator.userAgentData?.platform` (preferred, modern) → `navigator.platform`
→ `navigator.userAgent`.  A `Win` (case-insensitive) match returns `'windows'`;
everything else returns `'posix'` (safe default for Mac / Linux / Android).

The function accepts an optional platform hint for unit-testability (vitest
tests inject strings without a real `navigator`).

A `pf3d_os_override` localStorage key (`'windows' | 'posix' | 'auto'`) lets a
user force the display style in this browser (e.g. a Linux user connecting via
browser on a Windows machine).  The override is shown and editable on the
Settings page.

### Mount-path stripping (rewriteLocalPath)

`rewriteLocalPath(containerPath, libraryMountPath, localPrefix, os)` in
`catalog-utils.ts`:
1. Strips `libraryMountPath` from the front of `containerPath` (e.g. removes
   `/library/main` leaving `Creator/Model-abc`).
2. Joins the remainder onto `localPrefix` (e.g. `C:\prints\` → `C:\prints\Creator\Model-abc`).
3. Normalises all separators via `toPathStyle(path, os)`.

Falls back to the raw `containerPath` when `localPrefix` is absent.  This is
intentionally different from the old `rewritePath` (which prepended the prefix
to the whole path); `rewritePath` is kept for backward compatibility.

### Migration of legacy path_prefix (data migration in 0017)

`infer_prefix_map(path_prefix, library_ids)` (in `app/path_prefix_utils.py`)
is the shared helper used by both the Alembic data migration and the backend
tests.  For each user with a non-null legacy `path_prefix`, the function:
- Infers OS from the string (backslash present → `windows`; else `posix`).
- Applies the prefix to every library, setting the inferred OS entry and
  leaving the other OS entry null.

The helper lives in `app/` (not in the migration file) because migration files
have numeric-prefixed names that cannot be imported directly by Python.

### PUT endpoint validation

`PUT /api/me/path-prefixes` silently ignores unknown library IDs (deleted or
never-created libraries that appear in the client's map).  Only IDs present in
the `libraries` table are written to the DB.  This prevents stale map entries
from blocking the save on the frontend.

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
