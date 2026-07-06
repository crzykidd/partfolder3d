---
name: 2026-07-05-catalog-has-asset-filter
status: done
created: 2026-07-05
model: sonnet
completed: 2026-07-05
result: >
  Delivered has_asset flag (batch EXISTS query, no N+1) + has_asset filter param on
  GET /api/items; AssetFilter three-state control (All/With files/Without files) wired
  into URL params + TanStack query key; Box icon on ItemCard and TableView title column
  when has_asset=true; 8 backend tests + 5 frontend tests; both suites green (822 BE /
  401 FE). Print asset roles: model + gcode (zip excluded). See docs/decisions.md.
---

# Task: Catalog "has print asset" filter + asset icon on catalog cards

We deliberately allow committed items with NO print asset (metadata-only URL imports —
see the #27 work in `prompts/done/`). Owner request: (1) a catalog filter to show
all / with-asset / without-asset items, and (2) a small icon on the catalog card
indicating the item HAS print assets, so metadata-only entries are visually distinct.

## Before you start

- Read `CLAUDE.md` and `docs/architecture.md` (module map: catalog router/page,
  items model/schema, file roles).
- Define "print asset" precisely: a `File` row whose role is a 3D-model-ish type per
  the role taxonomy in `backend/app/storage/inventory.py::infer_role` (model formats;
  decide whether gcode counts — recommendation: yes, it's printable — and record the
  choice in `docs/decisions.md`). Images/docs/sidecars do NOT count.
- The catalog already has a library filter (shipped v0.4.0, "All" default) — match its
  UI pattern and placement for the new filter.

## Working tree check

Run `git status --porcelain` first; if a file you need is dirty, stop and report.
Unrelated dirty files: surface once, don't block. This prompt file is exempt.

## What to do

1. **Backend — expose the flag:** add `has_asset: bool` to the catalog item summary
   schema (the list endpoint the catalog page consumes). Compute it set-based (EXISTS
   subquery or a single aggregate join on the qualifying roles) — no N+1 per item.
2. **Backend — filter param:** add an optional query param to the catalog list endpoint
   (e.g. `has_asset=true|false`, absent = all). Compose with the existing library/tag/
   search filters and pagination.
3. **Frontend — filter control:** on the catalog page, next to the library filter, a
   three-state control (All / With files / Without files — match existing filter
   control style; "All" default). Wire into the query params + TanStack Query key like
   the library filter does.
4. **Frontend — card icon:** on each catalog card, when `has_asset` is true, show a
   small lucide icon (e.g. `Box`) with an accessible label/tooltip ("Print files
   attached"). Subtle Aurora-muted styling; when false show nothing (the icon's
   absence is the signal — no red warnings in the catalog grid).
5. **Tests:** backend — has_asset true/false computed correctly (model file vs
   images-only vs zero files), filter param returns the right subsets, composes with
   library filter; frontend — filter control renders/updates the query, icon shows
   only for has_asset items.
6. **Changelog** `[Unreleased] → ### Added`: catalog has-asset filter + card icon
   (same commit).
7. **Verify:** full `make verify` (both gates) green.

## Conventions to honor

- Conventional prefix `feat:`. Changelog same commit. No `Co-authored-by:`.
  Never `git add -A`. Aurora styling; no new deps.

## When done

1. Update frontmatter; move to `prompts/done/` or `prompts/failed/`.
2. `docs/decisions.md`: record the "print asset" role-set definition.
3. **Spawned agent: do NOT commit or push; stage nothing.** Report: file list,
   proposed `feat:` one-liner, verify outcome (both suites), deviations.
