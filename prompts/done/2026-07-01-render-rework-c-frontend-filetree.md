---
name: 2026-07-01-render-rework-c-frontend-filetree
status: done
created: 2026-07-01
model: sonnet
completed: 2026-07-01
result: >
  All deliverables complete. New: file-tree browser (DownloadsPanel rewrite),
  ThreeMfPanel collapsible component, ViewIn3DButton stub (Phase D hook-ready),
  embedded-thumbnail Slicer badge in ImageCarousel, collapsible-per-file
  ObjectBreakdown, FilamentEntry/PlateEntry/preview_3d types in items.ts,
  file-tree.ts utility. Tests: 34 new (14 file-tree + 20 threemf-panel), 271
  total passing. Gates: tsc clean, vitest 271/271, vite build success.
---

# Task: Frontend — file-tree browser + collapsible 3MF detail panel

Replace the flat downloads list with a real folder tree, and surface the 3MF slice metadata
(from Phase A) as a collapsible per-file element. Phase C of the four-phase rework; assumes
Phases A + B are committed on `dev` (the API exposes `object_analysis` sliced fields,
`ImageOut.source="embedded"`, and `FileOut.preview_3d`).

## Before you start

- Read `docs/decisions.md` top entry (**2026-07-01 — Asset-detail / 3D-preview rework**) for
  the exact collapsed/expanded 3MF panel spec, and `prompts/startnewsession.md`.
- **Frontend stack (critical):** Tailwind + CSS-variable (shadcn-style) theme + minimal Radix
  (dropdown/slot) + lucide-react + TanStack Query + React Router. Uses the `apiFetch` /
  `apiFetchForm` CSRF wrappers. **There is NO Mantine and NO toast library.** Match this.
- Relevant code:
  - `frontend/src/pages/item/DownloadsPanel.tsx` — current flat file list.
  - `frontend/src/pages/item/ObjectBreakdown.tsx` — current analysis table.
  - `frontend/src/pages/item/ImageCarousel.tsx` — image/render display.
  - `frontend/src/pages/ItemPage.tsx` — composition.
  - `frontend/src/lib/api/items.ts` — `FileOut` / `ImageOut` / analysis types + `fileDownloadUrl`.

## Working tree check

`git status --porcelain`; ask before touching anything already dirty.

## What to do

1. **File tree** (replace/extend `DownloadsPanel`): build a folder hierarchy client-side by
   splitting each `FileOut.path` on `/` (no API change). Expand/collapse folders (lucide
   chevrons), per-file role badge + size + a per-file **Download** link (`fileDownloadUrl`).
   Keep the existing "Download all as ZIP" + include-print-history controls. Sensible defaults:
   folders collapsible, reasonable initial expansion.
2. **Type-aware affordances** per file row:
   - image → small inline thumbnail;
   - `preview_3d === true` (stl/obj/3mf under cap) → a **"View in 3D"** button. Phase D wires
     the actual viewer; here render the button and call a placeholder handler (a disabled/
     "coming soon" state or a stub prop) so Phase D can slot in without restructuring.
   - 3mf → the collapsible detail panel below.
3. **3MF collapsible panel** (extend `ObjectBreakdown` or a new `ThreeMfPanel` component),
   **collapsed by default, one per 3MF file**:
   - **Collapsed summary row:** filename · `Sliced`/`Unsliced` badge · print time · total
     filament (g) · objects · plates · small embedded thumbnail · expand chevron.
   - **Expanded detail:** filament rows (color **swatch** from `color_hex` · type · grams ·
     meters); per-plate breakdown (plate thumbnail + its objects + its time/filament); per-object
     list (name · dims · color). Clearly label `est_method: sliced` (real) vs. volume-estimate
     (unsliced) data.
   - Keep the existing STL/OBJ analysis display in the same collapsible pattern for consistency.
4. **Embedded thumbnails**: show `Image` rows with `source="embedded"` in the carousel/hero,
   badged (e.g. "Slicer") the way renders are badged today. Confirm the thumbnail priority
   chain (Phase A) surfaces them as the default where appropriate.

## Conventions to honor

- **Changelog:** `CHANGELOG.md [Unreleased]` (Added: file-tree browser + 3MF detail panel).
- **Verify (all three gates):** `tsc` (typecheck), `vitest` (add tests for tree-building from
  paths + the 3MF panel collapsed/expanded rendering), and **`npx vite build`** — the real
  gate; tsc/vitest miss babel/esbuild parse errors. All must pass before reporting.
- Match the existing component/style idioms; keep new deps to zero this phase (three.js lands
  in Phase D).

## When done

1. Frontmatter (`status`/`completed`/`result`), then `git mv` into `prompts/done/` or
   `prompts/failed/`.
2. Record non-obvious decisions in `docs/decisions.md`.
3. **Spawned agent: do NOT commit/push.** Prepare the tree, run all three frontend gates, and
   report back the paths to stage, a one-line conventional-commit message, and verification
   results. Orchestrator auto-commits on `dev`. Never `git add -A`.
