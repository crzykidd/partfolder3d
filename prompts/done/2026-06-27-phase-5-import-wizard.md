---
name: 2026-06-27-phase-5-import-wizard
status: completed
created: 2026-06-27
model: sonnet
completed: 2026-06-27
result: >
  Phase 5a (backend) complete: ImportSession/ImportSessionFile/ImportSessionImage/
  SiteCapability/SiteToken models + migration 0006; scraper (httpx+selectolax,
  robots.txt); tag reconciliation + pending-tag approval; import sessions CRUD +
  commit (reusing create_item helpers); inbox scan + process_import_session arq
  tasks; site-capability endpoints with Fernet-encrypted token storage; share-link
  stub (501). Frontend split to prompts/2026-06-27-phase-5b-frontend-wizard.md.
---

# Task: Phase 5 — Import / inbox wizard

Build the **core intake flow end-to-end**: a user can drop a folder in the inbox **or** use
"Add Asset", run an import **wizard** (title-correctable, sidecar/scrape pre-fill, tag
reconciliation, creator capture, render), and **commit** a finished item — with tags, images,
a render, and a sidecar — at the right on-disk path the first time. This is **Phase 5** of
[`docs/build-plan.md`](../docs/build-plan.md).

**Exit criteria (build plan):** drop a folder OR use Add Asset → wizard → committed item with
tags, images, render, sidecar at the right path.

## Before you start

- Read [`docs/build-plan.md`](../docs/build-plan.md) **Phase 5** + the **Locked build-time
  technical decisions**.
- Read [`PRD.md`](../PRD.md) **§6 (Import / Inbox)** in full — §6.1 intake methods, §6.2 the
  import wizard as a **job that drives a completion wizard** (the inbox case enqueues a job
  that **surfaces the wizard rather than auto-finalizing**), §6.3 **site-capabilities** table
  + site-setup. Also **§5.3 tag reconciliation**, **§5.1** (aliases + **new-tag approval
  queue** — `TagStatus.pending`), **§4 Creator** ("my own design" → current user), **§7**
  (render on import), **§3.2/§3.3** (storage/paths — files are **moved**, never tag-organized).
- Read [`CLAUDE.md`](../CLAUDE.md) operating rules and [`docs/decisions.md`](../docs/decisions.md).
- **Read the existing code you will build on / reuse — do not reinvent it:**
  - `backend/app/routers/items.py` — `create_item` and its helpers
    (`_get_or_create_tag`, `_attach_tags`, `_build_sidecar_data`, `_write_item_sidecar`,
    `_apply_file_records`, `_enqueue_render`). **The wizard commit must finalize through this
    same path** so a committed import is indistinguishable from a normal item.
  - `backend/app/models/tag.py` — `Tag`, `TagStatus` (incl. `pending`), `TagAlias`,
    `ItemTag`. The alias + approval-queue **schema already exists**; Phase 5 wires the
    reconciliation logic and the approve flow on top.
  - `backend/app/models/creator.py` — `Creator` (`name`, `slug`, nullable `user_id`).
  - `backend/app/storage/sidecar.py` — `read_sidecar`, `build_sidecar`, `write_sidecar`,
    `SidecarData`/`SidecarCreator`/`SidecarFile`/`SidecarImage`.
  - `backend/app/storage/{paths.py,journal.py,inventory.py}` — path assignment + the
    **atomic-move journal** (Phase 2). Inbox files are **moved** into the library at commit
    via the journal, never copied/duplicated.
  - `backend/worker.py` + `backend/app/worker/` — the Phase 4 arq job model, `job_tracker`,
    and `scheduled_job` registry. The import wizard is a **job**; the inbox scan is a
    **scheduled job** (reuse the Phase 4 framework, incl. run-now).
  - Frontend `frontend/src/pages/admin/*`, `frontend/src/lib/api.ts`, routing in `App.tsx`
    — for the wizard/Add-Asset/inbox UI and the API client.

## Working tree check

`git status --porcelain` — expect a clean tree on `dev` (only this prompt untracked). Phase 4
is committed (`82e5f0a`). Surface anything unexpected before proceeding.

## Scope & split guidance

**Large — plan to split.** Do the **backend (5a) first and completely**; the **frontend
wizard/Add-Asset/inbox UI (5b)** may split to a `2026-06-27-phase-5b-*.md` handoff. If the
backend is a clean full pass but the frontend won't fit, **STOP after the backend, write the
5b handoff, and report.** Mirror how Phase 4 split.

**Out of scope (later phases) — do NOT build:**
- The full **scan/reconcile engine**, **Issues**, **Change Log**, **Auto vs. Review**, and
  **bidirectional sidecar⇄DB sync** — Phase 6. (Phase 5 only *reads* a sidecar to pre-fill an
  import, and *writes* one at commit via the existing path.)
- **AI** tagging/suggestions — Phase 8. Phase 5 is the **without-AI** reconciliation path
  (alias/existing-tag matching + manual required-tags); AI hooks are optional and deferred.
- **Import from another instance's share link** (§6.1.4) — **stub only** here (endpoint/UI
  placeholder that clearly says "coming in Phase 7"); completed in Phase 7.
- Per-site rendering add-ons; print history; sharing.

## What to do

### 1. Import session / staging model (backend core)
- A staging entity (e.g. **`ImportSession`** + child file/image rows, or a JSON-payload Job —
  pick the cleaner fit and record the choice) that holds an in-progress import **before** an
  Item exists: uploaded/dropped file references, scraped + sidecar metadata, **suggested
  title** (editable), candidate images, reconciled-tag state, candidate creator, source URL,
  and status. **The item directory is NOT created/named until commit** (§6.2) — a corrected
  title must yield the right path the first time.
- Migration (next number, **0006**). Wire models into `models/__init__.py`. `alembic upgrade
  head` **and** `downgrade base` must both pass.

### 2. Intake methods (§6.1)
- **Add Asset upload** — endpoint(s) to create an import session by uploading file(s), with
  the §6.1.2 fields (optional source URL, optional description/license/images, optional
  creator **or** "my own design" toggle, tags). Multipart upload to a staging area.
- **Inbox folder watcher/scan** — a **scheduled job** (default daily, **run-now**-able via the
  Phase 4 framework; inotify is a later enhancement — a periodic scan is fine) that scans the
  configured inbox dir; **each subfolder = one pending import**. Detect model files + a
  URL/link file + an optional **sidecar from another instance**; enqueue an import job that
  **surfaces the wizard** (does **not** auto-finalize). Make the inbox path configurable
  (`.env.example` + `config.py`); be safe on partial/in-progress folders (don't ingest a
  folder mid-write — e.g. settle/mtime check).
- **Source-URL-only** intake — create a session from just a URL (scrape per §6.3).

### 3. URL scrape + site capabilities (§6.3)
- Fetch **public metadata/images/tags/license/creator where permitted** for a source URL. Add
  the HTTP/parse deps to `backend/requirements.txt` (e.g. `httpx` + a lightweight HTML parser
  such as `selectolax` or `beautifulsoup4`). **Respect robots/ToS** (§6.3 legal note): default
  to scraping only public metadata/images; **files** rely on user-supplied tokens or manual
  drop — do **not** auto-download gated files.
- **Site-capabilities table** — learned per **domain**: anonymous image/file fetch allowed?
  token supported? files require manual upload? Probe + record on first hit; reuse thereafter.
  Migration + model for this (same 0006 or a sibling — your call, record it).
- **Site-setup flow** (backend side): when a domain needs auth, expose state so the UI can
  prompt for a token or tell the user to supply files manually. Store tokens **encrypted**
  using the existing instance-key mechanism (`storage/keys.py`); never commit secrets.

### 4. Tag reconciliation (§5.3, without-AI path)
- On import: (1) read **sidecar** tags first; (2) **alias-map** source/scraped tags onto
  canonical `Tag`s via `TagAlias`; (3) unknown tags become **suggestions** the user can
  accept → land in the **approval queue** (`TagStatus.pending`) rather than instantly
  canonical; (4) **enforce required tags** — the wizard cannot commit without them. **The
  manual path must always work** (user can type/select tags directly).
- Add the **approve-pending-tag** admin action if not already present (so pending tags from
  imports can be promoted to canonical). Keep it minimal.

### 5. Creator capture (§4)
- Capture a creator from sidecar/scrape, **deduped against existing `Creator`s** (by
  name/slug); OR a **"this is my own design"** toggle that attributes the item to the
  **current user** (`Creator.user_id`). Reuse the Phase 1/3 creator handling — don't fork it.

### 6. Commit / finalize
- A **commit** endpoint that finalizes an import session into a real Item **through the
  existing `create_item` path** (or the shared helpers it uses): assign the storage path from
  the **confirmed** title, **move** staged/inbox files into the library via the **journal**,
  attach tags + creator + images + default image, **write the sidecar**, and **enqueue the
  render** (Phase 4). Clean up the staging area. A failed commit must not leave a half-created
  item dir or a corrupt journal state — lean on the journal's roll-forward.

### 7. API (admin/authenticated; reuse Phase 1 auth deps)
- Import sessions: create (Add Asset upload / URL), list pending, get one, patch
  (title/tags/creator/default-image/required-tag fixes), **commit**, discard/cancel.
- Site capabilities: list/get per domain; set token / mark manual-only (site-setup).
- Inbox: trigger scan (run-now) + list detected pending imports (may reuse the sessions list).
- Share-link import: **stubbed** endpoint that returns "not yet (Phase 7)".

### 8. Frontend — MAY SPLIT TO 5b
- **Add Asset** button + upload modal (drag-drop file(s) + the §6.1.2 fields).
- **Import wizard** UI (job-driven, poll): steps for **title correction**, image scroll +
  **set default image**, **tag reconciliation** (accept aliased/suggested, satisfy required,
  manual entry), **creator** (pick/dedupe or "my own design"), source URL/scrape result; final
  **commit**. Surfaced for both Add-Asset and inbox-detected imports.
- **Inbox / pending-imports** list (detected folders awaiting the wizard).
- **Site-setup** prompt (enter token / accept manual-files).
- Extends Phase 3/4 UI; `npx tsc --noEmit` clean; vitest for non-trivial logic.

## Conventions to honor

- Match locked decisions + existing Phase 0–4 structure; **reuse** the item-create, sidecar,
  journal, tag, creator, and job/scheduled-job code rather than duplicating it.
- A failing import/scrape **marks the job/session failed and is visible** — it must **not**
  crash the worker or corrupt the library. Scrape failures degrade to the manual path.
- Secrets out of the repo; document new env (inbox path, scrape limits, etc.) in
  `.env.example`. Tokens encrypted via the instance key.
- Verify locally what you can: `ruff check backend/`, `pytest`, `npx tsc --noEmit`, `vitest`,
  `alembic upgrade head` + `downgrade base` (ephemeral Postgres), `docker compose config
  --quiet`. Recreate the scratchpad venv at
  `/tmp/claude-1000/-home-manderse-projects-partfolder3d/bd4b77b1-dcc4-4fbf-8dc0-d3990161f59a/scratchpad/venv`
  if gone (system Python is PEP-668; ruff/pytest are not global). Say explicitly what can only
  be confirmed in Docker/CI (e.g. live scraping of real sites).

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-27`, one-line `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`); **if you split, write the 5b handoff**
   (`prompts/2026-06-27-phase-5b-*.md`) describing exactly the remaining frontend scope.
3. Add `docs/decisions.md` entries (newest at top): import-session model shape (staging entity
   vs. job-payload), inbox-scan mechanism + safety, scrape library + robots/ToS stance,
   site-capabilities/token-encryption approach, tag-reconciliation/approval flow, and how
   commit reuses the `create_item` path + journal.
4. **You are a spawned agent: do NOT commit, push, or change branch.** Prepare the tree and
   **report back** with: complete file list; proposed one-line `feat:` commit message; exact
   local check results; full-phase vs. split (+ 5b path + what remains); any decision made or
   thing you could not verify (e.g. live scraping).
