---
name: 2026-06-27-phase-7-print-history-sharing
status: completed
created: 2026-06-27
model: sonnet            # coding against a locked plan
completed: 2026-06-27
result: Phase 7a backend complete — PrintRecord + gcode parser + stats + ShareLink + public endpoints + audit + instance-import; 271/271 tests pass; frontend split to 2026-06-27-phase-7b-frontend.md
---

# Task: Phase 7 — Print history + sharing

Add **print records** (notes, gcode with parsed filament/time, photos, structured settings) +
**print stats**, and **sharing** (per-design + full-site tokenized public read-only links with
expiry/revoke + access audit), wire **download-includes-print-history**, and **complete Phase
5's instance-import stub** (granular public-history pull). This is **Phase 7** of
[`docs/build-plan.md`](../docs/build-plan.md) and PRD **§9, §10, §11**.

**Exit criteria (build plan):** log a print, see stats; mint a share link, open it logged-out,
download; audit shows access; another instance can ingest a share link.

## Before you start

- Read [`docs/build-plan.md`](../docs/build-plan.md) **Phase 7** + the **Locked build-time
  technical decisions**.
- Read [`PRD.md`](../PRD.md): **§9** (print history — notes + private/public, §9.1 gcode
  best-effort parse for **filament length/weight + estimated time** across Prusa/Orca/Cura/
  Bambu, §9.2 stats, §9.3 external sources via API), **§10** (sharing — per-design + full-site
  links, public read-only exposes images/description/public-tags/**public** notes + file/zip
  download, **private notes hidden**; default expiry setting, revocable; machine-ingestible for
  instance import with **granular public-history pull**; **share audit** = creation/expiry/
  revocation + **access events**), **§11** (download — individual + ZIP, **include-print-history
  checkbox OFF by default**, private records only for the owner's own logged-in download, never
  on public links; ZIP expiry + invalidate-on-change).
- Read [`CLAUDE.md`](../CLAUDE.md) operating rules and [`docs/decisions.md`](../docs/decisions.md).
- **Read the existing code you will build on / reuse — do NOT reinvent it:**
  - `backend/app/routers/downloads.py` — `download_file`, `queue_zip`, `poll_or_download_zip`,
    `_compute_inventory_hash`. The ZIP-with-history option **extends** this.
  - `backend/app/models/download_bundle.py` + `backend/worker.py` `build_zip_bundle` —
    the ZIP build task (writes to `DATA_DIR/zips/`); add the include-history behavior here.
  - `backend/app/storage/inventory.py` — `prints/` dir already classified into **gcode** and
    **photo** roles; gcode uploads land there.
  - `backend/app/routers/import_sessions.py` — the **`/api/import-sessions/from-share-link`
    501 stub (line ~1091)**; Phase 7 implements it. Reuse the existing import-session commit
    path for the ingested design.
  - `backend/app/storage/keys.py` / the API-key + site-token patterns — for **unguessable
    share tokens** and any stored secrets.
  - `backend/app/auth/deps.py` — auth deps; **public share endpoints are UN-authenticated** but
    token-gated; everything else stays admin/owner-gated.
  - `backend/worker.py` `SCHEDULED_JOB_REGISTRY` — for a share-link **expiry cleanup** job if
    you add one.
  - Frontend: item page (`ItemPage.tsx`), `frontend/src/lib/api.ts`, routing in `App.tsx`,
    admin pages — for print-history UI, share controls, audit view, and the public page.

## Working tree check

`git status --porcelain` — expect a clean tree on `dev` (only this prompt untracked). Phase 6
is committed (`0797fbf`). Surface anything unexpected before proceeding.

## Scope & split guidance

**Very large — plan to split.** Default split is **backend (7a) first and completely**, then
**frontend (7b)**. **If the backend alone is too big for one clean pass, STOP after the
print-history backend** (PrintRecord + gcode parse + stats + ZIP-history) and write a handoff
for the **sharing** backend + all frontend. Use your judgment; **never half-build**. Whatever
you stop short of, write a precise handoff prompt for it and report the split.

**Out of scope (later phase) — do NOT build:** **AI** (Phase 8). Everything else in §9–11 is
in scope for Phase 7 (across 7a/7b/splits).

## What to do

### 1. Print history (PRD §9)
- **PrintRecord** model + migration (next number, **0008**): item FK, **note** + **visibility
  (private/public)** + **date** + logging-user FK; optional **structured settings** (printer,
  material/filament, nozzle, layer height, supports, success/fail, rating); attached **gcode/
  3mf** stored in the item's `prints/` dir; **print photo** (separate from renders) in
  `prints/`. All fields optional but supported. `alembic upgrade head` + `downgrade base` pass.
- **gcode metadata parse (§9.1)** — on gcode upload, parse slicer header comments **best-effort**
  for **filament required (length/weight)** and **estimated print time**; store on the record;
  handle Prusa/Orca/Cura/Bambu variance — fields present when found, gracefully absent otherwise.
  Pure, unit-tested parser with fixtures for each slicer dialect.
- **Print stats (§9.2)** — aggregate view: total prints, success/fail rate, filament used,
  total/avg print time, most-printed items.
- CRUD API for print records (create/list/update/delete), owner/admin gated; **§9.3** create-
  via-REST-API path so external integrations (OctoPrint) can auto-log.

### 2. Download: include-print-history (PRD §11)
- Extend the ZIP build with an **include-print-history checkbox, OFF by default**: when on,
  bundle **public** notes/settings + gcode + print photos. The owner's **private** records are
  included **only** for their own logged-in download — **never** on a public share-link
  download. Keep the existing expiry + invalidate-on-change behavior.

### 3. Sharing (PRD §10)
- **ShareLink** model + migration: **unguessable token**, scope (**per-design** → item FK, or
  **full-site/catalog** admin-only), **expiry** (admin default-expiry setting, overridable per
  link), **revoked** flag, creator + timestamps. Tokens never reversible to internal ids.
- **Public read-only endpoints (UN-authenticated, token-gated):** view a shared design
  (images, description, **public** tags, **public** print notes — **private hidden**) and
  **download files/ZIP**. A full-site link exposes a read-only browse of the catalog. Enforce
  expiry + revocation **server-side** on every request. **No private data ever leaks** through
  a public link — this is the critical security property; test it explicitly.
- **Share audit (§10):** record creation (who/when), expiry, revocation, and **access events**
  (timestamp, IP/user-agent where available, **view vs. download**). Admin-reviewable.
- Admin/owner API to **mint / list / revoke** links and **review the audit**.

### 4. Instance-to-instance import (completes Phase 5 stub)
- Implement `POST /api/import-sessions/from-share-link`: given another instance's share link,
  fetch the design's **metadata + files** and create an import session that reconciles against
  this library's settings + canonical tags (reuse the Phase 5 commit path). The wizard **asks
  whether to pull public print history**, granular: **public notes / gcode / print photos /
  structured settings** (default: notes + photos; ask before large gcode). **Private records
  never transfer.** Network fetch must be mockable/testable without hitting a live instance.

### 5. Frontend — MAY SPLIT TO 7b
- **Item page print history**: list records (public/private badge), add/edit/delete, gcode +
  photo upload, show parsed filament/time, structured settings.
- **Print stats** view.
- **Share controls** on the item page (mint per-design link, set/override expiry, revoke, copy)
  + admin **full-site** link management + **share audit** view.
- **Public share page** (logged-out): read-only design view + downloads; full-site browse.
- **Download** UI: the include-print-history checkbox.
- **Instance import**: the from-share-link entry in the import wizard + the granular
  print-history pull choices. `npx tsc --noEmit` clean; vitest for non-trivial logic.

## Conventions to honor

- Match locked decisions + existing Phase 0–6 structure; **reuse** downloads/ZIP, inventory,
  import-session commit, auth, settings, and the job/scheduled-job framework.
- **Security is the headline for this phase:** public endpoints are token-gated and read-only;
  expiry/revocation enforced on every request; **private notes/records never exposed** on
  public links or instance exports. Tokens are unguessable. Add explicit tests for these.
- A failing parse/share/import **degrades gracefully and is visible** — never crashes the
  worker, leaks data, or corrupts the library. Network (instance import) is mockable/off in
  unit tests.
- Secrets out of the repo; document new env/settings (share default-expiry, etc.) in
  `.env.example` (or as DB settings — say which).
- Verify locally what you can: `ruff check backend/`, `pytest`, `npx tsc --noEmit`, `vitest`,
  `alembic upgrade head` + `downgrade base`, `docker compose config --quiet`.
  **Bring up an ephemeral Postgres** for the migration + async DB tests (do this for every
  schema phase):
  `docker run -d --name pf3d-test-pg -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p 5433:5432 postgres:16-alpine`
  then `export DATABASE_URL="postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d"`,
  run `alembic upgrade head && alembic downgrade base && alembic upgrade head`, then `pytest`.
  Recreate the scratchpad venv at
  `/tmp/claude-1000/-home-manderse-projects-partfolder3d/bd4b77b1-dcc4-4fbf-8dc0-d3990161f59a/scratchpad/venv`
  if gone (system Python is PEP-668; pip-install requirements.txt incl. `python-multipart`,
  plus ruff/pytest). Tear the container down when done.

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-27`, one-line `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`); **for whatever you split off, write the
   handoff** (`prompts/2026-06-27-phase-7b-*.md`, and any further split) describing exactly the
   remaining scope.
3. Add `docs/decisions.md` entries (newest at top): PrintRecord + ShareLink + audit model
   shapes, the gcode-parse approach + which slicer headers, the share-token scheme + how
   public/private separation is enforced, the access-event capture, the include-history ZIP
   rule, and the instance-import fetch/granular-pull design.
4. **You are a spawned agent: do NOT commit, push, or change branch.** Prepare the tree and
   **report back** with: complete file list; proposed one-line `feat:` commit message; exact
   local check results (incl. the ephemeral-PG migration round-trip + pytest count); exactly
   what is complete vs. split (+ handoff paths + what remains); the **security tests** you added
   proving no private-data leak on public links; any decision made or thing you could not verify.
