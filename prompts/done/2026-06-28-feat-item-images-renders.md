---
name: 2026-06-28-feat-item-images-renders
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: >
  All 9 Phase-14 tests pass (403 total, 0 failures). ruff clean. tsc clean. vitest 185
  passed. vite build succeeded. Migration 0014 applied. render_item reconciles Image rows;
  upload/delete endpoints added; ItemPage shows Rendered badge, upload control, per-image
  delete. docs/decisions.md updated. Committed to dev.
---

# Task: Surface renders as gallery images + image upload/delete on an item

Two related gaps, confirmed with the owner:
1. **Renders are generated but never surfaced** — `render_item` writes `renders/<sha256>.png`
   into the item dir but creates no `Image` row and no API field, so the carousel/catalog never
   show them. → Make a successful render appear as a gallery **Image** (carousel + catalog
   thumbnail), with a "Rendered" badge.
2. **No way to add images to an existing item** (only import-time + set-default). → Add
   **upload + delete** on the item page (set-default already exists).

## Key facts (verified)
- `Image` model (`app/models/image.py`): `id`, `item_id`, `path` (relative to item dir),
  `source` (enum `ImageSource` = `scraped` | `uploaded`), `is_default`, `order`, `created_at`.
- Image files are served to the browser via `GET /api/items/{key}/files/{path}` (the carousel uses
  `src={/api/items/${itemKey}/files/${img.path}}`).
- `ItemDetail.images` comes from **DB Image rows** (`_build_sidecar_data` / the items detail query),
  NOT from the sidecar — so a render Image row in the DB will automatically appear in the carousel.
- `default_image_path` (the `is_default` image's path) drives the **catalog grid thumbnail**.
- `render_item` (in `worker.py`) renders each model `File` (role=model) to `renders/<sha256>.png`
  (SHA-keyed cache; skips if the png already exists; new sha on file change).
- Existing set-default: `PATCH /api/items/{key}/default-image`. Match its auth (authenticated user
  + CSRF) for the new mutations.
- Images are part of the **sidecar**; renders are derived/regenerable and must **NOT** be written
  to the sidecar (keep render Image rows DB-only so the sidecar stays portable/curated).

## Working tree check
`git status --porcelain` clean on `dev`. Latest: lxml fix committed.

## Part 1 — Renders as gallery images

### Migration 0014 — add `render` to the enum
- Add `render` to `ImageSource` (`scraped` | `uploaded` | `render`). Postgres `ALTER TYPE
  imagesource ADD VALUE 'render'` **cannot run inside a transaction** — use alembic's
  `op.get_context().autocommit_block()` (or `op.execute` with the connection's autocommit). Make
  `upgrade()` idempotent if practical. Removing an enum value on downgrade isn't supported by PG —
  make downgrade a documented no-op (or recreate the type); `alembic upgrade head` MUST succeed
  (the round-trip `downgrade base && upgrade head` may not fully reverse the enum — document it).

### `render_item`: reconcile render Image rows
- After rendering, the item has a set of current render pngs (`renders/<sha>.png` for each
  rendered model file). **Reconcile** the `source=render` Image rows for that item to exactly
  match that set: create rows for new render pngs, delete `source=render` rows whose png no longer
  exists (and you may delete orphaned old png files). Do NOT create duplicate render rows across
  repeated runs. `Image` has no `file_id`, so identify render rows by `(item_id, source=render)` +
  matching `path`.
- **Default image:** if the item has **no** `is_default` image after reconciling, set one render
  as default (so the catalog grid shows a thumbnail). If a curated (`scraped`/`uploaded`) image is
  already default, leave it.
- **Order:** render images sort after curated images.
- Keep all of this inside the existing best-effort/transaction handling — a DB hiccup recording the
  Image row must not crash the worker or fail the job spuriously (log + continue).
- Ensure `GET /api/items/{key}/files/renders/<sha>.png` actually serves the PNG (the files
  endpoint serves by path relative to the item dir — verify the `renders/` subpath isn't blocked
  by a role/allowlist; fix minimally if it is).
- **Sidecar:** exclude `source=render` images from sidecar writes.

## Part 2 — Upload / delete images on an item
- `POST /api/items/{key}/images` (multipart, authed + CSRF): accept an image file (validate
  content-type/extension: png/jpg/jpeg/webp/gif; reject others), write it safely into the item dir
  (match where scraped/uploaded images live — check the import-commit code; use a safe unique
  filename, no path traversal, stay within the item dir), create an `Image` row (`source=uploaded`,
  `order` after existing), and sync the sidecar. Return the updated item detail (or the new image).
- `DELETE /api/items/{key}/images/{image_id}` (authed + CSRF): remove the Image row + its file
  (within the item dir). If it was the default, reassign default to another image (or none). Sync
  the sidecar. (Deleting a render image is allowed but it'll regenerate on next render — fine.)
- Add `source` (and confirm `id`, `is_default`, `order`) to the `ImageOut` schema so the frontend
  can badge renders and manage rows.

## Part 3 — Item page UI (`frontend/src/pages/ItemPage.tsx`)
- Renders already flow into the carousel once they're Image rows — add a small **"Rendered"**
  badge on `source === 'render'` images (Aurora styling).
- **Upload** control (file input or drag) → `POST images` → invalidate the item query.
- **Delete** button per image (with confirm) → `DELETE images/{id}` → invalidate.
- Keep the existing **set-default**. (No drag-reorder.)
- Add `uploadItemImage(key, file)` + `deleteItemImage(key, imageId)` to `api.ts` (multipart upload
  via the existing form/CSRF helper). Keep all current item-page features intact (feature parity).

## Verify
- Backend: `ruff check backend/`; **ephemeral Postgres** for migration 0014 + tests
  (`docker run -d --name pf3d-test-pg -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p 5433:5432 postgres:16-alpine`,
  set `DATABASE_URL`, `alembic upgrade head`, `pytest`). Add tests: a successful render creates a
  `source=render` Image row (and sets it default when no other default); re-render reconciles
  without duplicating; `POST images` adds an uploaded Image + file; `DELETE images/{id}` removes
  it and reassigns default; renders excluded from the sidecar. Recreate the scratchpad venv at the
  session path if gone; tear down the container.
- Frontend: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite
  build` MUST succeed** (the real gate). Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: render→Image reconcile approach, default-image rule, sidecar exclusion of
   renders, enum-migration (non-transactional ADD VALUE + downgrade no-op), upload storage location.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; check results (ruff / pytest+count / alembic 0014 / tsc / vitest / **vite
   build**); the migration-restart note (recreate for 0014); confirmation renders now appear as
   gallery images + the catalog thumbnail; feature parity on the item page; anything unverified.
