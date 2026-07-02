---
name: 2026-07-01-prod-compose-and-readme
status: done
created: 2026-07-01
model: sonnet            # infra + docs
completed: 2026-07-01
result: >
  docker-compose.yml converted to production image-based deploy (build: blocks removed,
  :latest tags, prominent library mount comments, 5-step header). README Getting Started
  rewritten with production-first path + Quick Start callout; Container layout section
  clarified; WARNING banner replaced; roadmap checkbox ticked. CHANGELOG [Unreleased]
  entries added. .env.example production command updated. Both config --quiet pass.
---

# Task: Make docker-compose.yml an end-user production file + explain Docker + link Quick Start in README

Two things: (1) convert `docker-compose.yml` into a **production, end-user** compose that pulls
the published images (no building), structured for a deployer to modify; (2) update `README.md`
to explain the Docker/production setup and point to the in-app Quick Start guide. v0.1.1 is now
released with published images, so the README's "no published image yet / build from source"
framing is stale.

## Before you start
- Read `prompts/startnewsession.md` and `CLAUDE.md`. Spawned agent on `dev`: do NOT push, do NOT
  commit — prepare the tree, report back. Do NOT edit `docs/decisions.md` — report notes back.
- **Changelog rule:** these are user-facing changes → add entries under `## [Unreleased]` in
  `CHANGELOG.md` in the same change (v0.1.1 already shipped, so this is for the next release).
- Read the current files:
  - `docker-compose.yml` — TODAY it has `build:` blocks + `image: ghcr.io/crzykidd/partfolder3d:dev`
    (and `-frontend:dev`). Services: `db` (postgres:16-alpine), `redis`, `backend`, `worker`,
    `frontend`, `nginx`; named volumes `db_data`, `redis_data`, `frontend_dist`. Note how
    `frontend` + `nginx` + `frontend_dist` are wired (the frontend image populates the dist volume
    that nginx serves) and how library mounts + env are declared.
  - `docker-compose.dev.yml` — the self-contained BUILD/dev file (leave it as-is; it stays the
    contributor/dev path).
  - `.env.example` — the env vars (`APP_PORT`, `POSTGRES_PASSWORD`, `DATA_DIR`, `RENDER_*`,
    `JOB_RETENTION_*`, etc.).
  - `README.md` — the `## Getting started` section (currently a stale "Alpha — no published image
    yet" note + a build-from-source block) and the `### Container layout (docker-compose)` section.
  - `frontend/src/pages/settings/QuickStartPage.tsx` + `App.tsx` — the in-app Quick Start guide
    lives at route **`/quick-start`** (visible after first-run login).

## Part 1 — Production `docker-compose.yml`
Convert it to an image-based production deploy the end user edits. **Preserve the existing service
wiring** (backend/worker/frontend/nginx/db/redis, healthchecks, the frontend_dist+nginx serving
mechanism, `RUN_MIGRATIONS=true` on backend, worker gating on backend health) — change only what's
needed to make it production + end-user-editable:
- **Remove all `build:` blocks.** backend + worker → `image: ghcr.io/crzykidd/partfolder3d:latest`;
  frontend → `image: ghcr.io/crzykidd/partfolder3d-frontend:latest`. Add a comment showing how to
  **pin a version** (e.g. `:0.1.1`) and that `:latest` tracks the newest release.
- **Library mounts are the key end-user edit.** Make the library volume mount(s) obvious and
  commented — the user mounts their host library dir into BOTH `backend` and `worker` at the same
  container path, e.g.:
  ```yaml
  #   - /mnt/nas/3dprints:/library/main   # <-- EDIT: your host library dir → container path
  ```
  Then they register that container path (`/library/main`) on the Libraries admin page. Keep a
  sensible default/example mount, clearly marked as "edit me."
- **Env from `.env`.** Keep pulling `POSTGRES_PASSWORD`, `APP_PORT`, etc. from `.env` (via
  `${VAR}` / `env_file` as the file already does). Add a top-of-file comment block: "Production
  deploy — copy `.env.example` to `.env`, set a strong `POSTGRES_PASSWORD`, edit the library
  mount(s) below, then `docker compose up -d`."
- Keep **named volumes** (`db_data`, `redis_data`, `frontend_dist`) for production durability
  (contrast with the dev file's host bind-mounts).
- It must remain valid: `docker compose -f docker-compose.yml config --quiet` passes.

## Part 2 — README Docker + Quick Start
Rewrite `## Getting started` (and touch `### Container layout` if needed) to reflect reality:
- **Remove the stale "Alpha — no published image yet / build from source" NOTE.** v0.1.1 is
  released with images.
- **Primary path = production install** with the published images:
  ```bash
  # 1. Get the compose file + env template (clone, or download docker-compose.yml + .env.example)
  # 2. cp .env.example .env  — set POSTGRES_PASSWORD, APP_PORT
  # 3. Edit docker-compose.yml: mount your library dir(s) into backend + worker
  # 4. docker compose up -d
  # 5. open http://localhost:8973 → first-run wizard
  ```
  Explain briefly: images come from `ghcr.io/crzykidd/partfolder3d(-frontend)`; migrations run
  automatically on the backend entrypoint (no manual step); data lives in named volumes; the
  library mount + Libraries-admin registration is the one required setup step; port is `APP_PORT`.
- **Link the Quick Start guide:** after completing the first-run wizard, point users to the in-app
  **Quick Start** page at **`/quick-start`** (e.g. `http://localhost:8973/quick-start`) for guided
  next steps (add a library, load starter tags, enable AI, schedule backups). Make this a clear
  callout, not buried.
- **Keep a secondary "Build from source (dev)" subsection** for contributors using
  `docker-compose.dev.yml` (the existing block, minus the stale banner).
- If the `### Container layout (docker-compose)` section implies building, clarify that
  `docker-compose.yml` = production (pulls images) and `docker-compose.dev.yml` = dev (builds).

## Part 3 — Changelog
Add `## [Unreleased]` entries (Keep-a-Changelog) — e.g. under `### Changed`:
"`docker-compose.yml` is now a production, image-based deploy (pulls published images; edit library
mounts + `.env`); `docker-compose.dev.yml` remains the build-from-source dev stack." And under
`### Added` if apt: a README production-install guide + link to the in-app Quick Start.

## Verification
- `docker compose -f docker-compose.yml config --quiet` AND
  `docker compose -f docker-compose.dev.yml config --quiet` both pass.
- Markdown: no broken relative links you introduced; the `/quick-start` reference is an in-app
  route (note it's reachable after first-run, not a repo file).
- No code build/tests needed (yaml + docs only).

## When done
1. Update frontmatter (`status`, `completed: 2026-07-01`, `result`).
2. `git mv` into `prompts/done/`.
3. Do NOT edit `docs/decisions.md` — report the note back.
4. Do NOT commit/push. Report: files changed, a summary of the compose + README changes, the
   `[Unreleased]` changelog entries added, the `config --quiet` results, and a one-line
   `docs:`-prefixed (or `chore:`) commit message.
