# Decisions

ADR-style log of non-obvious decisions, newest at top.

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
