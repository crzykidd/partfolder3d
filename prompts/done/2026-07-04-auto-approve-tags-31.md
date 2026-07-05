---
name: auto-approve-tags-31
status: done
created: 2026-07-04
model: Sonnet
completed: 2026-07-04
result: >
  Added tags.auto_approve setting (bool, default false) validated in
  routers/settings.py and read via new services/settings_service.py; gated the
  import-commit tag-creation site (routers/import_sessions/commit.py) so brand-new
  tags land active when on, pending when off. Added POST /api/admin/tags/approve-all
  (idempotent, returns {approved}) in routers/tag_admin.py. Frontend: auto-approve
  AuroraToggle + "Approve all" button on TagAdminPage.tsx, with api helpers. Ruff
  clean; backend 744 passed (was 739, +5); frontend build OK + vitest 350 passed
  (was 346, +4). No migration needed. Tree prepared, not committed.
---

# Auto-approve pending tags (closes #31)

## Goal

#31: "Tags should be allowed to be auto-approved and not need an approval process." Today every
brand-new tag from an import lands in `TagStatus.pending` and an admin must approve it on the Tag
Admin page. Add an **admin opt-in** so new tags can skip the review queue, plus a bulk "approve
all pending" action for tags already queued.

## Design (implement this; flag in your report if you'd shape it differently)

1. **Setting `tags.auto_approve`** (bool, default `false`) — a DB setting stored/validated like the
   existing `render.mode` key (see `backend/app/routers/settings.py` — add it to the settings
   allowlist/validation so only `true`/`false` are accepted; match how booleans are already
   handled if any exist, else store `"true"`/`"false"` strings and parse). Read it via the same
   settings-read helper the rest of the backend uses.

2. **New tags land `active` when the setting is on.** Find EVERY path that currently mints a tag as
   `pending` and gate it on the setting so it creates `active` instead when auto-approve is on:
   - `backend/app/routers/import_sessions/commit.py` (~173 `Tag(status=TagStatus.pending)` and ~180
     `_attach_tags(..., new_tag_status=TagStatus.pending)`).
   - `backend/app/services/item_helpers.py` `_attach_tags` / `_get_or_create_tag` (the
     `new_tag_status` seam).
   - Grep for any other `TagStatus.pending` tag-creation site (reconcile, AI-suggested tag
     acceptance, manual tag add on an item) and make them consistent — when auto-approve is on, a
     newly-created tag is `active`; when off, behavior is exactly as today. Do NOT change how
     *existing* tags are matched/reused, only the status assigned to brand-new ones.

3. **Bulk approve-all endpoint.** Add `POST /api/admin/tags/approve-all` in
   `backend/app/routers/tag_admin.py` (admin-only, same auth dep as the other tag-admin routes)
   that promotes ALL `pending` tags to `active` in one call and returns the count approved.
   Idempotent (zero pending → 200, count 0). This complements auto-approve for the existing backlog.

4. **Frontend (Tag Admin page, `frontend/src/pages/admin/TagAdminPage.tsx`).**
   - A toggle bound to the `tags.auto_approve` setting (read current value, PUT on change) with a
     short helper line ("New tags are approved automatically instead of waiting in this queue").
   - An **"Approve all"** button on the pending list that calls the new endpoint and refreshes
     (invalidate the pending-tags + tags queries). Hide/disable it when the pending list is empty.
   - Match the existing page's components/ui + TanStack Query patterns; no new deps.

## Constraints / notes

- **No migration** — settings are key-value rows; a new key needs no schema change. If you think a
  migration is needed, STOP and report (it isn't).
- Auto-approve only affects tags created *after* it's enabled; flipping it on does NOT retroactively
  approve the existing queue — that's what the "Approve all" button is for. Note this in the report.
- Keep the pending workflow fully intact when the setting is off (default) — this is purely additive.

## Verify

- Ephemeral PG on :5433 (`pf3d-pg-v` up; `DATABASE_URL='postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d'`).
  Pinned `backend/.venv/bin/ruff check backend/` clean.
- Backend tests: setting rejects non-bool; with auto-approve ON a newly-imported unknown tag is
  `active` (not `pending`); with it OFF it's `pending` (unchanged); `approve-all` promotes all
  pending and is idempotent. Put them in the tag/tag-admin test files.
- `pytest -n auto` full suite green (was 739). Frontend: `npx tsc -b --force` + `npm run build` +
  `npx vitest run` (baseline 346) — add a focused test for the toggle and/or approve-all button.

## Reporting

Prepare the tree (do NOT git-commit). Report: files changed; the setting key + how bool is
stored/validated; every pending-creation site you gated; the approve-all endpoint shape; frontend
changes; ruff + full backend suite + frontend build/vitest results; proposed CHANGELOG
`[Unreleased] ### Added` (or `### Changed`) bullet with `closes #31` + commit message. Set this
prompt's frontmatter (`status: done` / `completed` / `result`) and `mv` it (plain mv, not git mv)
to `prompts/done/`, and tell me so I stage it.
