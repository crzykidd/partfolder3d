---
name: 2026-11-26-printer-profiles
status: done             # pending | in-progress | done | failed
created: 2026-11-26
model: sonnet
completed: 2026-11-26
result: printer profiles implemented (backend+frontend+tests+docs); fast checks pass, DB tests unrun
---

# Task: Per-user printer profiles that prefill the Log-print form

Users can define any number of named **printer profiles** in Settings (e.g. "Bambu X1C — PLA
0.4"), optionally mark one as **default**, and when logging a print pick a profile from a
dropdown to populate the print-settings fields (still editable afterwards). Owner decisions
(locked): **per-user** profiles; a profile can hold **all six** print-record settings fields;
**one optional default** that auto-fills a *new* Log-print form.

## Before you start

- Read `CLAUDE.md`, `docs/architecture.md` (module map + gotchas), and skim
  `backend/app/models/print_record.py`, `backend/app/routers/print_records.py`,
  `backend/app/routers/me.py`, `frontend/src/pages/item/PrintRecordFields.tsx`,
  `frontend/src/pages/item/PrintHistory.tsx`, `frontend/src/pages/catalog/BulkActions.tsx`,
  `frontend/src/pages/settings/SettingsPage.tsx`.
- Frontend stack: Tailwind + CSS-var theme (`AURORA_INPUT`, `Card`, etc. already used on these
  pages) + minimal Radix + lucide + TanStack Query + `apiFetch` (CSRF). **No Mantine, no toast lib.**
- **Migration number is `0028`** (latest is `0027_supersede_orphaned_extract_archives_jobs.py`).
  Match the style/`down_revision` chain of existing migrations.
- **Do NOT run `make verify`, the full `pytest`, `scripts/verify-*.sh`, or start any Postgres
  container.** The orchestrator runs the single authoritative gate. You may run DB-free fast checks:
  from `backend/`, `.venv/bin/ruff check app tests` (pinned 0.8.4, uses `backend/pyproject.toml`);
  in `frontend/`, `npx tsc -b --force` and `npx vitest run <specific test files you touched>`.
  Run nothing in the background.

## Working tree check

Run `git status --porcelain`; if any file you plan to touch is dirty, stop and report. This prompt
file is exempt.

## What to do

### Backend
1. **Model** `backend/app/models/printer_profile.py` → `PrinterProfile` (`printer_profiles` table):
   `id`, `user_id` (FK users, `ondelete=CASCADE`, indexed, not null), `name` (String 255, not null),
   the six optional settings fields with **the same types as `PrintRecord`**: `printer`, `material`,
   `filament_color`, `nozzle_diameter`, `layer_height`, `supports`; `is_default` (bool, not null,
   default false); `created_at`/`updated_at` like `PrintRecord`. Unique `(user_id, name)`.
   Enforce **at most one default per user** with a partial unique index
   (`WHERE is_default`) — and in the API, setting a profile default clears the others in the same
   transaction. Register the model wherever models are imported (`models/__init__.py`, alembic env).
2. **Migration** `backend/alembic/versions/0028_printer_profiles.py` creating the table + indexes;
   working `downgrade`.
3. **Router** — add to `backend/app/routers/me.py` (or a new `routers/printer_profiles.py` included
   in `main.py`; your call, match how per-user endpoints are organized), all auth-required, mutating
   routes CSRF-protected, every query scoped to `current_user.id` (another user's profile id → 404):
   - `GET    /api/me/printer-profiles` → list, default first then by name
   - `POST   /api/me/printer-profiles` → create (409 on duplicate name)
   - `PATCH  /api/me/printer-profiles/{id}` → partial update (incl. `is_default`)
   - `DELETE /api/me/printer-profiles/{id}` → 204
   Validate like print records do (e.g. same numeric bounds if any exist on `PrintRecordIn`).
4. **Tests** — new `backend/tests/test_printer_profiles.py`: CRUD happy path; per-user isolation
   (user B can't see/patch/delete A's profile); single-default invariant (setting B default unsets
   A); duplicate name → 409; CSRF required on mutations (match how other tests assert this).

### Frontend
5. **API client** — `frontend/src/lib/api/printer-profiles.ts` (or alongside `print-records.ts`,
   matching how `lib/api` is organized/re-exported): `PrinterProfile`, `PrinterProfileIn`,
   `listPrinterProfiles`, `createPrinterProfile`, `updatePrinterProfile`, `deletePrinterProfile`.
6. **Settings page** — new `PrinterProfilesSection` component (own file under
   `frontend/src/pages/settings/`), rendered in `SettingsPage.tsx` for **every** user right after
   `<PathPrefixesSection />`, titled "Printer profiles". List profiles in a `Card`; each row shows
   name, a short summary (printer · material · nozzle · layer), a "Default" marker, and actions
   **Set default / Edit / Delete** (delete with a simple confirm). "Add profile" opens an inline
   form with name + the six fields (reuse the same input styles; supports = Yes/No/unset select).
   Empty state: one line explaining what profiles do.
7. **Log-print form** — in `PrintRecordFields.tsx` (shared by the item page `PrintHistory` form and
   the catalog `BulkActions` "Log print"), add a **"Load from profile"** `<select>` at the top of the
   settings fields, listing the user's profiles (hidden entirely if they have none). Choosing a
   profile copies its **non-null** values into the six fields of `form` (null profile fields leave
   the form value alone); the user can then edit anything. Selecting the placeholder does nothing.
   - **Default auto-fill:** when a **new** record form opens (item-page "Log print" and bulk "Log
     print") and the user has a default profile, pre-fill from it and show the select set to it.
     **Do not** auto-fill when editing an existing print record — check how `PrintHistory` handles
     edit vs create and only apply on create (e.g. a prop like `applyDefaultProfile` passed by
     create call sites). Make sure the auto-fill doesn't clobber values the user already typed if
     the profiles query resolves late (apply once, only if the form is still untouched/blank).
8. **Tests** — vitest: Settings section create/list/set-default/delete against mocked fetch;
   PrintRecordFields: selecting a profile fills fields and leaves null-profile fields untouched;
   default profile pre-fills a new form but not an edit form. Extend
   `frontend/src/test/print-history-form.test.tsx` where it fits.

### Docs
9. `CHANGELOG.md` `[Unreleased]` → `### Added`: one bullet, e.g. "**Printer profiles.** Save named
   printer/material/nozzle/layer presets in Settings (one can be the default) and load them into the
   Log-print form from a dropdown — single and bulk."
10. `docs/architecture.md`: add the feature to the module map (router / model / migration 0028 /
    api client / settings section / test files), matching existing row format.

## Conventions to honor

- Match existing inline-style conventions on these pages; don't refactor unrelated code.
- Keep `PrintRecordFields`'s existing props working for current callers; add new props as optional.

## When done

1. Update this file's frontmatter: `status`, `completed` (date), `result` (one line).
2. Move this file into `prompts/done/` (or `prompts/failed/`) — it's untracked, so a plain `mv` is fine.
3. Record genuinely non-obvious decisions in `docs/decisions.md` (newest at top).
4. **Do not commit.** Report back: file list, any design choices you made (router placement,
   default-autofill mechanics), the fast-check results, and a proposed one-line `feat:` message.
