---
name: 2026-06-27-ui-theme-examples
status: completed
created: 2026-06-27
model: sonnet
completed: 2026-06-27
result: Built 3 standalone UI prototypes (/example1 Mission Control, /example2 Atelier, /example3 Aurora) + /examples index; tsc clean, 131 tests green
---

# Task: Build 3 navigation/theme PROTOTYPES for review (`/example1..3` + `/examples`)

The current UI is rough ("looks like a web page from 1993"). The owner wants to **choose a
direction** before we revamp real pages. Build **three distinct, high-craft UI prototypes** as
standalone routes so they can be browsed and compared, then one is picked. **Do NOT touch the
real pages, the real `AppShell`, or real data** — these are self-contained mockups with hard-
coded MOCK data. They must render with no auth and no backend.

## Hard requirements (from the owner, apply to all examples unless noted)

- **Left-nav examples must have a collapsible sidebar** — full (label+icon) ↔ icon-only rail —
  with the collapsed/expanded state persisted to **`localStorage`** (per-browser).
- **Grouped nav with expand/collapse groups** (also persisted), so admins with many items can
  tidy up. Group e.g.: *Library* (Catalog, Tags, Creators, Favorites), *Import* (Add Asset,
  Inbox, Imports), *Operations* (Jobs, Scheduled Jobs, Issues, Change Log, Reviews), *Admin*
  (Users, Invites, AI Providers, Site Capabilities, Backups, Export, Pending Tags, Settings).
- **Menu items are role-based.** Include an in-page **"Viewing as: Admin / Editor / Viewer"**
  toggle in each prototype so the reviewer can SEE the menu change by access (Operations/Admin
  groups hidden for non-admins, etc.). This demonstrates the requirement live.
- **Bottom-left of the nav pane: current version** (e.g. `v0.8.0` — read from a mock const) **+
  a "Release notes ↗" link** (href to the GitHub releases page is fine). For the top-nav
  example, surface version + release-notes in a footer or the user menu.
- **At least one TOP-NAV example** (primary areas as buttons + dropdown menus — use the
  available `@radix-ui/react-dropdown-menu`) **and at least one LEFT-SIDE-NAV example.** The
  third is your choice — make it the highest-polish / most distinctive one.
- **Different polish levels** across the three. Make them genuinely different aesthetics, not
  three skins of the same thing.
- A top **command/search affordance** (a styled search box / ⌘K pill) and a **user avatar menu**
  (theme toggle, logout-mock) in each, so they feel like a real app.
- Each prototype renders the **same representative content** so they're comparable: a catalog
  view (card grid with thumbnail placeholders, tags, creator) + a small stats row + a tasteful
  **import-wizard-style panel** (the multi-step format is liked — show it looking fast/clean).
- **Responsive** and **light + dark** where it makes sense. Smooth, tasteful micro-interactions.

## Aesthetic direction (you own the craft — these are starting points, make them sexy)

Brand colors: **teal `#0FA4AB`**, **navy `#091D35`**. Use them, but vary per example.
**Avoid generic AI-slop aesthetics** — no default purple-on-white gradients, no plain Inter-on-
white card filler. Give each a real point of view, cohesive type scale, and intentional spacing.

- **`/example1` — "Mission Control"**: left rail, dense pro dashboard (Linear/Vercel-grade).
  Dark-first navy surfaces + teal accent (also light mode). Active item = teal accent + subtle
  bg; icon-rail collapse; comfortable-compact density. The "serious tool" look.
- **`/example2` — "Atelier"**: top nav + dropdowns, airy & premium. Light-first, warm neutrals,
  generous whitespace, larger type, rounded cards, soft shadows, tasteful teal CTAs. The
  "polished consumer SaaS" look.
- **`/example3` — your highest-polish, most distinctive take** (left nav). Go further: glassy/
  frosted depth, a ⌘K command-palette overlay mock, animated group collapse, pill nav — a "wow"
  pass. Distinct from example1.

## Technical constraints

- **Stack:** Tailwind CSS v4 + the existing CSS-variable (shadcn-style) theme tokens +
  `lucide-react` icons + `@radix-ui/react-dropdown-menu`/`react-slot` (already installed) +
  TanStack Query (not needed for mock data). **NO Mantine, NO toast library, NO new heavy deps.**
  You MAY add scoped CSS (e.g. an `examples.css`) and extend theme variables for polish.
- **Self-contained + mock data only** — no `apiFetch`, no real API calls, no auth context. Each
  example must render at its route with the dev stack up (browse at e.g.
  `http://<host>:8973/example1`) AND with no backend.
- **Register routes OUTSIDE the auth guards** in `App.tsx`: `/examples`, `/example1`,
  `/example2`, `/example3` (siblings of the public `/share/:token` route, before `<AuthGuard>`).
- Build an **`/examples` index page**: a clean landing that links to the three with a one-line
  description + a small thumbnail/preview of each, so the reviewer can flip between them easily.
- Keep each example's code under its own dir (e.g. `frontend/src/pages/examples/`) so it's easy
  to delete the losers later. Do NOT modify real pages, real `AppShell`, real `api.ts` data
  functions, or any backend.
- `npx tsc --noEmit` MUST be clean. `npx vitest run` MUST still pass (don't break existing
  tests; add a tiny test only if you write non-trivial pure logic like the localStorage hook).

## Working tree note

Another agent may be working on **backend** files concurrently — stay entirely within
`frontend/` (new files under `frontend/src/pages/examples/` + route additions in
`frontend/src/App.tsx`). Do not touch backend or non-example frontend pages.

## When done

1. Update this file's frontmatter (`status: completed`, `completed: 2026-06-27`, one-line result).
2. `git mv` into `prompts/done/`.
3. Add a short `docs/decisions.md` note (the three directions + where they live, so they can be
   pruned after selection).
4. **You are a spawned agent: do NOT commit, push, or change branch, NEVER `git add -A`.**
   Prepare the tree and **report back** with: complete file list; proposed one-line `feat:`
   commit message; `tsc`/`vitest` results; a 2–3 line description of each of the three
   directions and what makes them distinct; and the exact URLs to view them
   (`/examples`, `/example1`, `/example2`, `/example3`).
