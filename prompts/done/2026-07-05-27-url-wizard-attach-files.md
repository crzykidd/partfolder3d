---
name: 2026-07-05-27-url-wizard-attach-files
status: done
created: 2026-07-05
model: sonnet
completed: 2026-07-05
result: Relaxed upload-files guards for url+pending_wizard; added DELETE file endpoint; added mid-wizard attach UI in SummaryStep; all tests green (779 BE, 366 FE).
---

# Task: Let URL-import sessions attach model files mid-wizard (closes #27)

A URL import (`source_type='url'`) currently commits with **zero model files** and the
wizard offers no way to add one — the only mitigation is the Files-row warning on
Review & Commit (shipped in v0.4.0). This task adds a mid-wizard "Attach files"
affordance so the user can paste a URL, let the scrape pre-fill metadata/images, then
download the model file from the source site themselves and drop it into the wizard
before committing. This is the owner's chosen resolution for #27's core issue
(option "b": manual attach; auto-fetch is deferred to the #23 pluggable-scraper work).

## Before you start

- Read `docs/architecture.md` (module map + gotchas) — especially the import-session
  and wizard sections.
- Key facts already established (verified in code — trust these, but re-check line
  numbers, they may have drifted):
  - `backend/app/routers/import_sessions/sessions.py::upload_session_files`
    (`POST /api/import-sessions/{session_id}/files`, ~line 213) already does the whole
    job: writes to `session.staging_dir`, infers roles via
    `app.storage.inventory.infer_role`, creates `ImportSessionFile` rows. It just
    refuses non-`draft` status and non-`upload` source types, and 500s when
    `staging_dir` is None.
  - URL sessions are created with `staging_dir=None`
    (`create_import_session`, ~line 167 — the staging dir is only made for
    `src == "upload"`), and their status flow is `draft → processing →
    pending_wizard → committed`. While the user is in the wizard the session is
    **`pending_wizard`**, not `draft`.
  - The commit path (`backend/app/routers/import_sessions/commit.py`, "Move staged
    files into item dir", ~line 119) iterates `session.files` generically — staged
    files attached to a URL session will be ingested with **no commit-side changes**.
  - Frontend: the Review step is
    `frontend/src/pages/import-wizard/SummaryStep.tsx` (it already renders the
    Files row + zero-file warning). `api.uploadSessionFiles(id, files)` already
    exists in `frontend/src/lib/api` (used by `AddAssetModal.tsx`'s Upload tab).
- **No Alembic migration is needed** — do not create one.
- Verify-before-commit discipline per `CLAUDE.md`: `make verify` (backend needs
  `pytest -n auto`; frontend needs the fresh `tsc -b --force` build). No worker/task
  files are touched, so no `make worker-restart` needed.
- The owner may be running the vite dev server / live `:dev` stack against this repo;
  keep the tree consistent (don't leave the frontend half-edited between long steps).

## Working tree check

Before making any edits, run `git status --porcelain` and cross-reference the files
this plan needs to modify. If any of those files have uncommitted changes, list them
and ask before touching them. Surface unrelated dirty files once as awareness; don't
block. This file (the handoff prompt itself) is exempt — it's expected to be modified
by "When done" below.

## What to do

1. **Relax `upload_session_files` guards** in
   `backend/app/routers/import_sessions/sessions.py`:
   - Allow `source_type` in `{upload, url}` (keep rejecting `inbox` and anything else).
   - Allow `status` in `{draft, pending_wizard}` (keep rejecting `processing`,
     `committed`, `failed`, `cancelled`). Update the error messages and the docstring
     to match the new contract.
   - **Lazily create the staging dir** when `session.staging_dir` is None: mirror
     `create_import_session`'s upload branch (`_get_staging_dir() / str(uuid4())`,
     `mkdir(parents=True, exist_ok=True)`, persist `session.staging_dir`). Do this
     instead of the current 500.
   - Do NOT re-run `/process` or the scrape after a mid-wizard upload — the files just
     sit staged; commit ingests them.
2. **Add a delete-staged-file endpoint** so the attach UI can undo a mistaken upload:
   `DELETE /api/import-sessions/{session_id}/files/{file_id}` in the same router.
   Same auth pattern as the other session endpoints (`_load_session` + CSRF where the
   siblings use it — match `delete_import_session_image`'s shape, ~line 787). Allowed
   only in `draft`/`pending_wizard`; deletes the `ImportSessionFile` row and
   best-effort unlinks the staged file (log a warning on FS failure, don't 500).
3. **Frontend — attach UI on the Review step** (`SummaryStep.tsx`):
   - For sessions in the wizard with `source_type` `'url'` or `'upload'`, extend the
     existing Files row area with: the list of currently staged files (name + role,
     with a per-file remove button calling the new delete endpoint) and an
     "Attach files" affordance (file input; a drag-drop zone is optional — match the
     look of `AddAssetModal`'s dropzone if cheap, else a plain styled button + input
     is fine). On selection call `api.uploadSessionFiles(session.id, files)`, then
     invalidate/refetch the session query so the Files row and warning update.
   - Add `api.deleteSessionFile(sessionId, fileId)` to the api client.
   - The zero-file warning stays, but for URL sessions reword it to point at the new
     affordance (e.g. "No model files attached — attach the file you downloaded from
     the source site, or commit metadata-only.").
   - Match the existing Aurora styling conventions in the wizard files (CSS-var
     styles, no new UI libs — Tailwind + inline Aurora style objects as the
     neighboring code does).
4. **Backend tests** (place next to the existing import-session router tests; follow
   their fixture patterns):
   - Upload to a `url` session in `pending_wizard` succeeds: staging dir lazily
     created, `ImportSessionFile` rows present, response includes the files.
   - Upload to a `committed` (or `processing`) session → 409.
   - Upload to an `inbox` session → 422 (unchanged behavior for other types).
   - Delete endpoint: removes row + staged file; 404 on foreign file id; blocked
     after commit.
   - Commit of a `url` session with a mid-wizard attached file produces `File` rows
     on the item (i.e. the end-to-end #27 scenario is actually fixed).
5. **Frontend tests**: extend the existing wizard tests
   (`frontend/src/test/import-wizard-*.test.tsx`) — staged-file list renders, attach
   calls `uploadSessionFiles` and refetches, remove calls the delete endpoint,
   zero-file warning still shows when no files.
6. **Changelog**: add to `CHANGELOG.md [Unreleased]` in the SAME commit — a `### Fixed`
   (or `### Added`) entry: URL-import wizard can now attach model files before commit
   (closes #27).
7. **Docs**: check `docs/architecture.md`'s import-session section — if it states
   "URL sessions never have files/staging", update it to describe the new behavior in
   the same commit.
8. Run `make verify` (both gates) and make sure everything is green before handing
   off.

## Conventions to honor

- Conventional-commit prefix; this is a `fix:` (it resolves bug #27). Commit message
  must contain `closes #27` (that exact keyword form, per project convention).
- Changelog updated in the same commit as the code (never a follow-up).
- No `Co-authored-by:` trailers. Never `git add -A`.
- Match surrounding code style; keep comments to non-obvious constraints only.

## When done

1. Update this file's frontmatter: set `status` (`done`/`failed`), `completed` (the
   date), and `result` (one line).
2. `git mv` this file into `prompts/done/` (on success) or `prompts/failed/` (on
   failure). Create the subdir if it doesn't exist yet.
3. Record the #27 resolution in `docs/decisions.md` (newest at top): owner chose
   manual mid-wizard attach (option b); auto-fetch deferred to #23; note the guard
   relaxation contract (which statuses/source-types may upload).
4. Hand off ONE commit covering this prompt file, the files this session modified, and
   the prompt move. **You are a spawned agent: do NOT commit or push.** Prepare the
   working tree, then report back: the file list, the proposed one-line commit
   message (`fix: ... closes #27`), the `make verify` results, and anything
   noteworthy. The orchestrating session commits on `dev` per the project's
   auto-commit override.
