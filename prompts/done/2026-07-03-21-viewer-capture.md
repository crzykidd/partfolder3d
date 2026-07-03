---
name: viewer-capture
status: completed
created: 2026-07-03
model: Sonnet
completed: 2026-07-03
result: Added camera capture button to 3D viewer; ImageSource.captured enum + migration 0022; source param on upload endpoint; wizard capture deferred
---

# Task: Add 3D viewer capture — save current view as item image (issue #21)

Adds a "Save view as image" camera-icon button inside the in-browser 3D viewer modal.
Each click captures the current WebGL canvas frame and POSTs it to
`POST /api/items/{key}/images` as a new `Image` row with `source=captured`. Multiple
captures per item are supported. Wizard capture (ImagesStep.tsx) is deferred.

## Before you start

- Read CLAUDE.md and standards.md.
- Frontend stack: Tailwind + CSS-var theme + minimal Radix + lucide + TanStack Query +
  apiFetch/apiFetchForm CSRF wrapper. No Mantine, no toast library.
- `ImageSource` is a native PG enum (`Enum(ImageSource, name="imagesource")`); adding
  `captured` requires a migration.

## Working tree check

Run `git status --porcelain` and verify no conflicts with:
- backend/app/models/image.py
- backend/app/routers/items.py
- backend/alembic/versions/
- frontend/src/components/viewer/ModelViewer.tsx
- frontend/src/pages/item/DownloadsPanel.tsx
- frontend/src/lib/api/items.ts

## What to do

1. **backend/app/models/image.py** — add `captured = "captured"` to `ImageSource` enum.
2. **backend/alembic/versions/0022_image_source_captured.py** — migration using same
   pattern as 0021: `ALTER TYPE imagesource ADD VALUE IF NOT EXISTS 'captured'` inside
   `autocommit_block()`. down_revision = "0021".
3. **backend/app/routers/items.py** — add `source: Annotated[str, Query()] = "uploaded"`
   param to `upload_image`; validate it and use `ImageSource.captured` when `source == "captured"`.
4. **frontend/src/lib/api/items.ts** — add optional `source` param to `uploadItemImage`
   (`'uploaded' | 'captured' = 'uploaded'`), passed as `?source=captured` query string.
5. **frontend/src/components/viewer/ModelViewer.tsx** — add `preserveDrawingBuffer: true`
   to Canvas `gl` prop; add `onCapture?: (blob: Blob) => void`, `isCapturing?: boolean`,
   `isOwner?: boolean` props; add a `GlCanvas` inner component (uses `useThree` to store
   `gl.domElement` in a ref); add camera button in the overlay that calls `canvas.toBlob`.
6. **frontend/src/pages/item/DownloadsPanel.tsx** — add `useQueryClient` + `useMutation`
   for image upload inside `DownloadsSection`; add `captureStatus` state for inline
   loading/error/success feedback; pass `isOwner`, `onCapture`, `isCapturing` to
   `LazyModelViewer`.
7. **CHANGELOG.md** — add entry to `[Unreleased] ### Added`.
8. **docs/decisions.md** — record ImageSource enum choice and wizard deferral.

## Conventions to honor

- Gate capture button on `isOwner`.
- Each capture appends a new Image (never overwrites).
- No Mantine/toast — use inline state text for loading/success/error in viewer overlay.
- `preserveDrawingBuffer: true` on the Canvas (required for `toBlob` to return non-blank).
- One conventional-commit `feat:` message, `closes #21` in body. No Co-authored-by.

## When done

1. Update this file's frontmatter: `status: completed`, `completed: 2026-07-03`, `result: ...`
2. `git mv` to `prompts/done/`.
3. Record decisions in `docs/decisions.md`.
4. Bundle into the single commit with all changed files.
