---
name: 2026-06-28-ui-A2-widget-framework
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: >
  Widget registry + per-user dashboard_layout (migration 0012, GET/PUT /api/me/dashboard)
  delivered. 11 stat tiles + 5 panel widgets registered. WidgetStatStrip and WidgetRail
  replace StatStrip/QuickImportRail in both shells. useDashboardLayout hook with graceful
  fallback. tsc clean, vitest 185/185 (37 new), ruff clean, pytest passed, alembic
  0012 round-trip verified.
---

# Task: UI revamp A2 — customizable widget framework (top stat strip + right rail)

Turn the two A1 regions into a **per-user customizable widget system**: the **top stat strip**
(stat tiles) and the **right rail** (panel widgets). One framework, a widget registry, a
per-user layout persisted server-side, with role-based defaults. Builds on A1 (committed
`3ca51e2`). The Aurora look + switchable nav already exist — extend them; do not regress them.

## Owner's intent (from the brief + the circled screenshot `private_data/screenshot/`)
- The **right rail** (where Quick Import sits) is a **collapsible widget area** the user fills:
  **add / remove / reorder** widgets; **default = Quick Import**.
- The **top stat strip** is **customizable**: role-based default tile set, the user can **add
  more** tiles, and **density is adjustable** so an admin can show **2 rows of smaller tiles to
  see more** at once.
- Persisted **per-user** (a real account setting, like nav_layout/theme).

## Stack / constraints
- Tailwind v4 + CSS-variable Aurora theme + minimal Radix (`react-dropdown-menu`/`react-slot`) +
  `lucide-react` + TanStack Query + `apiFetch`/`apiFetchForm`. **NO Mantine, NO toast lib, and
  NO new deps** — in particular **no drag-and-drop library**: implement reorder with move
  up/down (+ remove + an "add widget" picker); native HTML5 drag is an optional nice-to-have, not
  a dependency. Real data only. Do NOT touch `frontend/src/pages/examples/`.

## Working tree check
`git status --porcelain` clean on `dev`. A1 is committed.

## What to build

### 1. Widget registry
- `frontend/src/lib/widgets/registry.ts(x)`: each widget = `{ id, title, region: 'stat'|'panel',
  defaultForRoles?: Role[], icon, component, dataHook? }`. The registry is the single place to add
  a widget later.
- **Stat-tile widgets** (region `stat`): Total Assets, Prints Done, Filament Used, Success Rate,
  Jobs Running (migrate A1's `StatStrip` tiles into registered widgets), plus extra opt-in tiles:
  Open Issues, Pending Reviews (admin), Pending Tags (admin), Favorites, Creators, Storage Used
  (use real endpoints; if an endpoint is missing, show a graceful dash — don't invent backend).
- **Panel widgets** (region `panel`): Quick Import (default; reuse A1's rail widget), Recent
  Items / Recent Activity, Jobs Running (live mini-list), Pending Reviews (admin), Favorites mini.
  Keep each panel widget compact and real-data-backed.

### 2. Per-user dashboard layout (persisted server-side)
- **Backend:** add a per-user `dashboard_layout` JSON/text column on `users` (migration **0012**)
  + `GET`/`PUT /api/me/dashboard` (auth'd), mirroring the nav_layout/theme pref pattern. Shape
  (validate loosely): `{ stats: { density: 'comfortable'|'compact', tiles: string[] },
  rail: { collapsed: boolean, widgets: string[] } }` (lists are ordered widget ids). When null,
  resolve a **role-based default** (admins get a denser/larger default set incl. admin widgets;
  non-admins get a lean set with Quick Import). `alembic upgrade head`+`downgrade base` pass.
- **Frontend:** a `useDashboardLayout()` hook — server pref → localStorage → role default;
  **graceful fallback** if the endpoint errors/404s (pre-migration) so nothing hard-breaks.
  Optimistic PUT on change.

### 3. Customization UX
- **Stat strip:** an "edit" affordance to add/remove tiles (picker of available stat widgets),
  reorder (up/down), and a **density toggle** (comfortable ↔ compact). Compact + more tiles
  naturally wraps to 2 rows — verify the grid wraps cleanly and tiles shrink in compact mode.
- **Right rail:** collapse/expand (persisted), add widget (picker), remove, reorder (up/down).
  Default contains only Quick Import.
- Keep edit mode lightweight and obvious (e.g., a small "Customize" button per region revealing
  controls); changes persist immediately. Responsive: rail collapses on narrow screens.
- All driven by the registry + the per-user layout; both layouts (top-nav and side-nav) host the
  regions consistently (stat strip below the top chrome; rail on the right when expanded).

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes (don't break the 148 existing;
  add tests for the layout default-by-role + registry filtering + the dashboard hook fallback).
- Backend: `ruff check backend/`; **ephemeral Postgres** for migration 0012 + a `/api/me/dashboard`
  test (default-by-role + round-trip):
  `docker run -d --name pf3d-test-pg -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p 5433:5432 postgres:16-alpine`,
  `export DATABASE_URL="postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d"`,
  `alembic upgrade head && alembic downgrade base && alembic upgrade head`, then `pytest`.
  Recreate the scratchpad venv at
  `/tmp/claude-1000/-home-manderse-projects-partfolder3d/bd4b77b1-dcc4-4fbf-8dc0-d3990161f59a/scratchpad/venv`
  if gone. Tear the container down when done.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: widget-registry design, dashboard_layout shape + role defaults, reorder-
   without-DnD choice, density approach.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; check results (ruff/pytest+count/alembic 0012/tsc/vitest); the migration-
   restart note; confirmation real data + examples untouched + nav/shell not regressed; anything
   unverified.
