---
name: 2026-06-28-fix-libraries-management
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: >
  All deliverables complete. Dev library mount added to docker-compose.dev.yml
  (both backend and worker). Prod compose has commented examples. LibrariesPage.tsx
  (Aurora-styled) created with list/add/disable. createLibrary/disableLibrary added
  to api.ts. Libraries nav entry added to Admin group in navConfig.ts. Route
  /admin/libraries added to App.tsx under AdminGuard. Catalog empty-state CTA added
  (admin sees add-library link; non-admin sees ask-an-admin message). tsc clean,
  185 vitest tests pass, ruff clean, both compose configs valid, all 18 backend
  tests pass (includes test_create_item_dir_on_disk confirming mkdir-p path works).
---

# Task: Add Libraries management UI + dev library mount (functional gap)

The app has **no way to add/manage libraries in the UI** — the backend has CRUD
(`POST/GET/DELETE /api/libraries`) and the import wizard *lists* libraries, but there is no
management page, the first-run wizard doesn't create one, and the dev compose doesn't mount any
library directory. A fresh instance therefore can't store items. Fix all three. Build the new
page in the **Aurora** style (it's a new admin page).

## Facts
- Backend (already exists): `LibraryCreate {name, mount_path}`, `LibraryOut {id, name,
  mount_path, enabled}`; `POST /api/libraries` (create, 409 on duplicate mount_path), `GET
  /api/libraries` (list), `DELETE /api/libraries/{id}` (disable). `mount_path` is an absolute
  path INSIDE the container that must be a mounted volume.
- Frontend today: only `listLibraries()` in `api.ts` (used by the import library selector). No
  create/disable, no page, no nav entry.
- Stack: Tailwind v4 + Aurora CSS-vars (`--aurora-*`) + minimal Radix (dropdown/slot) +
  lucide-react + TanStack Query + `apiFetch`/`apiFetchForm`. **NO Mantine, NO toast, NO new deps.**
  Do NOT touch `frontend/src/pages/examples/`.

## Working tree check
`git status --porcelain` clean on `dev`. UI A1/A2/B1 are committed.

## What to do

### 1. Dev library mount (compose) — so libraries have a real home
- In `docker-compose.dev.yml`: mount a host library dir into **both backend and worker**:
  `./private_data/data/library:/library` (host-visible, gitignored, matches the dev storage
  convention). Pre-create `private_data/data/library/` so it exists.
- In `docker-compose.yml` (prod): add a commented example library mount + a short note that
  operators mount their own library volume(s) at e.g. `/library`. Document in `.env.example`
  and README (Getting started) that libraries live at a mounted path like `/library/<name>`.
- Validate: `docker compose config --quiet` and `docker compose -f docker-compose.dev.yml config
  --quiet` both pass.

### 2. Frontend: Libraries management page (Aurora-styled, admin)
- `frontend/src/pages/admin/LibrariesPage.tsx`: list libraries (name, mount_path, enabled, and
  item count if cheaply available — otherwise omit), an **Add library** form (name + mount_path
  with helper text: "Absolute path inside the container, mounted from your host — e.g.
  `/library/main`"), and a **disable** action (with confirm). Aurora look matching the shell/B1.
- `api.ts`: add `createLibrary({name, mount_path})` and `disableLibrary(id)` (and a typed
  `LibraryCreate`), reusing `apiFetch` + CSRF.
- Wire into nav + routes: add **Libraries** to the **Admin** group in `navConfig.ts` →
  `/admin/libraries`, and the route in `App.tsx` under `<AdminGuard>`.

### 3. Discoverability: catalog empty-state
- In `CatalogPage.tsx`, when there are **no libraries** (or no items because none exist yet),
  show a friendly empty-state CTA: "No libraries yet — add one to start storing models" linking
  to `/admin/libraries` (show the admin CTA only to admins; non-admins get a "ask an admin"
  message). Keep it tasteful + Aurora-styled; don't disturb the normal populated view.

### 4. Verify item creation works under a new library (don't assume)
- Confirm the storage layer creates the library/item directories as needed when an item is
  created under a freshly-added library (the atomic-move/inventory code should `mkdir -p` the
  item dir; the library root is the mounted `/library`). If there's a real gap (e.g. item create
  fails because the path isn't created), fix it minimally OR clearly report it — do not silently
  leave it broken. Add/extend a backend test for create-library → it appears in list (and, if
  feasible without huge effort, create-item-under-it).

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes (don't break existing; add a
  small test for the libraries api/page logic if non-trivial).
- Backend: `ruff check backend/`; if you touch backend/tests, run them against an **ephemeral
  Postgres** (`docker run -d --name pf3d-test-pg ... postgres:16-alpine`, set `DATABASE_URL`,
  `alembic upgrade head`, `pytest`); recreate the scratchpad venv if gone; tear down after.
- Both compose configs valid (step 1).

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: the dev library-mount convention + the libraries-management addition.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; check results (tsc/vitest/ruff/compose configs/any pytest); confirmation the
   add-library → mount → item-store path actually works (or a precise note on any remaining gap);
   examples untouched; anything you could not verify.
