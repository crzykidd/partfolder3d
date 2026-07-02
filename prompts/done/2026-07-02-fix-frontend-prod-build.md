---
name: 2026-07-02-fix-frontend-prod-build
status: done
created: 2026-07-02
model: sonnet
completed: 2026-07-02
result: >
  Fixed all 24 npm run build errors (20 TS6133 unused-import removals + 4 real
  type fixes). Updated CI gates in ci.yml and dev-checks.yml (step only, job names
  unchanged). Updated startnewsession.md and docs/decisions.md. CHANGELOG updated.
  NOTE: .claude/commands/release-prep.md could not be updated — auto-mode classifier
  blocked writes to .claude/ files; orchestrator must apply the npx tsc --noEmit →
  npm run build change manually.
---

# Task: Fix the frontend production build (`npm run build`) and correct the typecheck gates

The frontend production image build (`frontend/Dockerfile --target prod` → `npm run build`) has
**always failed** — which is why `partfolder3d-frontend` was never publishable. `npm run build` is
`tsc -b && vite build`, and `tsc -b` compiles the project references
(`tsconfig.app.json`/`tsconfig.node.json`) which set `noUnusedLocals`/`noUnusedParameters: true`.
Both CI (`ci.yml` + `dev-checks.yml` "Frontend" job) and `/release-prep` only ran
`npx tsc --noEmit`, which uses the *root* `tsconfig.json` (references-only, no strict settings) and
catches NONE of these. Fix the build AND fix the gates so it can't regress.

## Context

- Run `cd frontend && npm run build` (in the `partfolder3d-frontend-1` container:
  `docker exec partfolder3d-frontend-1 sh -c 'cd /app && npm run build'`) to see the full error
  list. ~24 errors as of now:
  - **~20 trivial TS6133** "declared but never used" — unused `React` imports (the project uses the
    automatic JSX runtime, so `import React` is unneeded), unused imports/vars/params. Remove them.
  - **~4 real type errors** needing actual fixes (understand each, don't just silence):
    - `src/components/shell/SideNavShell.tsx:227` — TS2345/TS7006: a functional updater
      `(prev) => …` passed where a `string[]` is expected + implicit `any`. Type it correctly.
    - `src/pages/CatalogPage.tsx:868` — TS2322: `MutationFunction` return-type mismatch
      (`Promise<void> | Promise<FavoriteOut>` vs `void`). Align the mutation's types.
    - `src/pages/admin/AiUsagePage.tsx:262` — TS2322: a Lucide component passed where `ReactNode`
      is expected (likely needs `<Icon />` or a prop-type fix).
- **Do NOT change behavior.** These are type-correctness fixes; keep runtime behavior identical.
- Frontend stack: Tailwind + CSS-var theme + Radix + lucide + TanStack Query; no Mantine/toast.

## What to do

1. **Fix every `npm run build` error** in `frontend/src`. Prefer removing genuinely-unused imports;
   for the real type errors, fix the types properly. Re-run `npm run build` until it's clean
   (`tsc -b` passes AND `vite build` produces a bundle).
2. **Correct the CI gate — change STEPS only, never job names.** In BOTH `.github/workflows/ci.yml`
   and `.github/workflows/dev-checks.yml`, the `frontend` job's typecheck step currently runs
   `npx tsc --noEmit`; change it to run **`npm run build`** (which does `tsc -b && vite build`) so
   CI catches strict-project-reference errors and validates the real bundle. Keep the `npm test`
   (vitest) step. **CRITICAL: do NOT rename the `name: Frontend` job (or any other job) — those
   bare job names are main's required-check contexts; renaming silently breaks release merges.**
   Only edit the run steps.
3. **Correct the release gate.** In `.claude/commands/release-prep.md`, change the frontend
   type-check validation from `npx tsc --noEmit` to `npm run build` (note briefly *why*: the root
   tsconfig skips the strict project-reference settings the real build uses).
4. **Record the gotcha** in `prompts/startnewsession.md` (verify-discipline section) and
   `docs/decisions.md`: the frontend typecheck gate is **`npm run build` (`tsc -b`)**, NOT
   `npx tsc --noEmit` — the latter uses the references-only root tsconfig and misses
   `noUnusedLocals`/type errors that the prod build enforces.

## Conventions to honor

- **Changelog:** `CHANGELOG.md [Unreleased]` — Fixed: frontend production build (`npm run build`)
  now succeeds; corrected CI + release typecheck gates.
- **Verify (all must pass):**
  - `docker exec partfolder3d-frontend-1 sh -c 'cd /app && npm run build'` → clean (tsc -b + vite
    build).
  - `docker exec partfolder3d-frontend-1 sh -c 'cd /app && npm test'` → vitest still green (was 280).
  - **`docker build -f frontend/Dockerfile --target prod -t pf3d-frontend-test ./frontend`** → now
    SUCCEEDS (the real prod image build). Clean up the throwaway image.
  - `ci.yml` + `dev-checks.yml` are valid YAML and **all job names are unchanged** (ci.yml jobs:
    Lint, Frontend, Config validation, Migration check, Compose validation, Image build, Test;
    dev-checks jobs keep their `(dev)` suffixes). Confirm this explicitly in your report.

## When done

1. Frontmatter (`status`/`completed`/`result`), then `git mv` into `prompts/done/` or
   `prompts/failed/`.
2. Record decisions in `docs/decisions.md`.
3. **Spawned agent: do NOT commit/push.** Prepare the tree, run every verification, and report back
   the paths to stage, a one-line `fix:` conventional-commit message, and verification results
   (incl. explicit confirmation the job names are unchanged). The orchestrator commits on `dev`.
   Never `git add -A`.
