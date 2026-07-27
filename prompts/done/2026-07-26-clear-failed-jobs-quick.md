---
name: 2026-07-26-clear-failed-jobs-quick
status: done          # pending | in-progress | done | failed
created: 2026-07-26
model: sonnet             # coding task
completed: 2026-07-26
result: Added an always-visible "Clear failed" button to JobsPage.tsx (top controls, live view only), reusing the existing clearMutation/handleClear UX; hidden when the failed filter is already active to avoid a duplicate button. Added frontend/src/test/jobs-page.test.tsx (4 tests). tsc/build/vitest all pass. Not committed — orchestrator commits on dev.
---

# Task: One-click "Clear failed" in the Job Monitor

Add an **always-available, one-click way to clear all failed jobs** from the Job Monitor,
so the user doesn't have to first switch the status filter to "failed" before the clear
button appears. **The capability already exists on the backend and in the api client** —
this is a small **frontend-only** UX change.

## Before you start

- **Read `prompts/startnewsession.md`, `CLAUDE.md`, and `docs/architecture.md`.**
- **This is FRONTEND-ONLY. Do NOT change the backend.** The endpoint
  `POST /api/jobs/clear?status=failed` already archives all failed jobs (see
  `backend/app/routers/jobs.py` `clear_jobs_by_status`, `_ARCHIVABLE_STATUSES`), and the
  api client method `api.clearJobsByStatus('failed')` already exists and is already used by
  `JobsPage.tsx` (`clearMutation`). You are only improving the UI affordance.
- **Match the existing stack:** Tailwind + CSS-var theme + minimal Radix + lucide +
  TanStack Query + `apiFetch`. No new dependency.
- **DO NOT run the full `make verify` / backend `pytest` gate** (shared ephemeral test PG
  corruption risk). Your local checks: **`tsc` / `npm run build`** and the frontend vitest
  for the touched file. **Never background a long check and exit.**

## The current behavior (what to change)

In `frontend/src/pages/admin/JobsPage.tsx`, the clear button is **contextual** — its
`clearConfig` is keyed to the active `statusFilter`: it only becomes "Clear all failed"
when the user has already selected the `failed` filter pill. So clearing failed jobs today
takes: click "failed" pill → click "Clear all failed" → confirm. The goal is to make
"clear failed" reachable in **one click regardless of the current filter**.

## What to do

1. In `JobsPage.tsx` (live view only, not the archive view), add an **always-visible
   "Clear failed" button** in the top controls (the same row as the existing
   contextual clear / "View archive" buttons). One click → confirm dialog → calls
   `clearMutation.mutate('failed')` (reuse the existing `clearMutation` and the existing
   `handleClear` confirm/`clearCount` result UX — mirror it; don't duplicate the mutation).
   - Keep the existing contextual clear button behavior intact (don't regress clearing
     succeeded/cancelled). Decide whether the always-on "Clear failed" is a *separate*
     dedicated button or a small refactor of the clear controls so failed is always
     offered — pick the cleaner option and note it. Avoid showing two identical "Clear all
     failed" buttons at once when the failed filter is active (de-dupe that case).
   - Use a clear label + a lucide icon consistent with the existing `Archive` icon usage.
   - Confirm dialog copy consistent with the existing one ("Archive all failed jobs? …").
   - After success, reuse the existing "Archived N jobs" feedback + `['jobs']` query
     invalidation.
2. **Optional (nice-to-have, only if clean & still no backend change):** show the failed
   count on/next to the button (e.g. a tiny `listJobs({ status: 'failed', per_page: 1 })`
   query for its `.total`, or disable/hide the button when there are zero failed jobs).
   If it adds meaningful complexity, skip it — the button is idempotent (archiving zero
   failed jobs is harmless) — and note the decision.
3. Update/extend the JobsPage vitest (`frontend/src/test/` — find the existing jobs page
   test) to cover: the "Clear failed" button is present without selecting the failed
   filter, and clicking it (through the confirm) calls the clear with `'failed'`.

## Conventions to honor

- Conventional-commit `feat:` prefix; **no `Co-authored-by:` trailer**.
- **Update `CHANGELOG.md` `[Unreleased]` in the SAME change.**
- Doc updates ship with the code: if the Job Monitor UX is described in
  `docs/architecture.md`, update that row; otherwise no doc change is required (note it).

## When done

1. Set this file's frontmatter: `status: done` (or `failed`), `completed: 2026-07-26`,
   `result:` one line.
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record any non-obvious decision (dedicated button vs refactor; whether you added a
   failed-count) in `docs/decisions.md` if it's non-trivial; a pure UI tweak may not
   warrant an entry — use judgement.
4. **You are a spawned agent: do NOT commit, do NOT push, and do NOT run the full test
   gate.** Run only `tsc`/`npm run build` + the JobsPage vitest, prepare the working tree,
   move the prompt, and **report back**: exact file list, a proposed one-line `feat:`
   message, tsc/build/vitest result, whether you added the optional failed-count, and
   anything the owner should eyeball. **The orchestrator runs the authoritative
   `make verify`, then commits + pushes on `dev`.**
