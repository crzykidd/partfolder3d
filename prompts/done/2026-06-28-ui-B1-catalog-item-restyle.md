---
name: 2026-06-28-ui-B1-catalog-item-restyle
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: >
  Restyled CatalogPage.tsx and ItemPage.tsx to the Aurora aesthetic using
  --aurora-* CSS vars and inline styles matching the shell pattern.
  Added lucide-react icons (Box, Star, Search, LayoutGrid, List, X, Copy,
  Check, Download). AuroraSection local primitive introduced in ItemPage.
  tsc clean; 185/185 vitest tests pass. All features preserved.
---

# Task: UI revamp B1 — restyle Catalog + Item pages to Aurora

The Aurora shell (A1) + widget dashboard (A2) are live. Now bring the **real Catalog page and
Item page** up to the **Aurora** aesthetic so the content matches the chrome. **Restyle only —
preserve every feature and behavior.** This is B1 of the page-restyle phase (B2 = import wizard,
B3 = admin pages, B4 = auth/public — later).

## Reference & stack
- **Look:** match the new Aurora shell + `frontend/src/pages/examples/Example3.tsx` catalog grid
  (glass cards, deep dark gradient surfaces, teal `#0FA4AB` accent + subtle glow, rounded, soft
  depth; refined type scale). Use the **existing Aurora theme tokens** added in A1
  (`--aurora-*` in `frontend/src/index.css`) and the shell's component patterns — do NOT invent a
  parallel theme. Honor **dark + light** modes.
- **Stack:** Tailwind v4 + Aurora CSS-vars + minimal Radix (`react-dropdown-menu`/`react-slot`) +
  `lucide-react` + TanStack Query + `apiFetch`/`apiFetchForm`. **NO Mantine, NO toast lib, NO new
  deps.** Real data/real endpoints only. **Do NOT touch `frontend/src/pages/examples/`.**

## Working tree check
`git status --porcelain` clean on `dev`. A1 (`3ca51e2`) + A2 (`3915af7`) committed.

## Scope — restyle, do not break
Restyle these REAL pages/components to Aurora while keeping ALL current functionality:
- **`CatalogPage.tsx`** (+ its card/table/row components): the grid view (Aurora glass cards with
  thumbnail/render placeholder, title, creator, tags, favorite star, file-count/size, render/
  print badges — like Example3's cards), the table view, the **grid/table toggle**, search +
  **filter bar**, tag-cloud / tag-filter UI, sort controls, **favorites** star/filter, pagination,
  and the **TanStack Virtual** virtualization (keep it working — don't regress scroll perf). The
  page sits inside the Aurora shell; its stat strip + rail come from the shell, so don't duplicate
  them.
- **`ItemPage.tsx`** (+ its sections): image carousel + set-default-image, full metadata, tags,
  linked creator, source link, license, the **full dir path + prefix rewrite + copy** control,
  **downloads** (single file + ZIP queue/poll + include-history checkbox), **print history**
  section (list/add/edit/delete, gcode/photo upload, parsed filament/time, structured settings),
  and the **share controls** (mint/list/revoke link + copy). Restyle all to Aurora cards/sections;
  keep every behavior + endpoint call exactly.

## Rules
- **Feature parity is mandatory** — this is a visual pass. Do not remove, rename, or rewire any
  feature, endpoint call, query key, or route. If you must refactor a shared bit for styling,
  keep its behavior identical and don't touch unrelated pages.
- Reuse/extract small shared Aurora UI primitives (e.g. a `Card`, `Badge`, `Button`, `Section
  header`, `Stat`/chip) if it helps consistency — but keep them lightweight and Tailwind-based,
  and don't disturb the shell or other pages' current look (B2–B4 will restyle those).
- Responsive + accessible (focus states, keyboard for interactive controls, alt text on images).
- Keep it fast: don't introduce heavy re-renders; preserve virtualization + query caching.

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes (don't break the 185 existing;
  add/adjust tests only if you change non-trivial pure logic — this is mostly markup/CSS).
- No backend changes expected (frontend-only). If you somehow need one, STOP and report instead.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: any non-obvious restyle decisions (shared primitives introduced, carousel/
   table approach, etc.).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:` or
   `style:`/`refactor:` commit message (pick best fit — likely `feat:` since it's a visible UI
   upgrade, or `style:`); `tsc` + `vitest` results; explicit **feature-parity confirmation**
   (grid/table toggle, search/filter, favorites, virtualization, carousel, downloads/ZIP, print
   history, share controls all still work); confirmation examples untouched + shell/other pages
   not disturbed; anything you could not verify (e.g. live behavior needing the running app).
