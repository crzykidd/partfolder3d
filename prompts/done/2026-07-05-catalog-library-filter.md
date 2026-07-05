---
name: catalog-library-filter
status: done
created: 2026-07-05
model: Sonnet
completed: 2026-07-05
result: >
  Added catalog "filter by library" control (default All, multi-select popover, URL-persisted
  as libs=1,2, hidden with ≤1 enabled library) + repeatable backend library_ids param combined
  with legacy library_id into one IN(...) set. Files: backend/app/routers/items/core.py,
  frontend/src/lib/api/items.ts, frontend/src/pages/CatalogPage.tsx,
  frontend/src/pages/catalog/LibraryFilter.tsx (new), plus backend + frontend tests.
  Ruff clean; backend 770 passed; frontend build OK, vitest 359 passed.

---

# Catalog: filter by library (All + multi-select)

## Goal

Now that multiple libraries exist, the catalog page needs a **library filter**: default **All**,
with a **multi-select** of libraries (pick one or more). Owner request.

## Backend (already half-there)

`backend/app/routers/items/core.py::list_items` already accepts a single `library_id: int | None`
(~line 209) and filters `Item.library_id == library_id` (~235). Extend it to filter by **multiple**
libraries:
- Add a repeatable list param `library_ids: list[int] | None = Query(default=None)` — mirror EXACTLY
  how the existing `tags` multi-value query param is declared/parsed in this same endpoint.
- When `library_ids` is non-empty, filter `Item.library_id.in_(library_ids)`. Keep the existing
  single `library_id` param working (backward-compat) — if both are given, combine sensibly (union
  of the single id + the list) or document precedence; simplest is to normalize both into one set of
  ids and use `.in_(...)`. Empty/None = all libraries (unchanged default).
- The response already includes each item's `library_id` / library name — no schema change needed.
  **No migration.**

## Frontend (the real work)

Add a **library filter** control to the catalog toolbar in `frontend/src/pages/catalog/` +
`CatalogPage.tsx` (the page was recently split into `pages/catalog/` subcomponents — follow that
structure; put a new `LibraryFilter.tsx` there if it's more than a few lines).
- The catalog already fetches libraries (`api.listLibraries` — there's a `libraries` query in
  CatalogPage). Reuse it; show only **enabled** libraries. If there's only **one** enabled library,
  HIDE the control entirely (no point).
- Default state = **All** (nothing selected → no `library_ids` sent → all items). Let the user select
  one or more libraries (a multi-select — checkboxes in a small popover, or a compact multi-select
  matching the existing toolbar controls; match the sort/per-page control styling, use existing
  components/ui — no new deps, no toast/Mantine).
- Wire it into the items query like the other filters: include the selected ids in the
  `['items', ...]` queryKey, pass them to `api.listItems`, persist in the URL (a param like
  `libs=1,2`), and **reset to page 1 when the selection changes** (same pattern as tag/sort/per-page
  changes — see how `setSort`/`setPage`/the debounced search do `next.delete('page')`). Show an
  active-filter chip / indicator consistent with the existing "Filtering by:" tag chip.
- Update the api client (`frontend/src/lib/api/items.ts` `listItems` / `ItemListParams`) to send
  `library_ids` (repeatable `?library_ids=1&library_ids=2` or however the backend expects it — match
  the backend param name/shape you chose).

## Verify

- Backend: ephemeral PG on :5433 (`DATABASE_URL='postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d'`),
  pinned `backend/.venv/bin/ruff check backend/` clean. Add tests: filter by one library id returns
  only that library's items; filter by two returns the union; no filter returns all. Put them in the
  catalog/items test file. Full `pytest -n auto` green (was ≈769).
- Frontend: `npx tsc -b --force` + `npm run build` + `npx vitest run` (baseline ≈357). Add a focused
  test: the control lists enabled libraries and is hidden with a single library; selecting a library
  re-queries `listItems` with that id (mirror the existing tag-filter test in `catalog-page.test.tsx`).

## Constraints

- No migration. Don't regress the existing single `library_id` behavior or the other catalog filters
  (tags/favorites/sort/search/per-page/pagination — especially the recent pagination fix: changing the
  library selection resets to page 1, but must not re-introduce the page-1 bounce bug).

## Reporting

Prepare the tree (do NOT git-commit). Report: files changed; backend param shape chosen; how the
multi-select + "All" default + URL persistence work; ruff + full backend suite + frontend build/vitest
results; proposed CHANGELOG `[Unreleased] ### Added` bullet + commit message. Set this prompt's
frontmatter (`status: done`/`completed`/`result`) and `mv` it (plain mv) to `prompts/done/`, and tell me.
