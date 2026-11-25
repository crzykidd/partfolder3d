# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** This is the **live-state handoff** — a
current, limited view so a new session can orient fast, then go deeper via the docs it points to.
It is NOT a full reference: durable rules live in `CLAUDE.md`, the module map + gotchas in
`docs/architecture.md`, history in `CHANGELOG.md` / `docs/decisions.md`. Keep it LEAN; refresh
"Current state" + "Next phases" before every `/clear`.

**Last updated:** 2026-11-25 — **`v0.9.0` RELEASED** (latest). Tag `v0.9.0` cut on `main`,
GitHub release published, `release`-triggered image build **succeeded** (`:latest`/`:0.9.0`/`:0`
for backend, frontend, nginx). README security callout followed via docs PR #52 (merged).
`dev` == `main` in content (main is 2 merge commits ahead; nothing unreleased).

> **⏭️ NO RELEASE IN FLIGHT, no forced next task.** Next pickup is an owner **choice**. Open issue:
> **[#41](https://github.com/crzykidd/partfolder3d/issues/41)** ACME at nginx. Strongest candidates are
> the **remaining security-audit tasks** (see Next phases): **#1 weekly rebuild + trivy in CI** (needs
> owner answer: may a scheduled rebuild republish `:latest` without a release?) and **#2b
> fastapi/starlette bump** (medium risk, starlette 0.x→1.x).

> **⚠️ DEPLOY NOTE (v0.9.0):** prod must pull `:latest` (or `:0.9.0`) for **all** services and recreate
> them — **including the one-shot `frontend` container** (it copies assets into the `frontend_dist`
> volume; if it doesn't re-run, nginx keeps serving the old UI — this bit the owner today). Migration
> **`0027`** auto-runs on backend start. Then check the **Version page**: every row should show v0.9.0 /
> `release`; a mismatch banner means a stale volume or an un-restarted container. Prod was running the
> `:dev` channel during testing — move it back to `:latest`/`:0.9.0`.

## Current state

- **Latest release `v0.9.0`** (2026-11-25). Full detail: `CHANGELOG.md` `[0.9.0]`, `docs/decisions.md`.
  - **Catalog multi-select + bulk actions** (`feat:`). Select-mode toggle (grid + list), shift-click
    range, selection persists across pages/filters (key→title map). Sticky bar: **Log print** (one
    identical record per item, all-or-nothing, `POST /api/items/bulk-print-records`), **Tags** add/remove
    (`bulk-tags`, same write-through as PATCH), **Move** (existing `POST /api/items/move` — closes the #25
    follow-up), **Rescan** (≤100, inline) and **Delete** (trash, typed confirm). Partial-success
    `{succeeded, failed[]}` for tags/delete/rescan. Single-segment `bulk-*` paths on purpose
    (`/bulk/rescan` would be captured by `/{key}/rescan`). Code: `routers/items/bulk.py`,
    `pages/catalog/{useCatalogSelection.ts,BulkActions.tsx}`, shared `pages/item/PrintRecordFields.tsx`.
    Follow-up fix shipped in-release: never `preventDefault` on the checkbox click (it reverted the native
    toggle — jsdom can't show it; test asserts the click isn't cancelled).
  - **Per-component build info** (`feat:`). CI build-args stamp commit/channel/date into all 3 images;
    `GET /api/version/details` (auth) = backend + worker (worker self-reports to Redis
    `pf3d:build:worker`, 180 s TTL, 1-min heartbeat); nginx serves `/build-info/nginx.json` (baked) and
    `/build-info.json` (**from the served `frontend_dist` volume** — the stale-volume check). Version page
    shows 5 rows + mismatch banner. `GET /api/version` unchanged/public.
  - **Security** (`chore:`) from `docs/security-audit-2026-11-25.md` (audit tasks 2a, 3, 4, 5): Pillow
    13, python-multipart 0.0.34 (reachable path-traversal fix), cryptography 50, lxml 6.1.3, PyYAML,
    CVE floors (PyJWT/certifi/dnspython/anyio); **`backend/requirements-dev.txt`** split (dev tools out
    of the image; CI installs the dev file); base pinned **`python:3.12-slim-trixie`** (forky drops
    `libosmesa6`); frontend prod stage **alpine-only** (821 MB → 15 MB, 0/0); npm in-range update
    (audit 12 → 3, only vitest left). Backend image CRIT 14 → 1 (unreachable no-fix Debian libxml2).
  - **fix: `extract_archives` orphaned `queued` Job rows** — the task used `create_job` instead of
    `claim_or_create_job`; migration **`0027`** supersedes provable orphans (queued row with a later
    extract run for the same item). Gotcha recorded in `docs/architecture.md`.
- **Earlier releases** (`v0.1.1`–`v0.8.1`): `CHANGELOG.md`. Recent — v0.8.1 Keep DB/Keep sidecar
  greenlet fix; v0.8.0 in-app description/tag edit, server-side OpenSCAD render, inline PDF, clear-failed,
  stlflix; v0.7.x OpenSCAD viewer, MakerWorld image fix, built-in TLS, prinnit.
- **Prod deploy facts** (compose in `~/projects/docker-compose/apps/partfolder3d/` on this host,
  deployed elsewhere via Komodo): Traefik ingress (`partfolder3d.crzynet.com`), NFS library,
  `user: 2000:66000`, worker capped `cpus:2 / 6G`. **Verify which build is live via the Version page**,
  or on the host: `docker image inspect <img> --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'`.
- **The dev docker stack on THIS host** is currently **down** (`docker compose -f docker-compose.dev.yml
  {up -d,stop}`); backend/frontend hot-reload, the worker does NOT (`make worker-restart`).
- **Local venv was rebuilt 2026-11-25** — host system Python moved 3.12 → **3.14**, which broke the old
  venv's interpreter symlink. Recreate with:
  `uv venv --python 3.12 backend/.venv && uv pip install --python backend/.venv/bin/python -r backend/requirements-dev.txt`.
- **CI vs local gotcha (recurring):** local vitest can flake under host load (`waitFor` timeouts, no
  real failures) — re-run the named files with `--no-file-parallelism`; CI is authoritative. (Today's
  runs were all clean.) Note `CI` runs on **pull_request only**; push-to-`main` runs only the publish.

## Next phases (roadmap)

- **Remaining security-audit tasks** (`docs/security-audit-2026-11-25.md` §5):
  - **#1 Weekly rebuild + trivy scan in CI** — highest leverage (stale images were the main CVE source).
    **Owner decision needed:** may a scheduled rebuild republish `:latest` without a release?
  - **#2b fastapi/starlette (+uvicorn) bump** — medium risk (starlette 1.x removed deprecated APIs;
    check `on_event`, `TemplateResponse` arg order, `request.form()` limits on upload routes). Clears the
    remaining starlette HIGHs. Full verify + built-image upload/render smoke.
  - #6 (opt) vitest 5 major (dev-only; clears last 2 npm crits). #7 (opt, later) PyPI `vtk` ≥9.7 over EGL
    replacing `vtk-osmesa` (unblocks Py 3.13 / post-trixie; audit proved stock vtk renders headless — the
    Dockerfile/requirements comments saying otherwise are stale). #8 (opt) headless OpenSCAD build
    (−8 HIGH, −180 MB; agent couldn't measure — external source compile blocked by permissions).
  - postgres:16-alpine carries 1/26 from upstream `gosu` (17/18 identical) — nothing to do but watch.
- **Automatic Let's Encrypt/ACME at nginx** ([#41](https://github.com/crzykidd/partfolder3d/issues/41)).
- **Other bulk actions** not yet built: bulk **set creator**, bulk **export/download**; "select all
  matching filter" (server-side) was deliberately skipped.
- **Deferred v0.8.0 follow-ups:** refresh a `.3mf`'s embedded thumbnail on in-place edit (route via
  `_enqueue_analyze`); manual "re-render `.scad`" button; optionally subprocess-isolate
  `validate_model_file`'s STL/OBJ/PLY path.
- **Small polish noticed:** print-record form labels aren't linked to inputs (a11y, pre-existing);
  nav shells show plain version only (could append short sha on non-release channels).
- **Next release:** `/release-prep 0.9.1` (patch) or `0.10.0` (feature batch). Standing gotchas: CodeQL
  path-injection FPs on `routers/downloads.py` (dismiss, matching #3/#4/#5/#37/#62/#63); never pipe
  `make verify` (masks exit code) — run it in a background task writing to a log.

## How we work (recap — full rules in `CLAUDE.md`)

- Central **Opus planning session**: plan, write handoff prompts in `prompts/`, dispatch **Sonnet
  subagents** to execute, report back. Owner doesn't babysit. Bigger than ~1–2 files → handoff prompt.
- **Auto-commit on `dev`** with conventional prefixes; **`main` is PR-only, never direct-push.** Use
  `closes #N` so issues auto-close on merge. Every feat/fix commit updates `CHANGELOG.md [Unreleased]`
  same commit.
- **During active build/test sessions the owner wants each verified item committed AND pushed to `dev`**
  so pushing rebuilds the `:dev` images and the owner's on-host stack + testers can pull. Gate each
  push on `make verify` (full backend suite + fresh frontend build/vitest).
- **Spawned-agent orchestration (learned the hard way):** tell agents to run **only** fast DB-free
  checks (ruff / tsc) and **never** the full `make verify` / `pytest` gate — a second concurrent
  pytest corrupts the single shared ephemeral test PG (`pf3d-pg-v`). The orchestrator runs ONE
  authoritative gate and finalizes (kill orphans, `docker rm -f pf3d-pg-v`, verify with no pipe,
  commit, push). Concurrent agents are safe only on **disjoint files with disjoint gates** (e.g.
  frontend vs backend) and told to skip CHANGELOG/docs (orchestrator adds those at commit).
- **Flag genuine design forks** for the owner instead of guessing; verify diagnoses on the live stack
  before building a fix.
- **Live-iteration caveat:** owner runs the vite dev server / the `:dev` stack on this repo; for bigger
  concurrent changes, an isolated worktree (Agent `isolation: worktree`) avoids stomping — but a fresh
  worktree lacks `.venv`/`node_modules`, so the agent can't run local gates there (orchestrator gates).
- **Verify + gotchas are NOT here.** Verify discipline: `CLAUDE.md` + `scripts/verify-*.sh` (`make
  verify`). Load-bearing gotchas: `docs/architecture.md`.

## Backlog (themes — `gh issue list` is the source of truth for what we build **now**, not the PRD)

- **Open issues:** only [#41](https://github.com/crzykidd/partfolder3d/issues/41) ACME at nginx.
- **Needs owner decision:** audit #1 (scheduled `:latest` republish?); #41 approach; whether the security
  follow-ups / v0.8.0 follow-ups / extra bulk actions get filed as issues.
- Older PRD §18 notes: real slicing for filament estimates, trash-purge UI, `.bgcode`/multi-filament gcode.

## Session start order

1. **This file** — live state + next phases.
2. **`CLAUDE.md`** — operating rules + verify discipline.
3. **`docs/architecture.md`** — where things live (module map) + load-bearing gotchas.
4. **`docs/decisions.md`** (newest-first ADR log) + **`CHANGELOG.md`** — the detailed look-back.
5. **`docs/audit-2026-07-03.md`** — the audit worklist (mostly done; deferrals noted).

## Repo, remotes, environment (quick-start)

- **Code:** GitHub [`crzykidd/partfolder3d`](https://github.com/crzykidd/partfolder3d). `main` protected
  (PR-only, required CI checks). Work on `dev`. `gh` authed as `crzykidd`.
- **Dev stack on THIS host** (when up): `partfolder3d-{backend,worker,db,redis,nginx,frontend,flaresolverr}-1`
  on `:dev` images. `docker logs`/`exec` to diagnose; app DB via `docker exec partfolder3d-db-1 psql -U
  partfolder3d -d partfolder3d`. Separate ephemeral **test** pg: `pf3d-pg-v` on :5433 (pytest only).
  Dev scraper config in DB points at the **shared** FlareSolverr (`https://flaresolverr.crzynet.com/`).
- **Stale-network recovery:** if `up` leaves containers stuck in `Created` with
  `failed to set up container networking: network <id> not found`, run
  `docker compose -f docker-compose.dev.yml down --remove-orphans` then `up -d` — always `down` before
  `up`, never `up` onto a half-running stack.
- **Run from scratch:** `cp .env.example .env` → `docker compose -f docker-compose.dev.yml up --build`
  (dev) or `docker compose up -d --build` (prod) → http://localhost:8973 first-run wizard. Migrations
  auto-run via the backend entrypoint. External port **8973** (nginx).
- **No sandbox here** — bash may prompt unless auto-approve is on. **System Python is PEP-668** (pip
  blocked); `backend/.venv` exists and runs repo code directly.

## Before-`/clear` checklist

1. Update **Last updated** + **Current state** + **Next phases** (release cut? `dev` vs `main`?).
2. Refresh **Backlog** themes — `gh issue list` is the source of truth; don't enumerate.
3. Ensure in-flight `prompts/` frontmatter + `done|failed/` placement is right; record decisions in
   `docs/decisions.md`.
4. Confirm work is committed **and pushed** on `dev` (note anything intentionally unpushed).
