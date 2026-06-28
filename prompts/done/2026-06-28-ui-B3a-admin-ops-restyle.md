---
name: 2026-06-28-ui-B3a-admin-ops-restyle
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: >
  Created 8 shared Aurora admin primitives under frontend/src/components/ui/
  (AdminPage, PageHeader, Card, Badge, Button, FilterPill, DataTable, TableRow,
  Td, Pagination, EmptyState, Field, AuroraInput, AuroraSelect). Restyled
  JobsPage, ScheduledJobsPage, IssuesPage, ChangesPage, ReviewsPage,
  PrintStatsPage, ShareAuditPage to Aurora aesthetic. Full feature parity
  preserved. tsc --noEmit clean; vitest 185/185 pass.
---

# Task: UI revamp B3a — restyle the Operations admin pages to Aurora (+ shared admin primitives)

Restyle the **Operations** admin pages to Aurora and, while doing it, **establish the shared
Aurora admin UI primitives** that B3b will reuse for the remaining admin pages. **Restyle only —
preserve every feature/behavior.** (B3b = the rest of the admin/settings pages; B4 = auth/public.)

## Reference & stack
- Match the Aurora look already established by the shell (A1), the restyled Catalog/Item (B1),
  the import flow (B2), and especially the **already-Aurora `LibrariesPage.tsx`** — use it as the
  canonical admin-page reference. Use the existing `--aurora-*` tokens in
  `frontend/src/index.css`. Dark + light.
- **Consistency note:** prefer the established **Tailwind-utility + `--aurora-*` token** approach
  used by the shell/B1/LibrariesPage for the shared primitives and pages (B2 used some inline
  styles; for the admin pages favor classes for maintainability).
- Tailwind v4 + Aurora CSS-vars + minimal Radix (`react-dropdown-menu`/`react-slot`) +
  lucide-react + TanStack Query + `apiFetch`/`apiFetchForm`. **NO Mantine, NO toast, NO new deps.**
  Real data only. **Do NOT touch `frontend/src/pages/examples/`**, the shell, B1's Catalog/Item,
  B2's import pages, the auth/public pages, or the B3b admin pages you're not restyling.

## Working tree check
`git status --porcelain` clean on `dev`. A1/A2/B1/B2 + libraries fix committed.

## 1. Build shared Aurora admin primitives (reused by B3b)
Create a small, lightweight set under e.g. `frontend/src/components/ui/` (Tailwind + aurora
tokens), enough to make admin pages consistent:
- `AdminPage`/`PageHeader` (title + description + actions slot), `Card`/`Panel`, `DataTable` (or a
  styled `<table>` wrapper with header/row/cell + empty + loading states), `Badge` (status
  variants), `Button` (primary/ghost/danger), `EmptyState`, and form bits (`Field`/`Input`/
  `Select`) if helpful. Keep them minimal and composable — don't over-engineer or pull in deps.
- If B1 already created shared primitives, extend/reuse those rather than duplicating.

## 2. Restyle these Operations admin pages (feature parity)
Apply Aurora + the primitives to, preserving ALL behavior/endpoints/routes:
- `admin/JobsPage.tsx` — job list, status + progress bars, filter/paginate, failed surfacing.
- `admin/ScheduledJobsPage.tsx` — recurring jobs (last/next/running) + **Run now** buttons
  (incl. the reindex `library_reconcile_scan` run-now).
- `admin/IssuesPage.tsx` — issues list, severity/type/status filters, row expand, resolve/ignore.
- `admin/ChangesPage.tsx` — change-log feed, behavior filter, pagination.
- `admin/ReviewsPage.tsx` — review queue, approve/reject, proposed-action expand, + the
  Reconcile-Modes (Auto/Review) settings card.
- `admin/PrintStatsPage.tsx` — stat cards + most-printed table.
- `admin/ShareAuditPage.tsx` — site share links list + per-link audit events.

## Rules
- **Feature parity mandatory** — visual pass only; no feature/endpoint/route changes.
- Responsive + accessible (focus states, keyboard, labelled controls).
- Keep tables fast (don't regress pagination/queries).

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes (don't break existing).
- Frontend-only. If you think you need a backend change, STOP and report.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: the shared admin primitives introduced (so B3b reuses them) + any notable
   restyle decisions.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list (incl. the new
   shared primitives, named, so B3b can reuse); one-line `feat:`/`style:` commit message; tsc +
   vitest results; **feature-parity confirmation** per page; confirmation other areas untouched;
   anything you could not verify.
