---
name: 2026-07-01-quickstart-and-wizard-polish
status: done
created: 2026-07-01
model: sonnet            # frontend
completed: 2026-07-01
result: >
  Part A: added `itemsTotal` (listItems per_page=1, universal) and `backups`
  (listBackups, admin-only) to StatusKey + statusMap in QuickStartPage.tsx;
  assigned statusKey to Import and Backups step defs. Personalize left as
  path-prefix only (no clean non-default-ambiguous nav-layout signal exists).
  Part B: SummaryStep.tsx now fetches listLibraries via useQuery(['libraries'])
  and displays the name; falls back to `ID N` while loading, '—' when null.
  CHANGELOG [Unreleased] ### Fixed entries added. tsc/vitest/vite-build all
  clean.
---

# Task: Quick Start step-completion detection + import-wizard library name (frontend)

Two small, unrelated frontend fixes on disjoint files.

## Before you start
- Read `prompts/startnewsession.md` and `CLAUDE.md`. Spawned agent on `dev`: do NOT push/commit —
  prepare the tree, report back. Do NOT edit `docs/decisions.md`.
- **Changelog rule:** add `### Fixed` entries under `## [Unreleased]` in `CHANGELOG.md` for these
  (same change). Frontend stack: Tailwind + CSS-var + lucide + TanStack Query + `apiFetch`.

## Part A — Quick Start "done" badges for Import + Backups (+ broaden Personalize)
File: `frontend/src/pages/settings/QuickStartPage.tsx`. Today only 3 steps have a live status
badge (`StatusKey = 'libraries' | 'pathPrefixes' | 'aiProviders'`). The **Import assets** step and
**Set up backups** step have no `statusKey`, so they never flag as done even when the user has done
them. Fix:
- Add status detection for the **Import assets** step: mark done when the instance has ≥1 item.
  Use the existing items list API (the same `GET /api/items?per_page=1` → `total` the stat tiles
  use — find the api.ts function, e.g. `listItems`/`getItems`). done = `total > 0`. This step is
  universal (all users) — the query must work for non-admins.
- Add status detection for the **Set up backups** step (adminOnly): mark done when ≥1 backup record
  exists. Use `GET /api/admin/backups` (find/add the api.ts function; returns a list) → done =
  `list.length > 0`. (A backup record means backups have actually run/been configured; the daily
  `db_backup` scheduled job is always registered, so that is NOT a valid "done" signal.)
- Extend the `StatusKey` union + `statusMap` accordingly, following the existing best-effort query
  pattern (`retry: false`, `staleTime`, `enabled` gating for admin-only queries; badge hidden while
  loading/on error). Assign the new `statusKey`s to the Import and Backups `StepDef`s.
- **Personalize** step currently uses `pathPrefixes` only (path prefix set). Broaden it minimally
  if there's a clean signal that the workspace was personalized (e.g. a stored per-user nav-layout
  preference in addition to path prefix). If no clean, non-default-ambiguous signal exists, LEAVE it
  as path-prefix and note the limitation in your report — do not invent a flaky check.

## Part B — Import wizard: show library NAME, not "ID N"
File: `frontend/src/pages/import-wizard/SummaryStep.tsx`. Line ~129 renders
`value={session.library_id != null ? \`ID ${session.library_id}\` : '—'}`. Show the library's
**name** instead:
- Fetch the libraries list (`listLibraries()` from `frontend/src/lib/api/libraries.ts`, returns
  `LibraryOut[]` with `id` + `name`) via `useQuery`, and display the name of the library whose
  `id === session.library_id`. Fallback to `ID ${session.library_id}` if the name isn't resolved
  yet / not found, and `'—'` when `library_id` is null. Keep the rest of the summary row unchanged.
- If a library-picker earlier in the wizard already fetches libraries, reuse the same query key so
  it's cached (no duplicate fetch). `listLibraries` must be callable by whoever runs the wizard.

## Verification (frontend — light)
- `npx tsc --noEmit`, relevant `npx vitest run`, and `npx vite build`.

## When done
1. Update frontmatter (`status`, `completed: 2026-07-01`, `result`).
2. `git mv` into `prompts/done/`.
3. Do NOT edit `docs/decisions.md` — report notes back.
4. Do NOT commit/push. Report: files changed, the `[Unreleased]` changelog entries, what signal you
   used for each new "done" badge (and any personalize limitation), a one-line `fix:`-prefixed
   commit message, and tsc/vitest/vite-build results.
