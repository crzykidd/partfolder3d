---
name: 2026-07-03-11-library-delete
status: completed
created: 2026-07-03
model: sonnet
completed: 2026-07-03
result: Hard-delete empty library (backend purge endpoint) + re-enable disabled library (backend enable endpoint) + admin UI actions for disabled library rows. Closes #11 (move-assets half is #25).
---

# Task: Hard-delete empty library + re-enable disabled library (issue #11, scoped)

Implement the narrowed scope of issue #11: guarded hard-delete for empty libraries and
a re-enable path for soft-disabled libraries. Move-assets-between-libraries is #25.

## Before you start

- Read `CLAUDE.md` for commit/branch rules (dev branch, feat: prefix, no Co-authored-by).
- Frontend stack: Tailwind + CSS-var Aurora theme + TanStack Query + apiFetch CSRF; no Mantine, no toast lib.
- Run `git status --porcelain` — confirm clean before touching files.

## Working tree check

Run `git status --porcelain`. All files should be clean. This task touches:
- `backend/app/routers/libraries.py`
- `frontend/src/lib/api/libraries.ts`
- `frontend/src/pages/admin/LibrariesPage.tsx`
- `backend/tests/test_libraries.py` (new)
- `CHANGELOG.md`
- `docs/decisions.md`

## What to do

### Backend (`backend/app/routers/libraries.py`)

1. Add `item_count: int = 0` to `LibraryOut` schema.
2. Update `list_libraries` to include per-library item counts via a correlated subquery
   (import `func` from sqlalchemy and `Item` from `..models.item`).
3. Add `POST /api/libraries/{lib_id}/enable` — sets `enabled = True`, returns `LibraryOut`.
4. Add `DELETE /api/libraries/{lib_id}/purge` — hard-delete guarded by zero-item check.
   - Count items for the library.
   - If count > 0: return 409 with a message pointing to #25 for move/removal.
   - If count == 0: `await db.delete(lib)` + flush.
   - Do NOT touch the filesystem (no existing dir-management code in disable_library).

### Frontend API (`frontend/src/lib/api/libraries.ts`)

1. Add `item_count: number` to `LibraryOut` interface.
2. Add `enableLibrary(id: number): Promise<LibraryOut>` → POST `/api/libraries/{id}/enable`.
3. Add `purgeLibrary(id: number): Promise<void>` → DELETE `/api/libraries/{id}/purge`.

### Frontend page (`frontend/src/pages/admin/LibrariesPage.tsx`)

1. Import new icons: `RefreshCw` (re-enable) from lucide-react.
2. Update `LibraryRowProps` to add `onEnable`, `onPurge`, `isEnabling`, `isPurging` props.
3. In `LibraryRow`, for disabled library rows show two buttons:
   - **Re-enable**: calls `onEnable(library.id)`.
   - **Delete permanently**: if `library.item_count > 0` → show inline error (asset count +
     "move/remove assets first; move-between-libraries is coming — issue #25");
     if empty → `window.confirm()` → call `onPurge(library.id)`.
4. Add local `useState<string | null>` in `LibraryRow` for the delete-blocked error message.
5. In `LibrariesPage`, add `enableMutation` and `purgeMutation` wired to `enableLibrary`
   and `purgeLibrary`, with query invalidation. Pass handlers + state to `LibraryRow`.

### Tests (`backend/tests/test_libraries.py`)

New test file with three tests:
- `test_purge_empty_library_succeeds` — create library (no items), DELETE purge → 204.
- `test_purge_nonempty_library_rejected` — create library + item, DELETE purge → 409.
- `test_enable_library_works` — create library, disable it, POST enable → 200 + enabled=True.

## Conventions to honor

- Aurora style constants already defined in LibrariesPage.tsx — reuse them.
- No new icon imports beyond what lucide-react provides.
- Ruff lint: `backend/.venv/bin/ruff check backend/` must be clean.
- Frontend: `npm run build` must pass (tsc -b + vite build).
- Tests: `backend/.venv/bin/pytest backend/tests/test_libraries.py -v` must pass.

## When done

1. Update this file's frontmatter (already done above).
2. `git mv` to `prompts/done/`.
3. Record decisions in `docs/decisions.md`.
4. Stage explicit paths and commit with `feat: guarded hard-delete + re-enable for libraries (closes #11)`.
