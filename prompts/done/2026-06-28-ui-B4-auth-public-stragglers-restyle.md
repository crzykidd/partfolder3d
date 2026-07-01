---
name: 2026-06-28-ui-B4-auth-public-stragglers-restyle
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: All 9 pages restyled to Aurora. tsc clean, 185/185 vitest pass. LoginPage/SetupPage logic preserved byte-for-byte. PublicSharePage stays auth-free.
---

# Task: UI revamp B4 (final) — restyle auth/public pages + remaining authenticated pages to Aurora

The last restyle pass to make the **entire app** Aurora. Two groups:
**(1) public/auth pages** (rendered OUTSIDE the AuroraShell — standalone full-screen Aurora
layouts) and **(2) remaining authenticated content pages** (rendered INSIDE the shell — use the
shared primitives). **Restyle only — preserve every feature/behavior.** After this, the revamp is
complete.

## Reference & stack
- Match the Aurora aesthetic established everywhere (shell A1, B1 Catalog/Item, B2 import, B3a/B3b
  admin, `LibrariesPage`). Use the `--aurora-*` tokens + the shared `@/components/ui` primitives
  (`AdminPage`/`PageHeader`/`Card`/`SectionHeader`/`DataTable`/`Badge`/`Button`/`Field`/
  `AuroraInput`/`AuroraSelect`/`EmptyState`/`AuroraToggle`). For the public/auth pages (no shell),
  build clean **standalone Aurora screens** (centered glass card on the Aurora gradient bg, brand
  logo/wordmark, dark+light) — reuse `Card`/`Button`/`Field` where they fit.
- Tailwind v4 + minimal Radix + lucide + TanStack Query + `apiFetch`/`apiFetchForm`. **NO Mantine,
  NO toast, NO new deps.** Real data only. **Do NOT touch** `frontend/src/pages/examples/`, the
  shell, or any already-restyled page (Catalog/Item, import, all admin ops + settings,
  Libraries).

## Working tree check
`git status --porcelain` clean on `dev`. Everything through B3b + libraries committed.

## Group 1 — public / auth pages (standalone Aurora, OUTSIDE the shell)
Restyle, preserving all behavior/endpoints/routes:
- `LoginPage.tsx` — email/password login, error states, the post-login flow (the setupStatus +
  me invalidation logic stays exactly as is).
- `SetupPage.tsx` — first-run wizard (admin + instance basics + skippable steps); keep the
  setQueryData(['setupStatus'], …) + navigation logic intact.
- `InviteAcceptPage.tsx` — accept-invite → create account → redirect.
- `ResetPasswordPage.tsx` — password reset via token → redirect to login.
- `PublicSharePage.tsx` — the unauthenticated share view (item view + downloads; full-site catalog
  browse). Keep it OUTSIDE auth, only calling `/api/public/share/...`, with the friendly
  "no longer available" 403 state. Make it look polished (it's public-facing — first impression).

## Group 2 — remaining authenticated pages (INSIDE the shell, use primitives)
Restyle to Aurora using `@/components/ui` + B1 patterns, preserving all behavior:
- `ApiKeysPage.tsx` — per-user API keys: create (copy-once), list, revoke.
- `CreatorPage.tsx` — creator browse/detail (their items grid — match B1's catalog card style).
- `MyCreationsPage.tsx` — "my creations" view (items the user designed — catalog-style).
- `VersionPage.tsx` — version/about page (tidy Aurora card; show version from `/api/version`).
- If a Tags or Favorites view turns out to be its own page (not a CatalogPage route), restyle it
  too; if they're just CatalogPage routes, they're already done — note which.

## Rules
- **Feature parity mandatory** — visual pass; no feature/endpoint/route/query-key changes.
- Public pages must NOT import auth context or hit authenticated endpoints (keep PublicSharePage
  clean). Keep destructive-action confirms + copy-once flows.
- Responsive + accessible.

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes (don't break existing; the
  auth tests must still pass — don't change LoginPage/SetupPage logic, only markup/styling).
- Frontend-only. If you think you need a backend change, STOP and report.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: notable decisions; and note the **UI revamp is complete** (all real pages
   on Aurora; examples retained as reference).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `style:`/
   `feat:` commit message; tsc + vitest results; per-page feature-parity confirmation (incl. that
   LoginPage/SetupPage logic + auth tests are unchanged and PublicSharePage stays auth-free);
   confirmation examples/shell/already-restyled pages untouched; a list of any pages still NOT on
   Aurora (should be none but say so); anything you could not verify.
