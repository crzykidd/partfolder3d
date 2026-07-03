---
name: 2026-07-03-catalog-grid-modes
status: completed
created: 2026-07-03
model: sonnet
completed: 2026-07-03
result: Implemented responsive grid columns (ResizeObserver), compact/full grid mode, and configurable page size selector in CatalogPage.tsx
---

# Task: Catalog grid improvements — responsive columns, compact/full mode, page-size selector

Add three UX improvements to the catalog grid view in `frontend/src/pages/CatalogPage.tsx`.

## Before you start

- Frontend stack: Tailwind + Radix + lucide + TanStack Query + apiFetch — NO Mantine/toast.
- Verify with `npm run build` (tsc -b && vite build) + `npx vitest run` for touched tests.
- The catalog is already paginated — do NOT rebuild pagination, only make page size configurable.

## What to do

1. **Responsive columns** — ResizeObserver on the VirtualGrid scroll container; compute
   `cols = computeCols(containerWidth, minCardWidth)` from `catalog-utils.ts`; use `cols`
   for both row-chunking and `gridTemplateColumns`.

2. **Compact / Full grid mode** — `gridMode` state persisted to `pf3d-catalog-grid-mode`
   (default `compact`). Compact: 220 px min card, 160 px image, objectFit cover. Full:
   340 px min card, 260 px image, objectFit contain with subtle letterbox backdrop. Segmented
   toggle in toolbar (grid view only).

3. **Page-size selector** — `perPage` state persisted to `pf3d-catalog-per-page` (default 20).
   Options: 20/40/60/100. Wire into query key and `per_page`. Reset to page 1 on change.

## When done

1. Update frontmatter: status, completed, result. ✓
2. `git mv` to `prompts/done/`. ✓
3. Record decisions in `docs/decisions.md`. ✓
4. Bundle into single `feat:` commit with CHANGELOG.md update.
