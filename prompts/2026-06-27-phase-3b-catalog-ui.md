---
name: 2026-06-27-phase-3b-catalog-ui
status: pending
created: 2026-06-27
model: sonnet
completed:
result:
---

# Task: Phase 3b — Catalog UI (browse, item page, downloads, path prefix, settings)

Build the browser-facing catalog UI for Phase 3, wiring up all the Phase 3a backend
endpoints that are already live, tested, and documented.  This completes Phase 3 of
[`docs/build-plan.md`](../docs/build-plan.md).

**Exit criteria (build plan):** browse/search/filter; open an item; set its default
image; download a file and a ZIP.

## Before you start

Read all of these fully before touching any file:

- [`docs/build-plan.md`](../docs/build-plan.md) — Phase 3 exit criteria, locked frontend
  libs.
- [`PRD.md`](../PRD.md) §3.3 (path display + prefix rewrite + copy button), §4 (Favorite,
  Creator, "My Creations"), §5.1–5.2 (tag tree, configurable depth default 4), §11
  (queued ZIP with ~1-day expiry, progress/poll), §12 (Search & Browse UI layout).
- [`CLAUDE.md`](../CLAUDE.md) — operating rules (no commit, no push, prepare tree only).
- [`docs/decisions.md`](../docs/decisions.md) — Phase 3a backend decisions.
- **Phase 3a API surface** (all endpoints are live on `dev`):
  - `GET /api/items` — now accepts `q`, `tags[]`, `creator_id`, `favorited`, `sort`,
    pagination; returns `ItemSummary` with `default_image_path`, `creator_name`,
    `tag_names`, `favorited`.
  - `POST /api/items/{key}/favorite`, `DELETE /api/items/{key}/favorite`
  - `GET /api/me/favorites`, `GET /api/me/creations`
  - `GET /api/me/path-prefix`, `PUT /api/me/path-prefix`
  - `GET /api/tags`, `GET /api/tags/tree`
  - `GET /api/creators`, `GET /api/creators/{id}`, `GET /api/creators/{id}/items`
  - `GET /api/items/{key}/files/{path:path}`
  - `POST /api/items/{key}/zip` → `{id, status, expires_at}`,
    `GET /api/items/{key}/zip/{id}` (poll) + `?download=true` (stream)
  - `PATCH /api/items/{key}/default-image` with body `{image_id: number}`
- **Frontend tech locked:** Vite + React 18 + TypeScript + Tailwind + shadcn/ui;
  **TanStack Query** (server state), **React Router** (routing), **TanStack Table**
  (table view), **TanStack Virtual** (large grid/list). Install `@tanstack/react-virtual`
  if not already in `package.json`.
- Existing frontend code: `frontend/src/lib/api.ts` (API client patterns), existing
  context providers, `AppShell`, existing page structure.

## Working tree check

Run `git status --porcelain`. Expect a clean tree on `dev` with only this prompt
untracked. Surface anything unexpected before proceeding.

## What to do

### 1. Install TanStack Virtual

Check `frontend/package.json` — if `@tanstack/react-virtual` is missing, add it:

```
cd frontend && npm install @tanstack/react-virtual
```

### 2. Extend `lib/api.ts` with Phase 3 functions

Add typed API functions for every new endpoint.  Follow the pattern of existing functions
(Bearer or cookie + CSRF as needed).  Key types to add:

- `ItemSummary` — matches the enhanced backend response (add `default_image_path`,
  `creator_name`, `tag_names`, `favorited` fields).
- `ItemListParams` — `q`, `tags`, `creator_id`, `favorited`, `sort`, `page`, `per_page`.
- `TagSummary`, `PaginatedTags`, `TagTreeNode`, `TagTree`.
- `CreatorSummary`, `PaginatedCreators`.
- `BundleOut` — `id`, `status`, `expires_at?`, `error_message?`.
- `PathPrefixResponse`.

CSRF is needed on: `POST/DELETE favorite`, `POST /zip`, `PUT path-prefix`.
Single-file download (`/files/{path}`) is a plain authenticated GET; stream via
`<a href>` (not via fetch) so the browser handles the file download natively.

### 3. Catalog browse page (`/catalog`)

Create `frontend/src/pages/CatalogPage.tsx`.

**Layout (PRD §12):**
- **Search bar** at top — controlled input, debounced 300 ms, drives `q` query param.
- **Sidebar (or collapsible panel)** — tag tree + tag list with popularity counts;
  clicking a tag toggles it as a stackable AND filter (multiple tags = AND semantics on
  the backend).
- **View toggle** — grid / table, persisted to `localStorage`.
- **Sort selector** — options: newest, title A–Z, most popular (by download count if
  available, else items per creator — use what the backend supports).
- **Grid view** — virtualized card grid via `@tanstack/react-virtual`.  Each card:
  cover image (placeholder SVG if none), title, creator name, tag chips (first 3 + overflow
  count), star button (favorite toggle).
- **Table view** — TanStack Table with columns: thumbnail, title, creator, tags, date,
  star.  Sortable header clicks update the sort param.
- **Favorites filter** — toggle: "show only favorites".
- All filter state (q, tags, page, sort, favorited) lives in URL search params so the
  page is deep-linkable.

### 4. Item detail page (`/items/:key`)

Create `frontend/src/pages/ItemPage.tsx`.

**Sections:**
- **Image carousel** — scrollable horizontal strip of all item images.  Clicking an image
  opens it full-size (overlay or new tab).  "Set as default" button visible on the active
  image (calls `PATCH /api/items/{key}/default-image`); the default is shown first and
  marked with a badge.
- **Metadata** — title, slug, creator (linked to `/catalog?creator_id={id}`), source URL
  (external link), license, description, created/updated timestamps.
- **Tags** — tag chips; clicking a tag navigates to `/catalog?tags={name}`.
- **Dir path + prefix rewrite + copy** (PRD §3.3):
  - Fetch `GET /api/me/path-prefix` (or read from user context if cached).
  - Display `path_prefix + item.dir_path` if prefix is set; else display the raw path.
  - Copy-to-clipboard button.
- **Downloads** panel:
  - List of files grouped by type (model, image, render, gcode, other) — fetch
    `GET /api/items/{key}` which already returns a `files` array.
  - Each file: filename, size, a download link (`<a href="/api/items/{key}/files/{path}"
    download>`).
  - "Download all as ZIP" button → `POST /api/items/{key}/zip` then poll
    `GET …/zip/{bundle_id}` every 2 s until `status === "ready"` or `"failed"`, then
    redirect to `GET …/zip/{bundle_id}?download=true`.  Show progress states: Queued →
    Building → Ready / Failed.
- **Print History placeholder** — a clearly commented-out or visually greyed section
  labelled "Print History (Phase 7)" with no actual data or endpoints.
- **Share placeholder** — similarly labelled "Sharing (Phase 7)".

### 5. Creator browse

Create `frontend/src/pages/CreatorPage.tsx` (or extend CatalogPage with a
`creator_id` filter route).  A route like `/creators/{id}` showing the creator's name,
profile link, and their items (reuse the catalog item list/grid).

### 6. "My Creations" and "My Favorites" nav entries

Add nav links in `AppShell` (or wherever the sidebar lives):
- **My Favorites** → `/catalog?favorited=true` (or a dedicated route that sets the
  filter).
- **My Creations** → `/me/creations` — a simple page using `GET /api/me/creations`.

### 7. Settings: path prefix + tag tree depth

Add to the appropriate settings page(s):
- **Per-user settings** — "Path prefix" input; `GET /api/me/path-prefix` on load,
  `PUT /api/me/path-prefix` on save (CSRF).
- **Admin / instance settings** — "Tag tree depth" (integer 1–10); read from
  `GET /api/settings` (key `catalog.tag_tree_depth`), write via `PUT /api/settings`
  (already implemented).

### 8. TypeScript + tests

- `npx tsc --noEmit` must pass with zero errors.
- Write **vitest** unit tests for non-trivial logic:
  - Search query state (debounce, URL sync).
  - Path-prefix rewrite function (test: prefix set vs. unset, trailing slash handling).
  - ZIP poll state machine (transitions: queued → building → ready → stream; failed).
  - Tag-tree rendering from a known `TagTree` fixture.
- Run `npx vitest run` — all existing tests must stay green; new tests must pass.

## Conventions to honor

- All server state through TanStack Query (`useQuery`, `useMutation`).  No raw `fetch`
  outside `lib/api.ts`.
- CSRF token on all cookie-auth state-changing mutations (favorite, zip, path-prefix).
  Bearer-auth requests (API key path) are exempt.
- Tailwind + shadcn/ui for styling; match the Phase 0–1 new-york/slate look.
- No out-of-scope features: no thumbnail rendering, no print history, no share links, no
  import wizard, no AI.
- Secrets out of the repo; document any new env vars in `.env.example`.

## Local verification checklist

Run all of the following and confirm each is green:

```
ruff check backend/              # must stay clean
pytest backend/tests/ -q         # all 157 tests must pass
npx tsc --noEmit                 # zero TS errors
npx vitest run                   # new + existing tests pass
alembic upgrade head             # no new migrations in this phase (backend done)
alembic downgrade base           # reversibility (sanity check; no new migrations)
docker compose config --quiet    # docker config still valid
```

Note anything you could not verify (e.g. if Postgres isn't running locally for alembic
checks).

## When done

1. Update this file's frontmatter: `status: completed`, `completed: 2026-06-27`,
   `result` (one line describing what shipped).
2. `git mv` this file into `prompts/done/`.
3. Add `docs/decisions.md` entries (newest-at-top) for non-obvious frontend calls
   (virtualization approach, ZIP polling strategy, tag-tree rendering, URL state
   management).
4. **You are a spawned agent: do NOT commit, push, or change git branch.** Prepare the
   working tree, then report back with:
   - Complete list of files created/modified.
   - Proposed one-line `feat:` commit message.
   - Exact local check results (ruff/pytest/tsc/vitest/alembic/compose).
   - Any decisions made or things you could not verify.
</content>
</invoke>