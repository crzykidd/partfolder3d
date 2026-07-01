---
name: 2026-06-27-phase-3-catalog-ui
status: completed
created: 2026-06-27
model: sonnet
completed: 2026-06-27
result: Phase 3a backend complete — favorites, FTS, tag browse/tree, creator browse, My Creations, file/ZIP downloads, set-default-image, path-prefix; 157 tests pass; 3b frontend handoff written.
---

# Task: Phase 3 — Catalog UI (search, browse, item page)

Make the catalog usable in the browser, on top of the Phase 2 item core. This is
**Phase 3** of [`docs/build-plan.md`](../docs/build-plan.md).

**Exit criteria (build plan):** browse/search/filter; open an item; set its default image;
download a file and a ZIP.

## Before you start

- Read [`docs/build-plan.md`](../docs/build-plan.md) **Phase 3** + the **Locked build-time
  technical decisions** (frontend: Vite+React18+TS+Tailwind+shadcn; **TanStack Query**,
  **React Router**, **TanStack Table** (table view), **TanStack Virtual** (large lists)).
- Read [`PRD.md`](../PRD.md) §3.3 (path display + prefix rewrite + copy), §5.1–5.2 (tag
  structure + **virtual tag tree**, default depth **4**, configurable), §11 (Download +
  **queued ZIP**, ~1-day expiry + invalidate-on-change), §12 (Search & Browse UI), §4
  (Favorite, Creator).
- Read [`CLAUDE.md`](../CLAUDE.md) operating rules.
- Read the existing backend (Phase 2 `routers/items.py`, `routers/libraries.py`,
  `storage/`, `models/`) and frontend (Phase 1 `lib/api.ts`, `context/AuthContext.tsx`,
  `components/AppShell.tsx`, `pages/`, the TanStack Query patterns) so you extend them
  idiomatically.

## Working tree check

Run `git status --porcelain`. Expect a clean tree on `dev` (only this prompt file may be
untracked). Surface anything unexpected before proceeding.

## Scope & split guidance

Large and frontend-heavy. Do the **backend API first and completely**, then the UI. If the
whole phase is too big for one clean, well-tested pass, **STOP after the backend and report
a 3a/3b split** — `3a` = search + favorites + creator-browse + downloads/ZIP + set-default +
path-prefix API; `3b` = the catalog UI — writing the `3b` handoff from `prompts/TEMPLATE.md`.

**Out of scope (do NOT build — later phases):** thumbnail **rendering** (Phase 4 — grid/
table just use existing images + a placeholder); **print history** and **share links**
(Phase 7 — leave clearly-marked placeholders on the item page, build nothing); tag
**reconciliation**/alias-matching/approval-queue and the **import wizard** (Phase 5); AI
(Phase 8). The print-history-in-ZIP checkbox (§11) is **stubbed off** here (no PrintRecord
model yet) — a plain ZIP of the item dir's files/images only.

## What to do — backend (3a)

### 1. Favorites
- **Favorite** model (User ↔ Item, unique) + migration `0004`. Endpoints: star/unstar;
  list "my favorites"; and a `favorited` flag + filter/sort option on item listing.

### 2. Full-text search
- PostgreSQL full-text over **title + description + tag names** (a `tsvector`, ideally a
  generated/maintained column with a GIN index; keep tags in sync on tag attach/detach).
- `GET /api/items` gains: `q` (search), tag filter (stackable, AND), `creator` filter,
  `favorites` filter, sort options, pagination. Document the query contract.

### 3. Tag browse
- `GET /api/tags` — tag list with popularity counts (click-to-search drives the `q`/tag
  filter).
- `GET /api/tags/tree` — the **virtual tag tree** derived from most-used tags in order,
  depth from a **configurable setting (default 4)**. Pure DB/UI construct (no disk
  hierarchy).

### 4. Creator browse + My Creations
- `GET /api/creators` / `GET /api/creators/{id}/items` — browse a creator's models.
- `GET /api/me/creations` — items whose Creator is linked to the current user (the
  **"My Creations"** view, per [`creator`](../docs/sidecar-schema.md) rules).

### 5. Downloads
- **Single file:** `GET /api/items/{key}/files/{...}` streams a file (stream via the app;
  the compose nginx can be configured later for X-Accel — not required now). Guard against
  path traversal (resolve within the item dir only).
- **Queued ZIP:** enqueue a ZIP build of the item dir on the **existing arq worker** (from
  Phase 0 — do NOT build Phase 4's general Job model/monitor). Track a lightweight
  **download bundle** (small table or Redis + on-disk artifact under `/data/zips/`):
  `POST /api/items/{key}/zip` → returns a bundle id/status; `GET …/zip/{id}` polls →
  `ready` streams the file. **Expire after ~1 day** and **invalidate immediately when
  anything in the item dir changes** (compare against the item's file inventory/hashes) so a
  download never serves stale contents.

### 6. Item detail extras
- `PATCH /api/items/{key}/default-image` (set default image from the item's images).
- **Per-user `path_prefix` setting** (like theme; e.g. `C:\prints\`): store per-user; the
  API returns the canonical full dir path, the **UI** does the prefix rewrite + copy.

## What to do — frontend (3b)

### 7. Catalog browse
- Search bar (drives `q`); **tag list** + click-to-search + stackable filters; **virtual
  tag tree** (depth from setting) for browse. **Table view** (TanStack Table) and **grid
  view** (image cards) with a toggle; **TanStack Virtual** for large result sets.
- **Favorites:** star/unstar on cards/rows; filter + sort by favorites.
- **Creator:** click a creator → their models; a **"My Creations"** nav entry.

### 8. Item page
- Image **carousel** (scroll + **set default**), full metadata, tags (click-to-search),
  **creator (linked)**, source link, license, **full dir path + prefix-rewrite + copy
  button** (§3.3), **downloads** (individual files + **queue ZIP** with progress/poll).
- Clearly-marked **placeholders** for Print History and Sharing (built in Phase 7) — no
  functionality.

### 9. Settings + tests
- Settings: tag-tree **depth** (admin/instance) + per-user **path prefix**.
- `npx tsc --noEmit` clean; **vitest** for non-trivial logic (search query state, tag-tree
  rendering, ZIP poll state machine, path-prefix rewrite); keep existing tests green.

## Conventions to honor

- Match locked decisions + existing Phase 0–2 structure. No out-of-scope features (above).
- TanStack Query for all server state; no manual fetch outside `lib/api.ts`. CSRF on all
  cookie-auth state-changing calls; Bearer exempt.
- Secrets out of the repo; document new env in `.env.example`.
- Verify locally: `ruff check backend/`, `pytest`, `npx tsc --noEmit`, `vitest`,
  `alembic upgrade head` + `downgrade base` (ephemeral Postgres), `docker compose config
  --quiet` (+ dev override). Keep CI green; note anything you couldn't verify.

## When done

1. Update frontmatter (`status`, `completed: 2026-06-27`, one-line `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`); if you split, write the `3b`
   handoff.
3. Add `docs/decisions.md` entries (newest at top) for non-obvious calls (search column
   strategy, tag-tree derivation, ZIP bundle tracking + invalidation, download streaming).
4. **You are a spawned agent: do NOT commit, push, or change branch.** Prepare the tree and
   **report back** with: complete file list; proposed one-line `feat:` commit message; exact
   local check results (ruff/pytest/tsc/vitest/alembic up+down/compose); full phase vs split
   (+ 3b path + remaining); any decision made or thing you couldn't verify.
