---
name: 2026-07-25-scad-ai-describe
status: done             # pending | in-progress | done | failed
created: 2026-07-25
model: sonnet            # coding task
completed: 2026-07-25
result: >
  Added scad_meta.extract_scad_header (deterministic title/description prefill
  from a .scad header on upload import), the ai/describe-scad endpoint + AI
  client method (whole-file), and a "Describe from SCAD" action in TitleStep.
  No migration. make verify-backend green (949); frontend build + new tests pass.
---

# Task: Prefill title/description from a `.scad` header on import + "Describe from SCAD" AI action

When a user imports an OpenSCAD `.scad` (self-designed items — the owner or Claude authors
the source, which leads with a rich header comment), **default to using that header**: auto-fill
the item **title** and **description** from the `.scad`'s leading comment block. Then, on the
wizard's description step, offer an **AI "Describe from SCAD"** action (alongside the existing
"clean up with AI") that sends the whole `.scad` to the configured AI provider and returns a
description the user can accept + edit before continuing.

This is the import-time companion to the read-only `.scad` viewer (already shipped:
`prompts/done/2026-07-25-scad-source-view.md`, `FileRole.source`).

## Before you start

- Read `CLAUDE.md` (verify-before-commit, commit rules) and `docs/architecture.md`.
- **Frontend stack:** Tailwind + CSS-var theme + minimal Radix + lucide + TanStack Query +
  `apiFetch` (CSRF). **No new dependencies.** Reuse existing wizard patterns/components.
- **No DB migration** in this task (reuses `session.suggested_title`/`confirmed_title`/
  `description` + the existing AI infra). Do NOT add a migration.
- **Verify gate mandatory:** `make verify` green before commit.

## Working tree check

`git status --porcelain` first (expected clean on `dev`). If files this task touches already
have uncommitted changes, list them and stop.

## Design (confirmed with owner)

1. **Default = the `.scad` header** (free, deterministic, no AI): on import of a `.scad`,
   pre-fill the **title** (from the header's first substantive line) and the **description**
   (from the rest of the header comment block).
2. **AI is optional and additive** on the description step: keep the existing
   "clean up with AI" (`ai/cleanup-description`) and add **"Describe from SCAD"**
   (`ai/describe-scad`) — sends the **whole `.scad`** file to the provider.
3. Everything stays **editable** before commit (title + description fields already are).

## Background (verified file map — confirm before editing)

- **Existing wizard AI actions:** `backend/app/routers/ai_actions.py` —
  `POST /api/import-sessions/{id}/ai/suggest-tags`, `ai/cleanup-description` (L278),
  `ai/summarize` (L355), gated by `GET /api/ai/status` (L184). **Mirror
  `cleanup-description` for the new `describe-scad` action** (same provider plumbing,
  auth/CSRF, error shape, and "no provider configured" handling).
- **Wizard description step:** `frontend/src/pages/import-wizard/TitleStep.tsx` (title +
  description), which already uses the shared **`AiTextPreview`** panel
  (`frontend/src/pages/import-wizard/AiTextPreview.tsx`, "Use this / Discard"). Add the new
  button + wiring here, matching how the existing cleanup-description button works.
- **Import-session model:** `session.suggested_title`, `session.confirmed_title`,
  `session.description`; staged files via `ImportSessionFile.staged_path`. A `.scad` file is
  classified `FileRole.source` (from the viewer task).
- **Upload → pending_wizard path:** find where an **upload** session gets its
  pre-wizard defaults (it does NOT scrape — trace the process/commit path in
  `backend/app/worker/tasks/import_session.py` and/or `routers/import_sessions/`
  helpers/sessions). That's where header prefill hooks in.
- **`.scad` text:** read the staged file's bytes from disk (`staged_path`); it's already
  accepted on upload.

## Implementation

### Backend

1. **Header extractor util** (e.g. `backend/app/storage/scad_meta.py`):
   `extract_scad_header(text: str) -> {title: str|None, description: str|None}`.
   - Take the **contiguous leading comment block** (before the first code/non-comment line,
     e.g. `$fn = 64;`): both `//` line comments and a leading `/* ... */` block.
   - Strip comment markers (`//`, `/*`, `*/`, leading `*`) and decorative rules (lines that
     are only `=`, `-`, `#`, spaces). Collapse the remaining lines.
   - **Title** = first substantive cleaned line (e.g. `SILICA-SOCK CLAMP  (for 3" / 76mm ...)`;
     it's fine to keep the parenthetical or trim at two spaces — pick something sensible and
     test it). **Description** = the cleaned block (optionally minus the title line).
   - Return `None`/empty when there's no usable header (hand-written files with no comments) —
     caller then leaves fields for the user / the AI action.
2. **Prefill on import** — in the upload→pending_wizard path, when the session has a staged
   `.scad` (role `source`) and the corresponding field is still empty:
   - set `suggested_title`/`confirmed_title` from the extracted title (only if not already set),
   - set `description` from the extracted description (only if empty).
   - Never overwrite a value the user already provided. If multiple `.scad` are present, use the
     first (or the one matching the item title heuristic) — keep it simple, document the choice.
3. **New AI action** `POST /api/import-sessions/{session_id}/ai/describe-scad` in
   `ai_actions.py`, mirroring `cleanup-description`:
   - Locate the session's staged `.scad` (400 if none). Read the **whole file** as the AI
     input (guard against absurd size — e.g. skip/trim beyond a sane cap like a few hundred KB;
     `.scad` are normally tiny).
   - Prompt the provider to produce a concise, user-facing **description** of the model from
     the OpenSCAD source (purpose, what it is, notable print/assembly notes if present in the
     code/comments) — do NOT echo code. Return the text in the **same response shape** as
     `cleanup-description` so the frontend can reuse `AiTextPreview`.
   - Respect the same provider-availability / not-configured handling as the other AI actions.

### Frontend

4. **`TitleStep.tsx`** — add a **"Describe from SCAD"** action (lucide icon + label; match the
   existing cleanup-description button's styling/placement). Show it only when the session has a
   `.scad`/`source` file AND `GET /api/ai/status` reports a provider available. On click, call
   the new endpoint, render the result in the existing `AiTextPreview` panel; **Use this** sets
   the description field (which stays editable). Match the loading/error UX of the existing AI
   button.
5. **API client** — add `describeScad(sessionId)` to the import API module next to the existing
   `cleanupDescription`/`suggestTags` calls.

## Tests

- **Backend** (`pytest -n auto`):
  - `extract_scad_header` unit tests: the owner's real header sample (title = the banner's
    first line, description contains the FILES/PRINT/HARDWARE notes); a file with only code and
    no header → `{None, None}`; a `/* ... */` block header; decorative-rule stripping.
  - Prefill: an upload session with a `.scad` whose title/description are empty gets them
    populated at pending_wizard; an already-set title/description is NOT overwritten.
  - `ai/describe-scad`: with a mocked AI provider returns a description; no `.scad` → 400;
    no provider configured → same handling as `cleanup-description`.
- **Frontend** (`vitest`):
  - "Describe from SCAD" renders only when a `.scad`/source file is present and AI is available.
  - Clicking calls the endpoint and "Use this" fills the description field.
  - (Note: local vitest can throw nondeterministic host-load `waitFor` timeout flakes — a
    different test each run, zero assertion failures. If seen, re-run; CI is authoritative. Your
    new tests + `npm run build` + `ruff`/`tsc` must be clean.)

## Changelog

Add a `### Added` entry to `CHANGELOG.md [Unreleased]` in the **same commit** (user-facing),
e.g.: "Importing an OpenSCAD `.scad` now pre-fills the item title and description from the
file's header comment, with an optional 'Describe from SCAD' AI action on the description step."

## Verify & commit

1. `make verify` — both gates green.
2. Commit on `dev` with a `feat:` prefix (e.g.
   `feat: prefill title/description from .scad header + AI describe-from-SCAD action`),
   one commit including code + tests + the CHANGELOG entry + this prompt file (moved to
   `prompts/done/`, frontmatter `status: done`/`completed`/`result` set). Push to `dev`.
   Never touch `main`. Record non-obvious decisions in `docs/decisions.md` (newest at top).

## Notes / gotchas

- No worker/task rendering — this is metadata prefill + one AI text endpoint. No OpenSCAD
  binary. Server-side `.scad` render remains deferred (FR #46).
- Don't overwrite user-entered title/description; header prefill only fills empties.
- Keep the AI response shape identical to `cleanup-description` so `AiTextPreview` is reused
  verbatim.
