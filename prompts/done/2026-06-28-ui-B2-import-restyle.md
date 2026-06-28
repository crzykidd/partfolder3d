---
name: 2026-06-28-ui-B2-import-restyle
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: |
  Restyled ImportWizardPage.tsx, ImportsPage.tsx, AddAssetModal.tsx to Aurora
  aesthetic. Aurora inline-style pattern (matching B1), stepper with labels +
  glow, tag chips, AI-assist ghost buttons with ✦ glyph, amber site-setup
  banner, aurora table/card wrappers, drop-zone keyboard accessibility added.
  tsc clean; 185/185 vitest pass. All features preserved.
---

# Task: UI revamp B2 — restyle the import flow to Aurora

Bring the **import experience** up to the Aurora aesthetic to match the shell + B1. The owner
specifically likes the **import-wizard format** — keep the multi-step structure; just make it
look polished, fast, and on-theme. **Restyle only — preserve every feature/behavior.** This is
B2 (B3 = admin pages, B4 = auth/public — later).

## Reference & stack
- Match the Aurora look (the A1 shell, B1's restyled Catalog/Item, and
  `frontend/src/pages/examples/Example3.tsx`) using the existing `--aurora-*` tokens in
  `frontend/src/index.css` + any shared primitives B1 introduced. Dark + light.
- Tailwind v4 + Aurora CSS-vars + minimal Radix (`react-dropdown-menu`/`react-slot`) +
  lucide-react + TanStack Query + `apiFetch`/`apiFetchForm`. **NO Mantine, NO toast, NO new deps.**
  Real data only. **Do NOT touch `frontend/src/pages/examples/`** or the shell/Catalog/Item (B1)
  or admin/auth pages (B3/B4).

## Working tree check
`git status --porcelain` clean on `dev`. A1/A2/B1 + the libraries fix are committed.

## Scope — restyle, preserve behavior
Restyle these REAL components to Aurora, keeping ALL functionality + endpoint calls + routes:
- **`ImportWizardPage.tsx`** (`/import/:sessionId`): the multi-step wizard (Title, Images +
  set-default, Tags reconciliation [confirmed/pending/manual], Creator [pick/dedupe or "my own
  design"], Summary + Commit). Make the **stepper** clean and obviously progressing, steps easy
  and fast to move through, the AI-assist buttons (suggest tags / cleanup / summarize) tasteful,
  the site-setup token banner clear, and the commit/cancel actions prominent. Keep polling,
  PATCH-per-step persistence, the site-capability banner, and the graceful "already committed"
  state.
- **`ImportsPage.tsx`** (`/imports`): the pending-imports list + the "From share link" panel.
  Aurora list/cards, status badges, "Open wizard" actions — all preserved.
- **`AddAssetModal.tsx`**: the Add-Asset dialog (Upload tab + From-URL tab, library selector,
  fields). Restyle to Aurora (custom overlay modal pattern already used). Keep both flows
  (create draft → upload → process → wizard; and URL → wizard) intact.

## Rules
- **Feature parity is mandatory** — visual pass only. Do not remove/rename/rewire any feature,
  endpoint, query key, or route. Reuse the shared Aurora primitives from B1 where they fit; don't
  fork the theme or disturb other pages.
- Responsive + accessible (focus states, keyboard nav through steps, labelled inputs, alt text).
- Keep the wizard genuinely **fast/easy** — minimal clicks, clear affordances; that's the owner's
  priority for import.

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes (don't break existing; adjust
  tests only if you change non-trivial pure logic — mostly markup/CSS).
- Frontend-only. If you think you need a backend change, STOP and report instead.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: any non-obvious restyle decisions.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`/
   `style:` commit message; tsc + vitest results; **feature-parity confirmation** (wizard steps +
   polling + per-step PATCH, AI-assist actions, site-setup banner, commit/cancel, imports list,
   from-share-link, AddAssetModal both tabs + library selector); examples/shell/B1/other pages
   untouched; anything you could not verify.
