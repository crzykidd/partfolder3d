# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** This is the **live-state handoff** — a
current, limited view so a new session can orient fast, then go deeper via the docs it points
to. It is NOT a full reference: durable rules live in `CLAUDE.md`, the module map + gotchas in
`docs/architecture.md`, history in `CHANGELOG.md` / `docs/decisions.md`. Keep it LEAN; refresh
"Current state" before every `/clear`.

**Last updated:** 2026-07-03 — **v0.3.0 released** on `main`; audit-remediation batch landed on `dev` (unreleased).

## Current state

- **Latest release: `v0.3.0`** (tagged, GitHub release live). The full app is built and shipping
  (identity, libraries + atomic-move storage, import wizard + bulk import, catalog, item pages with
  3D viewer + object breakdown, reconcile, print history + sharing, AI tagging, admin, worker
  resource limits). Feature detail: `CHANGELOG.md`.
- **`dev` is now AHEAD of `main`:** a two-round **audit-remediation** batch shipped on `dev`
  (`docs/audit-2026-07-03.md` is the worklist, ~83/93 done). Round 1 = docs/PRD/Claude-ergonomics;
  round 2 = the security cluster (SSRF, XSS, authz, Redis auth + nginx headers + DB-fail-fast + CORS +
  CI pinning, exception hygiene, data-safety), operational hygiene (crash recovery + reclamation cron),
  and the file-split refactors (items→package, catalog/imports pages, commit.py, issue_action).
  Deferred items + rationale are in `docs/decisions.md`.
- **`[Unreleased]` has a batch of Security/Fixed entries** ready for the next release. ⚠️ **Release
  deploy note:** the arq job serializer changed pickle→JSON — **drain the worker queue across that
  upgrade** (in-flight pickled jobs won't deserialize; queue is normally empty). Also new opt-in knobs
  to surface in release notes: `REDIS_PASSWORD`, `TRASH_RETENTION_DAYS`, `ORPHAN_PRINTS_DELETE`,
  `SCRAPE_IMAGE_MAX_MB`/`SCRAPE_HTML_MAX_MB`; and prod now **fails fast on a `changeme` DB password**.
- **Next release:** `/release-prep <next>` → merge PR (clean) → `:latest` publishes → `/release-cut <next>`.
  Likely a minor (broad security batch) — owner's call. **We do NOT archive old changelog series** (owner preference).

## How we work (recap — full rules in `CLAUDE.md`)

- Central **Opus planning session**: plan, write handoff prompts in `prompts/`, dispatch **Sonnet
  subagents** to execute, report back. Owner doesn't babysit. Bigger than ~1–2 files → handoff prompt.
- **Auto-commit on `dev`** with conventional prefixes; **`main` is PR-only, never direct-push.** Use
  `closes #N` so issues auto-close. Every feat/fix commit updates `CHANGELOG.md [Unreleased]` in the
  same commit.
- **Live-iteration caveat:** the owner runs the **vite dev server on this repo**, so inline edits
  hot-reload into their live app. For bigger changes while they test, dispatch to an **isolated
  worktree** (Agent `isolation: worktree`).
- **Verify + gotchas are NOT here anymore.** Verify discipline lives in `CLAUDE.md` +
  `scripts/verify-*.sh` (`make verify`); the load-bearing technical gotchas (render backend, 3MF,
  modals, worker-no-hot-reload, CI shape, merge-dup-symbols) live in `docs/architecture.md`.

## Backlog (themes only — full list + current scope: `gh issue list`)

GitHub issues are the source of truth for what we're building **now** (not the PRD). Current threads:
- **Job visibility:** #20 (queued jobs invisible), #30 (`analyze_item` creates no Job row) — fix together.
- **Scraper:** #23 (FlareSolverr alt — planned, `prompts/2026-07-03-23-flaresolverr.md`), #28 (full-res vs Printables og:image).
- **Libraries:** #25 (move assets between libraries). **Import wizard:** #26 (render-capture), #27 (URL-import cleanup). **Tags:** #31 (auto-approve pending).

## Session start order

1. **This file** — live state + what's in progress.
2. **`CLAUDE.md`** — operating rules + verify discipline.
3. **`docs/architecture.md`** — where things live (module map) + load-bearing gotchas.
4. **`docs/audit-2026-07-03.md`** — the current worklist.
5. **`docs/decisions.md`** (newest-first ADR log) + **`CHANGELOG.md`** — the detailed look-back.

## Repo, remotes, environment (quick-start)

- **Code:** GitHub [`crzykidd/partfolder3d`](https://github.com/crzykidd/partfolder3d). `main` protected
  (PR-only, 6 required CI checks). Work on `dev`. `gh` authed as `crzykidd`.
- **Run:** `cp .env.example .env` then `docker compose -f docker-compose.dev.yml up --build` (dev) or
  `docker compose up -d --build` (prod) → http://localhost:8973 first-run wizard. Migrations auto-run via
  the backend image entrypoint. External port **8973** (nginx).
- **No sandbox here** — bash may prompt unless auto-approve is on. **System Python is PEP-668** (pip
  blocked); a scratchpad venv exists for image work — recreate if gone.

## Before-`/clear` checklist

1. Update **Last updated** + **Current state** (release, `dev` vs `main`, what's in progress).
2. Refresh **Backlog** *themes* — `gh issue list` is the source of truth; don't enumerate.
3. Ensure in-flight `prompts/` frontmatter + `done|failed/` placement is right; record decisions in
   `docs/decisions.md`.
4. Confirm work is committed on `dev` (note anything intentionally uncommitted).
