---
name: 2026-06-30-refactor-split-api
status: done
created: 2026-06-30
model: sonnet
completed: 2026-06-29
result: >
  Split api.ts (2,011 lines) into 22 domain modules under frontend/src/lib/api/
  with barrel index.ts. Deleted old api.ts. tsc clean, 228 vitest tests pass,
  vite build succeeds. No consumer changes required.
---

# Task: Split `frontend/src/lib/api.ts` (2,011 lines) into per-domain modules — behavior-preserving

`api.ts` holds the entire app's API functions + types in one file, so **every** frontend task reads
all 2k lines. Split it by domain into `frontend/src/lib/api/` with a **barrel** that re-exports
everything, so **no caller has to change** (`import * as api from '@/lib/api'` and named imports
keep working). **Pure refactor — zero behavior change, zero signature change.**

## How
- Create `frontend/src/lib/api/` with:
  - `core.ts` — the shared internals: `ApiError`, CSRF helpers (`getCsrfToken`), `apiFetch`,
    `apiFetchForm`, and any shared constants. Export what other modules need.
  - Domain modules, each importing from `./core` and holding that domain's types + functions, e.g.:
    `setup.ts`, `auth.ts`, `users.ts`, `invites.ts`, `password-reset.ts`, `settings.ts`,
    `items.ts`, `import.ts` (import sessions + wizard + AddAsset), `tags.ts`, `creators.ts`,
    `favorites.ts`, `downloads.ts`, `shares.ts`, `print-records.ts`, `ai.ts` (ai actions/providers/
    usage), `agentql.ts`/`scraper.ts`, `jobs.ts`, `scheduled-jobs.ts`, `reviews.ts`, `issues.ts`,
    `changes.ts`, `tag-admin.ts`, `libraries.ts`, `backups.ts`, `export.ts`, `site-capabilities.ts`,
    `print-stats.ts`, `share-audit.ts`, `me.ts` (path-prefixes/nav/dashboard), `version.ts`,
    `widgets.ts`, etc. **Group by the existing section comments in api.ts** — don't invent a new
    taxonomy, just move each section into a file named for it. It's fine to consolidate small
    related sections.
  - `index.ts` — the **barrel**: `export * from './core'` + `export * from './<each module>'`. This
    becomes `@/lib/api`.
- **Delete the old `frontend/src/lib/api.ts`** (the `api/index.ts` barrel resolves `@/lib/api`).
- Every symbol previously exported from `api.ts` MUST be re-exported from the barrel (tsc will catch
  any miss — fix until clean). Do NOT rename or change any function/type/signature. No new deps.

## Constraints
- Behavior-preserving ONLY. Don't touch consumers (pages/components) except if an import path *must*
  change — it shouldn't, since `@/lib/api` still resolves. If any test imports a deep path, keep it
  working. Don't touch `frontend/src/pages/examples/`.

## Verify
- `cd frontend && npx tsc --noEmit` clean (this is the main safety net — it flags any missing
  re-export or broken import); `npx vitest run` passes unchanged; **and `npx vite build` MUST
  succeed**. Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: api.ts split into `lib/api/*` + barrel (token-efficiency refactor; no behavior change).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list (modules created); one-line
   `refactor:` commit message; tsc / vitest / **vite build** results; confirm every old export is
   re-exported (no consumer changes needed); anything unverified.
