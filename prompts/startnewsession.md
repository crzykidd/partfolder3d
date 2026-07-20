# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** This is the **live-state handoff** — a
current, limited view so a new session can orient fast, then go deeper via the docs it points to.
It is NOT a full reference: durable rules live in `CLAUDE.md`, the module map + gotchas in
`docs/architecture.md`, history in `CHANGELOG.md` / `docs/decisions.md`. Keep it LEAN; refresh
"Current state" + "Next phases" before every `/clear`.

**Last updated:** 2026-07-19 — **`v0.6.0` RELEASED** (Manyfold import; PR #36 merged, tag `v0.6.0`
cut, prod images publishing `:latest`/`:0.6.0`/`:0`). `dev` == `main`. **One open issue: #37**
(worker crash-loops OOM-analyzing large meshes — see below). MakerWorld creator thread RESOLVED
earlier (prod AgentQL misconfig).

## Current state

- **Latest release: `v0.6.0`** (2026-07-19, PR #36 — Manyfold import). Headline feature:
  **import a model straight from a self-hosted Manyfold instance** via its OAuth2
  (`client_credentials`) JSON-LD API — a *primary authenticated* source, NOT a scraper (bypasses
  the scrape/fallback chain and downloads real 3D files). Admin config (`ManyfoldInstance`,
  migrations `0023`/`0024`, `/api/admin/manyfold`, secret Fernet-encrypted & write-only), worker
  branch `_maybe_manyfold_import` (`storage/manyfold_client.py`), `/admin/ai/manyfold` admin tab,
  and a wizard **Assets** step (`import_session_files.selected`, files checked-by-default,
  deselectable). Live-validated end-to-end against the real `manyfold.crzynet.com`. Two live-found
  fixes baked in: rewrite Manyfold's internal-host `@id`/`contentUrl` onto the configured
  `base_url`; scope the download SSRF guard so the trusted instance host (may be a private/LAN IP)
  is exempt while cross-host redirects stay guarded; and derive a file extension from
  `encodingFormat` when the Manyfold filename lacks one. What's-New modal + README updated (README
  history collapsed to latest + CHANGELOG link; early-alpha warning softened to
  active-development).
- **OPEN — issue #37 (`bug`): worker crash-loops OOM-analyzing large meshes.** `analyze_item` runs
  **inline in the worker** (not subprocess-isolated like render), so a huge mesh (repro: a 1.36M-
  vertex / 37.9 MB `.3mf` needs ~4.7 GiB) OOM-kills the worker at its mem cap → SIGKILL (uncatchable)
  → container restart → the `on_startup` orphan-recovery re-queues the 'running' job with **no
  attempt cap** → infinite loop (saw 31 restarts). Prod (6 GiB cap) likely survives *this* file but
  any bigger one loops the same way. Proposed fixes in #37: cap orphan re-queue → mark failed;
  subprocess-isolate analyze; dedup concurrent analyze jobs per item; guard/decimate huge meshes.
  **Dev mitigation already applied:** bumped the dev worker to 6 GiB (`WORKER_MEM_LIMIT=6g` in the
  gitignored `.env`) and cleared the storm (cancelled the dup item-35 jobs, flushed the arq queue).
- **RESOLVED — prod MakerWorld imports missing creator/tags:** root cause was a prod-side
  AgentQL misconfiguration (not a code bug); owner corrected the config and imports now pull
  creator info. No code change needed. (Latent candidate, low priority: the AgentQL fallback
  query is still creator-blind by design — `{ title description images[] }` — so extending it
  with creator fields would harden the fallback, but it's no longer the active problem.)
- **Prod deploy facts** (compose in `~/projects/docker-compose/apps/partfolder3d/` on this
  host, deployed elsewhere via Komodo): `:latest` images, Traefik ingress
  (`partfolder3d.crzynet.com`), NFS library, `user: 2000:66000`, worker capped
  `cpus:2 / 6G` (matches `RENDER_CPU_THREADS=2`; `WORKER_MAX_JOBS=2`, `RENDER_CONCURRENCY=1`
  defaults). Shared FlareSolverr compose in `~/projects/docker-compose/apps/flaresolverr/`.
- **The dev docker stack on THIS host is UP** (worker recreated at **6 GiB** via
  `WORKER_MEM_LIMIT=6g` in `.env` — see #37). Bring up/down with
  `docker compose -f docker-compose.dev.yml {up -d,stop}`. backend/frontend hot-reload from the
  repo; the **worker does NOT** (restart after worker/task/scraper edits). The dev DB has a
  **configured Manyfold instance** (`manyfold.crzynet.com`, "Live test", real creds encrypted) +
  a few committed test imports (items ~30–35) from release testing.

## Next phases (roadmap)

- **Bulk move-assets UI** (#25 follow-up) — last Phase 2 item. Backend bulk endpoint live +
  tested; catalog needs a **multi-select** affordance (real UX decision — discuss with owner
  before building).
- **Issue #37 (`bug`) — worker analyze crash-loop robustness** (see Current state). Good next pickup:
  retry-cap the orphan re-queue + subprocess-isolate analyze. Not a release blocker.
- **Unfiled candidates:** harden the creator-blind AgentQL fallback query (low priority — see
  RESOLVED note); opportunistic auto-fetch of model files on the scraper framework (login-gated on
  Printables/MakerWorld — deferred from #27).
- Next release = `/release-prep <next>` when a batch is ready. Standing gotchas: CodeQL on big
  diffs surfaces pre-existing alerts (`sanitize_for_log` real ones; dismiss path-injection FPs with
  existing `resolve()`+`is_relative_to()` barriers); transient pip-download timeouts in the Image
  build check — just re-run the failed job; the local `verify-frontend` gate can flake (waitFor
  timeouts) when the host is CPU-loaded — CI on a clean runner is the authority.

## How we work (recap — full rules in `CLAUDE.md`)

- Central **Opus planning session**: plan, write handoff prompts in `prompts/`, dispatch **Sonnet
  subagents** to execute, report back. Owner doesn't babysit. Bigger than ~1–2 files → handoff prompt.
- **Auto-commit on `dev`** with conventional prefixes; **`main` is PR-only, never direct-push.** Use
  `closes #N` so issues auto-close. Every feat/fix commit updates `CHANGELOG.md [Unreleased]` same commit.
- **During active build/test sessions the owner wants each verified item committed AND pushed to `dev`**
  (not just committed) so pushing rebuilds the `:dev` images and the owner's on-host stack + testers can
  pull. Gate each push on `make verify` (full backend suite + fresh frontend build/vitest).
- **Flag genuine design forks** for the owner instead of guessing.
- **Live-iteration caveat:** owner runs the vite dev server / the `:dev` stack on this repo; for bigger
  changes while they test, dispatch to an **isolated worktree** (Agent `isolation: worktree`).
- **Verify + gotchas are NOT here.** Verify discipline: `CLAUDE.md` + `scripts/verify-*.sh` (`make verify`).
  Load-bearing gotchas (render backend, 3MF, modals, worker-no-hot-reload, CI shape, merge-dup-symbols):
  `docs/architecture.md`.

## Backlog (themes — `gh issue list` is the source of truth for what we build **now**, not the PRD)

- **Open: #37** (worker analyze crash-loop robustness). Unfiled candidates: harden creator-blind
  AgentQL fallback (low pri); auto-fetch model files.
- **Needs owner decision:** bulk-move multi-select UX.
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
- **Dev stack on THIS host** (when up): `partfolder3d-{backend,worker,db,redis,nginx,frontend,flaresolverr}-1`
  on `:dev` images. `docker logs`/`exec` to diagnose; app DB via `docker exec partfolder3d-db-1 psql -U
  partfolder3d -d partfolder3d`. Separate ephemeral **test** pg: `pf3d-pg-v` on :5433 (pytest only).
  Dev scraper config in DB points at the **shared** FlareSolverr (`https://flaresolverr.crzynet.com/`).
- **Run from scratch:** `cp .env.example .env` → `docker compose -f docker-compose.dev.yml up --build`
  (dev) or `docker compose up -d --build` (prod) → http://localhost:8973 first-run wizard. Migrations
  auto-run via the backend entrypoint. External port **8973** (nginx).
- **No sandbox here** — bash may prompt unless auto-approve is on. **System Python is PEP-668** (pip
  blocked); `backend/.venv` exists and runs repo code directly (used for the scrape repro).

## Before-`/clear` checklist

1. Update **Last updated** + **Current state** + **Next phases** (release cut? `dev` vs `main`?).
2. Refresh **Backlog** themes — `gh issue list` is the source of truth; don't enumerate.
3. Ensure in-flight `prompts/` frontmatter + `done|failed/` placement is right; record decisions in
   `docs/decisions.md`.
4. Confirm work is committed **and pushed** on `dev` (note anything intentionally unpushed).
