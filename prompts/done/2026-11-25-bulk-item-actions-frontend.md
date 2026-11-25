---
name: 2026-11-25-bulk-item-actions-frontend
status: done
created: 2026-11-25
model: sonnet
completed: 2026-11-25
result: Frontend multi-select + bulk action bar/dialogs implemented; tsc, vite build, 5 vitest files (42 tests) green.
---

# Task: Catalog multi-select + bulk action bar (log print, tags, move, delete, rescan)

Add a multi-select mode to the catalog (grid AND list views) with a sticky action bar for bulk
operations. A concurrent backend prompt implements the new endpoints per the contract below; bulk
move's endpoint already exists.

## Owner decisions (locked)

- **Select-mode toggle**: a "Select" button in the catalog toolbar enters selection mode. In mode:
  a checkbox on every card/row, click toggles selection (does NOT navigate), **shift-click selects a
  range** within the current page, "Select all on this page" / "Clear". Esc or the bar's ✕ exits
  mode and clears. Outside mode, the catalog behaves exactly as today.
- **Selection persists across pagination and filter/sort changes**, keyed by item key (store
  key → minimal display info, e.g. title, so the bar/dialogs can show names of off-page items).
  Clears on exit or navigating away from the catalog. No "select all matching filter".
- Sticky bottom action bar: `N selected · [Log print] [Tags] [Move] [More ▾: Rescan, Delete] [✕]`.
- **Bulk log print** = one identical record per selected item, all-or-nothing.

## Before you start

- Read `CLAUDE.md`, `docs/architecture.md` (frontend section + gotchas), `frontend/src/pages/CatalogPage.tsx`
  and `frontend/src/pages/catalog/*`, `frontend/src/pages/item/PrintHistory.tsx` (print-record form),
  `frontend/src/pages/item/ItemMetadata.tsx` (tag editor from #47), whatever item-page UI calls the
  single-item move, `frontend/src/api/print-records.ts`, the items api client, and `apiFetch`.
- **Stack: Tailwind + CSS-var theme + minimal Radix + lucide-react + TanStack Query + `apiFetch`
  (CSRF). No Mantine, no toast library** — show results inline in the dialog/bar.
- **Do NOT edit `CHANGELOG.md` or docs. Do not touch `backend/`.**
- Gate you may run: `cd frontend && npx tsc -b --force && npx vite build && npx vitest run <your test files>`
  (vitest is DB-free; the host is loaded, so run only your files with `--no-file-parallelism`).
  Don't run `make verify`.

## Working tree check

`git status --porcelain`; stop and report if any file you need is dirty. Unrelated dirty files
(a concurrent backend agent's, `prompts/*`): note once, don't block.

## API contract

`keys`: 1..500 item keys (rescan max 100 — disable/warn in UI above that). All POST via `apiFetch`.

- `POST /api/items/bulk-print-records` `{ keys, record: PrintRecordIn }` → 201
  `{ created: number, records: PrintRecordOut[] }`; 404 if any key missing (nothing created).
- `POST /api/items/bulk-tags` `{ keys, add: string[], remove: string[] }` → `BulkItemResult`
- `POST /api/items/bulk-delete` `{ keys }` → `BulkItemResult`
- `POST /api/items/bulk-rescan` `{ keys }` → `BulkItemResult`
- `BulkItemResult = { succeeded: string[], failed: { key: string, error: string }[] }`
- Existing `POST /api/items/move` — read `backend/app/routers/items/move.py` for its exact
  request/response and reuse/extend any existing client function.

## What to do

1. **Selection state**: a small hook/context (e.g. `useCatalogSelection`) owning mode, the
   key→info map, last-clicked index for shift-range. Unit-test it.
2. **Catalog UI**: Select toggle in the toolbar; checkbox + selected styling (ring/overlay) on
   grid cards and list rows; click/shift-click behavior; keyboard-accessible checkboxes with
   labels; "select all on page".
3. **Action bar** (sticky bottom, theme vars, works in both themes and on narrow widths).
4. **Dialogs** (Radix Dialog, matching existing modal style):
   - **Log print**: extract the print-record form fields from `PrintHistory.tsx` into a shared
     component used by both the item page and this dialog (no behavior change on the item page);
     no gcode/photo upload in bulk. Show "Log print for N items", list item titles (scrollable).
   - **Tags**: add tags + remove tags inputs (reuse the #47 editor's tag-input/autocomplete if
     factorable); note new tags may land pending approval.
   - **Move**: library picker (enabled libraries) → existing bulk move endpoint.
   - **Rescan**: confirm.
   - **Delete**: destructive confirm — explain items go to trash (retained ~30 days), require typing
     the count or "delete" to enable the button.
   - After completion: show succeeded/failed summary inline (list failures with item title + error),
     invalidate catalog/item/print-record queries, drop succeeded items from the selection after
     delete/move; keep failed ones selected for retry.
5. **API client** functions + types in the appropriate `frontend/src/api/*.ts`.
6. **Tests** (vitest + testing-library, matching existing catalog-page test style): mode toggle,
   click vs navigate, shift-range, persistence across page change, select-all-on-page, each dialog
   calls the right endpoint with the right body, partial-failure rendering, delete confirmation gating,
   and the item-page PrintHistory still works after the form extraction.

## When done

1. Update frontmatter; `git mv` this file to `prompts/done/` (or `failed/`).
2. Do **not** commit. Report: files changed, any contract assumption the backend must match,
   gate results (tsc/vite build/your vitest files).
