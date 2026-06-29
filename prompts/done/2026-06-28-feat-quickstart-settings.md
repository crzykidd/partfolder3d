---
name: 2026-06-28-feat-quickstart-settings
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: QuickStartPage at /quick-start added; navConfig Quick Start item (first in Settings group); route in App.tsx; navConfig.test.ts REAL_ROUTES updated; tsc clean; 198 vitest tests pass; vite build succeeds.
---

# Task: "Quick Start" onboarding page in Settings

Add an in-app **Quick Start** guide that walks a new user through the important setup steps with
short explanations and **deep links** to the relevant pages, plus a **live "done / to-do" status**
where it's cheaply checkable. Role-aware (admins see admin setup steps). This is the "here are the
important things" page.

## Placement
- New page `frontend/src/pages/settings/QuickStartPage.tsx`, route **`/quick-start`** (authed,
  inside the AuroraShell). Add a **Quick Start** item to the nav (`navConfig.ts`) — put it near the
  top so it's discoverable (e.g. first item in the user/Settings group; visible to all roles). Add
  the route in `App.tsx`.
- **Do NOT edit `frontend/src/pages/settings/SettingsPage.tsx`** (another change is in flight
  there) — Quick Start is its own page that links *to* Settings.

## Content — Aurora cards (reuse `@/components/ui`: `AdminPage`/`PageHeader`/`Card`/`Badge`/
`Button`), each: icon (lucide) + title + 1–2 line explanation + a "Go" link to the real route.
Role-filter so non-admins don't see admin-only steps. Suggested steps (use the REAL routes — verify
them in `navConfig.ts`/`App.tsx`):
1. **Add a library** (admin) → `/admin/libraries`. "Libraries are where your model files live."
2. **Set your local path display** → `/settings` (path-prefix section). "Make on-disk paths match
   where *you* open files; pick Windows `\` or Linux/macOS `/`."
3. **Personalize** → `/settings`. "Theme (light/dark/system) and top-bar vs sidebar navigation."
4. **Import your first asset** → the Add-Asset / Imports route. "Drag-drop upload or paste a source
   URL; or drop a folder in the inbox."
5. **AI tagging (optional, admin)** → `/admin/ai-providers` + mention `/admin/ai-usage`. "Add a
   Claude/OpenAI/Ollama key to auto-suggest tags; usage + cost is tracked."
6. **Invite your team (admin)** → `/admin/invites`. "No open registration — send invite links."
7. **Backups (admin)** → `/admin/backups`. "Schedule DB + config backups (library files aren't
   backed up by design)."
8. **Sharing** → mention per-item share links + the admin full-site share. (Link to an item or the
   share-audit page as appropriate.)

Trim/merge as sensible; keep it scannable (don't overwhelm). A short intro line at top.

## Live status (only where a cheap existing query exists — keep it best-effort)
Add a small **Badge** ("✓ Done" / "To do") to steps you can cheaply check with EXISTING endpoints,
e.g.: libraries configured (`listLibraries` length > 0), path prefix set (`/api/me/path-prefix`),
AI provider configured (`listAiProviders` length > 0). For steps with no cheap check, omit the
badge (just show the card). Never block render on these — if a query fails, just don't show its
badge.

## Constraints
- **Frontend only.** No backend/migration. Reuse existing api.ts functions; do NOT edit
  SettingsPage.tsx, ImportWizardPage.tsx, or catalog-utils.ts (other changes in flight). Tailwind +
  Aurora + `@/components/ui` + lucide. NO new deps. Don't touch `frontend/src/pages/examples/`.
- Verify the routes you link to actually exist in `App.tsx` before linking.

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes (update `navConfig.test.ts`
  REAL_ROUTES with `/quick-start` if that test enforces it); **and `npx vite build` MUST succeed**
  (the real gate). Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: one line (Quick Start as its own page + which steps have live status).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; tsc / vitest / **vite build** results; which steps show live status; confirmation
   you didn't touch the in-flight files; anything unverified.
