---
name: 2026-07-23-reviews-bulk-approve-reject
status: done             # pending | in-progress | done | failed
created: 2026-07-23
model: sonnet            # coding
completed: 2026-07-23
result: >
  Added POST /api/reviews/approve-all and /reject-all (admin+CSRF guarded,
  idempotent, cloning the tag approve-all precedent), the matching api client
  functions, and Approve all / Reject all buttons (confirm-gated) on the
  Reviews page Pending tab. Backend: 926 tests passed (pytest -n auto).
  Frontend: tsc -b --force + vite build clean, 430 vitest tests passed (a
  prior run hit the known unrelated waitFor CPU-load flake in a different
  test file; the final clean run had zero failures, including all newly
  authored tests). CHANGELOG [Unreleased] Added entry + docs/decisions.md
  entry recorded. Not committed — reported back to orchestrator per the
  spawned-agent workflow.
---

# Task: Bulk approve/reject for reconcile Reviews (clear a large pending backlog in one click)

The reconcile scan can queue hundreds of `ReviewItem` rows (the owner has ~405 pending in
prod). Today each must be approved/rejected individually — there is no bulk action. Add
**Approve all** and **Reject all** for pending reviews, mirroring the tag system's existing
`approve-all` precedent, plus buttons on the Reviews page.

## Before you start

- Read `docs/architecture.md` (reconcile/reviews section) and `CLAUDE.md` verify rules.
- Precedent to clone (do this first — match its shape): the tag bulk endpoint
  `POST /api/admin/tags/approve-all` at `backend/app/routers/tag_admin.py:133-156`
  (`approve_all_pending_tags` + `ApproveAllResponse` — idempotent single `UPDATE`,
  admin-guarded, CSRF-protected, returns a count).
- The reviews code:
  - `backend/app/routers/reviews.py` — existing `GET /api/reviews`, singular
    `POST /api/reviews/{id}/approve` (~96-135; marks approved + enqueues arq
    `apply_review_item`) and `POST /api/reviews/{id}/reject` (~138-160; pure status flip,
    no action). **Match the auth/CSRF guards these already use.**
  - `backend/app/models/review_item.py` — `ReviewStatus` enum (`pending`/`approved`/
    `rejected`), fields (`proposed_action`, `resolved_at`, `resolved_by_id`).
  - `backend/app/worker/reconcile.py` — `apply_review_item_action` (~999) is what an
    approve replays.
  - Frontend: `frontend/src/pages/admin/ReviewsPage.tsx` (route `/admin/reviews`,
    Pending/All tabs, per-row Approve/Reject), api client `frontend/src/lib/api/reviews.ts`.
- **Verify:** `make verify` (both gates) must pass. **No migration needed.**

## Working tree check

Run `git status --porcelain` and cross-reference the files this plan touches. If any have
uncommitted changes, list them and ask before touching. This prompt file is exempt.

## What to do

1. **Backend — two endpoints in `reviews.py`:**
   - `POST /api/reviews/reject-all` — pure, cheap status flip: `UPDATE review_items SET
     status='rejected', resolved_at=now(), resolved_by_id=<caller> WHERE status='pending'`.
     Return `{rejected: <count>}`. Idempotent (0 pending → 200, `rejected: 0`).
   - `POST /api/reviews/approve-all` — marks every pending row approved **and** enqueues
     the same `apply_review_item` arq job the singular approve does, for each row (this
     replays each `proposed_action` — real work; that's expected). Return
     `{approved: <count>}`. Idempotent.
   - **Important nuance to encode:** approve-all triggers N apply-jobs (potentially
     hundreds of mutations); reject-all is a safe status flip. Reflect this in the summaries
     and in the frontend confirm copy. Use response models mirroring `ApproveAllResponse`.
   - Guard both with the SAME admin + CSRF dependencies the existing reviews endpoints use.

2. **API client** — add `approveAllReviews()` / `rejectAllReviews()` to
   `frontend/src/lib/api/reviews.ts` (match existing CSRF `apiFetch` usage).

3. **Frontend — `ReviewsPage.tsx`:** add **Approve all** and **Reject all** buttons in the
   Pending tab header. Both behind a confirm step; make the Approve-all confirm explicit
   that it will replay every pending change (e.g. "Approve all N pending? This applies each
   change to your library."). Reject-all confirm can be lighter. On success, invalidate the
   reviews query so the list refreshes to empty and any Pending-Reviews dashboard widget
   updates. Show the returned count. Handle the empty case (disable buttons at 0 pending).

4. **Tests:**
   - Backend: endpoint tests for both — count correctness, idempotency at 0 pending,
     approve-all enqueues apply per row (assert the enqueue), reject-all does not, and the
     admin/CSRF guards reject unauthorized callers. Match existing reviews test style; the
     suite runs under `pytest -n auto`.
   - Frontend: a vitest for ReviewsPage covering the two buttons (confirm → call → list
     refresh), matching the existing per-row test patterns (Tailwind + Radix, no Mantine,
     no toast lib).

5. **Changelog:** `### Added` entry under `[Unreleased]` in `CHANGELOG.md`, SAME commit —
   "Bulk approve/reject all pending reconcile reviews."

## Conventions to honor

- Clone the tag `approve-all` precedent's structure rather than inventing a new shape.
- Frontend stack: Tailwind + CSS-var theme + minimal Radix + lucide + TanStack Query +
  `apiFetch` CSRF. No Mantine, no toast library.
- Backend tests require `pytest -n auto` (verify script handles it); pinned ruff 0.8.4.
- No `Co-authored-by:` trailers. Conventional-commit `feat:` prefix.

## When done

1. Update this file's frontmatter: `status`, `completed` (2026-07-23), `result`.
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record any non-obvious decisions in `docs/decisions.md`, newest at top.
4. **You are a spawned agent: do NOT commit.** Run `make verify` (both gates), confirm
   green (report the counts; the frontend `waitFor` timeout flakes under CPU load are
   known — a clean type-build + vite build with only those timeouts is acceptable, say so
   explicitly if it happens), prepare the tree, and report the exact file list + a proposed
   one-line `feat:`-prefixed commit message back to the orchestrator. Never `git add -A`,
   never push, never auto-commit.
