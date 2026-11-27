---
name: 2026-11-26-catalog-printed-badge
status: done             # pending | in-progress | done | failed
created: 2026-11-26
model: sonnet
completed: 2026-11-26
result: has_print_record flag + Printer badge in card/table; ruff, tsc, vitest pass; backend test not run (no DB)
---

# Task: Show a small "printed before" printer icon on catalog items

In the catalog (grid card + table view), items with at least one print record should show a
small lucide `Printer` icon next to the existing "Print files attached" `Box` badge and the
favorite star — a quick "I've printed this" cue.

## Before you start

- Read `docs/architecture.md` (module map + gotchas) and `CLAUDE.md`.
- Frontend stack: Tailwind + CSS-var theme + lucide icons; **no Mantine, no toast lib**.
- No migration needed — this is a computed flag from the existing `print_records` table.
- **Do NOT run `make verify`, the full `pytest`, or `scripts/verify-*.sh`** — the orchestrator
  runs the single authoritative gate (a concurrent pytest corrupts the shared test PG). You
  may run fast DB-free checks: `backend/.venv/bin/ruff` (pinned 0.8.4, uses
  `backend/pyproject.toml`), and in `frontend/` `npx tsc -b --force` and `npx vitest run <the
  specific test files you touched>`.

## Working tree check

Run `git status --porcelain` and cross-reference the files below. If any have uncommitted
changes, stop and report. This prompt file is exempt.

## What to do

1. **Backend — `backend/app/routers/items/schemas.py`:** add `has_print_record: bool = False` to
   `ItemSummary` (next to `has_asset`, with a short comment).
2. **Backend — `backend/app/routers/items/core.py` (list endpoint, ~line 362):** batch-load a set
   of item_ids that have ≥1 `PrintRecord` (one `SELECT DISTINCT item_id ... WHERE item_id IN
   (...)` query, same pattern as `has_asset_ids`), and set `has_print_record=` in `ItemSummary`.
   **Visibility:** match the rule the existing per-item print-records list endpoint uses for the
   current user (find it under `backend/app/routers/` — print records have `visibility`
   private/public and `logged_by_id`). A private record logged by someone else must NOT light the
   icon for another user. If that endpoint shows admins everything, mirror that too. State in
   your report which rule you mirrored.
3. **Backend test:** add a test in the existing items-list test file (see `docs/architecture.md`
   for where) covering: no records → false; own record → true; another user's private record →
   false for this user; public record → true. Don't run the full suite; the orchestrator will.
4. **Frontend — `frontend/src/lib/api/items.ts`:** add `has_print_record: boolean` to the item
   summary type. Fix any test fixtures/mocks that construct this type so `tsc` stays clean.
5. **Frontend — `frontend/src/pages/catalog/ItemCard.tsx`:** next to the `has_asset` `Box` badge
   (in the icon row before the favorite button), render when `item.has_print_record`:
   a `<span role="img" aria-label="Printed before" title="Printed before">` wrapping lucide
   `Printer` at `size={12}`, styled identically to the Box badge (`var(--aurora-muted)`).
   Order: Box, Printer, Star.
6. **Frontend — `frontend/src/pages/catalog/TableView.tsx`:** same badge (size 11, matching the
   Box there) after the `has_asset` Box in the title cell.
7. **Frontend tests:** extend the existing ItemCard / TableView tests (if present) to assert the
   badge appears when `has_print_record` is true and is absent when false.
8. **CHANGELOG.md `[Unreleased]` → `### Added`:** one short bullet, e.g. "**Printed-before badge
   in the catalog.** Items you've logged a print for show a small printer icon next to the
   files badge and favorite star (grid and table views)."
9. If `docs/architecture.md` documents the `ItemSummary` fields / `has_asset` flag, add
   `has_print_record` alongside it.

## Conventions to honor

- Keep the backend change to one extra query; no N+1.
- Match existing inline-style conventions in the two components; don't refactor them.

## When done

1. Update this file's frontmatter: `status`, `completed` (date), `result` (one line).
2. `git mv` this file into `prompts/done/` (or `prompts/failed/`).
3. Record any non-obvious decision (e.g. the visibility rule) in `docs/decisions.md` only if
   it's genuinely non-obvious.
4. **Do not commit.** Report back: the file list, the visibility rule you mirrored, the results
   of the fast checks you ran, and a proposed one-line `feat:` commit message.
