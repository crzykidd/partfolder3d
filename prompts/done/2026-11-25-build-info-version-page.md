---
name: 2026-11-25-build-info-version-page
status: done             # pending | in-progress | done | failed
created: 2026-11-25
model: sonnet
completed: 2026-11-25
result: Build info stamped into all images; /api/version/details; Version page Components table; smoke-tested locally
---

# Task: Stamp build info (commit / channel / build date) into every image + show all components on the Version page

The owner runs prod on the `:dev` channel and cannot tell which build each component is on:
`/api/version` returns only `0.8.1`, identical for `:dev` and `:latest`. (Real incident today: the
frontend `:dev` image was correct, but nginx was still serving stale assets from the `frontend_dist`
volume — invisible in the app.) Make every component report its own build so a mismatch is obvious.

## Before you start

- Read `CLAUDE.md`, `docs/architecture.md`, `.github/workflows/publish.yml` (3-image matrix:
  backend `.`, frontend `./frontend` target `prod`, nginx `nginx/Dockerfile`; metadata-action tags
  `dev` / `sha-<short>` / `latest` / semver), root `Dockerfile`, `frontend/Dockerfile`,
  `frontend/docker-entrypoint.sh`, `frontend/vite.config.ts`, `nginx/Dockerfile`, `nginx/nginx.conf`,
  `nginx/nginx.dev.conf`, `nginx/partfolder-common.conf`, `backend/app/main.py` (`/api/version`),
  `backend/app/version.py`, `backend/worker.py` + worker startup hooks, `frontend/src/pages/VersionPage.tsx`,
  and the nav shells that fetch `/api/version` (`components/shell/SideNavShell.tsx`, `TopNavShell.tsx`).
- Version stays **bare** in `version.py` / `package.json` (release standard) — do not change it.
- **No migration.** Stack: Tailwind + CSS vars + lucide + TanStack Query + `apiFetch`; no Mantine, no toast lib.
- Gates you may run: pinned ruff, `backend/.venv/bin/python -c "import app.main"` (needs `DEBUG=true`),
  `cd frontend && npx tsc -b --force && npx vite build && npx vitest run <your files> --no-file-parallelism`.
  **Do NOT run `make verify` / pytest** (orchestrator does). Don't edit `CHANGELOG.md`. Don't touch running containers.

## Working tree check

`git status --porcelain`; stop and report if a file you need is dirty.

## Design

**Build info shape** (same everywhere): `{ version, commit (full sha), channel, build_date (ISO-8601 UTC) }`.
- `channel`: `dev` for `refs/heads/dev`, `main` for `refs/heads/main`, `release` for release events,
  `local` when built outside CI. `commit`/`build_date` default to `unknown` for local builds.

1. **CI (`publish.yml`)**: pass `build-args` to `docker/build-push-action` for all three images:
   `GIT_SHA=${{ github.sha }}`, `BUILD_CHANNEL=<derived as above>`, `BUILD_DATE=<UTC now>` (compute in a
   prior step; reuse metadata-action's `org.opencontainers.image.created` output if convenient). Keep the
   existing OCI labels.
2. **Backend/worker (`Dockerfile`)**: `ARG GIT_SHA=unknown BUILD_CHANNEL=local BUILD_DATE=unknown` →
   `ENV PF3D_GIT_SHA=... PF3D_BUILD_CHANNEL=... PF3D_BUILD_DATE=...` in the **runtime** stage (late, so it
   doesn't bust the pip cache layer). Add `app/build_info.py` reading those env vars.
3. **Worker self-report**: on worker startup (and refresh on its existing heartbeat/cron if there is one —
   else on startup only, with a TTL'd key refreshed by a lightweight periodic arq cron if one fits cleanly)
   write its build info + `started_at` + hostname to Redis key `pf3d:build:worker`. If multiple workers is a
   realistic deployment, key by hostname under a hash; keep it simple.
4. **Backend endpoint**: keep `GET /api/version` **unchanged and public** (nav shells + first-run use it).
   Add **authenticated** `GET /api/version/details` (any logged-in user; `get_current_user`) returning
   `{ backend: BuildInfo, worker: BuildInfo & {started_at, host} | null }` (worker null if key missing;
   don't 500 if Redis is down — return null + an `error` string).
5. **Frontend bundle**: `frontend/Dockerfile` builder stage `ARG GIT_SHA/BUILD_CHANNEL/BUILD_DATE` exposed to
   Vite (e.g. as `VITE_GIT_SHA` etc. env, or `define` in `vite.config.ts` reading `process.env`) so the built JS
   knows its own build info; also extend the `/app/VERSION` file / entrypoint banner to print
   `v<version> (<channel> <short sha>, built <date>)`. Default `local`/`unknown` for `npm run dev` and vitest.
   Type it (`src/lib/buildInfo.ts` exporting a `BuildInfo` const).
6. **nginx**: `nginx/Dockerfile` ARGs → write `/usr/share/nginx/build-info/nginx.json` at build time; serve it
   at `location = /build-info/nginx.json` (no-cache headers) in `partfolder-common.conf` (so both prod and
   TLS server blocks get it). Make sure the dev nginx config (`nginx.dev.conf`, uses stock `nginx:1.30-alpine`
   with mounted config) degrades gracefully — return 404 there or add a static stub; the UI must handle 404.
   **Also expose what nginx is actually SERVING** — the frontend assets in the `frontend_dist` volume: have
   the frontend publish step write `build-info.json` into `/dist` (copied alongside `index.html`), so
   `/build-info.json` (served from the volume, no-cache) reveals the build of the files nginx is serving.
   This is the key check that would have caught today's stale-volume incident.
7. **Version page (`VersionPage.tsx`)**: replace the single "Backend version" line with a **Components**
   table: rows **Frontend (this browser's bundle)**, **Frontend (served by nginx — `/build-info.json`)**,
   **nginx**, **Backend**, **Worker**; columns Version · Channel · Commit (short sha, linked to
   `https://github.com/crzykidd/partfolder3d/commit/<sha>`, copy button optional) · Built (local time + relative).
   Show "unavailable" per row on fetch failure/404. Show a clear **warning banner** when commits differ across
   the rows that report one (e.g. "Components are on different builds — stale frontend volume or a
   container wasn't restarted?"), and specifically when bundle ≠ served (hint: hard refresh). Keep the existing
   card styling. Nav shells keep showing the plain version; optionally append the short sha when channel ≠
   release — your call, keep it subtle.
8. **Tests**: backend test for `/api/version/details` (auth required; env-var build info; worker key present /
   absent / Redis error) in a new `backend/tests/test_build_info.py` following existing fixture style; worker
   startup writes the key (unit-level, mock redis). Frontend vitest for the Version page: all rows render,
   mismatch banner shows/hides, 404 rows show "unavailable".
9. **Local smoke**: `docker build` each image with `--build-arg GIT_SHA=$(git rev-parse HEAD) --build-arg
   BUILD_CHANNEL=dev --build-arg BUILD_DATE=$(date -u +%FT%TZ)` (tags `pf3d-bi-*`), and verify:
   backend container `python -c` prints build info from `app.build_info`; frontend container run against a
   throwaway volume writes `build-info.json` with the sha and banner prints it; nginx image contains
   `nginx.json` and `nginx -t` passes. Remove the `pf3d-bi-*` images/volumes afterwards.
10. Docs: `docs/architecture.md` — a short "Build info / version page" gotcha (where each component's build info
    comes from, the `/build-info.json` served-volume check). `docs/decisions.md` entry (newest at top).

## When done

1. Frontmatter; move this file (plain `mv`, it's untracked) to `prompts/done/` or `prompts/failed/`.
2. Do **not** commit. Report files changed, endpoint shapes, smoke results, and gate results.
