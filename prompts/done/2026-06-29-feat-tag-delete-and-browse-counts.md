---
name: 2026-06-29-feat-tag-delete-and-browse-counts
status: done
created: 2026-06-29
model: sonnet
completed: 2026-06-29
result: >
  Part 1 — DELETE /api/admin/tags/{id} implemented in tag_admin.py; deletes
  ItemTag links (untags items, never deletes them), TagAlias rows, then the Tag;
  returns {deleted: true, items_untagged: <count>}; 404 on missing. Keep
  reject/merge-into unchanged. Frontend: Delete button per row in AllTagRow with
  inline confirm showing item count; invalidates admin-tags-all/pending + tags.
  deleteTag(id) added to api.ts.

  Part 2 — GET /api/tags now returns item_count (real COUNT(item_tags.item_id)
  join) alongside popularity_count; in_use_only=true query param filters to tags
  with count>0 (default false). CatalogPage cloud uses in_use_only=true, shows
  "#name (count)", sizes by item_count, empty-state if none in use.
  TagSummary.item_count added to api.ts.

  All checks passed: ruff clean (only pre-existing test_phase17 errors); pytest
  7/7 new + full suite passed; tsc clean; vitest 214 passed; vite build succeeded.
---

# Task: Delete tags (admin) + Browse-by-tags shows only in-use tags with usage counts

Two related tag improvements:
1. **Delete tag** — admins can only reject-pending or merge-active today; add a real delete for any
   tag (untags the items, removes aliases).
2. **Browse by tags** — the tag cloud should show **only tags actually in use** and display the
   **usage count** next to each, e.g. `#animal (44)`.

No migration needed.

## What exists
- `app/routers/tag_admin.py`: `reject_tag` (pending-only delete), `merge_into` (the safe-delete
  pattern: delete `ItemTag`s for the tag, delete its `TagAlias`es, delete the `Tag`). No plain
  delete for active tags.
- `app/routers/tags.py` `GET /api/tags`: returns `popularity_count`, `active_only=True` default,
  ordered by popularity desc. **`popularity_count` is a denormalized field that may be stale** —
  for the cloud, base "in use" + the shown number on the REAL count (join `item_tags`).
- Frontend tag cloud is in `frontend/src/pages/CatalogPage.tsx`. Admin tag table is
  `frontend/src/pages/admin/TagAdminPage.tsx`.

## Working tree check
`git status --porcelain` clean on `dev`. (Builds on the per-library path-prefix work just landed —
it touched `api.ts`; integrate cleanly.)

## Part 1 — Delete tag
- `DELETE /api/admin/tags/{id}` (admin + CSRF): delete the tag regardless of status — delete its
  `ItemTag` links, its `TagAlias` rows, then the `Tag` (mirror the `merge_into` cleanup). Return
  `{ deleted: true, items_untagged: <count> }` (count ItemTag rows removed first). 404 if missing.
  Keep `reject` + `merge-into` as-is.
- `TagAdminPage.tsx` All-Tags table: a **Delete** action per row (danger, inline confirm stating
  impact, e.g. "Delete 'games'? Removes it from N items."). On success invalidate
  `['admin-tags-all']`, `['admin-tags-pending']`, `['tags']`. Add `deleteTag(id)` to `api.ts`.
  Deleting **untags** the items — it never deletes items.

## Part 2 — Browse-by-tags: in-use only + counts
- Backend: make the tag list used by the cloud return an **accurate usage count per tag** and
  allow filtering to **in-use only** (count > 0). Prefer computing the count from a real
  `COUNT(DISTINCT item_tags.item_id)` join (so it's correct even if `popularity_count` drifted),
  exposed as the tag's count. Add a query param (e.g. `in_use_only: bool = False`) to `GET
  /api/tags` (default False to preserve existing callers; the cloud passes True) OR a dedicated
  cloud query — your call, but don't break existing `listTags` callers. If you keep using
  `popularity_count`, FIRST ensure it's accurate (and consider a one-time recompute) — but the
  join-count approach is preferred and simplest to trust.
- Frontend `CatalogPage.tsx` tag cloud: request in-use-only, and render each tag as
  **`#name (count)`** (the count visibly next to the name). Keep the popularity-driven sizing.
  Empty state if no tags are in use yet (e.g. "No tags in use yet — tags appear here once items use
  them."). Don't show count-0 / unused tags in the cloud. (The full tag list elsewhere can still
  show all active tags — only the BROWSE cloud filters to in-use.)
- Update `api.ts` types/params as needed.

## Constraints
- Reuse `@/components/ui` + Aurora. NO new deps, NO toast. Don't touch `frontend/src/pages/examples/`.
  Feature parity for the rest of CatalogPage + TagAdminPage.

## Verify
- Backend: `ruff check backend/`; **ephemeral Postgres** + tests (docker one-liner; `alembic upgrade
  head`; `pytest`; tear down; recreate the scratchpad venv if gone). Tests: deleting an active tag on
  ≥1 item removes the tag + ItemTag links (items remain) + aliases and returns the untagged count;
  delete missing → 404; the tags-cloud query returns accurate counts and excludes count-0 tags;
  in_use_only filters correctly.
- Frontend: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite build`
  MUST succeed**. Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: delete-tag semantics (untags items, removes aliases); cloud uses real
   join-count + in-use filter.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; check results (ruff / pytest+count / tsc / vitest / **vite build**);
   confirmation delete untags (not deletes) items + cloud shows counts/in-use-only; anything
   unverified.
