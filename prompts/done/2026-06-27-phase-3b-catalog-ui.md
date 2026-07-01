---
name: 2026-06-27-phase-3b-catalog-ui
status: completed
created: 2026-06-27
model: sonnet
completed: 2026-06-27
result: Built catalog browse (popularity tag cloud, virtualized grid, TanStack Table), item detail page (carousel, ZIP poll, path-prefix rewrite, downloads), creator browse, my creations, nav entries, path-prefix settings, and vitest tests; removed obsolete tag-tree backend endpoint and tests (155 passing).
---

# Task: Phase 3b — Catalog UI (browse, item page, downloads, path prefix, settings)

Build the browser-facing catalog UI for Phase 3, wiring up the Phase 3a backend endpoints
that are already live, tested, and documented. This completes Phase 3 of
[`docs/build-plan.md`](../docs/build-plan.md).

**Exit criteria (build plan):** browse/search/filter; open an item; set its default
image; download a file and a ZIP.

## Before you start

Read all of these fully before touching any file:

- [`docs/build-plan.md`](../docs/build-plan.md) — Phase 3 exit criteria, locked frontend libs.
- [`PRD.md`](../PRD.md) §3.3 (path display + prefix rewrite + copy), §4 (Favorite, Creator,
  "My Creations"), **§5.1–5.2 (tag popularity + the popularity tag cloud — NO hierarchy/tree,
  NO depth setting)**, §11 (queued ZIP, ~1-day expiry, progress/poll), §12 (Search & Browse).
- [`docs/decisions.md`](../docs/decisions.md) — esp. **"Tag tree dropped → popularity tag
  cloud"** and the Phase 3a backend decisions.
- [`CLAUDE.md`](../CLAUDE.md) — operating rules (no commit, no push, prepare tree only).
- **Phase 3a API surface** (live on `dev`):
  - `GET /api/items` — accepts `q`, `tags[]`, `creator_id`, `favorited`, `sort`, pagination;
    returns `ItemSummary` with `default_image_path`, `creator_name`, `tag_names`, `favorited`.
  - `POST /api/items/{key}/favorite`, `DELETE /api/items/{key}/favorite`
  - `GET /api/me/favorites`, `GET /api/me/creations`
  - `GET /api/me/path-prefix`, `PUT /api/me/path-prefix`
  - `GET /api/tags` (popularity counts) — drives the tag cloud + tag list.
  - `GET /api/creators`, `GET /api/creators/{id}`, `GET /api/creators/{id}/items`
  - `GET /api/items/{key}/files/{path:path}`
  - `POST /api/items/{key}/zip` → `{id, status, expires_at}`,
    `GET /api/items/{key}/zip/{id}` (poll) + `?download=true` (stream)
  - `PATCH /api/items/{key}/default-image` with body `{image_id: number}`
- **Frontend tech locked:** Vite + React 18 + TS + Tailwind + shadcn/ui; **TanStack Query**
  (server state), **React Router** (routing), **TanStack Table** (table view), **TanStack
  Virtual** (large grid/list). Install `@tanstack/react-virtual` if missing.
- Existing frontend: `frontend/src/lib/api.ts`, context providers, `AppShell`, page structure.

## Working tree check

Run `git status --porcelain`. Expect a clean tree on `dev` with only this prompt untracked.
Surface anything unexpected before proceeding.

## What to do

### 0. Remove the obsolete tag-tree backend (per the "tag tree dropped" decision)

The hierarchical tag tree was dropped — tags are now a flat popularity cloud (see
`docs/decisions.md`). In the backend, **remove**:
- the `GET /api/tags/tree` endpoint and its `TagTree`/`TagTreeNode` response schemas in
  `backend/app/routers/tags.py`,
- any `catalog.tag_tree_depth` setting handling tied to it,
- the corresponding tag-tree test(s) in `backend/tests/test_phase3_catalog.py`.
Keep `GET /api/tags` (popularity counts) — that powers the cloud. Re-run `pytest` after.

### 1. Install TanStack Virtual

If `@tanstack/react-virtual` is missing from `frontend/package.json`:
`cd frontend && npm install @tanstack/react-virtual`.

### 2. Extend `lib/api.ts` with Phase 3 functions

Typed API functions for every endpoint above, following existing patterns (cookie + CSRF or
Bearer as needed). Key types: `ItemSummary` (`default_image_path`, `creator_name`,
`tag_names`, `favorited`), `ItemListParams` (`q`, `tags`, `creator_id`, `favorited`, `sort`,
`page`, `per_page`), `TagSummary` + `PaginatedTags`, `CreatorSummary` + `PaginatedCreators`,
`BundleOut` (`id`, `status`, `expires_at?`, `error_message?`), `PathPrefixResponse`.
CSRF on: `POST/DELETE favorite`, `POST /zip`, `PUT path-prefix`. Single-file download is a
plain authenticated GET — stream via `<a href download>` so the browser handles it natively.

### 3. Catalog browse page (`/catalog`)

`frontend/src/pages/CatalogPage.tsx`. Layout (PRD §12):
- **Search bar** — controlled, debounced 300 ms, drives `q`.
- **Tag browse panel** — a **popularity-weighted tag cloud** (tag font-size/weight scales
  with its popularity count) plus a sortable tag list. Clicking a tag toggles it as a
  stackable **AND** filter. **No tree, no depth control.**
- **View toggle** — grid / table, persisted to `localStorage`.
- **Sort selector** — newest, title A–Z, **most popular** (by the backend's popularity sort).
- **Grid view** — virtualized card grid (`@tanstack/react-virtual`): cover image (placeholder
  SVG if none), title, creator, tag chips (first 3 + overflow), star toggle.
- **Table view** — TanStack Table: thumbnail, title, creator, tags, date, star; sortable headers.
- **Favorites filter** — "show only favorites" toggle.
- All filter state (q, tags, page, sort, favorited) lives in URL search params (deep-linkable).

### 4. Item detail page (`/items/:key`)

`frontend/src/pages/ItemPage.tsx`:
- **Image carousel** — scrollable strip of all images; click → full-size; "Set as default"
  on the active image (`PATCH …/default-image`); default shown first + badged.
- **Metadata** — title, slug, creator (linked to `/catalog?creator_id={id}`), source URL,
  license, description, timestamps.
- **Tags** — chips; click → `/catalog?tags={name}`.
- **Dir path + prefix rewrite + copy** (§3.3): fetch `GET /api/me/path-prefix`; show
  `path_prefix + dir_path` if set, else raw path; copy-to-clipboard button.
- **Downloads** — files from `GET /api/items/{key}` (`files` array), each with a download
  link; "Download all as ZIP" → `POST …/zip` then poll every 2 s until `ready`/`failed`,
  then `GET …/zip/{id}?download=true`. Show Queued → Building → Ready / Failed.
- **Placeholders** (no functionality): "Print History (Phase 7)" and "Sharing (Phase 7)".

### 5. Creator browse

`/creators/{id}` (own page or a CatalogPage `creator_id` route): creator name, profile link,
their items (reuse the catalog list/grid).

### 6. Nav entries

In `AppShell`/sidebar: **My Favorites** → `/catalog?favorited=true`; **My Creations** →
`/me/creations` (uses `GET /api/me/creations`).

### 7. Settings: path prefix only

- **Per-user** — "Path prefix" input; `GET/PUT /api/me/path-prefix` (CSRF on save).
- **No tag-tree-depth setting** (removed — the cloud has no depth).

### 8. TypeScript + tests

- `npx tsc --noEmit` zero errors.
- **vitest** for non-trivial logic: search query state (debounce, URL sync); path-prefix
  rewrite (prefix set vs unset, trailing-slash); ZIP poll state machine (queued → building →
  ready → stream; failed); **tag-cloud weighting** (popularity → font-size bucket) from a
  fixture. Keep existing tests green.

## Conventions to honor

- All server state via TanStack Query; no raw `fetch` outside `lib/api.ts`.
- CSRF on cookie-auth mutations (favorite, zip, path-prefix); Bearer exempt.
- Tailwind + shadcn/ui; match the Phase 0–1 new-york/slate look.
- No out-of-scope features: no rendering, no print history, no share links, no import
  wizard, no AI. Secrets out of the repo; document new env in `.env.example`.

## Local verification checklist

```
ruff check backend/              # stays clean (you removed the tree endpoint/test)
pytest backend/tests/ -q         # all tests pass after the tree removal
npx tsc --noEmit                 # zero TS errors
npx vitest run                   # new + existing tests pass
alembic upgrade head             # (no new migration expected)
alembic downgrade base
docker compose config --quiet
```

Note anything you could not verify.

## When done

1. Update frontmatter: `status: completed`, `completed: 2026-06-27`, one-line `result`.
2. `git mv` this file into `prompts/done/`.
3. Add `docs/decisions.md` entries (newest-at-top) for non-obvious frontend calls
   (virtualization approach, ZIP polling, tag-cloud weighting, URL state management) and the
   tag-tree-endpoint removal.
4. **You are a spawned agent: do NOT commit, push, or change git branch.** Prepare the tree
   and report back with: complete file list; proposed one-line `feat:` commit message; exact
   local check results (ruff/pytest/tsc/vitest/alembic/compose); any decisions made or things
   you could not verify.
