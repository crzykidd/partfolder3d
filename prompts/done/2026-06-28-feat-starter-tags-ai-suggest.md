---
name: 2026-06-28-feat-starter-tags-ai-suggest
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: >
  All deliverables implemented and verified. Backend: tags_defaults.py (57 tags, 7
  categories), POST /api/tags/load-defaults (admin+CSRF, idempotent), GET /api/ai/status
  (authenticated, no AI call, no usage row). Frontend: loadDefaultTags() + getAiStatus()
  in api.ts; "Load starter tags" button on TagAdminPage; ImportWizardPage TitleStep probe
  replaced with getAiStatus(); TagsStep auto-suggests once on entry. Tests: 4 new tests
  (load-defaults inserts active + idempotent; ai/status false/true + no usage row). All
  pass. ruff clean; tsc clean; vitest 198/198; vite build succeeded.
---

# Task: Starter tag set (admin "Load starter tags") + fix the AI tag-suggestion workflow

Two linked improvements (a fresh instance has 0 active tags, so AI canonical matching has nothing
to match, and the AI suggest step is a buried manual button gated by a token-wasting probe):

1. **Starter tags** — a curated default vocabulary + an admin **"Load starter tags"** button that
   seeds them as **active canonical** tags (idempotent).
2. **AI tag-suggestion workflow** — replace the token-wasting provider probe with a cheap status
   check, and **auto-run** tag suggestions on the Tags step when a provider is enabled.

No migration needed (seeding inserts rows; new endpoints add no schema).

## Working tree check
`git status --porcelain` clean on `dev`.

## Part 1 — Starter tags

### Backend
- Add a constants module (e.g. `backend/app/tags_defaults.py`) with the curated set as
  `(name, category)` pairs:
  - **type:** functional, decorative, miniature, toy, tool, gadget, jewelry, cosplay, prop,
    replacement-part, model-kit
  - **function:** storage, organizer, holder, stand, mount, wall-mount, hook, clip, bracket,
    cable-management, enclosure, planter, vase, sign
  - **feature:** print-in-place, articulated, no-supports, supports-required, multipart,
    multicolor, multimaterial, flexible
  - **theme:** fantasy, sci-fi, animal, holiday, christmas, halloween, kawaii, anime, gaming
  - **process:** fdm, resin
  - **audience:** kids, gift, educational
  - **mechanical:** gears, hinge, threaded, bearing
  (normalize names to the project's tag-name convention — lowercase/slug as tags are stored.)
- `POST /api/tags/load-defaults` (admin + CSRF): insert any of the above that don't already exist
  (match by normalized name), as `status=active` with the given `category`. **Idempotent** — skip
  existing names (don't touch their status/category). Return a small summary
  `{ added: int, skipped: int }`. Use the existing Tag model + status enum (`TagStatus.active`).

### Frontend
- On `admin/TagAdminPage.tsx`, add a **"Load starter tags"** button (Aurora, in a sensible spot
  near the top / the all-tags section) that calls the endpoint, invalidates the tags queries, and
  shows the result ("Added N, skipped M") inline. Add `loadDefaultTags()` to `api.ts`.

## Part 2 — AI tag-suggestion workflow

### Backend — cheap provider status
- Add `GET /api/ai/status` → `{ provider_available: bool }` (authenticated user, NOT admin-only —
  importers need it). It just checks whether an **enabled** provider exists
  (`get_enabled_provider`) — **NO AI/network call, records no usage**. (Place it where it fits —
  e.g. the ai_actions or ai_providers router.)

### Frontend — stop wasting tokens + auto-suggest
- In `ImportWizardPage.tsx`:
  - **Replace the provider probe**: today the Title step fires a real `aiCleanupDescription`
    request on mount just to learn `provider_available` (this spends tokens + writes a
    `cleanup_description` usage row). Switch both the description-cleanup/summarize gating AND the
    tags-step gating to the new cheap `GET /api/ai/status`. Do not make a billed AI call just to
    detect availability.
  - **Auto-suggest on the Tags step**: when the user reaches the Tags step and a provider is
    available, automatically run the suggest-tags call **once** (show a loading state; on result
    populate the existing suggestions card). Keep the existing manual **"✦ Suggest tags (AI)"**
    button for re-running. Don't auto-run repeatedly (guard so it fires once per session/step
    entry), and never block the manual tag flow if it errors (show the existing "No tag
    suggestions found." / error states).
  - Add `getAiStatus()` to `api.ts`.

## Notes
- Reuse `@/components/ui` + Aurora. NO new deps. NO toast. Don't touch
  `frontend/src/pages/examples/`. Keep all existing wizard features (feature parity).
- The suggest endpoint already feeds **active** tags as the canonical set — so once starter tags
  are loaded, canonical matching will actually work. No change needed there.

## Verify
- Backend: `ruff check backend/`; **ephemeral Postgres** + tests (`docker run -d --name pf3d-test-pg
  -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p
  5433:5432 postgres:16-alpine`, set `DATABASE_URL`, `alembic upgrade head`, `pytest`). Add tests:
  `load-defaults` inserts the set as active + is idempotent (second call adds 0); `GET /api/ai/status`
  returns false with no provider / true with an enabled provider and makes NO AI call (assert no
  ai_usage row written). Recreate the scratchpad venv at the session path if gone; tear down after.
- Frontend: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite
  build` MUST succeed** (the real gate). Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: the starter tag set + idempotent seed; the cheap `ai/status` endpoint
   replacing the billed probe; auto-suggest-once behavior.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; check results (ruff / pytest+count / tsc / vitest / **vite build**); confirmation
   the probe no longer makes a billed AI call; anything unverified.
