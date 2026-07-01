---
name: 2026-06-27-phase-1b-frontend
status: completed
created: 2026-06-27
model: sonnet            # coding against a locked plan
completed: 2026-06-27
result: "Built full identity UI: API client, AuthContext with theme sync, first-run wizard, login, auth gate, logout, admin (users/invites/password-reset), settings (instance + theme), API-keys UI; tsc clean, 19/19 tests pass."
---

# Task: Phase 1b — Identity UI (frontend)

Build the frontend identity UI on top of the Phase 1a backend that is now fully
implemented and tested. This is **Phase 1 section 8** of
[`docs/build-plan.md`](../docs/build-plan.md).

**Exit criteria:** first-run wizard → admin login → invite a user → accept → settings
editable; per-user theme persists to the server when logged in.

## Before you start

- Read [`docs/build-plan.md`](../docs/build-plan.md) **Phase 1** section and the
  locked frontend decisions (Vite + React 18 + TS + Tailwind + shadcn/ui; TanStack
  Query; React Router; TanStack Table).
- Read [`PRD.md`](../PRD.md) §2, §4, §13, §15, §16.
- Read [`CLAUDE.md`](../CLAUDE.md) — operating rules (work on `dev`, conventional
  commits, no `Co-authored-by:`, never `--no-verify`).
- Read the **existing frontend shell** to extend it idiomatically:
  - `frontend/src/App.tsx` (provider chain, routing)
  - `frontend/src/components/ThemeProvider.tsx` (localStorage theme — extend to
    server-persist when logged in)
  - `frontend/src/pages/VersionPage.tsx` (TanStack Query pattern to follow)
  - `frontend/src/components/AppShell.tsx` (nav shell)
- Read **backend API** to know the exact endpoints and schemas you're calling:
  - `backend/app/routers/setup.py` — `/api/setup/status`, `/api/setup`
  - `backend/app/routers/auth.py` — `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`
  - `backend/app/routers/users.py` — `/api/users` (admin)
  - `backend/app/routers/invites.py` — `/api/invites` (admin + public accept)
  - `backend/app/routers/password_reset.py` — `/api/password-reset` (admin + public)
  - `backend/app/routers/settings.py` — `/api/settings`, `/api/me/theme`
  - `backend/app/routers/api_keys.py` — `/api/api-keys`

## Working tree check

Run `git status --porcelain`. Expect a clean tree (only prompt files may be present).
If any files the plan needs to modify have uncommitted changes, list them before touching.

## What to do

### 1. API client + auth context

- Create `frontend/src/lib/api.ts` — typed fetch wrapper that:
  - Always includes `X-CSRF-Token` header (read from `pf3d_csrf` cookie) on
    POST/PUT/PATCH/DELETE.
  - Throws on non-2xx responses with a typed error.
  - Exports typed functions for every backend endpoint used in this phase.
- Create `frontend/src/context/AuthContext.tsx` — React context that:
  - Calls `GET /api/auth/me` via TanStack Query (staleTime=0 so it re-checks on mount).
  - Exposes `{ user, isLoading, isAuthenticated, logout }`.
  - Wraps the app shell; unauthenticated users are redirected to `/login` (or `/setup`
    if `GET /api/setup/status` returns `{ initialized: false }`).

### 2. First-run wizard (`/setup`)

- Shown when `setup.initialized === false` (before auth context runs).
- Steps:
  1. **Required:** admin email + name + password, instance name, timezone.
  2. **Skippable (visibly):** all later steps (library, AI, tag seed) — just show
     "You can configure these in Settings later" and a Skip / Next button.
- On submit: `POST /api/setup` → success → redirect to `/` (app shell, now logged in
  with the auto-login session set by the backend).

### 3. Login page (`/login`)

- Email + password form → `POST /api/auth/login`.
- On success → redirect to where they came from (or `/`).
- Show friendly error on 401.

### 4. Authenticated app gate

- Wrap all non-public routes: unauthenticated → redirect to `/login`; uninitialized
  → redirect to `/setup`.
- Check `/api/setup/status` once on app load (before routing to login or main).

### 5. Logout

- Logout button in the nav → `POST /api/auth/logout` → clear auth context →
  redirect to `/login`.

### 6. Admin area

Create pages under `/admin/`:

- **Users** (`/admin/users`) — `GET /api/users` list in a TanStack Table; columns:
  email, name, role, active (badge). Actions per row: disable/enable (PATCH), promote
  to admin (PATCH).
- **Invites** (`/admin/invites`) — Create form (email → POST /api/invites) that shows
  the raw invite URL in a copy-to-clipboard dialog (shown once). History table:
  email, status, expires_at, created_at, revoke button (DELETE /api/invites/{id}).
- **Password reset** (`/admin/password-reset`) — email input → POST → copy raw reset
  URL (shown once). Revoke buttons for active tokens.

Admin area is only accessible to `role === "admin"` users; non-admins see a 403 page.

### 7. Settings page (`/settings`)

- **Instance settings** (admin only) — list from `GET /api/settings`; editable
  key/value pairs for the known instance settings (instance.name, instance.timezone,
  etc.); `PUT /api/settings/{key}` on save.
- **Per-user theme** — already in the nav as a toggle; now also persist to the server
  via `PUT /api/me/theme` when logged in. Extend `ThemeProvider`:
  - When authenticated, load `theme_pref` from `GET /api/auth/me` (already fetched
    by auth context) as the source of truth.
  - `setTheme` calls `PUT /api/me/theme` + updates localStorage as a fast-path.
  - Pre-login: localStorage-only (existing behavior).

### 8. API keys UI (`/settings/api-keys`)

- List (`GET /api/api-keys`): label, last_used_at, revoke button (DELETE).
- Create form: label input → POST → show raw key in a copy-to-clipboard modal
  (once-only display, clearly labelled as such).

### 9. TypeScript + tests

- `npx tsc --noEmit` must be clean.
- Add **vitest** tests for any non-trivial logic (auth context state machine, CSRF
  header injection, first-run routing logic, theme sync logic). Keep existing smoke
  test green.
- Keep shadcn/ui component usage consistent with the Phase 0 shell.

## Conventions to honor

- Match the locked decisions + Phase 0 structure exactly.
- **No features beyond Phase 1:** no Item/Tag/Library pages, no AI calls, no SSO,
  no email/SMTP, no Favorites (Phase 3).
- **CSRF:** every state-changing API call must include the `X-CSRF-Token` header
  (read from the `pf3d_csrf` cookie). Bearer-authenticated calls are exempt.
- **TanStack Query** for all server state. No manual `fetch` outside `lib/api.ts`.
- Secrets never in the repo. `.env.example` documents any new frontend env vars.

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-27`, one-line `result`).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Add `docs/decisions.md` entries for any non-obvious frontend decisions.
4. **You are a spawned agent: do NOT commit, push, or change branch.** Prepare the
   working tree and **report back** to the orchestrator with:
   - the complete file list + a proposed one-line `feat:` commit message,
   - exact local check results (`tsc --noEmit`, `vitest`),
   - any decision you had to make or anything you could not verify.
