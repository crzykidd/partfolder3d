---
name: 2026-06-30-feat-wizard-tag-autocomplete
status: done
created: 2026-06-30
model: sonnet
completed: 2026-06-29
result: Implemented tag typeahead autocomplete in the import wizard Tags step. Backend: added ?search= prefix param to GET /api/tags (tags.py). Frontend: listTags in api.ts extended with search param; ImportWizardPage.tsx Tags step now shows a debounced (200ms) autocomplete dropdown with existing-tag rows (popularity count shown) + "Create new tag" row when no exact match. Keyboard accessible (arrows/Enter/Esc). All existing Tags-step behaviors preserved. 5 new backend tests pass; ruff/tsc/vitest/vite build all green.
---

# Task: Tag autocomplete in the import wizard (type → pick existing tag or create new)

In the import wizard's **Tags** step, besides AI suggestions there's **no way to choose existing
tags** — typing a tag just creates a new one. Add a **typeahead**: as the user types, show matching
**existing active tags** to select, plus a clear **"Create new tag: '<typed>'"** option.

## Backend
- The tag list endpoint needs **name-prefix search**. Check `GET /api/tags` (`app/routers/tags.py`,
  `list_tags`) — add a `search: str | None` query param that filters `Tag.name ILIKE '<q>%'` (or
  `%q%`), **active only**, ordered by popularity, limited (e.g. 10). Don't break existing callers
  (param optional). (If a suitable search already exists, reuse it.)

## Frontend (`frontend/src/pages/ItemPage.tsx`? NO — the wizard: `ImportWizardPage.tsx`, Tags step)
- Add an autocomplete on the tag input: debounce input (~200ms), call the search, show a dropdown:
  - **Matching existing tags** (click → add to confirmed tags; show popularity/count if handy).
  - A **"Create new tag: '<typed>'"** row when the typed text isn't an exact existing match
    (selecting it adds the new tag — which flows through the existing new-tag → pending path).
  - Dedup against already-confirmed tags (don't show ones already added).
- Keep ALL existing Tags-step behavior: the AI suggestions click-to-add box, the manual add
  (Enter/Add button), and the **pending-tag-on-Next confirmation** (typed-but-unadded prompt) — the
  autocomplete should integrate cleanly with these (e.g. Enter on a highlighted suggestion adds it;
  Enter with free text still works). Keyboard accessible (arrow keys + Enter + Esc to close).
- Add the search to `api.ts` (extend `listTags` with the search param, or a small `searchTags`).
- Aurora-styled, `@/components/ui` where it fits. NO new deps, NO toast. Don't touch
  `frontend/src/pages/examples/`.

## Verify
- Backend: `ruff check backend/` (run it yourself); **ephemeral Postgres** + tests (docker
  one-liner; `alembic upgrade head`; run pytest in the FOREGROUND to completion; tear down after;
  recreate the scratchpad venv if gone). Add a test: `GET /api/tags?search=an` returns active tags
  whose name matches, ordered by popularity, excludes non-matching.
- Frontend: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite
  build` MUST succeed**. Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: tag search param + wizard autocomplete (select existing or create new).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; check results (ruff / pytest+count / tsc / vitest / **vite build**); confirmation
   existing Tags-step features (AI box, manual add, pending-on-Next) still work; anything unverified.
