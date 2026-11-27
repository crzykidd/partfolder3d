---
name: 2026-11-26-printed-count-tooltip
status: done
created: 2026-11-26
model: sonnet
completed: 2026-11-26
result: print_count added; badge tooltip shows "Printed N time(s)"; ruff+tsc+vitest pass; backend tests not run (no DB)
---

# Task: Show "Printed N times" on the catalog printed-before icon

Commit `4fbb285` added a `Printer` badge to catalog cards/rows when `ItemSummary.has_print_record`
is true (tooltip/aria-label "Printed before"). Change it to show the count: **"Printed 1 time"** /
**"Printed N times"**.

## Before you start

- Read `backend/app/routers/items/core.py` (the `has_print_record` batch query in the list
  endpoint), `backend/app/routers/items/schemas.py`, `backend/tests/test_catalog_has_asset.py`,
  `frontend/src/lib/api/items.ts`, `frontend/src/pages/catalog/ItemCard.tsx`,
  `frontend/src/pages/catalog/TableView.tsx`, `frontend/src/test/catalog-page.test.tsx`.
- **Do NOT run `make verify` / full pytest / `scripts/verify-*.sh` or start any DB.** Fast checks only:
  from `backend/`, `.venv/bin/ruff check app tests`; in `frontend/`, `npx tsc -b --force` and
  `npx vitest run <files you touched>`. Nothing in the background.

## Working tree check

`git status --porcelain`; if a file you'll touch is dirty, stop and report. This prompt is exempt.

## What to do

1. **Backend:** add `print_count: int = 0` to `ItemSummary` (keep `has_print_record` for API
   compatibility, derived as `print_count > 0`). Replace the DISTINCT query with one grouped
   `SELECT item_id, COUNT(*) ... GROUP BY item_id` using the **same visibility filter** as now
   (authenticated → all records; anonymous → public only). Still one query, no N+1.
2. **Backend tests:** extend the existing tests in `test_catalog_has_asset.py` to assert
   `print_count` (0, 1, and ≥2 records; anonymous sees only public count).
3. **Frontend:** add `print_count: number` to the item summary type; update fixtures. In
   `ItemCard.tsx` and `TableView.tsx`, the badge's `title` and `aria-label` become
   `Printed ${n} time${n === 1 ? '' : 's'}` (render condition: `print_count > 0`, falling back to
   `has_print_record` is unnecessary). Small shared helper is fine if it avoids duplication.
4. **Frontend test:** update the existing "Printed before" badge test to assert the new label for
   1 and for several prints.
5. **CHANGELOG.md `[Unreleased]`:** amend the existing **Printed-before badge** bullet to mention
   the tooltip shows how many times it's been printed (don't add a new bullet).

## When done

1. Frontmatter: `status`, `completed`, `result`.
2. `mv` this file to `prompts/done/` (or `prompts/failed/`).
3. **Do not commit.** Report file list, fast-check results, proposed one-line `feat:` message.
