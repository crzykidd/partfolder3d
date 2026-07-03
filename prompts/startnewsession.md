# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** This is the fast-moving **live state** that
doesn't belong in `CLAUDE.md` (durable rules) or `CHANGELOG.md` / `docs/decisions.md` (detailed
history). **Keep it LEAN** — enough to orient a new session, not a log. Refresh "Current state" +
"Backlog" before every `/clear`.

**Last updated:** 2026-07-03 — **v0.3.0 released** on `main`; `dev` == `main`, no release gate open.

## Current state

- **Latest release: `v0.3.0`** (tagged, GitHub release live). `dev` == `main`, nothing queued.
- The full app is built and shipped: identity/first-run, libraries + storage (atomic moves), import
  wizard + **bulk import**, catalog, item pages (**file management**, **3D viewer + capture**, object
  breakdown with live **job status**), reconcile engine, print history + sharing, AI tagging, admin
  (libraries, jobs, reviews, backups), and **worker resource limits**. Feature-level detail lives in
  `CHANGELOG.md`; non-obvious decisions in `docs/decisions.md`.
- **Next release:** `/release-prep <next>` → merge PR (clean) → `:latest` publishes → `/release-cut <next>`.
  Likely a patch (`0.3.1`) unless scope grows. **We do NOT archive old changelog series** (owner preference).

## How we work (recap — full rules in `CLAUDE.md`)

- Central **Opus planning session**: plan, write handoff prompts in `prompts/`, dispatch **Sonnet
  subagents** to execute, report back. Owner doesn't babysit.
- **Bigger than ~1–2 files → handoff prompt + dispatched agent** (memory: dispatch-don't-inline). Trivial
  edits inline.
- **Auto-commit on `dev`** with conventional prefixes; **`main` is PR-only, never direct-push.** Use
  `closes #N` in the commit/PR body so issues auto-close on merge (memory: use-closes-keyword).
- **Every feat/fix commit updates `CHANGELOG.md [Unreleased]` in the same commit** (memory: changelog-every-commit).
- **Live-iteration caveat:** the owner runs the **vite dev server on this repo**, so inline edits hot-reload
  into their live app (and can flash broken mid-edit). For bigger changes while they're testing, dispatch to
  an **isolated worktree** (Agent `isolation: worktree`) so their view isn't disturbed.

## Verify discipline (before committing)

- **Backend lint:** `backend/.venv/bin/ruff check backend/` (pinned ruff **0.8.4** + `backend/pyproject.toml`).
- **Backend tests need Postgres** (spawned agents have none). Ephemeral: `docker run -d --name pf3d-pg-v
  -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p 5433:5432
  postgres:16-alpine`; conftest defaults to it. **Serial runs REUSE the DB** (committed rows accumulate →
  spurious count failures) — validate like CI with **`pytest -n N`** (xdist drops+creates a fresh DB per
  worker). Full suite ≈ **658**; migrations at **0022**.
- **Frontend:** `npm run build` (`tsc -b && vite build`) — NOT `npx tsc --noEmit` (misses strict errors) —
  plus `npx vitest run` (≈ **333**). Stack = Tailwind + CSS-var theme + minimal Radix + lucide + TanStack
  Query + apiFetch CSRF; **no Mantine, no toast lib.**
- **Worker has NO hot-reload** (dev worker = `python worker.py`); restart it after worker/task/scraper edits.
- **Batch of fixes:** scope each agent's tests to touched code; run the full suite once at the end
  (memory: batch-fix-testing).

## Load-bearing gotchas

- **Release CI shape — don't break it.** `main` required checks bind by **BARE job name** (`Lint`, `Test`,
  `Migration check`, `Compose validation`, `Config validation`, `Image build`) = the `ci.yml`
  `pull_request:[main]` jobs — **don't rename ci.yml jobs.** `dev-checks.yml` = fast non-required checks on
  `push:[dev]` ("(dev)" suffix; lint runs here — it caught a real F811 dupe). `publish.yml` = 3-image matrix
  on push:main + release. **CodeQL is NOT a required check** (doesn't block merge) but flags real issues on
  release PRs — **fix the real ones, dismiss FPs** via the code-scanning API (`gh api ... /alerts/N -f
  state=dismissed`, comment ≤ 280 chars). Done for v0.2.5 and v0.3.0.
- **Merging two branches that touch the same feature:** a clean text-merge is NOT enough — both may add the
  same symbol/route (bit us: duplicate `/{key}/jobs` endpoint + `ItemJobOut`/`ItemJobSummary`). After
  merging, **grep for duplicate symbols/routes and run a FRESH full build** — worktree agents' `tsc -b`
  incremental cache HID the error.
- **Render backend:** headless render uses the **`vtk-osmesa`** wheel + `libosmesa6` (NOT stock PyPI vtk =
  X11-only). Only verifiable in a **built image**. 3MF is read-not-rendered (embedded thumb + browser
  capture); all-3MF items skip server render.
- **Fixed modals must portal to `<body>`** — Aurora cards use `backdrop-filter`, which traps a
  `position:fixed` child inline (bit the 3D viewer + description modal).
- **Worker resource limits (v0.3.0):** `WORKER_MAX_JOBS` / `RENDER_CONCURRENCY` / `ANALYZE_CONCURRENCY` env
  + compose `WORKER_CPUS` / `WORKER_MEM_LIMIT` caps — small defaults so a bulk import can't overrun the host.
  To recover a wedged stack: bring it up **without the worker** (`docker compose -f docker-compose.dev.yml
  up -d db redis backend frontend nginx`), then start the worker with the caps.

## Backlog (themes only — full list: `gh issue list`)

Deliberately not exhaustive here. Current open threads by theme:
- **Job visibility:** #20 (queued jobs invisible until worker starts them), #30 (`analyze_item` creates no
  Job row → invisible CPU/RAM).
- **Scraper:** #23 (FlareSolverr as an AgentQL alternative — planned, `prompts/2026-07-03-23-flaresolverr.md`),
  #28 (prefer full-res over Printables `og:image`).
- **Libraries:** #25 (move assets between libraries — the deferred half of #11).
- **Import wizard:** #26 (wizard "Try to render file" capture, deferred from #21), #27 (URL-import wizard
  cleanup: title/desc/tags/creator/empty-review/zero-file commit).
- **Tags:** #31 (auto-approve pending tags).
- Older PRD §18 notes: real slicing for filament estimates, trash-purge UI, `.bgcode`/multi-filament gcode.

## Session start order

1. **This file** — current state + gotchas.
2. **`CLAUDE.md`** — operating rules + adopted-standard snippets.
3. **`standards.md`** — which standards/versions apply.
4. **`docs/decisions.md`** (newest-first ADR log) + **`CHANGELOG.md`** — for the detailed look-back.

## Repo, remotes, environment

- **Code:** GitHub [`crzykidd/partfolder3d`](https://github.com/crzykidd/partfolder3d). `main` protected
  (PR-only, 6 required CI checks). Work on `dev`. `gh` authed as `crzykidd`.
- **Registry:** `homelab-configs` on Gitea (`gitea.crzynet.com`) — separate repo (`projects/partfolder3d/`).
- **No sandbox here** — bash may prompt unless the session runs auto-approve. **System Python is PEP-668**
  (pip blocked); a scratchpad venv (Pillow/numpy/scipy/pyyaml) exists for image work — recreate if gone.
- **Run:** `cp .env.example .env` then `docker compose -f docker-compose.dev.yml up --build` (dev) or
  `docker compose up -d --build` (prod) → http://localhost:8973 first-run wizard. Migrations auto-run via
  the backend image entrypoint (no separate `migrate` container — owner rejected it).
- **Owner prod:** NFS (uid 2000 / gid 66000), behind https `partfolder3d.crzynet.com`, `COOKIE_SECURE=true`.
- **Brand:** teal `#0FA4AB`, navy `#091D35`; external port **8973** (nginx).

## Key file map

| Path | What |
|---|---|
| `PRD.md` | Authoritative product spec (§1–18). |
| `CHANGELOG.md` · `docs/decisions.md` | Detailed history · ADR log (the look-back lives here, not this file). |
| `CLAUDE.md` · `standards.md` | Operating rules · adopted standards + pinned versions. |
| `docs/build-plan.md` | Phased roadmap + locked build-time tech decisions. |
| `prompts/` | Handoff queue; `prompts/done/` + `prompts/failed/` archives. |
| `.claude/commands/release-{prep,cut}.md` | Release slash commands (proven through v0.3.0). |
| `.github/workflows/` | `ci` (required PR gate) · `dev-checks` · `publish` · `codeql` · retention. |

## Before-`/clear` checklist

1. Update **Last updated** + **Current state** (release, `dev` vs `main`, any open release gate).
2. Refresh **Backlog** *themes* — don't list every issue; `gh issue list` is the source of truth.
3. Ensure any in-flight `prompts/` frontmatter + `done|failed/` placement is right; record decisions in
   `docs/decisions.md`.
4. Confirm work is committed on `dev` (note anything intentionally uncommitted).
