---
name: 2026-06-27-phase-0-scaffolding
status: pending          # pending | completed | failed
created: 2026-06-27
model: sonnet            # execution of a locked plan
completed:
result:
---

# Task: Phase 0 — repo scaffolding & dev loop

Stand up the PartFolder 3D monorepo so `docker compose up` serves a themed app shell at
`:8973` talking to a live FastAPI backend, and flip the tolerant CI guards into real
enforcement. This is **Phase 0** of [`docs/build-plan.md`](../docs/build-plan.md).

## Before you start

- Read [`docs/build-plan.md`](../docs/build-plan.md) — especially **Locked build-time
  technical decisions** and the **Phase 0** section. Those decisions are settled; do not
  re-litigate them.
- Read [`PRD.md`](../PRD.md) §3 (architecture, containers, storage, port 8973) and
  [`CLAUDE.md`](../CLAUDE.md) (operating rules: work on `dev`, conventional commits, no
  `Co-authored-by:`, never `--no-verify`).
- Read the existing `.github/workflows/ci.yml` and `publish.yml` — you will remove the
  bootstrap existence-guards for the pieces this phase creates.
- This is a large phase. If you judge it too big for one clean pass, STOP and report a
  proposed split (e.g. 0a backend+compose, 0b frontend, 0c CI) rather than half-doing it.

## Working tree check

Run `git status --porcelain`. Expect only this prompt file to be dirty. If anything else
overlaps the files below, list it and ask before proceeding.

## What to do

### 1. Monorepo layout
Create:
```
backend/            FastAPI app (see §2)
frontend/           Vite + React + TS app (see §4)
nginx/              reverse-proxy config (proxy /api → backend, serve frontend, :8973)
docker-compose.yml          # db, redis, backend, worker, frontend(build), nginx
docker-compose.dev.yml      # dev overrides (hot reload, bind mounts)
Dockerfile                  # root: backend+worker image (ghcr.io/crzykidd/partfolder3d)
.env.example                # documented env (DB creds, ports, DATA_DIR, etc.)
```
Mount model from PRD §3.2: `./data:/data` (app-owned) and a sample library mount.

### 2. Backend skeleton (`backend/`)
- Python 3.12, FastAPI, **SQLAlchemy 2.0 async** (asyncpg), Pydantic v2, **Alembic**, **arq**.
- `backend/requirements.txt` (CI reads this) pinning the above + `ruff`, `pytest`,
  `pytest-asyncio`, `cryptography`, `argon2-cffi`/passlib (auth lands Phase 1 — just add
  deps you use now; don't build auth yet).
- `backend/app/version.py` → `__version__ = "0.1.0"` (bare).
- `backend/app/main.py`: FastAPI app, CORS as needed, OpenAPI enabled, routes:
  - `GET /health` → `{"status":"ok"}`
  - `GET /api/version` → `{"version": __version__}`
- `backend/app/db.py`: async engine + session factory reading `DATABASE_URL`.
- `backend/app/config.py`: Pydantic settings (DATA_DIR=/data, DATABASE_URL, REDIS_URL, …).
- Alembic: `alembic init`, configured for the async engine; **one empty baseline migration**
  (no tables yet — models come in Phase 1+). `alembic upgrade head` must succeed.
- `backend/worker.py`: minimal arq worker (empty task set, connects to Redis) so the
  `worker` container has something to run.
- One passing test: `backend/tests/test_health.py` hitting `/health` + `/api/version`.

### 3. Database + Alembic in CI
- The `migration-check` CI job runs `alembic upgrade head`, which needs Postgres. Add a
  **`services: postgres:16`** block to the `migration-check` job (and `test` if tests touch
  the DB) with a healthcheck, and point `DATABASE_URL` at it. Keep the env var names the
  workflow already uses where possible.

### 4. Frontend skeleton (`frontend/`)
- Vite + React 18 + TypeScript + Tailwind + **shadcn/ui** initialized.
- **Theme**: system / light / dark via CSS vars + a toggle; **system default first**, user
  choice persisted to localStorage (per-user server persistence comes Phase 1).
- App shell: header with the logo (`docs/images/logo-horizontal-{light,dark}.png` via the
  `<picture>` pattern or theme-aware swap) + nav placeholder + a page that fetches
  `GET /api/version` and renders it.
- `npm ci` clean; `npx tsc --noEmit` clean; a baseline `vitest` test passes.

### 5. nginx + compose + Dockerfile
- `nginx/`: proxy `/api/` → `backend:8000`, serve the built frontend, listen on the
  internal port mapped to host **8973** (changeable in compose).
- Root `Dockerfile`: build the backend+worker image (multi-stage; CPU-only).
- `docker-compose.yml`: services `db` (postgres:16, volume), `redis`, `backend`, `worker`,
  `frontend` (build → static served by nginx), `nginx` (ports `8973:80`). `.env.example`
  documents every var. `docker compose config --quiet` must pass.

### 6. CI: remove bootstrap guards now satisfied
In `.github/workflows/ci.yml` remove the existence-guards for pieces that now exist so the
jobs enforce for real: `lint` (backend ruff + frontend tsc), `config-validate`,
`migration-check` (with the Postgres service from step 3), `compose-validate`,
`image-build` (Dockerfile now present), `test`. In `publish.yml`, the Dockerfile now
exists so the build runs normally — keep it sane (it only pushes on dev/main/release).
Leave a brief comment noting guards were removed in Phase 0. **Do NOT touch branch
protection** — adding the 2 CodeQL required checks is the orchestrator's job after CI is
green (call it out in your report).

### 7. Tooling
- `ruff` config (e.g. `backend/pyproject.toml` or `ruff.toml`) — `ruff check backend/` clean.
- Ensure `pytest` (backend) and `vitest` (frontend) both run green locally.

## Conventions to honor

- Match the PRD's stack + the locked decisions exactly. Don't add product features beyond
  the Phase 0 shell (no auth, no models beyond the empty baseline, no item logic).
- Keep secrets out of the repo; `.env.example` only (real `.env` is gitignored).
- Verify what you can locally: `ruff check`, `tsc --noEmit`, `pytest`, `vitest`,
  `docker compose config --quiet`, `alembic upgrade head` against an ephemeral Postgres (or
  a local one). Full `docker compose up` boot is verified by the user/CI — note that in your
  report rather than claiming it if you couldn't run it.

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-27`, one-line `result`).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/`.
3. Add a `docs/decisions.md` entry (newest at top) for any non-obvious Phase 0 call
   (e.g. Dockerfile layout, nginx routing, CI Postgres service).
4. **You are a spawned agent: do NOT commit, push, or change branch protection.** Prepare
   the working tree and report back:
   - the file list + a proposed one-line commit message (`feat:` or `chore:` prefix),
   - which CI guards you removed and the exact local check results (ruff/tsc/pytest/vitest/
     compose/alembic),
   - an explicit note that the orchestrator should, after the dev→main PR CI is green, add
     `CodeQL / Analyze (python)` and `CodeQL / Analyze (javascript-typescript)` to `main`'s
     required status checks,
   - anything you couldn't verify (e.g. full compose boot) or had to decide.
