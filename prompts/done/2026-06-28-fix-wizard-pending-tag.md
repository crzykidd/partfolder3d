---
name: 2026-06-28-fix-wizard-pending-tag
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: Implemented inline pending-tag confirmation panel in TagsStep; added pendingTagNextAction helper to import-utils.ts; 6 new unit tests; tsc/vitest/vite build all clean.
---

# Task: Import wizard — don't silently lose a typed-but-unadded tag on Next

In the import wizard's **Tags** step, if the user types a new tag into the tag input and clicks
**Next** (advance) *before* committing it (Enter / the Add button), the typed text is silently
discarded. **Fix:** when advancing with non-empty text in the tag input, **ask** what to do
instead of dropping it.

## Behavior to implement
- When the user clicks Next / advances from the Tags step AND the new-tag text input has
  non-empty (trimmed) content that hasn't been added yet:
  - **Intercept** the advance and show a small, clear confirmation (inline panel or Aurora dialog
    matching the wizard's style), e.g. "You typed **'<tag>'** but haven't added it. Add it?"
    with three clear choices:
    - **Add & continue** — add the tag (same code path as the Add button / Enter), then advance.
    - **Discard & continue** — clear the input and advance without adding.
    - **Cancel** — stay on the Tags step (so they can keep editing).
  - If the input is empty, advance normally (no prompt).
- Respect existing tag rules (dedup, required-tags validation, canonical/pending handling). If the
  typed tag is a duplicate of one already added, just clear it and advance (or fold into the same
  confirm — keep it sensible).

## Constraints
- **Frontend only** — `frontend/src/pages/ImportWizardPage.tsx` (and only its Tags-step area).
  Don't touch other steps, the shell, or other pages. **Feature parity** for everything else in
  the wizard.
- Stack: Tailwind + Aurora CSS-vars + `@/components/ui` where it fits + lucide. NO new deps. NO
  toast. Accessible (focus management, keyboard, the confirm is dismissible). Don't touch
  `frontend/src/pages/examples/`.

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite build` MUST
  succeed** (the real gate). Add/adjust a small vitest for the "pending tag on next" logic if it's
  cleanly unit-testable; don't force it if it's purely interaction. Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: one line on the chosen UX (confirm vs auto-add).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `fix:`
   commit message; tsc / vitest / **vite build** results; confirmation wizard feature parity;
   anything unverified.
