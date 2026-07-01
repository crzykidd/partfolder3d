---
name: 2026-06-28-fix-tag-approve-and-ai-suggest-ux
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: >
  All three parts delivered. Part 1: PendingTagsPage now uses listAdminPendingTags()
  with ['admin-tags-pending'] key (pending-only endpoint) so approved tags disappear
  immediately; TagAdminPage invalidation broadened; Reject added to PendingTagsPage;
  cross-links added. Part 2: AI suggestions card redesigned as click-to-add chips —
  chips disappear when added, two labeled groups, Add all buttons, calm non-blocking
  messaging. Backend: _get_or_create_tag/attach_tags accept a status param; import
  commit passes new_tag_status=pending so brand-new tags enter the approval queue.
  New test test_commit_new_tag_created_as_pending passes. All checks green: tsc clean,
  vitest 198/198, vite build success, ruff clean, pytest 23/23.
---

# Task: Fix tag approval (won't refresh) + clarify the AI tag-suggestion UX

Owner-reported issues, with diagnosis already done:

1. **"Can't approve tags."** The backend approve **works and persists** (`get_db` auto-commits;
   logs show `POST /api/tags/{id}/approve → 200`, and repeated 200s are the idempotent
   "already-active" branch). The real problem is the **pending list doesn't refresh in the UI**
   after approve, so it looks like nothing happened and the user clicks again. There are also
   **two pending-tag screens** with **two endpoints**, which adds confusion:
   - `admin/PendingTagsPage.tsx` → `approvePendingTag` → `POST /api/tags/{id}/approve`
     (list query key `['tags','pending']`; onSuccess invalidates `['tags']`).
   - `admin/TagAdminPage.tsx` → `POST /api/admin/tags/{id}/approve` (tag_admin router) with its
     own pending section.
2. **AI suggestion UX is confusing** — new AI tags say "admin will need to approve", which reads
   as a blocker. The user wants AI suggestions presented as a clear **click-to-add** box, with the
   AI **aligning to existing tags** (canonical) — new ones added as suggestions with a calm note.

## Working tree check
`git status --porcelain` clean on `dev`. (Starter tags + auto-suggest just landed — build on them.)

## Part 1 — Make tag approval reliably update the UI + de-confuse the two screens
- **Reproduce + fix the refresh**: after approve/reject on **both** `PendingTagsPage` and the
  pending section of `TagAdminPage`, the approved/rejected tag must disappear from the list
  immediately. Audit the mutation `onSuccess` invalidations vs the actual list query keys (e.g.
  `['tags','pending']` vs the tag-admin pending key) and fix any mismatch; ensure
  `await queryClient.invalidateQueries(...)` (or `refetch`) targets the exact key the visible list
  uses. If a `staleTime`/select-filtering is masking the refetch, fix that too.
- **Reduce the two-screen confusion**: pick ONE of these and document it in `docs/decisions.md`:
  (a) keep both but make their behavior + invalidation identical and add a one-line cross-link/note;
  OR (b) make `TagAdminPage`'s pending section the single approval surface and have the standalone
  `PendingTagsPage` defer to it (e.g. redirect / link), removing the duplicate. **Recommended: (a)**
  — lowest risk; just make both reliably refresh and behave the same. Do NOT remove backend
  endpoints. Keep the duplicate-detection section on PendingTagsPage working.
- Add/adjust a small test where feasible (e.g. the api wrapper or a pure helper); the core fix is
  cache-invalidation so it may be mostly interaction — don't force a brittle test.

## Part 2 — AI tag-suggestion box: clear click-to-add + calm messaging
In `ImportWizardPage.tsx` (Tags step, the existing "AI Tag Suggestions" card):
- Present suggestions as an obvious **click-to-add** box, visually distinct from the confirmed-tags
  area. Two groups, clearly labeled:
  - **Matches your tags** (canonical) — clicking a chip adds it to confirmed tags directly.
  - **New suggestions** — clicking adds it; show a **calm, non-alarming** note, e.g. "Added now;
    new tags are reviewed by an admin before they join the global tag cloud" (it's NOT a blocker —
    the tag still applies to this item). Replace any wording that sounds like approval blocks the
    import.
- Clicking a suggestion should **remove it from the suggestion box** and add it to confirmed
  (dedup against already-confirmed; no duplicates). Keep an "add all" affordance if it's easy.
- Keep the auto-suggest-once behavior + the manual "✦ Suggest tags (AI)" button. Emphasize that
  the AI aligns to existing tags (canonical) — now meaningful since starter tags exist.
- Feature parity for the rest of the wizard.

## Constraints
- Frontend-focused; backend likely untouched (the approve/reject + suggest endpoints already
  exist). If you must change backend, keep it minimal and verify with ephemeral Postgres.
  `@/components/ui` + Aurora, NO new deps, NO toast. Don't touch `frontend/src/pages/examples/`.

## Verify
- If backend touched: `ruff check backend/` + ephemeral Postgres pytest (see other prompts for the
  docker one-liner; tear down after; recreate the scratchpad venv if gone).
- Frontend: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite build`
  MUST succeed** (the real gate). Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: the approve-refresh fix + the two-screen decision; the AI-suggestion
   click-to-add UX + reworded approval messaging.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `fix:`
   commit message; check results (tsc / vitest / **vite build** [+ ruff/pytest if backend]);
   confirmation approve now refreshes the list on both screens; the AI box is click-to-add with
   calm messaging; anything unverified (note that interaction/visual needs a running app).
