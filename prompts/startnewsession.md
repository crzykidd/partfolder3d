# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** This is the **live-state handoff** — a
current, limited view so a new session can orient fast, then go deeper via the docs it points to.
It is NOT a full reference: durable rules live in `CLAUDE.md`, the module map + gotchas in
`docs/architecture.md`, history in `CHANGELOG.md` / `docs/decisions.md`. Keep it LEAN; refresh
"Current state" + "Next phases" before every `/clear`.

**Last updated:** 2026-07-26 — **`v0.7.5` RELEASED.** Tag `v0.7.5` cut on `main`, GitHub release
published, `release`-triggered "Build and publish Docker images" green — prod images
`:latest`/`:0.7.5`/`:0` for all three (backend/frontend/nginx). **v0.7.5 = OpenSCAD `.scad` support**
for self-designed items: a read-only **Show SCAD** viewer (copy / download / **Open in OpenSCAD
Playground** deep-link) + **import-time title/description prefill from the `.scad` header** and an
optional **Describe from SCAD** AI action. Adds a `source` `FileRole` (migration **0025**). Previous
`v0.7.4` was the MakerWorld octet-stream image-save fix (`sniff_image_ext`); `v0.7.3` (the diagnostic
logging that found it) merged but was never tagged.

> **⏭️ NO RELEASE IN FLIGHT, no forced next task.** `dev` == `main` (v0.7.5). Next build pickup is an
> owner **choice** (`gh issue list` is the source of truth): **[#47](https://github.com/crzykidd/partfolder3d/issues/47)**
> edit an existing item's description + add/remove tags in-app; **[#46](https://github.com/crzykidd/partfolder3d/issues/46)**
> optional server-side `.scad` render/preview; **[#41](https://github.com/crzykidd/partfolder3d/issues/41)**
> automatic Let's Encrypt/ACME at nginx; or **bulk move-assets UI** (#25 follow-up). Optional tidy-up:
> the `[0.7.4]`/`[0.7.3]` CHANGELOG compare links don't resolve (v0.7.3 was never tagged).

## Current state

- **Latest release `v0.7.5`** (2026-07-26, on `main`; `:latest`/`:0.7.5`/`:0` published) — **OpenSCAD
  `.scad` support**, two features (`make verify-backend` 949 pass):
  - **Read-only viewer** (`feat:` `7a3f456`). `.scad` is a new **`FileRole.source`** (migration
    **0025**), accepted on upload; classified in `storage/inventory.py` `infer_role`. A **Show SCAD**
    modal on the item details card (`frontend/src/pages/item/ItemMetadata.tsx`) shows the source with
    **Copy / Download / Open in OpenSCAD Playground** — the last deep-links `ochafik.com/openscad2`
    with the code prefilled via the playground's compressed hash-fragment format (encoder:
    `frontend/src/lib/openscadPlayground.ts`). No server render, no in-app editing.
  - **Import prefill + AI describe** (`feat:` `9cfcb82`). On import, item title/description are
    pre-filled from the `.scad`'s leading comment header (`backend/app/storage/scad_meta.py` —
    deterministic, no AI; only fills empties). Optional **Describe from SCAD** AI action on the wizard
    description step (`POST /api/import-sessions/{id}/ai/describe-scad` in `routers/ai_actions.py`,
    button in `pages/import-wizard/TitleStep.tsx`, whole-file to the provider, reuses `AiTextPreview`).
  - Deferred: server-side `.scad`→STL render/preview → **#46**. In-app edit of `.scad` → future.
- **`v0.7.4`** (2026-07-24, on `main`; `:latest`/`:0.7.4`/`:0` published) —
  **fix: scraped images served as `application/octet-stream` are now saved** (`fix:` `acef0c9`;
  `make verify-backend` 930 pass). MakerWorld's `bblmw.com` CDN began returning some gallery PNGs
  (dated filenames, e.g. `design/2025-08-16_*.png`) with a generic octet-stream Content-Type; the
  import-commit download (`_commit_session_inner`, `routers/import_sessions/commit.py`) enforced an
  `image/*`-only content-type via `guarded_fetch` and rejected every one → the wizard showed the
  images (the browser renders by content, ignoring the header) but the committed item had none. New
  `sniff_image_ext` (`routers/import_sessions/sessions.py`) recognizes PNG/JPEG/GIF/WEBP magic
  numbers; commit now allows octet-stream through the guard but only writes when the bytes are a
  real image — non-images are skipped. Fixes prinnit + any mislabeling CDN too. NOT egress/NFS/the
  prinnit code (all earlier hypotheses, disproven on the live stack).
- **`v0.7.3`** (2026-07-24; PR [#44](https://github.com/crzykidd/partfolder3d/pull/44) merged but
  **never tagged** — `main` advanced to v0.7.4 before the cut, so only v0.7.4 is a tag/release) —
  **per-image commit diagnostic logging** (`feat:` `c295834`) that pinpointed the octet-stream cause
  from prod backend logs: a start line, the concrete per-image failure reason + exception type
  (previously a bare "failed to download image" that swallowed the cause), a missing-staged-file
  warning, and a saved/failed/elapsed summary.
- **`v0.7.2`** (2026-07-23, on `main`; `:latest`/`:0.7.2`/`:0` published) — three
  things, verified (`make verify`: backend 926 pass, frontend build clean):
  - **Reconcile corruption-vs-legit-edit fix** (`fix:` `0b4882c`). `_behavior_re_render` is now the
    single classifier for a changed model file: **newer mtime + still parses → legitimate edit**
    (adopt new hash/mtime/size baseline, re-render, NO Issue); **newer mtime + unparseable →
    `corruption`** (bad/interrupted write); **hash changed + unchanged/older mtime → `corruption`**
    (silent bit-rot). `_behavior_integrity` now skips model files the validator understands. New
    `render_mesh.validate_model_file` (dispatches to `threemf.validate_3mf_structure` / a trimesh
    load; **fails open above `RENDER_MAX_FILE_MB`** so the capped worker never loads a giant mesh
    in-process). **`.3mf` is now covered by the re-render/adoption path for the first time** (owner's
    real workflow: edit a `.3mf` in a slicer in place). Full rationale in `docs/decisions.md`
    (2026-07-23 entry).
    - **Two noted follow-ups (not built):** a `.3mf` re-render does NOT refresh the embedded slicer
      thumbnail (would need `_enqueue_analyze`); the mesh validator is size-bounded but NOT
      subprocess/RLIMIT-isolated like analyze/render (acceptable — only fires on an already-detected
      within-cap mismatch). Both in `docs/decisions.md`.
  - **Bulk Approve-all / Reject-all for pending reviews** (`feat:` `072f690`). New
    `POST /api/reviews/{approve-all,reject-all}` (admin+CSRF, idempotent, cloned from the tag
    `approve-all` precedent) + buttons on `ReviewsPage.tsx` Pending tab. **Reject-all** = cheap
    status flip; **Approve-all** = replays every `apply_review_item` (real work, confirm-gated).
    Solves the owner's **405 pending prod reviews** — recommended clear once 0.7.2 is deployed:
    **Reject all** (auto modes re-apply the still-present drift on next scan).
  - **Two modal-portal UI fixes** (`4e9d2ac`, `e4036d2`). Log-a-Print + Add-asset dialogs are now
    `createPortal(..., document.body)` so a sibling card's `backdrop-filter` stacking context can't
    trap their `z-index` (the Share card was painting over the Log-a-Print modal).
- **`v0.7.1`** (2026-07-22, on `main`) — **optional built-in HTTPS/TLS at nginx** (`TLS_MODE`
  off/selfsigned/provided, opt-in `TLS_REDIRECT`/`:443`/`nginx_certs`, admin Settings info card) +
  nginx base-image bump `1.27→1.30-alpine` (closed #40). Code in `nginx/*` + `docs/tls.md`. Full
  automatic Let's Encrypt/ACME deferred → [#41](https://github.com/crzykidd/partfolder3d/issues/41).
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

- **Edit an existing item's description + add/remove tags in-app** (issue [#47](https://github.com/crzykidd/partfolder3d/issues/47)) —
  today description/tags are only set at import (or by editing the on-disk sidecar + rescan). Needs an
  item-update endpoint that **writes through to the sidecar** and marks a legit local edit (same
  baseline discipline as the v0.7.2 corruption-vs-edit work), plus inline edit UI on the item card.
- **Optional server-side `.scad` render/preview** (issue [#46](https://github.com/crzykidd/partfolder3d/issues/46)) —
  deferred companion to the v0.7.5 `.scad` viewer: add the `openscad` binary + a sandboxed compile
  (`.scad`→STL) that reuses the existing render/analyze/viewer pipeline. Not needed yet (the playground
  covers edit/preview/STL export). Also future: in-app `.scad` editing (pairs with #47's write path).
- **Automatic Let's Encrypt/ACME at nginx** (issue [#41](https://github.com/crzykidd/partfolder3d/issues/41)) —
  the deferred follow-up to v0.7.1's BYO/self-signed TLS. Bigger lift (certbot companion or Caddy
  edge; needs public 80/443 + DNS + renewal). Not started; owner decides approach at build time.
- **Bulk move-assets UI** (#25 follow-up) — last Phase 2 item. Backend bulk endpoint live +
  tested; catalog needs a **multi-select** affordance (real UX decision — discuss with owner
  before building).
- **Unfiled candidates:** (NEW, from the v0.7.2 corruption work) refresh a `.3mf`'s embedded slicer
  thumbnail on in-place edit (route the re-render through `_enqueue_analyze`, not just render);
  optionally give `validate_model_file`'s STL/OBJ/PLY path the same subprocess/RLIMIT isolation as
  analyze/render (currently size-bounded only). Older: harden the creator-blind AgentQL fallback
  query (low priority, v0.6.0 MakerWorld thread — RESOLVED as a prod config issue, not code);
  opportunistic auto-fetch of model files on the scraper framework (login-gated on
  Printables/MakerWorld — deferred from #27). Partial analysis of very large 3MFs
  (streaming/decimation) if ever wanted. Prinnit's `/designs/<sub>` returns the designer's whole
  catalog (~1.2 MB) to get one design — fine today, but revisit for a lighter path if it ever slows.
- **Next release = `/release-prep <next>` when a batch is ready** (v0.7.5 is fully cut; next is
  `0.7.6`). Standing gotchas: CodeQL on big diffs surfaces pre-existing alerts (`sanitize_for_log`
  real ones; dismiss path-injection FPs with existing `resolve()`+`is_relative_to()` barriers);
  transient pip-download timeouts in the Image build check — just re-run the failed job; the local
  `verify-frontend`/vitest gate flakes hard (nondeterministic `waitFor` 5s timeouts, a *different*
  heavy-async test each run — catalog-page/reviews-page/scrapers/tag-admin — zero assertion failures)
  when the host is CPU-loaded — **CI (`dev-checks` on push, `CI` on the PR) on a clean runner is the
  authority; don't chase them.** **`make verify` via `| tail` masks the real exit code** (tail's 0
  hides a red gate) — read the summary line / capture `$?` without a pipe.

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

- **Open issues (run `gh issue list`):** [#47](https://github.com/crzykidd/partfolder3d/issues/47)
  edit item description + add/remove tags in-app; [#46](https://github.com/crzykidd/partfolder3d/issues/46)
  optional server-side `.scad` render/preview (deferred companion to v0.7.5); [#41](https://github.com/crzykidd/partfolder3d/issues/41)
  automatic Let's Encrypt/ACME at nginx. All three await an owner call on scope/approach.
- **Needs owner decision:** which of #47 / #46 / #41 is next; bulk-move multi-select UX (#25 follow-up).
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
