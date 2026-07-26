---
name: 2026-07-25-edit-item-description-tags
status: done          # pending | in-progress | done | failed
created: 2026-07-25
model: sonnet             # coding task
completed: 2026-07-25
result: PATCH /api/items/{key} (already write-through-to-sidecar) reused; new tags now respect tags.auto_approve; TagOut exposes status; inline description+tags editor added to ItemMetadata.tsx reusing import-utils chip helpers; title deferred; make verify green (backend 979 pass, frontend build+vitest clean).
---

# Task: Edit an existing item's description + add/remove tags in-app (closes #47)

Let a user edit an **existing** catalog item's **description** and **add/remove tags**
directly from the item page — with a proper **write-through to the on-disk sidecar** so
the change survives a rescan and is NOT flagged as drift/corruption by the reconcile
engine. Today these fields are only settable at import time or by hand-editing the
`.yml` sidecar + rescanning.

## Before you start

- **Read `prompts/startnewsession.md`, `CLAUDE.md`, and `docs/architecture.md`** (module
  map + load-bearing gotchas). Skim the newest `docs/decisions.md` entries — especially
  the **v0.7.2 corruption-vs-legit-edit** work (2026-07-23); this task must reuse that
  same baseline discipline.
- **This is the load-bearing part:** the edit must go through the same
  **DB ⇄ sidecar ⇄ disk** path the reconcile engine expects. After a write-through, a
  subsequent library scan must treat it as a **legitimate local edit** (adopt the new
  baseline), NOT as drift or corruption. Study how `backend/app/worker/reconcile.py`
  decides legit-edit vs drift and how the sidecar baseline (hash/mtime/size) is recorded,
  then make the edit endpoint update that baseline in the same operation.
- **Verify before commit is mandatory** — `make verify` (backend gate: ephemeral PG +
  pinned ruff 0.8.4 + alembic + `pytest -n auto`; frontend gate: fresh `tsc -b --force` +
  `npm run build` + vitest). Do NOT background `make verify` and exit (it orphans pytest
  and corrupts the shared test PG) — run it to completion in-session.
- **If (and only if) you need a schema change, the next migration number is `0026`.**
  You most likely do **not** need one — description/tags already exist and the reconcile
  baseline machinery is from v0.7.2. Prefer no migration; only add `0026_*` if genuinely
  required, and say so in your report.
- **Match the existing stack:** Tailwind + CSS-var theme + minimal Radix + lucide +
  TanStack Query + `apiFetch` (CSRF). No Mantine, no toast lib.

## Working tree check

Run `git status --porcelain` and cross-reference the files below. If any have
uncommitted changes, list them and ask before touching. Surface unrelated dirty files
once; they don't block. This prompt file is exempt.

## What to do

### Backend
1. **Item-update endpoint(s)** in `backend/app/routers/items/` (see `core.py`,
   `helpers.py`, `schemas.py`). Add a PATCH (admin + CSRF, like other mutations) that can:
   - update the item **description**;
   - **add** tags and **remove** tags on the existing item.
   Consider whether **title** should be editable here too for parity with the import
   wizard (title/description/tags) — the issue explicitly raises this. Implement title
   edit **only if** it's a clean, low-risk addition through the same write-through path;
   otherwise scope to description+tags and note the deferral. Flag this as a judgement
   call in your report.
2. **Tag handling must reuse the existing tag reconciliation**: new tags land `pending`
   unless auto-approve is on; respect the tag status/approval workflow. Do not re-invent
   tag creation — reuse whatever `POST /api/items` / the wizard path already calls.
3. **Write-through to the sidecar AND the DB in one operation**, then **refresh the FTS
   `search_vector`** (title/description/tags feed it — find how import/create refreshes it
   and reuse that). Sidecar write lives around `backend/app/storage/sidecar.py`.
4. **Update the reconcile baseline** so the next scan sees a legit local edit, not drift
   (the v0.7.2 discipline). This is the crux — get it right and test it.
5. Tests: endpoint happy-path + auth/CSRF rejection + tag add/remove (incl. pending vs
   auto-approve) + **a reconcile test proving an edited item is NOT flagged as drift on
   the next scan**. Follow existing test patterns/fixtures.

### Frontend
6. **Inline edit on `frontend/src/pages/item/ItemMetadata.tsx`**: editable description
   (textarea with Save/Cancel) and tag chips with remove + an add-tag input. **Reuse the
   wizard's tag picker/reconcile UI** — see `frontend/src/pages/item/TagsStep.tsx` and
   `TitleStep.tsx` (and whatever shared tag-input component they use). Do not duplicate it.
7. Surface **pending tag state** (added tags may be `pending` under moderation) so the
   user understands approval.
8. On save, **refresh the item and the tag cloud** (invalidate the right TanStack Query
   keys). Add/extend vitest coverage for the edit interaction.

## Conventions to honor

- Conventional-commit `feat:` prefix; **no `Co-authored-by:` trailer**.
- **Update `CHANGELOG.md` `[Unreleased]` in the SAME change** describing the feature.
- Doc updates ship with the code: if this adds an endpoint/flow, update
  `docs/architecture.md`'s module map row for items.
- The worker has **no hot-reload** — if you touch anything the worker imports
  (`reconcile.py`, tasks), note that `make worker-restart` is needed to exercise it live.

## When done

1. Set this file's frontmatter: `status: done` (or `failed`), `completed: 2026-07-25`,
   `result:` one line.
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record any non-obvious decisions (esp. the title-editable call and the baseline
   approach) in `docs/decisions.md`, newest at top.
4. **You are a spawned agent: do NOT commit and do NOT push.** Run `make verify` to green,
   prepare the working tree, and **report back** to the orchestrator: the exact file list,
   a proposed one-line `feat:` message (include `closes #47`), the verify result
   (backend pass count + frontend build/vitest), whether a migration was added, and the
   title-editable decision. The orchestrator commits + pushes on `dev`.
