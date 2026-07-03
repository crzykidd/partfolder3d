# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** It carries the project-specific,
fast-moving context that does **not** live in `CLAUDE.md` (which holds the durable
standards/operating rules). Keep them separate: rules in `CLAUDE.md`, live state here.

> 🔄 **UPDATE THIS FILE BEFORE EVERY `/clear`.** Before clearing context, refresh the
> "Current status" and "Open threads" sections so the next session loses nothing. This is
> a deliberate ritual — see the checklist at the bottom.

**Last updated:** 2026-07-02 (v0.2.5 released on `main`; **`dev` is AHEAD of `main`** — #15 bulk import
merged to `dev`, unreleased. New backlog issues #16/#20/#21/#24 filed; render-capture direction shaped)

> ## CURRENT STATE (2026-07-02) — v0.2.5 released; #15 bulk import queued on `dev`
> **Latest release: `v0.2.5`** on `main` (merge `569d5e1`, tag `v0.2.5`). **`dev` is AHEAD of `main`**:
> the #15 bulk-import feature is merged to `dev` (merge `0952358`) and awaits the next release —
> **next release is `v0.3.0`** (minor bump — large feature batch: #15 bulk import + the overnight
> batch #16/#17/#18/#19/#21/#24/#11 + #15 render param; a minor triggers the 0.2.x changelog archive
> at `/release-prep`). As each issue is fixed on `dev`, comment it "fixed on dev → shipping in v0.3.0".
> Release history since v0.1.1:
> - **v0.2.0** — "read-don't-render" asset-detail rework: 3MF READ not rendered (embedded slicer
>   thumbnail `ImageSource.embedded` + slice metadata, migration **0021**), bounded STL/OBJ/PLY render
>   on the **`vtk-osmesa`** wheel (+`libosmesa6`; stock PyPI `vtk` is X11-only, can't render headless),
>   ZIP auto-extraction, file-tree UI + collapsible 3MF panel, in-browser three.js viewer, per-file 3MF
>   thumbnails. `networkx` is an explicit backend dep. (v0.2.1 prepped-but-never-tagged → rolled into 0.2.2.)
> - **v0.2.2** — PUID/PGID runtime user (NFS), **pytest-xdist** parallel CI, the branch-protection fix (below).
> - **v0.2.3** — published **`partfolder3d-frontend` + `-nginx` images**; **nginx config baked into the
>   nginx image** (`nginx/Dockerfile`; optional `./nginx/nginx.conf` bind-mount override); fixed the
>   frontend prod build — `npm run build` (`tsc -b`) catches strict errors `npx tsc --noEmit` misses.
> - **v0.2.4** — production-deploy hardening + issue batch:
>   - **nginx image-serving fix** — the baked static-asset regex `location ~* \.(png|jpg|…)$` was stealing
>     `/api/…/*.png` (item images/renders) and `/img/` logos → **404** (served from the frontend root,
>     never proxied). Fixed with **`^~`** on `/api/` and `/img/` so they beat the regex. **This was the
>     prod "images/renders don't display" bug.** Found via logs (404 only in nginx, never reached backend).
>   - **Fail-loud startup logging on EVERY service** — backend entrypoint (DB preflight via `app.dbcheck`,
>     writable check, streamed alembic + hard `MIGRATION_TIMEOUT`, version/uid/redacted-DB banner) +
>     frontend publish container (version banner, writability check, loud copy errors). A silent hang is
>     no longer possible; a user's log paste is a complete bug report.
>   - **`ALLOWED_ORIGINS` fix** — accepts comma / JSON / empty (was crashing boot with a pydantic
>     `SettingsError`: `env_file: .env` injects the whole file and pydantic JSON-decodes list vars).
>     `NoDecode` + a `field_validator`. Same pattern applied to `FS_BROWSE_ROOTS`.
>   - **Issues fixed:** #8 admin **folder browser** (allowlist `FS_BROWSE_ROOTS`, traversal-safe, 14
>     tests; CodeQL path-injection FPs dismissed + log-injection fixed — see decisions), #9 disabled
>     libraries filtered from the add-item picker, #7 version-page nav link → **Admin → Content**,
>     #6/#10 dark-mode `<select>` option popups (opaque `option` bg — the semi-transparent input bg is
>     ~white over a native popup's light base; `color-scheme` alone insufficient on Chrome/Windows).
> - **v0.2.5** — setup/import bug fixes + hardening: **#13** first-run auto-login (await the `/me`
>   refetch before `navigate` so completing the wizard lands you in the app, not `/login`; fix on
>   Setup **and** Login; + a confirm-password field; defensive `await db.commit()` in `run_setup`),
>   **#14** import "set default image" not applied on commit (PATCH now syncs
>   `ImportSessionImage.is_default` + a commit-side fallback), and a CodeQL `py/log-injection` fix
>   (escape CR/LF before logging user-supplied `default_image_path`). Release verify: 607 backend
>   pass on ephemeral PG (2 `test_run_db_backup_*` fail ONLY locally — they read `settings.DATABASE_URL`
>   =:5432 default while the suite runs on :5433; CI has DATABASE_URL set, so it covers them) + 286 vitest.
>   **Gotcha:** #13's commit said "(issue #13)" not "closes #13" → didn't auto-close on merge; closed
>   manually. Use `closes #N` going forward (see memory).
>
> ### 🏭 Production-deploy operational knowledge (learned bringing up the owner's prod stack)
> - **`frontend` is a ONE-TIME-RUN container** (`restart: "no"`): copies the built UI into the shared
>   **`frontend_dist`** volume, then **exits 0** (expected — `Exited (0)` frontend is normal). nginx
>   serves that volume read-only and waits via `depends_on: service_completed_successfully`.
> - **#1 prod gotcha: `frontend_dist` volume permissions.** The frontend writes it as `PUID:PGID`; a
>   reused/old volume owned by a different UID makes the copy fail → nginx never starts. Fix:
>   `docker compose down -v` (recreates the volume) or chown it. Documented in the README deploy section.
> - Owner runs on **NFS** (uid=2000 gid=66000), behind **https** (`partfolder3d.crzynet.com`),
>   `COOKIE_SECURE=true`. Diagnose image/asset problems by the **status code in the nginx log** (404 =
>   path/regex, 403/500 = perms). The 0.2.4 logging makes all of this visible.
>
> ### 🔑 Release-bypass problem is FIXED — see `docs/decisions.md` (still true, LOAD-BEARING)
> `main` required checks bind by **BARE job name** (`Lint`, `Test`, …), NOT `CI / Test`. Required
> contexts = the 6 `ci.yml` bare job names — **don't rename ci.yml jobs.** CI shape: **`ci.yml`**
> `pull_request:[main]` only (the required gate); **`dev-checks.yml`** `push:[dev]` (fast, non-required,
> jobs suffixed "(dev)"); **`publish.yml`** 3-image matrix (backend/frontend/nginx) on push:main +
> release; **`codeql.yml`** PR + push:main (green, **NOT required** — doesn't block merge). Releases:
> `/release-prep <v>` → merge PR (clean) → `:latest` publishes → `/release-cut <v>`. Worked for 0.2.3–0.2.5.
>
> ---
>
> ## PRIOR STATE (2026-07-01) — v0.1.1 released, no open release gate
> **v0.1.1 is live on `main` and tagged.** PR #1 (`dev`→`main`) merged as `79ed44b`; tag `v0.1.1`
> points at `1b3990a` on `main`. `/release-prep 0.1.1` bumped `backend/app/version.py` +
> `frontend/package.json`, rolled `CHANGELOG.md`, synced docs (ruff clean, tsc clean, **229/229
> vitest**, vite build clean, both compose configs valid). The PR triggered the **first-ever
> CodeQL run** — 36 alerts (1 critical/20 high/15 medium, because `main` was empty so it scanned
> the whole tree at once) — triaged in one pass: **12 fixed in code**, **24 dismissed** as verified
> false positives via the code-scanning API (full disposition in `docs/decisions.md`, 2026-07-01
> entry). CI (6 checks) + CodeQL both green; `Build and publish Docker images` pushed `:latest`.
>
> **Since the tag, 4 more commits landed on `dev`** (pushed to `origin/dev`, matches local exactly
> — nothing queued for release):
> - `97dcd1b` docs — `docker-compose.yml` converted to a **production, image-based deploy**
>   (`build:` blocks removed, pulls `ghcr.io/crzykidd/partfolder3d[-frontend]:latest`); README
>   Getting Started rewritten production-first with a Quick Start (`/quick-start`) callout.
>   `docker-compose.dev.yml` (build-from-source, hot-reload) untouched.
> - `f2b6353` / `b53b8d9` — sidebar highlight fixes: a nav item now highlights only its own route
>   (API Keys no longer also lights up Settings), and Catalog vs. My Favorites are distinguished by
>   the `?favorited=true` query since they share the `/catalog` pathname.
> - `2ff3c4c` — QuickStart page's Import/Backups steps now get real done-detection (item count /
>   backup existence); import wizard Summary step shows the resolved library **name** instead of
>   its numeric ID.
>
> All four are captured in `CHANGELOG.md [Unreleased]`. **`dev` is 4 commits ahead of `main`** —
> these ship next time the owner wants a release (v0.1.2, or bundled with whatever's next).
>
> ### OPEN ITEMS
> - **CodeQL still NOT a required check on `main`.** Confirmed via
>   `gh api repos/crzykidd/partfolder3d/branches/main/protection/required_status_checks` — contexts
>   are still just the original 6 CI jobs (`Lint`/`Config validation`/`Migration check`/
>   `Compose validation`/`Image build`/`Test`); the 2 CodeQL contexts run on PRs but don't gate
>   merges yet. Owner action (GitHub branch-protection settings or `gh api`).
> - **Rotate the AgentQL API key** (owner pasted it in chat during earlier testing) — still
>   outstanding.
> - Watch whether AgentQL **tetra proxy adds cost** beyond $0.02/call (default proxy-on, beats
>   Cloudflare) — switch off if it gets costly.
> - Real **slicing** for accurate filament grams/colors (currently a volume estimate;
>   `est_method` field reserved for when this lands). Type-2 **"newer version online"** upstream
>   check (`source_version` captured, unused).
> - **Trash purge / empty-trash admin UI** — delete-to-trash accumulates under
>   `private_data/data/app/trash` with no way to clear it from the UI.
> - Print-log **gcode multi-filament** parsing + `.bgcode` support.
>
> **Verify discipline (unchanged):** backend = `ruff check backend/` (pinned 0.8.4 +
> `backend/pyproject.toml` config — unpinned/no-config gives false UP042/F841) + ephemeral-PG
> pytest (`alembic upgrade head` first, now at migration **0021**, 21 revisions; suite = **605**);
> frontend = **`npm run build`** (`tsc -b && vite build`) + vitest (**280 passing**). Use **`npm run
> build`**, NOT `npx tsc --noEmit` — the latter uses the root `tsconfig.json` which has
> no `noUnusedLocals`/`noUnusedParameters` and misses the strict project-reference errors
> that the prod build enforces. **Worker has NO hot-reload** (restart for worker/task/scraper
> edits); backend uses uvicorn --reload.
>
> **⚠️ Render-backend gotcha (2026-07-02):** headless rendering uses the **`vtk-osmesa`** wheel
> (Kitware index `https://wheels.vtk.org`) + `libosmesa6` — NOT the stock PyPI `vtk` wheel, which is
> X11-only and silently yields `get_backend()=="none"`. Render viability is **only** verifiable in a
> **built image**: `docker exec <worker> python -c "from app.worker.render_mesh import get_backend;
> print(get_backend())"` must print `vtk`, then render a test STL. Never trust a render/Dockerfile
> change from unit tests alone.

---

## Session start order

1. **This file** — current state + gotchas.
2. **`CLAUDE.md`** — operating model + adopted-standard rules (auto-read per its own pointer).
3. **`standards.md`** — which standards/versions apply.
4. **`docs/build-plan.md`** — the phased roadmap; find the current phase.
5. **The current phase's prompt** in `prompts/` — the next executable handoff.

## Operating model (recap — full version in `CLAUDE.md`)

- This is the **central Opus planning session**. It **plans, writes handoff prompts**
  (`prompts/`), and **dispatches autonomous Sonnet subagents** to execute them, then
  reports back. The user does **not** babysit.
- **Auto-commit on `dev`** (no per-step y/n) with conventional prefixes. **`main` is
  PR-only / never direct-pushed.**
- Bigger-than-1–2-file changes → write a prompt + dispatch; don't do them inline.

## Current status

- **v0.2.5 is the latest release on `main`** (see the CURRENT STATE block above). **`dev` is AHEAD
  of `main`** — the **#15 bulk-import** feature is merged to `dev` (bulk-commit endpoint +
  `import.default_library_id` setting + inbox auto-resolution + "Commit ready" UI on `/imports`),
  unreleased. The full stack (Phases 0–10 + Aurora UI + render rework + v0.2.x hardening + #15) has shipped/queued.
- **NEXT ACTIONS:** none blocking. When the owner wants to ship what's on `dev`: `/release-prep 0.3.0`
  (minor — confirm the warn prompt; it archives 0.2.x) → merge PR → `:latest` publishes →
  `/release-cut 0.3.0` (never re-tag). **Open GitHub issues**
  (backlog): **#11** library hard-delete + move-assets-between-libraries (future); **#16** import
  wizard "Clean up (AI)" ignores a typed-but-unsaved description (frontend must PATCH the description
  before calling, or the endpoint should accept it in the body); **#20** queued worker jobs are
  invisible in the Jobs monitor (Job row only created at run-time as `running` — create it at enqueue
  as `queued`); **#21** capture the in-browser 3D viewer view as an item image (multiple captures for
  multi-part 3MF; offered in the Add Asset wizard "Try to render file", browser render preferred);
  **#24** release-notes popup on first load after upgrade. (#13 and #14 shipped in v0.2.5 and are CLOSED.)
- **🎨 Render direction (shaped this session, see #21 + #15 comments):** server auto-render stays for
  STL/OBJ/PLY (unchanged); 3MF (often no embedded thumb) → **browser viewport capture** is the answer,
  supporting **multiple captures**; offer capture **in the Add Asset wizard** ("Try to render file",
  browser render = preferred method, server-render/embedded as fallbacks); headless paths (bulk import
  #15, API) get a `render: auto|off` preference param instead (browser capture can't run headless).
  All layer via the existing `Image` + `set_default_image` model. Next: turn #21 into a build plan.
- Optional: make the 2 CodeQL checks required on `main` branch protection (still not required).
- **Deploy-readiness fix (committed):** scaffolding gap (since Phase 0) — nothing ran migrations
  on startup, so a fresh stack came up on an empty DB and the wizard failed. Fixed by **bundling
  migrations into the backend's image entrypoint** (`backend/docker-entrypoint.sh`:
  `RUN_MIGRATIONS=true` → `alembic upgrade head` → `exec "$@"`). **No separate `migrate`
  container** (a one-shot exits and reads as a broken stack in Portainer). Worker + nginx gate on
  `backend: service_healthy` (backend has a `/health` healthcheck), so migrations run exactly once
  before anything touches the DB. Also: **`docker-compose.dev.yml` is self-contained** (all
  services + build, one file) and **dev storage is bind-mounted under `./private_data/data/
  {postgres,redis,app}`** (gitignored, host-visible — no named volumes); prod keeps named volumes.
  **Run:** `cp .env.example .env` then `docker compose -f docker-compose.dev.yml up --build`
  (dev) or `docker compose up -d --build` (prod) → http://localhost:8973 first-run wizard.
- **⚠️ Deployment-readiness is an open audit item for Phase 10** — the migration gap was a miss;
  re-check the whole runnable-stack story (entrypoints, healthchecks, first-run, env) at hardening.
- **Phase 8 agent died mid-run** on an internal API error (oversized tool call in its transcript)
  after building most of 8a. Recovered via a fresh finish/verify agent (did NOT resume the dead
  one — replaying its transcript would re-hit the 400). 299 pytest on real PG, ruff, alembic
  0008 (no new migration — AiProvider predates Phase 8). 2nd infra-level interruption this
  session (Phase 4 was 1st); both recovered cleanly since nothing commits until verified.
- **⚠️ Frontend stack gotcha (caught in 7b):** the UI is **Tailwind + CSS-variable (shadcn-style)
  theme + minimal Radix (dropdown/slot) + lucide-react + TanStack Query**, and uses the
  `apiFetch`/`apiFetchForm` CSRF wrapper. **There is NO Mantine and NO toast library** — a 7a-
  written handoff wrongly said "Mantine"; corrected before dispatch. Tell future frontend
  prompts this explicitly.
- **Branch:** `dev` (work here). `main` is protected, PR-only — proven out by PR #1 (`dev`→`main`,
  merged, tagged v0.1.1). `origin/dev` is currently pushed and matches local exactly.
- **Done so far:** Phases 0–6a committed on `dev`:
  - **0** scaffolding/dev loop; **1** identity/first-run/settings; **2** libraries/storage/
    sidecar/item core (atomic rename); **3** catalog UI (FTS, tag cloud, browse, item page,
    file/ZIP downloads); **4** worker jobs + mesh rendering + job/scheduled-jobs monitor UI;
    **5** import wizard (a backend ImportSession/scraper/site-caps/tag-reconcile/inbox-scan;
    b Add Asset modal + `/import` wizard + `/imports` + `/admin/pending-tags`);
    **6a** reconcile engine **backend** — Issue/ChangeLog/ReviewItem (migration 0007), the
    `reconcile.py` engine (4 §8.1 behaviors, isolated per-item txns, daily `library_reconcile_scan`,
    `apply_review_item`), issues/changes/reviews routers; `rescan_item` refactored onto the engine.
    All checks green (214 pytest on real PG, alembic 0007 round-trip, ruff);
    **6b** reconcile **frontend** — `/admin/issues`, `/admin/changes`, `/admin/reviews`
    (approve/reject) + Reconcile-Modes Auto/Review toggles (96 vitest, tsc clean);
    **7a** print-history + sharing **backend** — PrintRecord + gcode parser (Prusa/Orca/Cura/
    Bambu) + print-stats; ShareLink (256-bit token, per-design + full-site) + ShareAuditEvent +
    public token-gated read-only endpoints; ZIP include-print-history; instance-import (completes
    Phase 5 stub). Migration 0008. **271 pytest on real PG incl. 7 private-data-leak security
    tests; alembic 0008 round-trip; ruff clean.**
  - **7b** print/sharing **frontend** — print-history section + share controls on ItemPage,
    public `/share/:token` page (outside auth guards), `/admin/print-stats`, `/admin/shares`
    audit, include-history ZIP checkbox, from-share-link import panel (tsc clean, 109 vitest);
  - **8a** AI-tagging **backend** — `app/ai/client.py` provider abstraction (anthropic SDK for
    Claude default `claude-opus-4-8`; openai SDK for OpenAI + Ollama-via-`base_url`; test-injectable
    callers), `ai_providers` CRUD + `ai_actions` (suggest-tags/cleanup/summarize) routers, Fernet
    key encryption. Best-effort: no-AI manual path proven by tests; no real provider calls in tests;
  - **8b** AI **frontend** — `/admin/ai-providers` CRUD page, wizard AI actions (suggest tags /
    cleanup / summarize, opt-in, graceful when no provider), client-side fuzzy duplicate detection
    on PendingTagsPage (tsc clean, 131 vitest). Phase 8 done.

## Phase 5 follow-ups (small; fold into a later phase)

- **`TagSummary` lacks a `status` field**, so the frontend can't distinguish pending vs. active
  tags — `/admin/pending-tags` lists ALL tags (Approve is idempotent, so it's safe but noisy).
  Add `status` to `TagSummary` + filter the page to pending-only. Good Phase 6 cleanup.
- **No `GET /api/items/by-id/{id}`** — committed-session deep-links fall back to `/catalog`
  instead of the new item. Minor; add if a by-id lookup is otherwise needed.
- **Verification gotcha (closed):** the 5a agent had no Postgres, so it could only run 6 pure
  unit tests. The orchestrator spun up an ephemeral PG (docker `postgres:16-alpine` on `:5433`,
  user/pass/db `partfolder3d`/`testpass`/`partfolder3d`) and caught **2 real bugs**: invalid
  `CREATE TYPE IF NOT EXISTS` in migration 0006 (→ `DO`-block guard) and missing
  `python-multipart` dep (app wouldn't boot). After fixes: **189 pytest passed**, alembic
  up/down/up clean, ruff/tsc/vitest green. **Lesson: bring up an ephemeral PG to verify any
  migration/DB work before committing.**
- **Phase 4 recovery note:** the Phase 4 agent hard-crashed before its verify/commit step; no
  git loss; resumed + verified + fixed 3 `render_mesh.py` bugs. Render spike **go**
  (pyrender+OSMesa CPU-only).

## Phase 4 follow-ups to confirm later (need Docker/CI, not verifiable here)

- pyrender+EGL path (Dockerfile installs `libegl1`/`libgbm1`) and OSMesa **inside** the image.
- End-to-end render wiring (item create → render job → `renders/<sha256>.png`) needs the full
  compose stack (arq worker + Redis).
- VTK offscreen does **not** work on a stock CPU host (Xlib SIGABRT); kept in the detect chain
  only for EGL/OSMesa-built VTK. See `docs/decisions.md` Phase 4 entries.

## Repo & remotes

- **Code:** GitHub [`crzykidd/partfolder3d`](https://github.com/crzykidd/partfolder3d).
  `main` protected (PRs required, 6 CI checks, no direct push). Work on `dev`.
- **Registry:** `homelab-configs` on **Gitea** (`gitea.crzynet.com`) — separate repo,
  separate remote. Its `projects/partfolder3d/` entry is committed locally but **not yet
  pushed** (see Open threads).
- `gh` is authenticated as `crzykidd`.

## Environment gotchas

- **No sandbox here** — `repo-sandbox-permissions` was intentionally not adopted, so bash
  may prompt unless the session runs in an auto-approve mode. (User runs it auto so agents
  aren't babysat.)
- **Image processing needs a venv** — system Python is PEP-668 externally-managed (pip
  blocked). A scratchpad venv with Pillow/numpy/scipy/pyyaml exists under the session
  scratchpad; recreate if gone.
- **External port `8973`** (nginx) — changeable in `docker-compose.yml`.
- **Brand colors:** teal `#0FA4AB`, navy `#091D35`. Source logo PNGs in `private_data/`
  (gitignored). Locked logo style: **flat icon, both modes** (dark = navy flat recolored
  light).

## Key file map

| Path | What |
|---|---|
| `PRD.md` | Authoritative product spec (§1–18). |
| `docs/build-plan.md` | Phased roadmap + locked build-time tech decisions. |
| `docs/decisions.md` | ADR-style decision log (newest at top). |
| `CLAUDE.md` | Operating model + adopted-standard snippets. |
| `standards.md` | Adopted standards + pinned versions + deviations. |
| `prompts/` | Handoff queue; `prompts/done/` + `prompts/failed/` archives. |
| `.claude/commands/release-{prep,cut}.md` | Release slash commands (filled + working; used for v0.1.1). |
| `.github/workflows/` | CI (`ci`, `codeql`, `publish`, `retention`). |
| `docs/images/` | Brand assets + usage README. |

## Open threads (carry these forward)

- [x] **`homelab-configs` registry entry pushed** to Gitea by the user (2026-06-27).
- [x] **`release-prep`/`release-cut` filled and proven** — used successfully for v0.1.1
      (2026-07-01).
- [ ] **Add the 2 CodeQL contexts to `main` required status checks** — they now run (first CodeQL
      pass was on the v0.1.1 PR, 36 alerts triaged) but branch protection's
      `required_status_checks` still only lists the original 6 CI jobs. Owner action.
- [x] **Render / asset-detail rework landed on `dev`** (2026-07-02, 5 commits `247dfa6`→`5797b0c`) —
      3MF read-not-render, ZIP auto-extract, file-tree + 3MF collapsible UI, in-browser three.js
      viewer, vtk-osmesa render fix. Verified against a rebuilt image (see CURRENT STATE).
- [x] **v0.2.5 released** (2026-07-02) — #13 auto-login + #14 default-image + CodeQL log-injection fix.
      Both #13 and #14 CLOSED. **#15 bulk import merged to `dev`** (merge `0952358`) — queued for v0.3.0.
- [ ] **Ship what's on `dev` as v0.3.0** when the owner wants — `dev` is ahead of `main` by #15 + the
      overnight batch (#16/#17/#18/#19/#21/#24/#11 + #15 render param). Minor bump; `/release-prep 0.3.0`.
- [ ] **Open GitHub issues** (backlog): **#11** library hard-delete + move-assets (future); **#16**
      import "Clean up (AI)" ignores typed-but-unsaved description; **#20** queued jobs invisible in the
      monitor; **#21** capture 3D viewer view → item image (multi-capture; wizard "Try to render file",
      browser preferred); **#24** release-notes popup after upgrade. Render direction shaped — see the
      Current-status "🎨 Render direction" note; **next: turn #21 into a build plan** + add the #15
      `render` param.
- [ ] **Re-verify on the owner's prod deploy after upgrading to 0.2.5:** first-run auto-login (#13)
      lands you in the app; import "set default image" (#14) sticks. (0.2.4: dark-mode dropdowns +
      NFS image display already confirmed.)
- [ ] **Rotate the AgentQL API key** (owner pasted it in chat during earlier testing).
- [ ] **PRD §18 remaining notes** to honor when relevant: move journaling/crash recovery,
      real slicing for filament estimates, trash purge UI (see OPEN ITEMS above for detail).

## Before-`/clear` checklist

1. Update **Last updated** date + **Current status** (phase, what just finished, next action).
2. Update **Open threads** (tick done, add new).
3. Ensure any in-flight handoff prompt's frontmatter + `prompts/done|failed/` placement is
   correct, and decisions went into `docs/decisions.md`.
4. Confirm work is committed on `dev` (and note anything intentionally uncommitted here).
