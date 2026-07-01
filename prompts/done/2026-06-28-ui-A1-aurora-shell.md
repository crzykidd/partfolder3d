---
name: 2026-06-28-ui-A1-aurora-shell
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: >
  Aurora shell built and verified. Backend: migration 0011 (nav_layout column),
  GET/PUT /api/me/nav-layout, 6 new passing tests, ruff clean. Frontend: navConfig.ts
  (real routes), useNavLayout hook (server→localStorage→role default fallback),
  SideNavShell + TopNavShell + StatStrip + QuickImportRail + AuroraShell,
  CSS variable theme tokens (--aurora-*), App.tsx wired to AuroraShell.
  All checks: tsc clean, vitest 148/148, pytest 362/362, alembic 0011 round-trip OK.
  Examples untouched. Migration-restart note: running containers need recreate to pick
  up 0011; frontend falls back gracefully via localStorage + role default until then.
---

# Task: UI revamp A1 — real Aurora AppShell with switchable top/side nav

The owner chose the **Aurora** prototype (`frontend/src/pages/examples/Example3.tsx`) as the
real app's look. Build the **real authenticated app shell** in that aesthetic, with a
**switchable top-nav / side-nav** driven by a per-user setting, replacing today's plain
`AppShell`. Existing pages render unchanged INSIDE the new shell (page restyling is a later
phase). This is **A1** of the UI revamp (A2 = widget customization framework; B = page restyle).

## Reference & stack
- **Aesthetic:** lift the Aurora visual language from `frontend/src/pages/examples/Example3.tsx`
  (deep dark gradient, frosted-glass surfaces, teal `#0FA4AB` accent + glow, pill active nav,
  brand navy `#091D35`) into REAL, reusable shell components + theme tokens. Also reference
  `Example2.tsx` for the **top-nav horizontal arrangement** (render it in the Aurora skin, not
  Atelier's light look). Keep a **dark + light** mode (theme toggle already exists).
- **Stack (mandatory):** Tailwind v4 + CSS-variable theme + minimal Radix (`react-dropdown-menu`
  /`react-slot` only) + `lucide-react` + TanStack Query + the `apiFetch`/`apiFetchForm` CSRF
  wrapper. **NO Mantine, NO toast lib, NO new heavy deps.** The example files are mock prototypes
  — extract their *look*, but the real shell uses REAL data/routes/auth (no mock).
- **DO NOT delete or modify `frontend/src/pages/examples/`** — kept as reference.

## Working tree check
`git status --porcelain` — expect clean on `dev`. All phases 0–10 are committed.

## What to build

### 1. Single shared nav config (source of truth)
- `frontend/src/lib/navConfig.ts(x)`: the real nav model — groups → items with `{label, path,
  icon (lucide), requiredRole?}`. Mirror the actual routes/role-gating in `App.tsx`:
  - **Library**: Catalog (`/catalog`), Tags (`/tags` if present), Creators (`/creators`),
    Favorites (`/favorites`). (Use the real paths that exist; omit any that don't.)
  - **Import**: Add Asset (opens AddAssetModal), Imports (`/imports`).
  - **Operations** (admin): Jobs (`/admin/jobs`), Scheduled Jobs (`/admin/scheduled-jobs`),
    Issues (`/admin/issues`), Change Log (`/admin/changes`), Reviews (`/admin/reviews`).
  - **Admin** (admin): Users, Invites, AI Providers, Site Capabilities, Backups, Export,
    Pending Tags, Tag Admin, Print Stats, Settings — use the real `/admin/*` paths from
    `App.tsx`/`AppShell.tsx`.
  - Filter items/groups by the current user's role (from `useAuth()`).
- Verify every path against the real `App.tsx` routes — do NOT invent routes.

### 2. Two shells from that config
- `SideNavShell` — collapsible sidebar (full ↔ icon-rail, persisted to localStorage), grouped
  with expand/collapse (persisted), pill active state w/ teal glow, Aurora glass. Like Example3.
- `TopNavShell` — top bar: brand, primary groups as buttons + Radix dropdown menus for their
  items, global search affordance, theme toggle, user/avatar menu. Aurora-skinned Example2
  arrangement. (Admins have many items → that's why they default to the sidebar.)
- Both include a **version + release-notes** affordance: read version from `GET /api/version`
  (already exists); "Release notes ↗" links to the GitHub releases page. In SideNav it sits
  bottom-left; in TopNav put it in the user menu or a slim footer.
- Both render `<Outlet/>` for the page, plus the regions in #4.

### 3. Per-user nav-layout setting (top vs side)
- **Backend:** add a per-user `nav_layout` preference, mirroring the existing theme pref
  (`/api/me/theme` + `users.theme_pref`). Add `users.nav_layout` (nullable; values `top`|`side`)
  via migration **0011**, and `GET`/`PUT /api/me/nav-layout` (auth'd). When unset/null, the
  **default is resolved by role: admin → `side`, otherwise → `top`** (resolve in the API
  response or the frontend — your call, but document it). `alembic upgrade head`+`downgrade base`
  must pass.
- **Frontend:** a `useNavLayout()` hook — reads the server pref (TanStack Query), falls back to
  localStorage then the role default; a **toggle in the user menu** flips it and PUTs the pref
  (optimistic, persists). **Graceful fallback:** if `GET/PUT /api/me/nav-layout` errors/404s
  (e.g. migration not yet applied on a running container), fall back to localStorage + role
  default so the app NEVER hard-breaks. The chosen layout picks which shell wraps the app.

### 4. The two regions (functional now, customizable in A2)
- **Top stat strip:** a row of stat tiles with **REAL data** — Total Assets (items count),
  Prints Done / Filament / Success Rate (from the print-stats endpoint), Jobs Running (jobs
  endpoint). Use a fixed sensible default set for A1 (A2 makes it customizable). Aurora tile
  styling from Example3. If an endpoint/value isn't available, show a graceful dash, not an error.
- **Right rail:** a collapsible panel (persist collapsed state) containing a **Quick Import**
  widget that is FUNCTIONAL — it should launch the real import flow (reuse `AddAssetModal` /
  the real Add-Asset → `/import/:sessionId` path). Fixed single widget for A1 (A2 makes the rail
  a customizable widget area). Make the rail collapsible and not crowd small screens (responsive:
  hide/collapse on narrow widths).

### 5. Wire it in
- Replace the current authenticated-layout `AppShell` usage in `App.tsx` with the new shell so
  ALL authenticated pages render inside it with the chosen layout + regions. Keep `AuthGuard`/
  `AdminGuard` and all routes intact. Public routes (`/login`, `/setup`, `/share/:token`,
  `/examples`, `/example1..3`) stay OUTSIDE and unchanged. You MAY keep the old `AppShell.tsx`
  file or replace it — but everything must still route and render.

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes (don't break existing tests);
  add vitest for the pure logic (nav role-filtering, layout default-by-role, useNavLayout
  fallback).
- Backend: `ruff check backend/`; **ephemeral Postgres** for migration 0011 + tests:
  `docker run -d --name pf3d-test-pg -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p 5433:5432 postgres:16-alpine`,
  `export DATABASE_URL="postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d"`,
  `alembic upgrade head && alembic downgrade base && alembic upgrade head`, then `pytest` (add a
  test for the nav-layout pref endpoint + default-by-role). Recreate the scratchpad venv at
  `/tmp/claude-1000/-home-manderse-projects-partfolder3d/bd4b77b1-dcc4-4fbf-8dc0-d3990161f59a/scratchpad/venv`
  if gone. Tear the container down when done.

## When done
1. Update frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md` entries: the locked UI decisions (Aurora theme; nav_layout = per-user
   setting, default-by-role admin=side/user=top, toggle; the two customizable regions to come in
   A2; graceful pref fallback), and how the shell is structured.
3. **You are a spawned agent: do NOT commit, push, or change branch, NEVER `git add -A`.** Prepare
   the tree and report back with: complete file list; proposed one-line `feat:` commit message;
   exact check results (ruff/pytest+count/alembic 0011/tsc/vitest); confirmation real
   routes/data/auth used (no mock, examples untouched) + the migration-restart note (running
   container needs recreate to apply 0011; frontend falls back gracefully meanwhile); anything
   you could not verify.
