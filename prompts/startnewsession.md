# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** This is the **live-state handoff** — a
current, limited view so a new session can orient fast, then go deeper via the docs it points to.
It is NOT a full reference: durable rules live in `CLAUDE.md`, the module map + gotchas in
`docs/architecture.md`, history in `CHANGELOG.md` / `docs/decisions.md`. Keep it LEAN; refresh
"Current state" + "Next phases" before every `/clear`.

**Last updated:** 2026-07-05 — **v0.4.0 released to production**; `dev` == `main`; next up = the
Phase 2 owner-decision items below.

## Current state

- **Latest release: `v0.4.0`** (2026-07-05 — tagged, GitHub release live, **deployed to prod**;
  `:latest`/`:0.4.0`/`:0` images published). **`dev` == `main`, nothing queued.** v0.4.0 shipped the
  two-round audit remediation + a big feature/security batch — full list in `CHANGELOG.md [0.4.0]`.
  Headline items: the security cluster (SSRF, `javascript:` XSS, authz, Redis-auth, nginx headers,
  DB-fail-fast, CI SHA-pinning), job visibility (#20/#30), move-between-libraries (#25) + multi-library
  + catalog library filter, auto-approve tags (#31), and the wizard render-capture (#26).
- **The docker stack runs on THIS host** — diagnose live via `docker logs`/`exec` + the app DB
  (`docker exec partfolder3d-db-1 psql -U partfolder3d -d partfolder3d`). Backend routes + frontend
  **hot-reload** from the repo; the **worker does NOT** (restart it after worker/task/scraper edits).

## Next phases (roadmap)

**Phase 1 — cut the release. ✅ DONE (v0.4.0, 2026-07-05)** — the whole dev batch shipped and is in
prod; upgrade caveats (queue drain, DB/Redis passwords, new knobs) are in the `[0.4.0]` CHANGELOG /
GitHub release notes. Next release is `/release-prep <next>` when the next batch is ready. **Release
gotcha to remember:** the CodeQL PR check reports findings against the *changed* code — on a large
diff it surfaces pre-existing/moved alerts too. Fix real log-injections (`sanitize_for_log`), and
dismiss genuine path-injection FPs that already have a `resolve()`+`is_relative_to()` barrier (done
for v0.4.0). CodeQL is non-required but shows the PR red until resolved.

**Phase 2 — owner-decision items (BLOCKED on owner input — don't guess).** All in `docs/decisions.md`:
  - **#27 core fork** — URL import attaches no model file. Pick: (a) auto-fetch the file
    (fragile/login-gated on most sites), (b) add a manual-upload step to the URL wizard, or
    (c) accept metadata-only (the Files-row 0-file warning already ships).
  - **#23 FlareSolverr** — the written prompt (`prompts/2026-07-03-23-flaresolverr.md`) has OPEN
    design questions (Q1/Q5 on the pluggable-scraper-backend UI). Answer those first; also wants a
    live FlareSolverr instance to validate end-to-end.
  - **Bulk move-assets UI** (#25 follow-up) — the backend bulk endpoint is live + tested; the UI needs
    a catalog **multi-select** affordance that doesn't exist yet (a real UX decision).

**Phase 3 — remaining backlog** — `gh issue list` after the above.

## How we work (recap — full rules in `CLAUDE.md`)

- Central **Opus planning session**: plan, write handoff prompts in `prompts/`, dispatch **Sonnet
  subagents** to execute, report back. Owner doesn't babysit. Bigger than ~1–2 files → handoff prompt.
- **Auto-commit on `dev`** with conventional prefixes; **`main` is PR-only, never direct-push.** Use
  `closes #N` so issues auto-close. Every feat/fix commit updates `CHANGELOG.md [Unreleased]` same commit.
- **During active build/test sessions the owner wants each verified item committed AND pushed to `dev`**
  (not just committed) so pushing rebuilds the `:dev` images and the owner's on-host stack + testers can
  pull. Gate each push on `make verify` (full backend suite + fresh frontend build/vitest).
- **Flag genuine design forks** (like #27 core / #23 open questions) for the owner instead of guessing.
- **Live-iteration caveat:** owner runs the vite dev server / the `:dev` stack on this repo; for bigger
  changes while they test, dispatch to an **isolated worktree** (Agent `isolation: worktree`).
- **Verify + gotchas are NOT here.** Verify discipline: `CLAUDE.md` + `scripts/verify-*.sh` (`make verify`).
  Load-bearing gotchas (render backend, 3MF, modals, worker-no-hot-reload, CI shape, merge-dup-symbols):
  `docs/architecture.md`.

## Backlog (themes — `gh issue list` is the source of truth for what we build **now**, not the PRD)

- **Done on `dev`, awaiting release:** #20, #30, #28, #31, #25, #26 (+ #27 partial).
- **Needs owner decision (Phase 2):** #27 core, #23 (FlareSolverr, open Qs), bulk-move UI.
- Older PRD §18 notes: real slicing for filament estimates, trash-purge UI, `.bgcode`/multi-filament gcode.

## Session start order

1. **This file** — live state + next phases.
2. **`CLAUDE.md`** — operating rules + verify discipline.
3. **`docs/architecture.md`** — where things live (module map) + load-bearing gotchas.
4. **`docs/decisions.md`** (newest-first ADR log) + **`CHANGELOG.md`** — the detailed look-back.
5. **`docs/audit-2026-07-03.md`** — the audit worklist (mostly done; deferrals noted).

## Repo, remotes, environment (quick-start)

- **Code:** GitHub [`crzykidd/partfolder3d`](https://github.com/crzykidd/partfolder3d). `main` protected
  (PR-only, 6 required CI checks). Work on `dev`. `gh` authed as `crzykidd`.
- **Live stack on THIS host:** `partfolder3d-{backend,worker,db,redis,nginx,frontend}-1` on `:dev`
  images. `docker logs`/`exec` to diagnose; app DB via `docker exec partfolder3d-db-1 psql -U
  partfolder3d -d partfolder3d`. Separate ephemeral **test** pg: `pf3d-pg-v` on :5433 (pytest only).
- **Run from scratch:** `cp .env.example .env` → `docker compose -f docker-compose.dev.yml up --build`
  (dev) or `docker compose up -d --build` (prod) → http://localhost:8973 first-run wizard. Migrations
  auto-run via the backend entrypoint. External port **8973** (nginx).
- **No sandbox here** — bash may prompt unless auto-approve is on. **System Python is PEP-668** (pip
  blocked); a scratchpad venv exists for image work — recreate if gone.

## Before-`/clear` checklist

1. Update **Last updated** + **Current state** + **Next phases** (release cut? `dev` vs `main`?).
2. Refresh **Backlog** themes — `gh issue list` is the source of truth; don't enumerate.
3. Ensure in-flight `prompts/` frontmatter + `done|failed/` placement is right; record decisions in
   `docs/decisions.md`.
4. Confirm work is committed **and pushed** on `dev` (note anything intentionally unpushed).
