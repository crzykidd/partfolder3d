---
name: 2026-06-28-ui-B3b-admin-settings-restyle
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: All 10 admin/settings pages restyled to Aurora using shared @/components/ui primitives. New AuroraToggle primitive added to Button.tsx. tsc clean; 185/185 vitest pass. Feature parity confirmed across all pages.
---

# Task: UI revamp B3b — restyle the remaining admin/settings pages to Aurora

Finish the admin restyle by bringing the remaining admin + settings pages up to Aurora, **reusing
the shared primitives B3a created** in `@/components/ui`. **Restyle only — preserve every
feature/behavior.** (B4 = auth/public is the last piece after this.)

## Reference & stack
- **REUSE the shared primitives from `frontend/src/components/ui/`** (barrel: `@/components/ui`):
  `AdminPage`, `PageHeader`, `Card`, `SectionHeader`, `DataTable`/`TableRow`/`Td`/`Pagination`,
  `Badge` (+ `BadgeVariant` and the `*Variant` helpers), `Button`, `FilterPill`, `EmptyState`,
  `Field`/`AuroraInput`/`AuroraSelect`. Match how the B3a pages (e.g. `IssuesPage`, `ReviewsPage`,
  `ShareAuditPage`) and `LibrariesPage` use them. Add a new primitive ONLY if genuinely missing
  (and put it in `@/components/ui`).
- Existing `--aurora-*` tokens; Tailwind v4 + minimal Radix + lucide + TanStack Query +
  `apiFetch`/`apiFetchForm`. **NO Mantine, NO toast, NO new deps.** Real data only. **Do NOT
  touch** `frontend/src/pages/examples/`, the shell, B1 (Catalog/Item), B2 (import), the B3a ops
  pages, `LibrariesPage` (already Aurora), or the auth/public pages (B4).

## Working tree check
`git status --porcelain` clean on `dev`. A1/A2/B1/B2/B3a + libraries committed.

## Restyle these pages (feature parity — preserve all behavior/endpoints/routes)
- `admin/UsersPage.tsx` — user list, create/disable, roles.
- `admin/InvitesPage.tsx` — generate invite link, invite history (status/who/when), revoke, copy link.
- `admin/PasswordResetPage.tsx` — admin-generate reset link, copy, revoke.
- `admin/AiProvidersPage.tsx` — provider CRUD, write-only key field, enable, test-connection.
- `admin/SiteCapabilitiesPage.tsx` — per-domain capabilities CRUD, token set/clear, reprobe.
- `admin/BackupsPage.tsx` — backup list, run-now, retention setting, download, delete, and the
  **LOUD "library files are NOT backed up" callout** (keep it prominent).
- `admin/ExportPage.tsx` — JSON catalog export download.
- `admin/TagAdminPage.tsx` — pending approve/reject, category, aliases CRUD, merge.
- `admin/PendingTagsPage.tsx` — pending-tag list + approve (+ the client-side fuzzy duplicate
  detection section).
- `settings/SettingsPage.tsx` — whatever settings it hosts (theme, etc.); make it Aurora and
  consistent. If it's a natural home for app-level settings, fine — just restyle, don't add
  features.

## Rules
- **Feature parity mandatory** — visual pass; no feature/endpoint/route/query-key changes.
- Consistent with B3a: same primitives, spacing, table/badge/button conventions.
- Responsive + accessible (focus states, keyboard, labelled controls, confirms on destructive
  actions preserved).

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes (don't break existing).
- Frontend-only. If you think you need a backend change, STOP and report.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: any notable decisions (new primitive added, etc.).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `style:`/
   `feat:` commit message; tsc + vitest results; per-page feature-parity confirmation; confirmation
   the shared primitives were reused (not re-forked) + other areas untouched; anything unverified.
