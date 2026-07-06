---
name: 2026-07-05-scrapers-ui-collapsible-drag
status: done
created: 2026-07-05
model: sonnet
completed: 2026-07-05
result: >
  Implemented collapsible scraper sections with drag-to-reorder priority.
  ScraperSection wrapper component added; FlareSolverrCard and AgentQLCard
  refactored to FlareSolverrBody / AgentQLBody with priority inputs removed.
  ScrapersList orchestrates ordering, drag-and-drop (HTML5, header-only drag
  zone), and PUT persistence. sessionStorage persists expand state per scraper.
  reorderScrapers pure helper exported for testability. 18 new tests added;
  verify-frontend green (384 tests). Touch/pointer reordering: desktop-only.
---

# Task: Scrapers admin UI — collapsible per-scraper sections + drag-to-reorder priority

Owner-requested redesign of the "Scrapers" area on the admin Site Capabilities page
(`/admin/ai/sites`), which currently renders `AgentQLCard` and `FlareSolverrCard` as
always-open cards with numeric priority inputs (shipped earlier today for #23).

Owner's spec, verbatim intent:
1. Each scraper is a **collapsible section**. The collapsed summary row shows the
   **scraper name** and an **"Enabled" / "Disabled"** state. Expanding reveals the
   full card details (all existing fields/buttons).
2. **Expanded by default**; each section's expand/collapse state is **remembered per
   browser session** (use `sessionStorage`, key per scraper, e.g.
   `pf3d.scrapers.expanded.<name>`).
3. **Priority is set by dragging the sections up/down** — the list position IS the
   priority (top = tried first). Remove the numeric priority inputs from the cards.

## Before you start

- Read `CLAUDE.md`, `docs/architecture.md` (frontend conventions section), and skim
  `docs/scrapers-spec.md` §6 (the generic-admin-UI goal still stands: a future third
  backend should slot into this list without bespoke UI).
- Current code: `frontend/src/pages/admin/SiteCapabilitiesPage.tsx` — `FlareSolverrCard`
  (~line 488), `AgentQLCard` (~line 660s), `UsagePanel`, rendered together (~line 1001).
  API clients: `frontend/src/lib/api/scrapers.ts` (FlareSolverr + test-connection),
  `frontend/src/lib/api/agentql.ts` (AgentQL settings incl. `priority`, `timeout_s`).
- Frontend stack constraints (hard): Tailwind + CSS-var Aurora theme + minimal Radix +
  lucide + TanStack Query + `apiFetch`. **No new dependencies — no drag-and-drop
  library.** Use native HTML5 drag-and-drop (draggable sections or a drag handle +
  `onDragStart`/`onDragOver`/`onDrop`). If a touch/pointer-events fallback is cheap to
  add, include it; otherwise leave reordering desktop-only and note it in your report.
- Backend is untouched: priorities persist through the EXISTING settings endpoints
  (`updateFlareSolverrSettings({priority})`, `updateAgentQLSettings({priority})`).
  The dispatcher already sorts enabled backends by ascending priority.

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files
this plan touches. If any have uncommitted changes, list them and ask before touching.
Surface unrelated dirty files once; don't block. This prompt file is exempt.

## What to do

1. **Extract a generic `ScraperSection` wrapper component** (name, enabled/disabled
   badge, chevron expand/collapse, drag affordance) that wraps each scraper's existing
   card body. Keep the per-scraper bodies as they are (fields, Test connection, usage);
   only the chrome changes. Design it so adding a third scraper = adding one entry to a
   local list of `{name, label, enabled, priority, body}` — no per-scraper chrome code.
2. **Collapse/expand:**
   - Header row (always visible): scraper display name + a small "Enabled"/"Disabled"
     pill (derive from that scraper's settings query; render a neutral placeholder while
     loading). Clicking the header (or a chevron) toggles.
   - Default expanded. Persist each section's state in `sessionStorage`
     (`pf3d.scrapers.expanded.<name>`); read lazily on mount, guard for SSR-less
     environments per existing patterns (plain `window.sessionStorage` access in an
     effect/initializer is fine — this app is client-only).
3. **Drag-to-reorder:**
   - Sections render sorted by their current `priority` (ascending). A drag handle
     (lucide `GripVertical`) in the header; dragging a section above/below another
     reorders the list with a visible drop indicator.
   - On drop, immediately persist: assign `priority = index + 1` to each scraper in
     the new order and PUT each one's settings (only send `{priority}`); optimistic
     UI update, invalidate the settings queries after. Failures roll back and surface
     the existing error style.
   - Remove the numeric priority inputs from both cards. Add a short helper line under
     the section header ("Drag to set fallback order — top is tried first").
   - Do NOT start a drag from interactive elements inside the expanded body (limit
     draggable to the handle/header) so text selection and inputs keep working.
4. **A11y niceties (cheap, do them):** the header toggle is a `button` with
   `aria-expanded`; the drag handle has an `aria-label`. No keyboard-reorder
   requirement for now.
5. **Tests:** extend the existing frontend tests covering this page (find them via
   the test files that reference `SiteCapabilities` / `FlareSolverr`): summary shows
   name + Enabled/Disabled, toggle collapses/expands, sessionStorage read/write,
   sections sorted by priority, and the drop handler PUTs the recomputed priorities
   (simulate the reorder function directly if simulating native DnD events is flaky —
   extract the reorder+persist logic into a testable helper).
6. **Changelog:** `CHANGELOG.md [Unreleased] → ### Changed` — collapsible scraper
   sections + drag-to-reorder priority (same commit).
7. **Verify:** `make verify-frontend` (fresh `tsc -b --force` + `npm run build` +
   vitest) must be green. Backend untouched — if you truly changed no backend file,
   the backend gate is not required; say so in your report.

## Conventions to honor

- Match the Aurora inline-style conventions already in `SiteCapabilitiesPage.tsx`.
- Conventional-commit prefix `feat:` (UI capability change). Changelog same commit.
- No `Co-authored-by:`. Never `git add -A`.

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record any non-obvious decisions in `docs/decisions.md` (newest at top) — e.g. how
   the drag implementation works and the touch-support outcome.
4. **You are a spawned agent: do NOT commit or push.** Prepare the tree and report
   back: file list, proposed one-line commit message, verify outcome, touch-support
   status, and any deviations.
