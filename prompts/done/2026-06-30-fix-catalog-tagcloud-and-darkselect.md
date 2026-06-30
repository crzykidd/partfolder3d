---
name: 2026-06-30-fix-catalog-tagcloud-and-darkselect
status: done
created: 2026-06-30
model: sonnet
completed: 2026-06-29
result: >
  Tag cloud: replaced linear scale (max 2rem) with log scale capped at 1.375rem (~22px);
  added Alpha/Number sort toggle (localStorage-persisted, client-side via sortTags helper).
  Dark-mode select: colorScheme style property set via useTheme isDark check.
  tsc clean; vitest 228/228 pass; vite build succeeds.
---

# Task: Catalog tag-cloud sort toggle + tamer sizing, and fix the dark-mode white sort dropdown

Two CatalogPage issues:
1. **Tag cloud**: tags with 2+ items balloon to huge font sizes; and there's no way to change the
   ordering. Tame the sizing and add an **Alpha / Number** sort toggle at the top of the tag browse.
2. **Sort `<select>`** ("Newest first" etc.) renders a **white dropdown in dark mode** (unreadable).

## Scope — `frontend/src/pages/CatalogPage.tsx` only (+ `catalog-utils.ts` if helpers live there)
Self-contained; do NOT touch other pages, `api.ts`, or the backend. The tag list already arrives
with `item_count` (real count) — sorting is client-side.

## 1. Tag cloud
- **Tame font sizing**: the current `getTagFontSize`/`getTagFontWeight` scale too aggressively
  (2+ items → very large). Cap the max font size to something reasonable (e.g. ~22–24px) and use a
  gentler scale (e.g. log or clamped-linear) between min/max counts so the cloud stays balanced
  even with a few high-count tags. Keep the smallest tags readable (~12–13px).
- **Sort toggle** at the top of the tag-browse area: **Alpha** (A→Z by name) vs **Number** (by
  `item_count` desc, ties → name). A small Aurora segmented toggle; default Number (current
  behavior). Re-sorts the displayed tags client-side. Persist the choice in localStorage if easy.
- Keep: only in-use tags shown, `#name (count)` label, click-to-filter behavior.

## 2. Dark-mode sort dropdown
- The catalog sort `<select>` (and any other native `<select>` on the page) shows OS-default white
  options in dark mode. Fix so the control + its options are readable in dark mode — e.g. set
  `color-scheme` appropriately and/or background/color on the select+options using `--aurora-*`
  tokens (or switch to the existing `@/components/ui` `AuroraSelect` if it renders correctly in
  dark mode). Verify both light and dark look right.

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes (if you add/adjust sizing/sort
  helpers in `catalog-utils.ts`, add a small unit test); **and `npx vite build` MUST succeed**. Do
  NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: sizing scale choice + sort toggle + dark-select fix approach.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `fix:`
   commit message; tsc / vitest / **vite build** results; note dark-mode needs a visual check;
   anything unverified.
