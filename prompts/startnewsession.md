# Start-new-session — PartFolder 3D

**Read this first when you (re)open this project.** It carries the project-specific,
fast-moving context that does **not** live in `CLAUDE.md` (which holds the durable
standards/operating rules). Keep them separate: rules in `CLAUDE.md`, live state here.

> 🔄 **UPDATE THIS FILE BEFORE EVERY `/clear`.** Before clearing context, refresh the
> "Current status" and "Open threads" sections so the next session loses nothing. This is
> a deliberate ritual — see the checklist at the bottom.

**Last updated:** 2026-06-28 (UI A1+A2 committed `3ca51e2`,`3915af7`; B1 catalog/item restyle in flight)

> **UI REVAMP underway (owner-directed, autonomous run).** Owner chose **Aurora** (`/example3`)
> as the real look. Locked spec:
> - **Theme:** Aurora, cohesive across both layouts, dark + light. Examples KEPT (not deleted).
> - **Nav:** per-user setting `nav_layout` (server-side, like theme pref); **default by role:
>   admin→sidebar, others→top-bar**; user-menu toggle overrides; ONE shared `navConfig` →
>   `TopNavShell` + `SideNavShell`.
> - **Two customizable regions (one widget framework):** (1) **top stat strip** = customizable
>   stat tiles, role-based defaults, user-addable, flexible sizing/rows (admin may want 2 rows of
>   smaller tiles); (2) **right rail** = collapsible widget panel, add/remove/reorder, **default
>   = Quick Import widget**, extensible registry. Per-user layout persisted server-side; real data.
> - **Phasing:** A1 = Aurora shell + switchable nav + version/release-notes + default stat strip +
>   Quick Import rail (real data, functional, not-yet-customizable). A2 = the widget framework
>   (make both regions customizable). B = restyle real pages (catalog/item/import/admin) to Aurora.
> - Reference screenshot the owner circled: `private_data/screenshot/` (right Quick-Import panel
>   = the future widget rail).

> **Phase 10a hardening landed** (`a2b612b`): fixed **2 HIGH SSRF holes** (scraper + instance
> import now block internal/link-local/metadata IPs via `backend/app/storage/ssrf_guard.py`);
> verified path-traversal/admin-gating/share-privacy/key-masking (tests added); migration **0010**
> adds 8 hot-path indexes; **356 pytest** (DNS-rebinding SSRF variant deferred + documented;
> 100k load-test deferred — needs a seed harness).

> **Release machinery still UNFILLED (Phase 10b, orchestrator to do after 10a):** version
> source-of-truth (only `frontend/package.json`=0.1.0 today; no bare VERSION file), the
> `.claude/commands/release-{prep,cut}.md` placeholders (36 + 17), and there's no `CHANGELOG.md`.
> Fill these to make `/release-prep` + `/release-cut` functional. **Do NOT cut the release**
> until after the UI revamp + explicit owner go.

> **UI prototypes for owner review** are live at `/examples`, `/example1` (Mission Control —
> dense dark left rail), `/example2` (Atelier — airy light top-nav + Radix dropdowns),
> `/example3` (Aurora — glassy dark + ⌘K palette). Public mock routes (no auth), under
> `frontend/src/pages/examples/`. Owner picks one → revamp real pages to match, then delete the
> losers. Requirements captured: collapsible localStorage sidebar, expand/collapse groups,
> role-based menus, version + release-notes bottom-left.

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

- **ALL PHASES 0–10 COMPLETE** on `dev`. Full app built + hardened. **Full test pass GREEN**
  (2026-06-28): **356 backend pytest** (real PG, alembic at `0010`), **ruff clean**, **131 vitest**,
  **tsc clean**, both compose configs valid. Latest: Phase 9 (`930a075`/`da49b50`), Phase 10a
  hardening (`a2b612b`), Phase 10b release-machinery (`867c460`).
- **NEXT ACTIONS (awaiting owner):**
  1. **Pick a UI theme** from `/examples` (`/example1` Mission Control, `/example2` Atelier,
     `/example3` Aurora) → then **UI revamp**: restyle real pages to the chosen direction (left/
     top nav, collapsible groups, role-based menu, version+release-notes), delete the losing
     prototypes under `frontend/src/pages/examples/`. This is the main remaining build.
  2. **Cut v1** when owner gives the go: `/release-prep <version>` → review/merge PR → wait for
     main CI green + `:latest` published → `/release-cut <version>`. Machinery is filled + ready
     (version source `backend/app/version.py`=0.1.0). **Held for explicit go** (outward-facing).
- **Release/UI both DEFERRED to owner.** Do NOT cut the release or push to main without the go.
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
- **Branch:** `dev` (work here). `main` is protected. Nothing pushed/PR'd yet (no dev→main
  until a working product exists).
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
| `.claude/commands/release-{prep,cut}.md` | Release slash commands (parked; placeholders unfilled). |
| `.github/workflows/` | CI (`ci`, `codeql`, `publish`, `retention`). |
| `docs/images/` | Brand assets + usage README. |

## Open threads (carry these forward)

- [x] **`homelab-configs` registry entry pushed** to Gitea by the user (2026-06-27).
- [ ] **After Phase 0 CI is green:** add `CodeQL / Analyze (python)` +
      `CodeQL / Analyze (javascript-typescript)` to `main` required status checks (deferred
      because CodeQL errors on an empty source tree).
- [ ] **Remove remaining CI bootstrap guards** per-piece as later phases add them.
- [ ] **`release-prep`/`release-cut` placeholders** stay parked until a version file + CI
      exist (Phase 0 adds the version file; fill at first release).
- [ ] **PRD §18 remaining notes** to honor when their phase arrives: instance-encryption-key
      provisioning/rotation (Phase 1), move journaling/crash recovery (Phase 2/6), title
      sanitization (Phase 2).

## Before-`/clear` checklist

1. Update **Last updated** date + **Current status** (phase, what just finished, next action).
2. Update **Open threads** (tick done, add new).
3. Ensure any in-flight handoff prompt's frontmatter + `prompts/done|failed/` placement is
   correct, and decisions went into `docs/decisions.md`.
4. Confirm work is committed on `dev` (and note anything intentionally uncommitted here).
