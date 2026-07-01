---
name: 2026-06-27-phase-9-admin-backup-export-api
status: completed
created: 2026-06-27
model: sonnet            # coding against a locked plan
completed: 2026-06-27
result: "Phase 9a backend complete: in-process backup (db+secret.key tar.gz), JSON export, tag admin (aliases/categories/merge/approve), site-caps admin, API parity; split to 9b for frontend"
---

# Task: Phase 9 — Admin, backup, export, API completeness

Round out the admin surface: **reindex**, **scheduled DB+config backup** with retention,
**JSON catalog export**, **tag administration** (aliases/categories/merge + the existing
approval queue), **site-capabilities management**, **full REST API parity + per-user API-key
UI**, and **OpenAPI polish**. This is **Phase 9** of [`docs/build-plan.md`](../docs/build-plan.md)
and PRD **§13** (admin) + **§15** (API).

**Exit criteria (build plan):** admin can back up, export, manage tags/sites/users; the API
covers all UI actions.

## Before you start

- Read [`docs/build-plan.md`](../docs/build-plan.md) **Phase 9** + the **Locked build-time
  technical decisions**.
- Read [`PRD.md`](../PRD.md): **§13 Admin Features** (reindex; **scheduled backup of DB + config
  only**, cron schedule + retention count, target under `./data/backups`, with a **prominent UI
  callout that library files are NOT backed up** — the user owns that; JSON export of the whole
  catalog; user management; invites; tag administration = approval queue/aliases/categories/
  merges; site-capabilities management; settings), **§15 API** (full REST parity; per-user API
  keys managed in settings; OpenAPI/Swagger auto-docs).
- Read [`CLAUDE.md`](../CLAUDE.md) operating rules and [`docs/decisions.md`](../docs/decisions.md).
- **READ THE MEMORY/LESSON: deployment readiness is part of the work.** Several prior phases
  shipped code that crashed when the stack was actually run (worker startup, missing migrations,
  Secure cookies over http). **Anything you add must actually work in the running container**, not
  just in unit tests. Specifically for this phase: **`pg_dump` is NOT in the image** (python:3.12-
  slim) — a backup job that shells out to `pg_dump` will fail at runtime. If you implement DB
  backup via `pg_dump`, you MUST add the matching client to the `Dockerfile` (`postgresql-client-16`
  from the PGDG apt repo — Debian's default client is v15 and may refuse to dump a v16 server), and
  verify it. If that's too heavy, use a robust in-process dump (SQLAlchemy → SQL/JSON) and say so.
- **Read the existing code you will build on / reuse:**
  - `backend/worker.py` + `SCHEDULED_JOB_REGISTRY` + the Phase 4 scheduled-job framework
    (cron + run-now). The backup + reindex are scheduled jobs; reindex reuses the Phase 6
    `library_reconcile_scan`.
  - `backend/app/models/{tag.py (Tag/TagAlias/TagStatus), api_key.py, setting.py, site_capability.py}`.
  - `backend/app/routers/{tags.py, api_keys.py, settings.py, scheduled_jobs.py, import_sessions.py}`
    and `backend/app/auth/deps.py` (`get_current_user` already accepts a session cookie OR a
    Bearer API key — confirm API-key auth works across routers).
  - `backend/app/storage/keys.py` (the instance encryption key under `DATA_DIR/config/secret.key`
    — part of what "config backup" must capture).
  - Frontend `frontend/src/pages/admin/*`, `frontend/src/lib/api.ts`, routing, `AppShell.tsx`.

## Working tree check

`git status --porcelain` — expect a clean tree on `dev` (only this prompt untracked). Surface
anything unexpected. Latest commits are the Phase 8 + deploy-readiness fixes.

## Scope & split guidance

**Large — plan to split.** Do the **backend (9a) first and completely**; the **frontend (9b)**
(backup/export/reindex admin UI, tag-admin UI, site-capabilities UI, API-keys settings UI) may
split to `2026-06-27-phase-9b-*.md`. If the backend is a clean full pass but the frontend won't
fit, **STOP after the backend, write the 9b handoff, and report.** Mirror Phases 5–8.

**Out of scope (Phase 10):** broad test-coverage pass, security review, perf-at-100k, the
actual release cut. Do NOT cut a release or push to `main`.

## What to do

### 1. Backup (DB + config) — scheduled + run-now + retention
- A **backup job** that writes a timestamped archive under **`/data/backups/`** containing the
  **database dump + instance config** (at minimum `config/secret.key` and the `settings` table;
  a full `pg_dump` covers the DB). **Library files are explicitly NOT included.**
- **Retention:** keep the most recent N (a configurable count setting); prune older ones.
- Register as a **scheduled job** (configurable cron; reuse the Phase 4 framework) **and**
  run-now-able. Record each run (a Backup model or reuse Job/ChangeLog) with path, size, status.
- **Runtime requirement (see "Before you start"):** ensure the dump tool actually exists in the
  image and verify a backup file is produced. If using `pg_dump`, add `postgresql-client-16` to
  the Dockerfile and confirm; otherwise use an in-process dump and document the trade-off.

### 2. JSON export
- Admin endpoint to **export the entire catalog as JSON** (items, tags, creators, files/images
  metadata, print records, etc. — not the binary files). Streamed if large.

### 3. Reindex
- Admin trigger for a **full library scan/reindex** — reuse the Phase 6 `library_reconcile_scan`
  run-now path (likely just an endpoint/button, not new engine code).

### 4. Tag administration
- Backend for **aliases** (CRUD: map source/alt strings → canonical Tag), **categories/
  namespaces** (set/edit a tag's category), and **merge** (merge tag B into A: repoint ItemTags
  + aliases, delete B). Plus the existing **approval queue** (`TagStatus.pending` → approve).
  Keep operations safe + idempotent; update FTS/search vectors where needed.

### 5. Site-capabilities management
- Admin CRUD over `SiteCapability` (list per-domain flags; set token / mark manual-only;
  re-probe). The Phase 5 model + token-encryption exist — add the admin API.

### 6. Full REST API parity + per-user API keys
- **Audit** that every UI action has a REST endpoint; fill gaps. Confirm **Bearer API-key auth**
  works on the API (reuse `get_current_user`). Add the **per-user API-key management** API
  (create → returns the raw key once, list, revoke) if not already complete.
- **OpenAPI polish:** ensure routers have tags/summaries/descriptions so `/api/docs` is coherent.

### 7. API (admin/authenticated; reuse Phase 1 auth deps)
- Backup: list/trigger/configure retention; download a backup. Export: trigger/download.
  Reindex: trigger. Tag admin: alias/category/merge/approve. Site-caps: list/update.
  API keys: create/list/revoke. All admin-gated except API-key self-management (per-user).

### 8. Frontend — MAY SPLIT TO 9b
- Admin pages: **Backups** (list, run-now, retention setting, restore is out-of-scope unless
  trivial, + the LOUD "your library files are NOT backed up — own your backup strategy" callout),
  **Export** (download JSON), **Reindex** (button + job status), **Tag administration**
  (aliases/categories/merge/approve), **Site capabilities** (list/edit/token). **Settings → API
  keys** (create/copy-once/revoke). `npx tsc --noEmit` clean; vitest for non-trivial logic.

## Conventions to honor

- Match locked decisions + existing Phase 0–8 structure; reuse the scheduled-job framework,
  reconcile engine, tag/alias models, api-key model, settings, crypto, and auth.
- **It must work in the running stack**, not just tests (see the deployment-readiness lesson).
- Secrets stay encrypted/out of the repo; backups may contain secrets (secret.key) — they live
  under `/data` (gitignored), never in the image or repo.
- **UI stack (for any 9b frontend / your 9b handoff): Tailwind + CSS-variable (shadcn-style)
  theme + minimal Radix (react-dropdown-menu/react-slot only) + lucide-react + TanStack Query +
  the `apiFetch`/`apiFetchForm` CSRF wrapper. NO Mantine, NO toast library.** State this in the
  9b handoff.
- Verify locally what you can: `ruff check backend/`, `pytest`, `npx tsc --noEmit`, `vitest`,
  `alembic upgrade head` + `downgrade base`, `docker compose -f docker-compose.dev.yml config
  --quiet`. **Bring up an ephemeral Postgres** for the migration + DB tests:
  `docker run -d --name pf3d-test-pg -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p 5433:5432 postgres:16-alpine`
  then `export DATABASE_URL="postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d"`,
  run `alembic upgrade head && alembic downgrade base && alembic upgrade head`, then `pytest`.
  Recreate the scratchpad venv at
  `/tmp/claude-1000/-home-manderse-projects-partfolder3d/bd4b77b1-dcc4-4fbf-8dc0-d3990161f59a/scratchpad/venv`
  if gone (PEP-668; pip-install requirements.txt incl. python-multipart/anthropic/openai + ruff/
  pytest). If a backup uses `pg_dump`, also verify the dump command runs (the test PG container
  has `pg_dump` you can point at, or test the in-process dump). Tear the container down when done.

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-27`, one-line `result`).
2. `git mv` into `prompts/done/`; **if you split, write the 9b handoff** with the UI-stack note.
3. Add `docs/decisions.md` entries (newest at top): backup format + dump tool choice (+ any
   Dockerfile change), retention approach, JSON export shape, tag merge/alias/category model,
   API-key management approach, API-parity audit result.
4. **You are a spawned agent: do NOT commit, push, or change branch.** Prepare the tree and
   **report back** with: complete file list; proposed one-line `feat:` commit message; exact
   local check results (incl. ephemeral-PG migration round-trip + pytest count, and proof the
   backup actually produces a file in the running image / a note on what needs the Docker image);
   full-phase vs split (+ 9b path + remaining); any decision/limitation.
