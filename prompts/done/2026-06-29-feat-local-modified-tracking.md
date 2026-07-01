---
name: 2026-06-29-feat-local-modified-tracking
status: done
created: 2026-06-29
model: sonnet
completed: 2026-06-29
result: >
  All deliverables implemented. Migration 0015 applied cleanly. 13 new tests + 421
  total pass. ruff clean. tsc clean. 198 vitest pass. vite build succeeds. Share
  page shows prominent modified-copy notice. source_version stub captured for future
  type-2 upstream check.
---

# Task: Track & surface "modified locally vs the original" (especially on shares)

When an item was imported from an online source, show whether the **local copy has diverged from
the version originally downloaded** — most importantly on the **public share page** ("this is a
modified copy, different from the original at <source>"). This is **type 1 of two**: *local*
modification (auto baseline-diff + manual override). A future follow-up will add *type 2* ("a
newer version is available online"); **capture the source version signal now** so that's possible
later, but do NOT build the upstream re-check in this task.

## What exists (verified)
- `Item` has `source_url`, `source_site` (so we know if it came online + the link). Files have
  `sha256` (recomputed on change; cheap-first drift via size+mtime). The reconcile/scan engine
  (`app/worker/reconcile.py`) already detects model-file changes. There is **no import baseline**
  to compare against, and no modified flag.
- Public share view is served by `app/routers/shares.py` (find the public/unauth response model).

## Working tree check
`git status --porcelain` clean on `dev`.

## Data model — migration 0015 (next number)
Add to `Item`:
- `source_baseline` (JSONB, nullable): snapshot captured **at import commit** = mapping of each
  **model** file's relative path → its `sha256` (role=model only; exclude renders/thumbnails/
  sidecar/print photos). Null for items not imported from a source / created before this feature.
- `source_version` (String, nullable): a best-effort version/updated marker reported by the source
  at import (e.g. a scraped "updated"/"version"/published date string) — captured for the FUTURE
  upstream-update check; may be null. Wire it from the scraper if such a field is readily available;
  otherwise leave null (don't over-engineer scraping here).
- `locally_modified` (Boolean, not null, default false): set by the scan engine when current model
  files diverge from `source_baseline`.
- `locally_modified_at` (timestamptz, nullable): when divergence was last detected (the "last
  changed locally" time).
- `modified_override` (String, nullable): manual override — `'modified'` | `'original'` | null
  (null = use the auto value). **Effective state** = `modified_override` if set, else
  `locally_modified`.
`alembic upgrade head` must succeed; document the downgrade.

## Capture baseline at import
- In `commit_import_session` (`app/routers/import_sessions.py`), after files are inventoried,
  populate `item.source_baseline` from the committed **model** files' paths→sha256. Only set it
  when the item has a `source_url` (it's the "original online version" reference); for sourceless
  items leave null. Capture `source_version` if the scraped metadata exposes one.

## Detect divergence in the scan engine
- In the reconcile/scan flow, after model-file hashing, compute the current model-file path→sha256
  map and compare to `source_baseline`: if they differ (any file added/removed/changed), set
  `locally_modified=true` and stamp `locally_modified_at` (only update the timestamp when the
  modified state newly becomes true or the change set changes — don't churn it every scan). If they
  match again, set `locally_modified=false`. Skip items with null baseline. Keep it best-effort
  (wrapped so a hiccup doesn't fail the scan). Also expose a per-item **"Rescan disk"** path that
  recomputes this (the rescan button already enqueues reconcile — just ensure it updates the flag).

## API
- `ItemDetail`: add `is_modified: bool` (effective), `locally_modified_at`, `modified_override`,
  and enough to render the source link (`source_url` already present). Optionally a small
  `modified_summary` (counts of added/removed/changed vs baseline) if cheap.
- Public share response (`shares.py`): include `is_modified` + `source_url`/`source_site` so the
  share page can show the notice. Don't leak the baseline hashes publicly — just the boolean + the
  source link.
- A manual override endpoint: `PATCH /api/items/{key}/modified-override` (authed + CSRF) accepting
  `{ override: 'modified' | 'original' | null }`.

## UI
- **Item page** (`frontend/src/pages/ItemPage.tsx`): when the item has a `source_url`, show a badge
  — **"Modified from original"** (effective true) vs **"Matches original"** (false) — with the
  "last changed locally" time and a link to the source. A small control to set/clear the manual
  override (mark as modified / mark as original / auto). Keep feature parity.
- **Public share page** (`frontend/src/pages/PublicSharePage.tsx`): when modified + has a source,
  a **prominent notice**: "⚠ This is a modified copy — it differs from the original at <source>."
  with the source link. Tasteful, Aurora, auth-free (page stays public-only).
- *(Optional, if cheap)* a small "modified" marker on catalog cards.
- **Sidecar**: record the modified state + the original source reference in the YAML sidecar so the
  divergence info travels (add fields to the sidecar writer/reader; keep backward-compatible).
- Add the needed `api.ts` functions/types.

## Out of scope (state clearly in the report)
- Re-checking the live source for a newer upstream version (type 2) — not in this task.

## Verify
- Backend: `ruff check backend/`; **ephemeral Postgres** for migration 0015 + tests (docker
  one-liner as in other prompts; `alembic upgrade head`; `pytest`; tear down; recreate the
  scratchpad venv at the session path if gone). Add tests: import commit captures a baseline;
  modifying a model file's hash flips `locally_modified` on scan; manual override wins; public
  share response carries `is_modified`. Run a broad set (the reconcile + import + items tests at
  minimum).
- Frontend: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite
  build` MUST succeed**. Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: baseline-diff approach, effective-state rule (override vs auto), what counts
   as "modified" (model files only), source-version captured-but-unused-for-now, sidecar fields.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; check results (ruff / pytest+count / alembic 0015 / tsc / vitest / **vite
   build**); the migration-restart note; confirmation the share page shows the notice; what's left
   for the future upstream-update check; anything unverified.
