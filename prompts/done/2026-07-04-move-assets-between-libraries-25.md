---
name: move-assets-between-libraries-25
status: done
created: 2026-07-04
model: Sonnet
completed: 2026-07-04
result: >
  Shipped cross-mount item move (copy→verify-hash→remove, interrupted-safe, journaled) in
  new storage/library_move.py; single POST /api/items/{key}/move + bulk POST /api/items/move
  (N isolated per-item txns) in new routers/items/move.py; single-item "Move to library" UI
  on the item page (bulk UI deferred — no catalog multi-select exists). ruff clean; backend
  761 passed (was 744, +17); frontend tsc+build clean, vitest 353 (was 350, +3). No migration.
---

# Move asset(s) between libraries — single + bulk (closes #25)

## Goal

#25 (the filesystem-touching half of #11): let a user move an item from one library to another —
for reorganizing, or to empty a mis-configured library so it can be hard-deleted (#11). Read
`gh issue view 25` and `docs/atomic-moves.md` first.

## Behavior

- A **"Move to library →"** action on an item (single), and a **bulk** move for a selection —
  available only when **more than one enabled library** exists.
- The move: relocate the item's on-disk directory from the source library mount to the target
  library mount, update the item's `library_id` **and** `dir_path`, rewrite/sync the sidecar to
  the new path, and **re-inventory** so File rows/paths stay correct.
- **Cross-mount safety (NFS ↔ local): copy → verify (hash) → remove.** The source and target may
  be on different filesystems (a plain `os.rename` will `EXDEV`), so implement a
  copy-then-verify-then-remove move: copy the item dir to the target path, verify every file by
  hash (reuse the existing sha256 helper) against the source, and only then remove the source.
  **Interrupted-safe:** if anything fails before verification, the source dir is left fully intact
  and the partial target is cleaned up — never lose data. Follow the move-journal patterns in
  `backend/app/storage/journal.py` / `docs/atomic-moves.md` (there's already cross-mount
  `move_to_trash` and `item_dir_path(library_mount, key, title)` to compute the target path).
- Respect the FK `items.library_id → libraries.id` (NOT NULL, ON DELETE RESTRICT): do the whole
  thing in the app layer (files + DB row together), never a raw library_id UPDATE.
- **Bulk = per-item isolation:** one item failing must not roll back or corrupt the others; report
  per-item success/failure. Same isolation the bulk-commit path uses.
- Target library must be enabled and different from the source; reject moving into the same
  library or a disabled/nonexistent one.

## Where to build

- **Storage:** a new `move_item_to_library(...)` (in `backend/app/storage/` — near the journal/
  paths modules) that does the copy→verify→remove and returns the new dir path. Keep it pure/
  testable (operate on paths + key + title), no DB inside.
- **Router:** add the endpoint(s). A single-item `POST /api/items/{key}/move` (body: target
  `library_id`) and a bulk `POST /api/items/move` (body: list of keys + target `library_id`), OR
  put them under `libraries.py` — pick whichever fits the existing router conventions; explain the
  choice. Update `library_id` + `dir_path`, rewrite the sidecar, re-inventory (reuse
  `inventory_item` + the File-row sync the rescan/commit paths use), all in one transaction per
  item. Admin/owner auth consistent with sibling mutating routes.
- **Frontend:** a "Move to library →" control on the item page (single) and a bulk action in the
  catalog selection UI if a bulk-select affordance exists (if there's no existing multi-select in
  the catalog, do the single-item move well and note bulk-UI as follow-up rather than inventing a
  whole selection system). Use existing components/ui + TanStack Query; invalidate the item +
  catalog + libraries queries + `item_count` after a move. Only show it when ≥2 enabled libraries.

## Constraints

- **No migration** (only `library_id`/`dir_path` values change — both columns already exist). If
  you think a migration is needed, STOP and report; I'll assign the number.
- Do NOT weaken the atomic-move guarantees. The invariant: **an interrupted move never loses
  files** (source intact until the target is hash-verified).

## Verify

- Ephemeral PG on :5433 (`pf3d-pg-v`; `DATABASE_URL='postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d'`).
  Pinned `backend/.venv/bin/ruff check backend/` clean.
- Storage-level tests (tmp dirs, no DB): a successful cross-dir move relocates all files and
  removes the source; a hash-mismatch / mid-copy failure aborts with the **source left intact** and
  no partial target; moving to the same path is a no-op/rejected. Router tests: single + bulk move
  updates `library_id`+`dir_path`+File rows and the sidecar lands at the new path; bulk isolates a
  failing item; same-library / disabled-target / bad-key are rejected. Put them in the item/library
  test files (+ a storage move test file).
- `pytest -n auto` full suite green (was 744). Frontend: `npx tsc -b --force` + `npm run build` +
  `npx vitest run` (baseline 350) — add a focused test for the move control.

## Reporting

Prepare the tree (do NOT git-commit). Report: files changed; the move function's copy→verify→
remove flow + how it stays interrupted-safe; the endpoint shape (single + bulk, where you put
them); whether you shipped bulk UI or deferred it (+ why); ruff + full backend suite + frontend
build/vitest results; proposed CHANGELOG `[Unreleased] ### Added` bullet with `closes #25` +
commit message. Set this prompt's frontmatter (`status: done`/`completed`/`result`) and `mv` it
(plain mv) to `prompts/done/`, and tell me.
