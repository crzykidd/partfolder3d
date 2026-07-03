---
name: 2026-07-02-versionpage-settings-nav-text
status: done
created: 2026-07-02
model: sonnet
completed: 2026-07-02
result: >
  Updated VersionPage.tsx — replaced the stale "Admin → Settings" text with a
  React Router <Link> pointing to /admin/content/libraries, labelled
  "Admin → Content" (confirmed correct from navConfig.ts + App.tsx).
  Added changelog entry to CHANGELOG.md [Unreleased] Fixed section.
  npm run build (tsc + vite) and vitest (280 tests) both pass.
---

# Task: Fix stale "Admin → Settings" nav text on the version/landing page (issue #7)

The post-login landing/version page tells users configuration lives in **"Admin → Settings"**, but
those settings are actually under **"Admin → Content"**. The instruction points at a menu item that
doesn't exist.

## Before you start

- Location: `frontend/src/pages/VersionPage.tsx` (~lines 108–109):
  `Configuration, library paths, and system settings are managed in <strong>Admin → Settings</strong>.`
- **Verify the real location/label + route** before editing — check the sidebar nav config (grep
  `nav`, `Admin`, `Content`, `Settings`, the routes in the router) to confirm the exact wording and
  path where library/system settings actually live.

## What to do

1. Update the copy to the correct location (**Admin → Content**, or whatever the nav actually
   shows — confirm first).
2. Prefer making it a real **link** to that settings route (React Router `<Link>`), styled to match
   the surrounding text, so it can't drift out of sync with a hard-coded breadcrumb again.
3. Leave the "report issues, see the project repository" part as-is (unless it's also a dead/wrong
   link — fix only if clearly broken).

## Conventions to honor

- **Changelog:** `CHANGELOG.md [Unreleased]` (Fixed: corrected the settings location text on the
  version/landing page).
- **Verify:** `docker exec partfolder3d-frontend-1 sh -c 'cd /app && npm run build'` (tsc -b + vite
  build) + `npm test` (vitest). All green before reporting.

## When done

1. Frontmatter, then `git mv` into `prompts/done/` or `failed/`.
2. Record non-obvious decisions in `docs/decisions.md` if any.
3. **Spawned agent: do NOT commit/push.** Prepare the tree, run the gates, report paths to stage +
   a one-line `fix:` message (reference issue #7) + verification. Orchestrator commits on `dev`.
   Never `git add -A`.
