---
name: wizard-render-capture-26
status: done
created: 2026-07-04
model: Sonnet
completed: 2026-07-04
result: >
  Shipped the "Try to render file" viewport capture in the wizard Images step.
  Backend: added GET /api/import-sessions/{id}/files/{filename} (path-traversal-guarded,
  owner-scoped) and POST /api/import-sessions/{id}/images (session-image save, source=capture),
  and repaired the dormant is_url=False commit branch to copy staged captures into images/ with
  ImageSource.captured. Frontend: ImagesStep gains a lazy-loaded ModelViewer + capture wired to a
  new uploadSessionImage, gated to sessions with a renderable staged model (.stl/.obj/.3mf); strip
  now previews local images via the serve endpoint. Deviation: uploadSessionFiles does NOT produce a
  session image (draft-only, creates File rows), so a dedicated image endpoint was required (per #26).
  No migration. Backend 769 passed (761 + 8 new); ruff clean; frontend build OK (ModelViewer stays a
  separate chunk), 357 vitest passed (353 + 4 new). WebGL toBlob pixel capture untestable in jsdom
  (same boundary as #21) — wiring tested with a mocked blob.
---

# "Try to render file" viewport-capture in the Add Asset wizard (closes #26)

## Goal

#26 (deferred from #21): in the import/Add-Asset wizard's **Images step**
(`frontend/src/pages/import-wizard/ImagesStep.tsx`), offer a **"Try to render file"** action that
loads a staged model file in the in-browser 3D viewer and captures a viewport image as a
**session** image — valuable at import time because no server render exists yet and 3MF may lack an
embedded thumbnail. Read `gh issue view 26` and `gh issue view 21` first.

## What already exists (verified — reuse, don't rebuild)

- **Capture mechanics (#21, shipped):** `frontend/src/components/viewer/ModelViewer.tsx` +
  `frontend/src/pages/item/DownloadsPanel.tsx` — react-three-fiber with `preserveDrawingBuffer`,
  offscreen render, `canvas.toBlob(...)`. **Mirror this exactly** for the capture itself.
- **Save path:** the wizard already uploads images via `api.uploadSessionFiles(session.id, files)`
  (`POST /api/import-sessions/{id}/files`), and image-type uploads become `ImportSessionImage`
  rows shown in the strip. So a captured PNG can be saved by uploading it through the SAME path —
  confirm this produces a session image (it should); if a captured image needs a distinct
  provenance, set it, but do NOT invent a new save endpoint if `uploadSessionFiles` already works.
- **Delete/set-default** session-image controls already exist in ImagesStep.

## The gap to fill

- **A session-file SERVE endpoint** so the browser viewer can fetch a staged model file. There is
  an upload endpoint (`POST …/files`) but no GET-serve. Add
  `GET /api/import-sessions/{session_id}/files/{filename}` (owner-auth, same dep as sibling session
  routes) that streams a file from that session's staging dir. **Path-safety is mandatory:** resolve
  the requested name within the staging dir and reject any traversal (reuse the
  `resolve()`+`is_relative_to()` barrier the item download endpoint uses). Serve with a sane
  content-type / `application/octet-stream`; the viewer fetches the bytes.
- **A way for the wizard to know the staged model files.** Determine what the frontend already has
  (does the `session` object expose its files? is there a list endpoint?). If the model-file list
  isn't already available to ImagesStep, expose it minimally (a field on the session response or a
  small list — prefer reusing what exists). Renderable = `.stl/.obj/.ply` (browser-renderable) and
  `.3mf` (viewer supports it per #21); non-model files aren't offered.

## Frontend behavior (ImagesStep)

- Show a **"Try to render file"** control ONLY when the session has ≥1 renderable staged model file
  (upload imports; URL imports typically have none — that's fine, hide it).
- Clicking it opens the `ModelViewer` on a selected staged model (via the new serve endpoint; if
  multiple model files, let the user pick which), with a **Capture** button that grabs the current
  viewport (mirroring the #21 `preserveDrawingBuffer`/`toBlob` flow) and uploads it via
  `uploadSessionFiles`, then refreshes the session so the new image appears in the strip.
- **Support multiple captures** (e.g. different angles / multi-part 3MF), consistent with #21.
- Reuse existing components/ui + TanStack Query; ModelViewer is already `React.lazy`-loaded — keep
  it code-split (don't eagerly import three.js into the wizard bundle). Match the existing wizard
  styling.

## Constraints

- **No migration** (session images/files already modeled). If you think one is needed, STOP and
  report.
- Keep the ModelViewer lazy/code-split. Don't regress the existing ImagesStep upload/delete/default.

## Verify

- Backend: ephemeral PG on :5433 (`DATABASE_URL='postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d'`),
  pinned `backend/.venv/bin/ruff check backend/` clean. Test the serve endpoint: serves a staged
  file, **rejects path traversal** (`../`, absolute), 404 for missing/other-session files, auth
  required. Full `pytest -n auto` green (was 761).
- Frontend: `npx tsc -b --force` + `npm run build` + `npx vitest run` (baseline 353). Add a focused
  test for the control's visibility (shown with a renderable file, hidden without) and the
  upload-on-capture wiring (mock the capture/upload).
  **HONEST LIMITATION:** the actual WebGL `toBlob` capture cannot run in jsdom (no WebGL) — same
  boundary as #21. Test everything AROUND it (visibility gating, file selection, the upload call on
  a mocked blob); do NOT fake a passing test of the pixel capture itself. Report this boundary.

## Reporting

Prepare the tree (do NOT git-commit). Report: files changed; the serve endpoint + how path-safety
is enforced; how the wizard learns the staged model files; whether the save reused
`uploadSessionFiles` or needed anything new; what's tested vs the WebGL-capture limitation; ruff +
full backend suite + frontend build/vitest results; proposed CHANGELOG `[Unreleased] ### Added`
bullet with `closes #26` + commit message. Set this prompt's frontmatter (`status: done`/
`completed`/`result`) and `mv` it (plain mv) to `prompts/done/`, and tell me.
