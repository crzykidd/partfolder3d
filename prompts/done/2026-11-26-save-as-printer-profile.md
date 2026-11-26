---
name: 2026-11-26-save-as-printer-profile
status: done
created: 2026-11-26
model: sonnet
completed: 2026-11-26
result: Save-as-profile inline form added to PrintRecordFields; tsc clean, printer-profiles tests 11 pass
---

# Task: "Save as profile" button on the Log-print form

Printer profiles shipped in `2a2cf1f` (per-user, `/api/me/printer-profiles`, "Load from profile"
select in `frontend/src/pages/item/PrintRecordFields.tsx`). Add a **"Save as profile"** action so a
user can create a new profile from the six settings fields currently in the form (printer,
material, filament color, nozzle diameter, layer height, supports).

## Before you start

- Read `frontend/src/pages/item/PrintRecordFields.tsx`, `frontend/src/lib/api/printer-profiles.ts`,
  `frontend/src/pages/settings/PrinterProfilesSection.tsx`, `frontend/src/test/printer-profiles.test.tsx`,
  and `backend/app/routers/printer_profiles.py` (for create semantics: trimmed name, 422 blank,
  409 duplicate).
- Frontend stack: Tailwind + CSS-var theme + lucide + TanStack Query + `apiFetch`. **No Mantine, no
  toast lib** — show success/error inline.
- Frontend-only change; no backend changes expected.
- **Do NOT run `make verify` / full pytest / `scripts/verify-*.sh` or start any DB.** Fast checks only:
  in `frontend/`, `npx tsc -b --force` and `npx vitest run <files you touched>`. Nothing in background.

## Working tree check

`git status --porcelain`; if a file you'll touch is dirty, stop and report. This prompt is exempt.

## What to do

1. In `PrintRecordFields.tsx`, next to the "Load from profile" select (render the action **even when
   the user has zero profiles** — then it's the way to create their first one; restructure so the
   row shows whenever the user is authenticated / the component is mounted), add a small
   secondary "Save as profile" button (lucide `Save` or `BookmarkPlus` icon + text).
2. Clicking it reveals an inline mini-form: name input (prefill with the `printer` field value if
   set), a "Make default" checkbox, Save / Cancel. Save is disabled when the name is blank or all six
   settings fields are empty (nothing to save — show a short hint).
3. On save: `createPrinterProfile` with the six current form values (empty strings → null) +
   `is_default`. On success: invalidate the printer-profiles query (same key the select and Settings
   section use), set the "Load from profile" select to the new profile, collapse the mini-form, show
   a brief inline "Saved" note. On 409: inline "A profile with that name already exists." Other
   errors: inline generic message. The button must be `type="button"` and the mini-form must **not**
   be a nested `<form>` (the parent print-record form would submit) — use a div and handle Enter on
   the name input yourself (`preventDefault`).
4. Saving a profile must **not** change any print-record form values.
5. Tests in `frontend/src/test/printer-profiles.test.tsx`: save creates a profile with the current
   field values and doesn't submit the print form; blank name / all-empty fields disables Save; 409
   shows the duplicate message; button is present with zero profiles.
6. `CHANGELOG.md` `[Unreleased]`: extend the existing **Printer profiles** bullet (don't add a new
   one) with "…or save the current settings as a new profile right from the form."

## When done

1. Frontmatter: `status`, `completed`, `result`.
2. `mv` this file to `prompts/done/` (or `prompts/failed/`).
3. **Do not commit.** Report file list, fast-check results, proposed one-line `feat:` message.
