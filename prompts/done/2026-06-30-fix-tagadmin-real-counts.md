---
name: 2026-06-30-fix-tagadmin-real-counts
status: done
created: 2026-06-30
model: sonnet
completed: 2026-06-29
result: >
  Fixed: tag_admin.py list_pending_tags now computes item_count via outer join;
  item_count added to TagAdminOut (backend + api.ts); TagAdminPage.tsx pending row,
  all-tags uses column, and merge dropdown all show item_count. New test
  test_admin_pending_list_item_count passes. ruff/tsc/vitest/vite build all clean.
---

# Task: Tag Admin shows "0 uses" for every tag — use the real item count

The Tag Admin page shows **0 uses for all tags** even when they're in use. Root cause: it displays
`popularity_count`, a denormalized field that is **never maintained** (always 0). The browse cloud
already worked around this by computing a **real `COUNT(item_tags)` join** (`item_count`). Do the
same for the admin tags listing.

## Backend — `app/routers/tag_admin.py`
- The admin tags list endpoint (`GET /api/admin/tags`, returns `TagAdminOut`) should return an
  accurate per-tag **`item_count`** computed via an outer join `COUNT(DISTINCT item_tags.item_id)`
  (mirror how `list_tags` in `app/routers/tags.py` does it — reuse the same approach). Add
  `item_count: int` to `TagAdminOut`. Keep `popularity_count` if it's part of the schema, but the
  UI should show the real count. (Apply to the pending list too if it shows a count.)

## Frontend — `frontend/src/pages/admin/TagAdminPage.tsx`
- Display `item_count` in the "uses"/popularity column (All Tags table) instead of the stale
  `popularity_count`. Update `api.ts` `TagAdminOut` type with `item_count`.

## Note
- `popularity_count` is effectively superseded by computed counts for display; don't try to
  backfill/maintain it here (out of scope) — just show the real join count. Mention this in the
  decisions entry.

## Verify
- Backend: `ruff check backend/` (run it yourself); **ephemeral Postgres** + tests (docker
  one-liner; `alembic upgrade head`; run pytest in FOREGROUND to completion; tear down after;
  recreate the scratchpad venv if gone). Add/extend a test: a tag applied to N items reports
  `item_count == N` via `GET /api/admin/tags`; an unused tag reports 0.
- Frontend: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite
  build` MUST succeed**. Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: admin tags use real join count (popularity_count unmaintained).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `fix:`
   commit message; check results (ruff / pytest+count / tsc / vitest / **vite build**);
   confirmation counts are now accurate; anything unverified.
