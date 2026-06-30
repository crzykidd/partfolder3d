---
name: 2026-06-30-feat-import-management
status: done
created: 2026-06-30
model: sonnet
completed: 2026-06-29
result: >
  Implemented all three gaps. Backend: DELETE /api/import-sessions/{id} (204, cascade +
  staging-dir cleanup, DATA_DIR safety check); DELETE /api/import-sessions/{id}/images/{image_id}
  (200 → updated session, default-image reassignment, staged-file cleanup, db.expire() identity-map
  fix); INBOX_DIR auto-created at lifespan startup. Frontend: deleteImportSession + deleteImportSessionImage
  in api.ts; Delete row action in ImportsPage; ✕ per-image button in ImportWizardPage. Tests: 10/10
  pass (ruff clean, tsc clean, vitest 228/228, vite build succeeds).
---

# Import management bundle: remove-image + delete-import-session + auto-create inbox dir

Three related import-flow gaps (all touch `import_sessions.py` / `api.ts`, so do them together):

## A. Delete an import session (the Imports list has no delete)
- Today only **Cancel** exists (`POST /api/import-sessions/{id}/cancel` → status=cancelled); there's
  no way to remove a session row, so cancelled/failed/committed sessions pile up.
- Add `DELETE /api/import-sessions/{session_id}` (authed + CSRF; owner/admin): delete the
  `ImportSession` row (cascade its `ImportSessionImage`/`ImportSessionFile` rows) and best-effort
  remove its **staging dir** (`staging_dir`, under DATA_DIR) if present — do NOT touch any committed
  Item or library files. 404 if missing. Return 204.
- Frontend `frontend/src/pages/ImportsPage.tsx`: a **Delete** action per row (with confirm),
  invalidates the sessions list. Add `deleteImportSession(id)` to `api.ts`. (Keep Cancel for
  in-progress ones; Delete is for clearing rows.)

## B. Auto-create the inbox directory at startup
- The inbox scanner skips `INBOX_DIR` (default `/data/inbox`) if it doesn't exist. Create it on
  startup so inbox import works out of the box — `mkdir(parents=True, exist_ok=True)` in the app
  startup (e.g. `app/main.py` lifespan/startup, next to other DATA_DIR setup) and/or the worker
  startup. Best-effort (log on failure, don't crash).

## C. Remove an image from the import list (wizard Images step)

# Task: Let the user remove an image from the import list (wizard Images step)

When importing a new asset, the wizard's Images step lists scraped/uploaded images (often many,
e.g. 12–16 from a scrape). The user wants to **remove an image from the import list before commit**
so unwanted images don't carry into the item.

## What exists
- `app/models/import_session.py` → `ImportSessionImage` (per-session image rows: id, session_id,
  path, is_default, order). The wizard Images step in `frontend/src/pages/ImportWizardPage.tsx`
  renders `session.images` (set-default + upload already exist; NO remove). There is currently no
  delete-session-image endpoint (`app/routers/import_sessions.py` only has set-default + upload).

## Working tree check
`git status --porcelain` clean on `dev`.

## Backend — `app/routers/import_sessions.py`
- `DELETE /api/import-sessions/{session_id}/images/{image_id}` (authed + CSRF; owner/admin like the
  other session mutations): delete that `ImportSessionImage` row. If the image was a staged/uploaded
  file inside the session's staging dir, remove the file too (best-effort; don't fail the request if
  the file is already gone). For scraped image URLs not yet downloaded, just drop the row. If the
  removed image was `is_default`, clear/reassign default sensibly (e.g. first remaining, or none).
  Return the updated session (or 204 — match the style of the existing session endpoints). 404 if
  the image/session doesn't exist or isn't this session's.

## Frontend — `ImportWizardPage.tsx` Images step
- Add a **remove (✕)** control on each image in the Images-step list (hover or always-visible),
  with a light confirm or immediate remove (your call — keep it quick). On success invalidate the
  import-session query so the image disappears. Keep set-default + upload working; if the default
  was removed, reflect the new default. Add `deleteImportSessionImage(sessionId, imageId)` to
  `api.ts`.
- Aurora + `@/components/ui`. NO new deps, NO toast. Don't touch `frontend/src/pages/examples/`.
  Feature parity for the rest of the wizard.

## Verify
- Backend: `ruff check backend/` (run it yourself); **ephemeral Postgres** + tests (docker
  one-liner; `alembic upgrade head`; run pytest in FOREGROUND to completion; tear down after;
  recreate the scratchpad venv if gone). Test: removing a session image deletes the row (and
  reassigns default if it was default); 404 on a foreign/missing image.
- Frontend: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite
  build` MUST succeed**. Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: remove-session-image semantics (default reassignment, staged-file cleanup).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; check results (ruff / pytest+count / tsc / vitest / **vite build**); anything
   unverified.
