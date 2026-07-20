# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** This is the **live-state handoff** — a
current, limited view so a new session can orient fast, then go deeper via the docs it points to.
It is NOT a full reference: durable rules live in `CLAUDE.md`, the module map + gotchas in
`docs/architecture.md`, history in `CHANGELOG.md` / `docs/decisions.md`. Keep it LEAN; refresh
"Current state" + "Next phases" before every `/clear`.

**Last updated:** 2026-07-20 — **`v0.6.1` RELEASED** (issue #37 — worker analyze crash-loop
hardening; PR #38 merged, tag `v0.6.1` cut, prod images publishing `:latest`/`:0.6.1`/`:0` for all
three images). `dev` == `main`. **No open issues** (`#37` fully closed). Previous release `v0.6.0`
was the Manyfold import feature.

## Current state

- **Latest release: `v0.6.1`** (2026-07-20). A pure **bug-fix/hardening** release closing
  **issue #37** — a large mesh could OOM-kill the whole background worker, which then
  crash-looped forever. Shipped as five changes, each `make verify`-green and live-proven on
  this host:
  - **#1 orphan-requeue retry cap** — `_recover_orphaned_jobs` (`backend/worker.py`) now re-queues
    an orphaned idempotent job at most **3× within 6h** (counted by `payload.item_id` + recency
    window), then marks it terminally `failed`. Kills the infinite loop.
  - **#2 subprocess-isolate analyze** — `analyze_file` now runs in a spawned child via
    **`backend/app/worker/analyze_subprocess.py`** (mirrors `render_subprocess.py`) with a
    wall-clock timeout AND a per-child **`RLIMIT_AS` memory bound** (`ANALYZE_MEM_LIMIT_MB`,
    default 4096) set BEFORE trimesh import. The RLIMIT is the crux — a bare subprocess isn't
    enough because the container cgroup OOM-killer could pick the parent.
  - **#4 triangle cap** — post-load `ANALYZE_MAX_TRIANGLES` (default 2,000,000) → cap-skip stub.
  - **#3 per-item analyze dedup** — claim-time supersede (`mark_superseded` in `job_tracker.py`)
    if another analyze for the same item is already `running`, + opt-in enqueue-time skip in
    `_write_queued_row_and_enqueue`.
  - **Pre-load 3MF size guard** — `_check_3mf_xml_size` in `mesh_analysis.py` reads the ZIP
    central directory (no decompression), sums `3D/**/*.model` uncompressed bytes, and cap-skips
    over `ANALYZE_MAX_3MF_XML_MB` (default 256) BEFORE trimesh. Over-cap files are stored as a
    cached low-confidence `analysis_skipped:"too_large"` stub, so they never retry.
  - **Live-proven:** re-analyzing item 11 ("Dahlia," a **140 MB / 1.09 GB-uncompressed** 3MF with
    two ~505 MB geometry parts) now finishes in ~11s as a clean cap-skip stub, worker
    `RestartCount=0`. Before: OOM crash-loop.
- **Known finding (not a bug, not filed):** trimesh's own 3MF loader parses each
  `3D/Objects/*.model` geometry XML into an lxml DOM; a ~500 MB part balloons **past 8 GB**, so
  such files genuinely can't be geometry-analyzed under any sane memory bound. The pre-load size
  guard is the intended answer (skip + flag, don't attempt). `_parse_3mf_colors` was NOT the
  culprit (it's already guarded and its `3dmodel.model` is tiny). Only revisit if someone wants
  partial analysis of giant 3MFs (would need streaming/decimation, not huge_tree).
- **Config knobs added this release** (env, defaults in `backend/app/config.py` + `.env.example`):
  `ANALYZE_TIMEOUT_S=300`, `ANALYZE_MEM_LIMIT_MB=4096`, `ANALYZE_MAX_TRIANGLES=2000000`,
  `ANALYZE_MAX_3MF_XML_MB=256`.
- **Prod deploy facts** (compose in `~/projects/docker-compose/apps/partfolder3d/` on this
  host, deployed elsewhere via Komodo): `:latest` images, Traefik ingress
  (`partfolder3d.crzynet.com`), NFS library, `user: 2000:66000`, worker capped
  `cpus:2 / 6G` (matches `RENDER_CPU_THREADS=2`; `WORKER_MAX_JOBS=2`, `RENDER_CONCURRENCY=1`,
  `ANALYZE_CONCURRENCY=2` defaults). Shared FlareSolverr in `~/projects/docker-compose/apps/flaresolverr/`.
- **The dev docker stack on THIS host is UP.** The worker was bumped to **6 GiB**
  (`WORKER_MEM_LIMIT=6g` in the gitignored `.env`) as a #37 *mitigation*; that mitigation is now
  **superseded by the real fix** (analyze child is RLIMIT-bounded at 4 GiB), so the dev worker no
  longer needs 6 GiB for analyze — the `.env` override is harmless and left in place. Bring
  up/down with `docker compose -f docker-compose.dev.yml {up -d,stop}`. backend/frontend
  hot-reload from the repo; the **worker does NOT** (`make worker-restart` after worker/task/
  scraper edits). Dev DB has a configured Manyfold instance + committed test imports (items ~11,
  25, 29–35); item 11 now carries a `too_large` analysis stub from the #37 live test.

## Next phases (roadmap)

- **Bulk move-assets UI** (#25 follow-up) — last Phase 2 item. Backend bulk endpoint live +
  tested; catalog needs a **multi-select** affordance (real UX decision — discuss with owner
  before building).
- **Unfiled candidates:** harden the creator-blind AgentQL fallback query (low priority, from the
  v0.6.0 MakerWorld thread — RESOLVED as a prod config issue, not code); opportunistic auto-fetch
  of model files on the scraper framework (login-gated on Printables/MakerWorld — deferred from
  #27). Partial analysis of very large 3MFs (streaming/decimation) if ever wanted (see finding
  above).
- Next release = `/release-prep <next>` when a batch is ready. Standing gotchas: CodeQL on big
  diffs surfaces pre-existing alerts (`sanitize_for_log` real ones; dismiss path-injection FPs with
  existing `resolve()`+`is_relative_to()` barriers); transient pip-download timeouts in the Image
  build check — just re-run the failed job; the local `verify-frontend` gate can flake (waitFor
  timeouts) when the host is CPU-loaded — CI on a clean runner is the authority.

## How we work (recap — full rules in `CLAUDE.md`)

- Central **Opus planning session**: plan, write handoff prompts in `prompts/`, dispatch **Sonnet
  subagents** to execute, report back. Owner doesn't babysit. Bigger than ~1–2 files → handoff prompt.
- **Auto-commit on `dev`** with conventional prefixes; **`main` is PR-only, never direct-push.** Use
  `closes #N` so issues auto-close on merge. Every feat/fix commit updates `CHANGELOG.md [Unreleased]`
  same commit.
- **During active build/test sessions the owner wants each verified item committed AND pushed to `dev`**
  (not just committed) so pushing rebuilds the `:dev` images and the owner's on-host stack + testers can
  pull. Gate each push on `make verify` (full backend suite + fresh frontend build/vitest).
- **Flag genuine design forks** for the owner instead of guessing. (This session: a first
  lxml-`huge_tree` hypothesis was wrong — verify diagnoses on the live stack BEFORE building the fix.)
- **Live-iteration caveat:** owner runs the vite dev server / the `:dev` stack on this repo; for bigger
  changes while they test, dispatch to an **isolated worktree** (Agent `isolation: worktree`).
- **Verify + gotchas are NOT here.** Verify discipline: `CLAUDE.md` + `scripts/verify-*.sh` (`make verify`).
  Load-bearing gotchas (render/analyze subprocess isolation, 3MF, modals, worker-no-hot-reload, CI shape):
  `docs/architecture.md`.

## Backlog (themes — `gh issue list` is the source of truth for what we build **now**, not the PRD)

- **No open issues.** Next pickup is a roadmap item, not an issue.
- **Needs owner decision:** bulk-move multi-select UX (#25 follow-up).
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
