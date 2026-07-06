---
name: 2026-07-05-scraper-order-arrows
status: done
created: 2026-07-05
model: sonnet
completed: 2026-07-05
result: All 3 new arrow tests pass; 396 total tests green; tsc + vite build clean.
---

# Task: Up/down arrows for scraper priority (touch/keyboard fallback to drag)

Owner tested the drag-to-reorder scrapers UI (committed as `acc21fc`) on desktop and
approved it, but drag is desktop-only (native HTML5 DnD doesn't fire on touch). Add
**up/down arrow buttons** to each scraper section header as a second way to reorder —
drag stays.

## Before you start

- Read `CLAUDE.md`. Current code: `frontend/src/pages/admin/SiteCapabilitiesPage.tsx`
  — `ScraperSection` (header chrome: grip, name, Enabled/Disabled pill, chevron),
  `ScrapersList` (owns `orderedNames` state), and the exported pure helper
  `reorderScrapers` (reorder + reprioritize; already unit-tested in
  `frontend/src/test/scrapers.test.tsx`).
- The persist path already exists: on reorder, each scraper's settings are PUT with
  sequential priorities, with rollback on failure. **Reuse it — do not duplicate.**
- Stack constraints: no new deps; lucide icons (`ChevronUp`/`ChevronDown` or
  `ArrowUp`/`ArrowDown` — match whatever the codebase already uses for similar
  affordances); Aurora styling.

## Working tree check

Run `git status --porcelain` first. If `SiteCapabilitiesPage.tsx` or
`scrapers.test.tsx` are dirty, stop and report. Unrelated dirty files: surface once,
don't block. This prompt file is exempt.

## What to do

1. In each `ScraperSection` header, add two small icon buttons (up / down) — placed
   near the grip so the affordances read as one "ordering" cluster. Clicking moves the
   section one position up/down and persists through the SAME reorder+PUT+rollback
   path the drag drop uses.
2. Disable (and visually dim) "up" on the first section and "down" on the last.
3. The buttons must not toggle collapse/expand (stopPropagation as the header's other
   controls already do) and must work on touch.
4. A11y: `aria-label` like "Move FlareSolverr up in fallback order"; buttons are real
   `<button>` elements so keyboard works for free.
5. Tests (`scrapers.test.tsx`): arrows render; up disabled on first / down disabled on
   last; clicking down on the first scraper swaps the order and triggers the persist
   call (mock-level assertion consistent with the existing reorder tests).
6. `CHANGELOG.md [Unreleased]`: extend the existing "Scrapers admin UI" `### Changed`
   bullet with the arrows (don't add a separate entry — it's the same unreleased
   feature).
7. `make verify-frontend` green (no regressions; suite was 384 + whatever the
   attach-modal task added).

## Conventions to honor

- Aurora inline styles as in the surrounding header code. `feat:` prefix. Changelog
  same commit. No `Co-authored-by:`. Never `git add -A`.

## When done

1. Update frontmatter; `git mv` to `prompts/done/` or `prompts/failed/`.
2. No decisions.md entry needed unless you deviate somewhere non-obvious.
3. **Spawned agent: do NOT commit or push.** Prepare the tree; report: file list,
   proposed `feat:` one-liner, verify-frontend outcome, deviations.
