---
name: 2026-06-30-clickable-stat-tiles
status: completed
created: 2026-06-30
model: sonnet            # frontend only
completed: 2026-06-30
result: >
  Added linkTo field to StatWidgetDef type and populated 9 tiles with verified routes.
  StatTileBase now conditionally renders as <Link> (react-router) when linkTo is set
  and not in editMode. Tiles without a sensible destination (creators, storage-used)
  remain non-clickable. favorites links to /catalog?favorited=true (CatalogPage
  supports that query param). All verification passed: tsc clean, 229/229 vitest,
  vite build success.
---

# Task: Make the global stat tiles clickable (navigate to detail pages)

The stat strip (`WidgetStatStrip`, shown on every page) renders stat tiles as plain,
non-clickable divs. Make each tile a link to the page where you can see more detail
(e.g. "Jobs Running" → the job monitor, "Pending Tags" → tag admin). Frontend only.

## Before you start

- Read `prompts/startnewsession.md` and `CLAUDE.md` (you are a spawned agent on `dev`;
  do NOT commit/push — prepare the tree and report back). Frontend stack: Tailwind +
  CSS-var theme + minimal Radix + lucide + TanStack Query + react-router. No Mantine, no toast lib.
- Read these fully:
  - `frontend/src/lib/widgets/registry.ts` — the tile registry (each tile: `id`, `title`,
    `region`, `icon`, `color`, `defaultForRoles`, `getValue`). Tile ids include
    `total-assets`, `prints-done`, `filament-used`, `success-rate`, `jobs-running`,
    `open-issues`, `pending-reviews`, `pending-tags`, `favorites`, `creators`, `storage-used`.
  - `frontend/src/components/shell/WidgetStatStrip.tsx` — renders tiles via `StatTileBase`
    (the individual tile div, ~lines 52-95) inside a `.map` (~lines 450-468); has an
    `editMode` for customizing the strip.
  - `frontend/src/App.tsx` — the route table (for valid link targets).

## Working tree check

`git status --porcelain` first. Expect clean `dev` (a render-reliability agent may be
running in parallel but it only touches backend/infra — no overlap). If `registry.ts`,
`WidgetStatStrip.tsx`, or `App.tsx` have unrelated uncommitted changes, list them and ask.

## What to do

1. Add an optional **`linkTo?: string`** field to the tile registry type and populate it
   per tile with the best existing route (verify each route exists in `App.tsx`):
   - `total-assets` → `/catalog`
   - `jobs-running` → `/admin/activity/jobs` (job monitor)
   - `open-issues` → `/admin/activity/issues`
   - `pending-reviews` → `/admin/activity/reviews`
   - `pending-tags` → `/admin/content/tags`
   - `prints-done` / `filament-used` / `success-rate` → `/admin/content/print-stats`
   - `favorites` → the favorites view. Check how favorites are surfaced (look for a
     `favorited`/`favorites` query param on `/catalog` or a dedicated route). If a clean
     target exists, link it; if not, **omit the link for this tile** rather than inventing one.
   - `creators` → there is a `/creators/:id` detail route but no creators-list route. **Omit
     the link** (no sensible destination) unless you find a real list route.
   - `storage-used` → not implemented (shows `—`). **Omit the link.**
   Tiles without `linkTo` stay non-clickable.

2. In `WidgetStatStrip` / `StatTileBase`, wrap a tile in a react-router `<Link to={linkTo}>`
   **only when** `linkTo` is set AND the strip is **not** in `editMode` (in edit mode the
   tile must remain draggable/removable, not navigate). Preserve all existing visuals
   (hover, compact sizing, edit-mode move/remove controls). Use the app's existing `Link`
   import convention. Add a subtle affordance (e.g. `cursor: pointer`) for linked tiles;
   don't restyle the tiles otherwise.

3. Keep role-gating intact — admin-only tiles already only render for admins, so their
   admin-route links are fine.

## Conventions to honor

- Match the existing component style (inline styles + CSS vars as used in the shell components).
- No new dependencies.
- **Verify (REQUIRED):** `npx tsc --noEmit` (or the project's typecheck), the relevant
  vitest if any covers the registry/strip, and **`npx vite build`** (the real gate — tsc
  and vitest miss babel/esbuild parse errors). Report results.

## When done

1. Update frontmatter (`status`, `completed: 2026-06-30`, `result`).
2. `git mv` into `prompts/done/` (success) or `prompts/failed/` (failure).
3. **Do NOT edit `docs/decisions.md`** (a parallel agent shares it — concurrent edits would
   race). Instead, include any non-obvious choice (e.g. which tiles you left unlinked and
   why) in your report-back; the orchestrator records it.
4. **Do NOT commit.** Prepare the tree; report back: files changed, the decision note (if
   any), a one-line `feat:`-prefixed commit message, and verify results (tsc + vitest + vite build).
