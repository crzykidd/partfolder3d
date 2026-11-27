# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** This is the **live-state handoff** — a
current, limited view so a new session can orient fast, then go deeper via the docs it points to.
It is NOT a full reference: durable rules live in `CLAUDE.md`, the module map + gotchas in
`docs/architecture.md`, history in `CHANGELOG.md` / `docs/decisions.md`. Keep it LEAN; refresh
"Current state" + "Next phases" before every `/clear`.

**Last updated:** 2026-11-27 — **`v0.10.0` RELEASED** (latest). PR #53 merged, tag `v0.10.0` cut on
`main`, GitHub release published, `release`-triggered image build **succeeded** (`:latest`/`:0.10.0`/`:0`
for backend, frontend, nginx). `dev` == `main` in content (nothing unreleased).

> **⏭️ NO RELEASE IN FLIGHT, no forced next task.** Next pickup is an owner **choice**. Open issue:
> **[#41](https://github.com/crzykidd/partfolder3d/issues/41)** ACME at nginx. Security audit's required
> work is **done** (2b shipped in v0.10.0); remaining audit items are **#1** (needs owner decision) and
> optional #6–#8 — see Next phases.

> **⚠️ DEPLOY NOTE (v0.10.0):** prod must pull `:latest` (or `:0.10.0`) for **all** services and recreate
> them — **including the one-shot `frontend` container** (it copies assets into the `frontend_dist`
> volume; if it doesn't re-run, nginx keeps serving the old UI). Migration **`0028`** (printer_profiles)
> auto-runs on backend start. Then check the **Version page**: every row v0.10.0 / `release`, no mismatch
> banner. Owner should smoke **uploads** (Add Asset, import wizard) on prod — starlette 1.x changed form
> parsing (built-image smoke passed: 200 MB multipart OK, Range → 206).

## Current state

- **Latest release `v0.10.0`** (2026-11-27). Full detail: `CHANGELOG.md` `[0.10.0]`, `docs/decisions.md`.
  - **Printer profiles** (`feat:`). Per-user named presets of the six print-record settings fields
    (printer, material, filament color, nozzle, layer height, supports); optional single **default**
    (partial unique index `WHERE is_default` + API clears others in the same txn). Migration **`0028`**,
    `models/printer_profile.py`, `routers/printer_profiles.py` → `/api/me/printer-profiles` (CRUD, scoped to
    current user → foreign id 404, dup name 409). UI: `pages/settings/PrinterProfilesSection.tsx` (Settings,
    after path prefixes); `PrintRecordFields.tsx` gets **"Load from profile"** select (copies non-null
    fields only) + **"Save as profile"** inline mini-form (not a nested `<form>`). Default auto-fills
    **new** forms only (`applyDefaultProfile` prop: `!existing` in `PrintHistory`, always in bulk dialog),
    once, and only while all six fields are blank.
  - **Printed-before catalog badge** (`feat:`). `ItemSummary.print_count` (+ legacy `has_print_record`)
    from one grouped COUNT; lucide `Printer` between the files `Box` badge and the star; tooltip
    "Printed N time(s)" (`printedLabel` in `lib/catalog-utils.ts`). **Visibility mirrors
    `list_print_records`:** any authenticated user counts all records (private only hides from anonymous
    share viewers); anonymous callers count public only.
  - **Cancel queued jobs / manage superseded / auto-supersede stale queued rows** (`fc0e931`,
    `STALE_QUEUED_JOB_HOURS`, default 24, only when the arq task is gone).
  - **Security — audit task 2b** (`chore:`): fastapi 0.165.0, starlette 1.10.0 (floor `>=1.3.1`),
    uvicorn 0.54.0. No removed-API usage; renamed `HTTP_422_UNPROCESSABLE_ENTITY` →
    `HTTP_422_UNPROCESSABLE_CONTENT` (22 files). pip-audit on runtime reqs: **0** (vtk-osmesa unauditable,
    not on PyPI). Code-scanning #61 (`py/log-injection`, agentql.py, admin-only `%r`) **dismissed** as FP.
- **Earlier releases** (`v0.1.1`–`v0.9.0`): `CHANGELOG.md`. Recent — v0.9.0 catalog multi-select + bulk
  actions, per-component build info, security refresh; v0.8.x in-app edit, server-side OpenSCAD render,
  inline PDF, stlflix.
- **Prod deploy facts** (compose in `~/projects/docker-compose/apps/partfolder3d/` on this host,
  deployed elsewhere via Komodo): Traefik ingress (`partfolder3d.crzynet.com`), NFS library,
  `user: 2000:66000`, worker capped `cpus:2 / 6G`. **Verify which build is live via the Version page**,
  or on the host: `docker image inspect <img> --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'`.
- **The dev docker stack on THIS host** is currently **down** (`docker compose -f docker-compose.dev.yml
  {up -d,stop}`); backend/frontend hot-reload, the worker does NOT (`make worker-restart`). Owner tested
  the v0.10.0 features on `:dev` before release.
- **Local venv** is Python 3.12 (host system Python is 3.14). Recreate if broken:
  `uv venv --python 3.12 backend/.venv && uv pip install --python backend/.venv/bin/python -r backend/requirements-dev.txt`.
- **Dependabot alerts are DISABLED** on the repo — dependency checks are local only:
  `uvx pip-audit -r backend/requirements.txt` and `(cd frontend && npm audit)`. (Owner could enable it in
  Settings → Code security.) npm audit = 3 (vitest/tinypool/@vitest/mocker, dev-only → audit #6).
- **CI vs local gotcha (recurring):** local vitest can flake under host load (`waitFor` timeouts) —
  re-run named files with `--no-file-parallelism`; CI is authoritative. `CI` runs on **pull_request
  only**; push-to-`main` runs only the publish.

## Next phases (roadmap)

- **Remaining security-audit tasks** (`docs/security-audit-2026-11-25.md` §5; 2a/2b/3/4/5 done):
  - **#1 Weekly rebuild + trivy scan in CI** — highest leverage (stale images were the main CVE source).
    **Owner decision needed:** may a scheduled rebuild republish `:latest` without a release?
  - #6 (opt) vitest 5 major (dev-only; clears the last npm crits). #7 (opt, later) PyPI `vtk` ≥9.7 over EGL
    replacing `vtk-osmesa` (unblocks Py 3.13 / post-trixie; stale Dockerfile/requirements comments say
    otherwise). #8 (opt) headless OpenSCAD build (−8 HIGH, −180 MB). Minor: starlette's TestClient warns to
    move to `httpx2` eventually.
  - postgres:16-alpine carries 1/26 from upstream `gosu` — nothing to do but watch.
- **Automatic Let's Encrypt/ACME at nginx** ([#41](https://github.com/crzykidd/partfolder3d/issues/41)).
- **Printer-profile follow-ups (not requested yet):** profiles are per-user only (shared/admin profiles
  were an offered option, owner chose per-user); no reorder; badge counts others' private prints for
  logged-in users (offered "own prints only" — owner didn't ask).
- **Other bulk actions** not yet built: bulk **set creator**, bulk **export/download**.
- **Deferred v0.8.0 follow-ups:** refresh a `.3mf`'s embedded thumbnail on in-place edit; manual
  "re-render `.scad`" button; optionally subprocess-isolate `validate_model_file`'s STL/OBJ/PLY path.
- **Small polish:** print-record form labels aren't linked to inputs (a11y); nav shells show plain version
  only (could append short sha on non-release channels).
- **Next release:** `/release-prep 0.10.1` (patch) or `0.11.0`. Standing gotchas: CodeQL path-injection FPs
  on `routers/downloads.py` (dismiss); never pipe `make verify` (masks exit code) — run it in a background
  task writing to a log; **don't `pkill -f pytest` from a command line that itself contains "pytest"** (it
  kills its own shell, exit 144).

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
- **Needs owner decision:** audit #1 (scheduled `:latest` republish?); #41 approach; whether security
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
