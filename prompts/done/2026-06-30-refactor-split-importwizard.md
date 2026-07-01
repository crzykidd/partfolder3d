---
name: 2026-06-30-refactor-split-importwizard
status: done
created: 2026-06-30
model: sonnet
completed: 2026-06-29
result: >
  Extracted 10 files under frontend/src/pages/import-wizard/ (styles.ts, StepProgress.tsx,
  SiteSetupBanner.tsx, AiTextPreview.tsx, TitleStep.tsx, ImagesStep.tsx, TagsStep.tsx,
  CreatorStep.tsx, SummaryStep.tsx, ProcessingOverlay.tsx). ImportWizardPage.tsx reduced
  from 2,389 to 289 lines. tsc --noEmit clean; vitest 228/228 passed;
  vite build succeeded. All step/polling/mutation/query-key/AI-assist/autocomplete/
  pending-tag-on-Next/commit-cancel flows preserved exactly.
---

# Task: Split `frontend/src/pages/ImportWizardPage.tsx` (2,341 lines) into per-step components — behavior-preserving

The wizard packs every step (Title, Images, Tags, Creator, Summary/Commit) + AI assist + tag
autocomplete + reconcile chips into one file. Extract per-step components so the page is a thin
stepper orchestrator. **Pure refactor — preserve EVERY step, behavior, polling, mutation, query
key, and the cross-step flow. No functional change.**

## How
- Create `frontend/src/pages/import-wizard/` and extract the step components, e.g.:
  `TitleStep.tsx` (editable title + site-setup token banner + AI cleanup/summarize),
  `ImagesStep.tsx` (scrolling strip, set-default, upload, **remove-image ✕**),
  `TagsStep.tsx` (confirmed tags + reconcile accept/reject chips + **AI suggestions click-to-add
  box** + **typeahead autocomplete** + **pending-tag-on-Next confirmation**), `CreatorStep.tsx`
  (pick/dedupe / "my own design"), `SummaryStep.tsx` (review + commit/cancel). Plus shared bits
  (stepper UI, style constants → `import-wizard/styles.ts`, the `scrape_note` banner).
- `ImportWizardPage.tsx` keeps: the session query + 3s polling, step state machine
  (next/prev/handleNext + `pendingTagNextAction`), per-step PATCH persistence wiring, commit/cancel
  mutations + navigation, the already-committed/cancelled states. It composes the step components and
  passes session data + handlers via props.
- Keep `@/lib/api`, `@/components/ui`, `--aurora-*`. **Do NOT change behavior**: same polling,
  per-step PATCH, AI-assist calls, autocomplete debounce/search, pending-on-Next prompt, commit
  flow. Mechanical extraction + prop-wiring only. NO new deps. **JSX must live in `.tsx` files**
  (esbuild rejects JSX in `.ts` — keep `styles.ts` JSX-free). Don't touch
  `frontend/src/pages/examples/`.

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes unchanged (the import-wizard
  vitest suite must stay green); **and `npx vite build` MUST succeed**. Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: ImportWizardPage split into `import-wizard/*` step components (token-efficiency; no behavior change).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list (steps extracted +
   resulting ImportWizardPage.tsx line count); one-line `refactor:` commit message; tsc / vitest /
   **vite build** results; confirmation all steps + flows preserved (polling, per-step PATCH, AI
   assist, tag autocomplete, AI suggestions box, pending-on-Next, image remove/set-default/upload,
   creator, commit/cancel); anything unverified.
