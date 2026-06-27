# Decisions

ADR-style log of non-obvious decisions, newest at top.

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
