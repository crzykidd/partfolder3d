---
name: 2026-07-05-url-import-attach-modal
status: done
created: 2026-07-05
model: sonnet
completed: 2026-07-05
result: >
  Added AttachOrCommitModal component (portaled to <body>) in SummaryStep.tsx.
  Modal shows once per wizard visit for url+0-file sessions (sessionStorage keyed by
  session id). "Attach files" closes modal + triggers file picker. "Create without
  objects" reuses the same commit handler/disabled state as the main commit button.
  8 new modal tests added to import-wizard-steps.test.tsx. All 393 frontend tests pass.
---

# Task: Attach-files modal on Review & Commit for zero-file URL imports (owner test feedback)

Owner tested the #27 mid-wizard attach (shipped earlier today as an "Attach Model Files"
section on the Review step) and found it **not obvious enough**. Requested UX, verbatim
intent: when reaching Review & Commit on a URL import with no files, show a **modal**:

> Site "makerworld.com" needs auth to download print assets. Please attach.

with two actions: **Attach** and **Create without objects**.

## Before you start

- Read `CLAUDE.md` and the frontend conventions in `docs/architecture.md` (note the
  architecture gotcha list mentions modal patterns — there is no @radix-ui/react-dialog;
  custom overlay modals follow the `AddAssetModal.tsx` Aurora pattern).
- Current code: `frontend/src/pages/import-wizard/SummaryStep.tsx` — has the Files row,
  zero-file warning, and the "Attach Model Files" section (file list + remove + attach
  button calling `api.uploadSessionFiles`). Domain extraction from the source URL: check
  for an existing helper (`extract_domain` exists backend-side; frontend may need
  `new URL(...).hostname` — strip a leading `www.`).
- Stack constraints: no new dependencies, Aurora styling, TanStack Query, `apiFetch`.

## Working tree check

Run `git status --porcelain` first and cross-reference the files this plan touches.
If SummaryStep.tsx or the wizard test files are dirty, stop and report. Surface
unrelated dirty files once; don't block. This prompt file is exempt.

## What to do

1. **Modal component** (local to the wizard, e.g. in `SummaryStep.tsx` or a sibling
   file): custom overlay modal per the `AddAssetModal` pattern (backdrop blur, Aurora
   palette card, Escape closes, click-outside closes = same as "not now"/dismiss).
   Content:
   - Title: something like "No model files attached".
   - Body: `Site "<domain>" needs auth to download print assets. Please attach.`
     (`<domain>` = hostname of the session's `source_url`, `www.` stripped; if the
     session has no source_url, fall back to generic copy: "This import has no model
     files attached.").
   - Primary button **"Attach files"**: closes the modal and opens the existing
     attach file-picker directly (trigger the same input the "Attach Model Files"
     section uses — lift a ref/callback if needed) and scrolls that section into view.
   - Secondary button **"Create without objects"**: performs the SAME commit action as
     the step's main commit button (reuse the exact mutation/handler — do not duplicate
     commit logic). If commit is currently disabled by validation (e.g. no library),
     this button is disabled too, with the same reason the main button shows.
2. **Trigger rules:**
   - Show when the Review & Commit step mounts AND `source_type === 'url'` AND the
     session has zero staged files.
   - Show at most once per wizard visit: after any dismissal (Escape/outside/Attach),
     don't re-show while the user stays in this wizard — including stepping back and
     forth. Component-level state lifted to the wizard page (or sessionStorage keyed by
     session id) — pick the simpler one that survives step navigation.
   - Never show when files are already attached; if files get attached after showing,
     it stays closed.
3. **Keep the existing inline "Attach Model Files" section and warning** — the modal is
   an extra nudge, not a replacement.
4. **Tests** (`frontend/src/test/import-wizard-*.test.tsx`): modal shows for url+0-files
   with the domain in the copy; not for upload sessions; not when files exist; "Attach
   files" closes it and focuses/opens the attach flow (assert the callback); "Create
   without objects" invokes the same commit handler as the main button; dismissed →
   doesn't re-show on step re-entry.
5. **Changelog** `[Unreleased] → ### Changed`: zero-file URL imports now get an explicit
   attach-or-create-without-objects modal at Review & Commit (same commit).
6. **Verify:** `make verify-frontend` green (fresh `tsc -b --force` + `npm run build` +
   `vitest run`). Frontend-only task; if you somehow need a backend change, stop and
   report instead.

## Conventions to honor

- Aurora inline-style conventions as in `AddAssetModal.tsx` / `SummaryStep.tsx`.
- `feat:` prefix (UX capability). Changelog same commit. No `Co-authored-by:`.
  Never `git add -A`.

## When done

1. Update frontmatter (`status`, `completed`, `result`).
2. `git mv` into `prompts/done/` or `prompts/failed/`.
3. Record in `docs/decisions.md` (newest at top): "Create without objects" commits
   directly (same handler as the commit button); modal is once-per-wizard-visit.
4. **Spawned agent: do NOT commit or push.** Prepare the tree; report back: file list,
   proposed `feat:` one-liner, verify-frontend outcome, deviations.
