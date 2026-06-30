# PartFolder 3D — Admin Navigation Architecture

Documents the final information architecture (IA) for the admin navigation,
introduced in the post-Phase-10 nav reorg. Useful for future devs adding new
admin features.

---

## Overview

The admin navigation has **5 sections**, each rendered as a single route with a
tab bar (`AdminSectionLayout`). Both the top-bar nav and side nav render the same
5 items (both read `navConfig.ts`). The non-admin nav is unchanged.

### Non-admin nav groups

| Group | Pages |
|---|---|
| Library | Catalog, Favorites, My Creations |
| Import | Add Asset, Imports |
| Personal | Quick Start, Settings, API Keys |

---

## Admin sections and route map

| Section | Base route | Tabs |
|---|---|---|
| Content | `/admin/content` | Libraries, Tags, Print Stats |
| Users & Access | `/admin/access` | Users, Invites, Password Resets |
| AI & Scraping | `/admin/ai` | AI Providers, AI Usage, Site Capabilities |
| Jobs & Activity | `/admin/activity` | Jobs, Scheduled, Reviews, Issues, Change Log |
| Data & Backups | `/admin/data` | Backups, Export, Share Audit |

### Detailed tab → component map

| Section | Tab slug | Route | Component |
|---|---|---|---|
| Content | `libraries` | `/admin/content/libraries` | `LibrariesPage` |
| Content | `tags` | `/admin/content/tags` | `TagAdminPage` |
| Content | `print-stats` | `/admin/content/print-stats` | `PrintStatsPage` |
| Users & Access | `users` | `/admin/access/users` | `UsersPage` |
| Users & Access | `invites` | `/admin/access/invites` | `InvitesPage` |
| Users & Access | `password-resets` | `/admin/access/password-resets` | `PasswordResetPage` |
| AI & Scraping | `providers` | `/admin/ai/providers` | `AiProvidersPage` |
| AI & Scraping | `usage` | `/admin/ai/usage` | `AiUsagePage` |
| AI & Scraping | `sites` | `/admin/ai/sites` | `SiteCapabilitiesPage` |
| Jobs & Activity | `jobs` | `/admin/activity/jobs` | `JobsPage` |
| Jobs & Activity | `scheduled` | `/admin/activity/scheduled` | `ScheduledJobsPage` |
| Jobs & Activity | `reviews` | `/admin/activity/reviews` | `ReviewsPage` |
| Jobs & Activity | `issues` | `/admin/activity/issues` | `IssuesPage` |
| Jobs & Activity | `changes` | `/admin/activity/changes` | `ChangesPage` |
| Data & Backups | `backups` | `/admin/data/backups` | `BackupsPage` |
| Data & Backups | `export` | `/admin/data/export` | `ExportPage` |
| Data & Backups | `shares` | `/admin/data/shares` | `ShareAuditPage` |

---

## Back-compat redirects

Every old `/admin/*` path is kept as a `<Navigate replace>` redirect so bookmarks,
Quick Start deep links, and cross-links never 404.

| Old path | Redirects to |
|---|---|
| `/admin/libraries` | `/admin/content/libraries` |
| `/admin/tags` | `/admin/content/tags` |
| `/admin/pending-tags` | `/admin/content/tags` |
| `/admin/print-stats` | `/admin/content/print-stats` |
| `/admin/users` | `/admin/access/users` |
| `/admin/invites` | `/admin/access/invites` |
| `/admin/password-reset` | `/admin/access/password-resets` |
| `/admin/ai-providers` | `/admin/ai/providers` |
| `/admin/ai-usage` | `/admin/ai/usage` |
| `/admin/site-capabilities` | `/admin/ai/sites` |
| `/admin/jobs` | `/admin/activity/jobs` |
| `/admin/scheduled-jobs` | `/admin/activity/scheduled` |
| `/admin/reviews` | `/admin/activity/reviews` |
| `/admin/issues` | `/admin/activity/issues` |
| `/admin/changes` | `/admin/activity/changes` |
| `/admin/backups` | `/admin/data/backups` |
| `/admin/export` | `/admin/data/export` |
| `/admin/shares` | `/admin/data/shares` |

Note: `/admin/pending-tags` redirects to `/admin/content/tags` because
`PendingTagsPage` is removed from the nav (it was merged into `TagAdminPage`'s
pending section); the component is retained in the codebase as a reference.

---

## Adding a new admin page

1. Build the page component under `frontend/src/pages/admin/`.
2. Decide which section it belongs to (Content / Users & Access / AI & Scraping /
   Jobs & Activity / Data & Backups).
3. Add a tab entry in the relevant `AdminSectionLayout` usage in `App.tsx` (or the
   routes file).
4. Add a redirect from any legacy path if needed.
5. Update `docs/nav-architecture.md` (this file) with the new row.

---

## Implementation notes

- `AdminSectionLayout` (`frontend/src/components/admin/AdminSectionLayout.tsx`):
  Aurora underline tab bar with `NavLink` isActive detection and `<Outlet />`. No new
  dependencies.
- `navConfig.ts`: Replaced `operations` + `admin` groups with a single `admin` group
  of 5 items. Both `SideNavShell` and `TopNavShell` read `navConfig`.
- The pending-reviews badge is attached to the **Jobs & Activity** nav item
  (path `/admin/activity/jobs`).
