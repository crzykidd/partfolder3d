# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** This is the **live-state handoff** — a
current, limited view so a new session can orient fast, then go deeper via the docs it points to.
It is NOT a full reference: durable rules live in `CLAUDE.md`, the module map + gotchas in
`docs/architecture.md`, history in `CHANGELOG.md` / `docs/decisions.md`. Keep it LEAN; refresh
"Current state" + "Next phases" before every `/clear`.

**Last updated:** 2026-07-22 — **`v0.7.1` RELEASED.** Feature: **optional built-in HTTPS/TLS at
nginx** (opt-in, off by default) + the **nginx base-image security bump** `1.27→1.30-alpine`
(closed #40). PR #42 merged, tag `v0.7.1` cut, the `release`-triggered "Build and publish Docker
images" run fired — prod images publishing `:latest`/`:0.7.1`/`:0` for all three
(backend/frontend/nginx). **`dev` == `main`.** Previous release `v0.7.0` was the prinnit.com import
connector.

> **⏭️ NO RELEASE IN FLIGHT, no forced next task.** Next pickup is a roadmap **choice**, not an
> issue-driven must-do — see "Next phases". The two live options: (a) **bulk move-assets UI**
> (#25 follow-up, needs an owner UX call), or (b) **automatic Let's Encrypt/ACME** at nginx
> ([#41](https://github.com/crzykidd/partfolder3d/issues/41) — the deferred follow-up to the v0.7.1
> BYO/self-signed TLS work).

## Current state

- **Latest release `v0.7.1`** (2026-07-22) — **optional built-in HTTPS/TLS at nginx** + the nginx
  base-image security bump. `dev` == `main`. Live-verified: the new image with **no** TLS env serves
  plain `:80` unchanged (owner confirmed on a rebuild; also proven standalone).
  - **What shipped:** a `TLS_MODE` env on the `partfolder3d-nginx` image — `off` (default, plain
    `:80`, byte-for-byte unchanged) / `selfsigned` (entrypoint auto-generates a cert, immediate HTTPS
    w/ browser warning) / `provided` (BYO real cert mounted; missing files exit 1, never a silent
    HTTP downgrade). Plus opt-in `TLS_REDIRECT`, an opt-in `:443` port + `nginx_certs` volume in
    `docker-compose.yml`, a `COOKIE_SECURE=true` tie-in, an **admin Settings "HTTPS / TLS" info
    card** (signpost only — TLS is deploy-level, not a stored setting), and README/`docs/tls.md`.
  - **Where the code lives:** `nginx/Dockerfile` (`FROM nginx:1.30-alpine`, `apk add openssl`,
    build-time `nginx -t` patches both configs), `nginx/40-partfolder-tls.sh` (POSIX
    `/docker-entrypoint.d/` script assembling `:443` at start), `nginx/partfolder-common.conf`
    (shared server block `include`d by both `:80` and `:443` — the refactor that triggered the
    "nginx config changed" callout), `nginx/partfolder-redirect.conf`, `docs/tls.md`, the Settings
    card in `frontend/src/pages/settings/SettingsPage.tsx`. Decisions in `docs/decisions.md`.
  - **Upgrade note (already documented):** default HTTP users need **no** compose change; only
    **custom-`nginx.conf` bind-mounters** must reconcile against the refactored config.
  - **Deferred → issue [#41](https://github.com/crzykidd/partfolder3d/issues/41):** full automatic
    Let's Encrypt/ACME (certbot companion or Caddy edge). This release is BYO/self-signed only.
- **`v0.7.0`** — the **prinnit.com import connector** (`backend/app/storage/prinnit_client.py` +
  a domain short-circuit in `tasks/import_session.py`; reads prinnit's public no-auth JSON API).
  Full detail in `CHANGELOG.md` / `docs/decisions.md`.
- **`v0.6.1`** — issue #37 worker-analyze OOM crash-loop hardening (`ANALYZE_*` knobs in
  `backend/app/config.py`). Dev DB item 11 carries a `too_large` analysis stub from that test.
- **Prod deploy facts** (compose in `~/projects/docker-compose/apps/partfolder3d/` on this
  host, deployed elsewhere via Komodo): `:latest` images, Traefik ingress
  (`partfolder3d.crzynet.com`), NFS library, `user: 2000:66000`, worker capped
  `cpus:2 / 6G` (`WORKER_MAX_JOBS=2`, `RENDER_CONCURRENCY=1`, `ANALYZE_CONCURRENCY=2` defaults).
  Shared FlareSolverr in `~/projects/docker-compose/apps/flaresolverr/`.
- **The dev docker stack on THIS host is UP.** Bring up/down with
  `docker compose -f docker-compose.dev.yml {up -d,stop}`. backend/frontend hot-reload from the
  repo; the **worker does NOT** (`make worker-restart` after worker/task/scraper edits). Dev DB has
  a configured Manyfold instance + committed test imports (items ~11, 25, 29–35).
- **CI vs local gotcha (confirmed this session):** the local `verify-frontend`/vitest gate flaked
  with nondeterministic `waitFor` 5s timeouts (a *different* unrelated test each run) while the host
  was CPU-loaded from the build — **PR #39's CI Frontend + Test jobs are green.** CI on a clean
  runner is authoritative; don't chase local frontend timeout flakes.

## Next phases (roadmap)

- **Automatic Let's Encrypt/ACME at nginx** (issue [#41](https://github.com/crzykidd/partfolder3d/issues/41)) —
  the deferred follow-up to v0.7.1's BYO/self-signed TLS. Bigger lift (certbot companion or Caddy
  edge; needs public 80/443 + DNS + renewal). Not started; owner decides approach at build time.
- **Bulk move-assets UI** (#25 follow-up) — last Phase 2 item. Backend bulk endpoint live +
  tested; catalog needs a **multi-select** affordance (real UX decision — discuss with owner
  before building).
- **Unfiled candidates:** harden the creator-blind AgentQL fallback query (low priority, from the
  v0.6.0 MakerWorld thread — RESOLVED as a prod config issue, not code); opportunistic auto-fetch
  of model files on the scraper framework (login-gated on Printables/MakerWorld — deferred from
  #27). Partial analysis of very large 3MFs (streaming/decimation) if ever wanted. Prinnit's
  `/designs/<sub>` returns the designer's whole catalog (~1.2 MB) to get one design — fine today,
  but if it ever gets slow, revisit for a lighter path (none is currently public).
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

- **Open issue [#41](https://github.com/crzykidd/partfolder3d/issues/41)** — automatic Let's
  Encrypt/ACME at nginx (deferred follow-up to v0.7.1 TLS; not started). (#40 nginx bump: **closed**
  in v0.7.1.)
- **Needs owner decision:** Let's Encrypt approach (#41); bulk-move multi-select UX (#25 follow-up).
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
