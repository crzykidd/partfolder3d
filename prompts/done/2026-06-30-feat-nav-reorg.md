---
name: 2026-06-30-feat-nav-reorg
status: done
created: 2026-06-30
model: sonnet
completed: 2026-06-29
result: >
  AdminSectionLayout created; App.tsx restructured with 5 nested section routes + 18 back-compat
  redirects; navConfig collapsed to 5 admin items; navConfig.test updated (18/18 pass, 229 total);
  QuickStartPage deep links updated; badge paths updated in both shells;
  docs/decisions.md updated. tsc clean, vitest 229/229 pass, vite build success.
---

# Task: Nav reorg — collapse the 17-item admin menu into 5 tabbed sections

Owner-approved. The admin nav today is two groups (Operations + a 12-item Admin) = 17 entries, which
is daunting. Reorganize into **5 themed admin sections**, each a single page with a **tab bar** that
hosts the existing admin pages as tab panels. **The existing admin page components keep their current
behavior — this is IA/routing/nav restructuring, not a rewrite of the pages.**

## Target structure (admin)
| Section (nav entry) | Route base | Tabs → existing page component |
|---|---|---|
| **Content** | `/admin/content` | Libraries (`LibrariesPage`) · Tags (`TagAdminPage` — already has pending + all-tags + starter-tags) · Print Stats (`PrintStatsPage`) |
| **Users & Access** | `/admin/access` | Users (`UsersPage`) · Invites (`InvitesPage`) · Password Resets (`PasswordResetPage`) |
| **AI & Scraping** | `/admin/ai` | AI Providers (`AiProvidersPage`) · AI Usage (`AiUsagePage`) · Site Capabilities (`SiteCapabilitiesPage` — hosts AgentQL) |
| **Jobs & Activity** | `/admin/activity` | Jobs (`JobsPage`) · Scheduled (`ScheduledJobsPage`) · Reviews (`ReviewsPage`) · Issues (`IssuesPage`) · Change Log (`ChangesPage`) |
| **Data & Backups** | `/admin/data` | Backups (`BackupsPage`) · Export (`ExportPage`) · Share Audit (`ShareAuditPage`) |

- **Tag Admin + Pending Tags merge:** the Content→Tags tab IS `TagAdminPage` (it already contains the
  pending-approval section). The standalone `PendingTagsPage` becomes redundant — drop it from the
  nav and **redirect** its old route to the Tags tab.

## Implementation (tabbed section pages — the approved approach)
1. **`AdminSectionLayout`** component (e.g. `frontend/src/components/admin/AdminSectionLayout.tsx`):
   an Aurora tab bar (role-aware) + `<Outlet/>`, driven by a tabs config `{label, path}[]`. Highlights
   the active tab from the route.
2. **Routing** (`App.tsx`): nested routes under each section base, e.g.
   `/admin/ai` → `AdminSectionLayout` with children `providers` (`AiProvidersPage`), `usage`
   (`AiUsagePage`), `sites` (`SiteCapabilitiesPage`); index redirects to the first tab. Do the same
   for all 5 sections. Keep everything under the existing admin guard.
3. **Back-compat redirects:** every OLD admin path (`/admin/libraries`, `/admin/users`,
   `/admin/ai-providers`, `/admin/ai-usage`, `/admin/site-capabilities`, `/admin/jobs`,
   `/admin/scheduled-jobs`, `/admin/issues`, `/admin/changes`, `/admin/reviews`, `/admin/backups`,
   `/admin/export`, `/admin/shares`, `/admin/print-stats`, `/admin/tags`, `/admin/pending-tags`,
   `/admin/invites`, `/admin/password-resets` if it exists) → `<Navigate replace>` to its new tab
   route, so bookmarks, QuickStart links, and any cross-links don't break.
4. **`navConfig.ts`:** replace the `operations` + `admin` groups with **one admin group of 5 items**
   (Content · Users & Access · AI & Scraping · Jobs & Activity · Data & Backups), each pointing at its
   section's first-tab route. Keep the non-admin groups (Library, Import, the personal Settings group:
   Quick Start / Settings / API Keys) as-is. Pick sensible lucide icons.
5. **QuickStartPage.tsx:** update the 5 deep links to the new routes (libraries → `/admin/content/libraries`,
   ai-providers → `/admin/ai/providers`, invites → `/admin/access/invites`, backups → `/admin/data/backups`,
   shares → `/admin/data/shares`).
6. **`navConfig.test.ts`:** update `REAL_ROUTES` to the new route set so the test passes.

## Rules
- The admin page COMPONENTS are reused unchanged (they render inside the tab outlet). Don't change
  their internal behavior. If a page assumed it was the whole route, ensure it still renders fine
  inside the layout (it should — they're self-contained). Add `PasswordResetPage` to the nav (it
  exists but wasn't linked).
- Aurora + `@/components/ui`. NO new deps. Don't touch backend or `frontend/src/pages/examples/`
  (already removed). Top-nav AND side-nav shells must both render the new 5-section structure (they
  share `navConfig`).

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes (update navConfig.test); **and
  `npx vite build` MUST succeed**. Manually trace each of the 5 sections' tab routes + each old→new
  redirect resolves. Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: the 5-section tabbed admin IA + route map + redirects (note: docs/README/
   `.env`/QuickStart references now use the new paths).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:` commit
   message; tsc / vitest / **vite build** results; the full new route map (section → tabs → component)
   + the old→new redirect list; confirmation both shells render the 5 sections + all admin pages still
   reachable; anything unverified.
