---
name: 2026-06-30-refactor-split-itempage
status: done
created: 2026-06-30
model: sonnet
completed: 2026-06-29
result: >
  ItemPage.tsx split from 2,589 lines into 9 files under pages/item/. ItemPage.tsx
  now 300 lines. tsc clean, vitest 228/228, vite build success. All features preserved.
---

# Task: Split `frontend/src/pages/ItemPage.tsx` (2,589 lines) into per-feature components — behavior-preserving

`ItemPage.tsx` packs the whole item view (carousel, metadata, path display, downloads, print
history, share controls, object breakdown, modified badge, image upload/delete, item delete) into
one file, so any item-page bug reads all 2.6k lines. Extract cohesive subcomponents so the page
becomes a thin orchestrator. **Pure refactor — preserve EVERY feature, behavior, query key, and
state interaction. No functional change.**

## How
- Create `frontend/src/pages/item/` (or `frontend/src/components/item/`) and extract the existing
  internal components/sections into their own files, e.g.: `ImageCarousel.tsx` (+ its pager/thumbs),
  `Metadata.tsx`, `PathDisplay.tsx`, `DownloadsPanel.tsx` (single + ZIP queue/poll + include-history),
  `PrintHistory.tsx` (records CRUD + gcode/photo upload + stats), `ShareControls.tsx` (mint/list/
  revoke/copy), `ObjectBreakdown.tsx`, `ModifiedBadge.tsx`/override control, and any small shared
  bits (shared style constants → a local `item/styles.ts` or keep inline). `ItemPage.tsx` keeps the
  top-level data query + layout and composes the subcomponents.
- Move the component's own helpers/types alongside it. Keep using `@/lib/api`, `@/components/ui`,
  the `--aurora-*` tokens. Pass data/handlers via props (don't change what the API calls do).
- **Do NOT change behavior**: same TanStack queries/keys, same mutations, same carousel paging,
  same upload/delete/set-default, same print-history forms, same share flow, same delete-to-trash.
  This is mechanical extraction + prop-wiring only. NO new deps. Don't touch
  `frontend/src/pages/examples/`.

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes unchanged; **and `npx vite build`
  MUST succeed**. Do NOT commit `dist/`. (tsc + build are the safety net for prop/import wiring.)

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: ItemPage split into `item/*` subcomponents (token-efficiency refactor; no behavior change).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list (components extracted +
   resulting ItemPage.tsx line count); one-line `refactor:` commit message; tsc / vitest / **vite
   build** results; confirmation all item-page features preserved (carousel/paging, set-default,
   image upload/delete, downloads+ZIP, print history, shares, object breakdown, modified badge,
   delete-to-trash); anything unverified (note visual/interaction needs a browser).
