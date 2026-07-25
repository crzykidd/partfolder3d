---
name: 2026-07-25-scad-source-view
status: done             # pending | in-progress | done | failed
created: 2026-07-25
model: sonnet            # coding task
completed: 2026-07-25
result: >
  Added FileRole.source + migration 0025, .scad classification + upload allowlist,
  and a read-only "Show SCAD" modal on the item page (view/copy/download + Open in
  OpenSCAD Playground via compressed hash deep-link). Read-only v1; server render
  deferred to #46. make verify green.
---

# Task: View & hand off OpenSCAD `.scad` source files (read-only v1)

Make `.scad` (OpenSCAD source) a first-class, recognized **source** file on import, and
give the item page a **"Show SCAD"** action that pops a modal with the code (scrollable,
monospace), a **Copy** button, a **Download** button, and an **Open in OpenSCAD Playground**
button that deep-links `ochafik.com/openscad2` with the code prefilled. This is for
self-designed items (the owner or Claude authors the `.scad`). No server-side rendering.

## Before you start

- Read `CLAUDE.md` (verify-before-commit, migration numbering, commit rules) and
  `docs/architecture.md` (module map). This is a multi-file change → it is correctly a
  handoff, not an inline edit.
- **Frontend stack:** Tailwind + CSS-var theme + minimal Radix + lucide + TanStack Query +
  `apiFetch` (CSRF). **No new dependencies** — no syntax-highlighting library; render the
  code in a plain monospace `<pre>`/textarea. No toast lib.
- **Verify gate is mandatory** before committing: `make verify` (backend + frontend). The
  backend gate needs the ephemeral PG the script manages; there is a new migration here, so
  the migration must apply cleanly under `alembic upgrade head`.
- **This task creates Alembic migration `0025`** (the next free number — current head is
  `0024`). Use exactly `0025_*`. Do not pick another number.

## Working tree check

Run `git status --porcelain` first. Expected clean on `dev`. If files this task touches
already have uncommitted changes, list them and stop before editing.

## Scope

**In scope (v1, read-only):**
1. Recognize `.scad` as a new `FileRole.source` (DB enum migration + classifier).
2. Allow `.scad` on the per-item direct-upload endpoint (currently rejected).
3. Item page: a **Show SCAD** button on the top-right source/metadata card (only when the
   item has a `.scad`/`source` file) → modal with code + Copy + Download + Open in Playground.

**Explicitly NOT in scope:**
- Server-side compile/render of `.scad` → tracked in **FR #46** (deferred; the playground
  covers editing/preview/STL export for now). Do not add the `openscad` binary or any
  compile step.
- In-app **editing/saving** of the `.scad` (read-only for v1; it would need a new write path
  + reconcile-baseline handling — a fast-follow, not now).

## Background (verified file map — confirm before editing)

- **Classification:** `backend/app/storage/inventory.py` — `MODEL_EXTENSIONS` (~L35),
  `infer_role()` (~L51–79). Today `.scad` → `FileRole.other`.
- **Role enum:** `backend/app/models/file.py:19-26` `FileRole(model, zip, image, render,
  gcode, photo, other)`; column is `Enum(FileRole, name="filerole")` (~L38) → **new value
  needs a PG enum migration.**
- **Per-item upload allowlist:** `backend/app/routers/items/files.py:52-62`
  `_ALLOWED_FILE_EXTENSIONS` — the one place `.scad` is rejected today; add it.
- **Import-session upload:** `backend/app/routers/import_sessions/sessions.py:226`
  (`upload_session_files`) already accepts any extension and assigns role via `infer_role`
  → no change needed there beyond the classifier update; verify a `.scad` staged + committed
  ends up role `source`.
- **File serving (for the code view):** the existing endpoint that serves item files
  (`/api/items/{key}/files/{path}`, backend `routers/items/files.py` / `downloads.py`) serves
  raw bytes — the frontend fetches the `.scad` and reads it as text. **No new backend endpoint
  is required for viewing.**
- **Item detail API** returns the file list with `role` + `path` + `size` — the frontend uses
  this to detect a `.scad`/`source` file and to size-guard the fetch.
- **Frontend item page:** `frontend/src/pages/item/` — locate the top-right **source/metadata
  card** (the one showing source URL / creator / license / downloads) and add the button there.

## Implementation

### Backend

1. **`FileRole.source`** — add `source = "source"` to the `FileRole` enum in
   `models/file.py`. Keep it distinct from `model` (it is not a printable/mesh asset).
2. **Migration `0025`** — `ALTER TYPE filerole ADD VALUE IF NOT EXISTS 'source'`.
   - Postgres 16 allows `ADD VALUE` in a transaction as long as the value isn't *used* in the
     same migration (we don't), so a normal Alembic revision is fine; still use
     `IF NOT EXISTS`. Match the style of any prior enum-adding migration if one exists
     (grep `alembic/versions` for `ADD VALUE`).
   - **Downgrade:** Postgres cannot easily drop an enum value — make `downgrade()` a
     documented no-op (comment why). Don't attempt to remove the value.
3. **`infer_role()`** (inventory.py) — map `.scad` → `FileRole.source`. Add a
   `SOURCE_EXTENSIONS = {".scad"}` constant next to the other extension sets and branch on it
   (top-level extension check, same first-match-wins structure). **v1 = `.scad` only** (the
   role is named generically so more source types can be added later without another
   migration).
4. **`_ALLOWED_FILE_EXTENSIONS`** (routers/items/files.py) — add `.scad` so direct per-item
   upload is accepted.
5. **Sanity-check role fallout** — `.scad`/`source` must NOT be treated as a printable asset:
   confirm `routers/items/core.py` `_PRINT_ASSET_ROLES = [model, gcode]` is left unchanged
   (source excluded), and that reconcile/inventory round-trips a `source` file without
   flagging it as drift/unexpected. It should simply persist as role `source`.

### Frontend

6. **"Show SCAD" button** on the item's top-right source/metadata card, shown only when the
   item has a file with `role === 'source'` (fallback: path ends `.scad`). Use a lucide icon +
   label. Opens the modal below.
7. **Modal** (Radix dialog, matching existing modal patterns — note the createPortal fix used
   for other dialogs so a sibling card's `backdrop-filter` can't trap it):
   - On open, fetch the `.scad` text via the existing file URL (`apiFetch`, `.text()`).
     **Size-guard** using the file's `size` from item detail (skip/inline-warn above a
     sensible cap, e.g. reuse/mirror `BROWSER_PREVIEW_MAX_MB` or a smaller text cap).
   - Show it in a scrollable monospace `<pre>` (read-only). No syntax highlighter.
   - **Copy** button (navigator.clipboard.writeText; show inline "Copied" state — no toast lib).
   - **Download** button — link to the file URL with a download attribute / the download param
     the file endpoint already supports.
   - **Open in OpenSCAD Playground** button — see encoder below; `window.open(url, '_blank',
     'noopener')`.
8. **Playground deep-link encoder** (new util, e.g. `frontend/src/lib/openscadPlayground.ts`).
   Replicate the playground's own permalink format (durable + supports multi-file) — verified
   against `openscad/openscad-playground` `src/state/fragment-state.ts`
   (`encodeStateParamsAsFragment` + `compressString`) and `src/state/app-state.ts` (`State`):

   ```ts
   // State.params = { activePath: string, sources: {path, content}[], features: string[], ... }
   // fragment = base64( gzip( JSON.stringify({ params, view?, preview? }) ) ), read raw from location.hash
   export async function playgroundUrl(scadCode: string, filename: string): Promise<string> {
     const path = '/' + (filename || 'model.scad')     // leading slash per playground convention
     const state = { params: { activePath: path, sources: [{ path, content: scadCode }], features: [] } }
     const bytes = new TextEncoder().encode(JSON.stringify(state))
     const gz = new Response(new Blob([bytes]).stream().pipeThrough(new CompressionStream('gzip')))
     const buf = new Uint8Array(await gz.arrayBuffer())
     // chunk to avoid String.fromCharCode(...huge) stack overflow on large files
     let bin = ''; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000))
     return 'https://ochafik.com/openscad2#' + btoa(bin)   // base64 is valid in a URL fragment; do NOT url-encode it
   }
   ```
   - The playground decoder (`readStateFromFragment`) `atob`s + gunzips the raw hash, so pass
     the base64 **unencoded**.
   - **Documented fallback** (simpler, but the playground marks it "for testing"):
     `https://ochafik.com/openscad2#src=' + encodeURIComponent(scadCode)`. Prefer the
     compressed format above; keep this note in a code comment only.
   - **CSP note:** this is a top-level `window.open` navigation to an external origin, which our
     nginx CSP (`default-src 'self'`) does **not** block (CSP governs resource loads within our
     page, not user navigation). No CSP change needed. Do not `fetch()` or `<iframe>` the
     playground.

## Tests

- **Backend** (`backend/tests/`, `pytest -n auto`):
  - `infer_role("x.scad")` → `FileRole.source`; a `renders/x.scad` / `images/…` still follow
    the directory rules.
  - Migration `0025` applies under `alembic upgrade head` (the verify script covers this).
  - Per-item upload of a `.scad` is now accepted (previously 4xx); import-session upload +
    commit yields a stored file with role `source`.
  - `source` role is excluded from print-asset queries (`_PRINT_ASSET_ROLES`).
- **Frontend** (`vitest`):
  - The **Show SCAD** button renders only when a `source`/`.scad` file is present.
  - Modal fetches + displays the text; Copy calls the clipboard.
  - `playgroundUrl()` round-trips: gunzip+parse the produced hash and assert
    `params.sources[0].content === code` and `activePath` matches (prove the encoder is
    decodable by the playground format).

## Changelog

Add a `### Added` entry to `CHANGELOG.md [Unreleased]` **in the same commit** (per project
rules), user-facing voice, e.g.: "View an item's OpenSCAD `.scad` source in-app (Show SCAD) —
copy, download, or open it prefilled in the OpenSCAD web playground; `.scad` is now recognized
as a design-source file." Mention server-side rendering is tracked separately (FR #46).

## Verify & commit

1. `make verify` — both gates green (backend incl. the new migration + tests; frontend build +
   vitest). Fix anything red; never `--no-verify`.
2. Commit on `dev` with a `feat:` prefix, e.g.
   `feat: view OpenSCAD .scad source in-app + open in playground (source FileRole)`.
   Include the code, the migration, the tests, the docs, and this prompt file (moved to
   `prompts/done/`) in the **one** commit. Update this prompt's frontmatter
   (`status: done`, `completed:`, `result:`) and `git mv` it to `prompts/done/`.
3. The orchestrator auto-commits/pushes on `dev` (project operating model). Do NOT touch
   `main`. Record any non-obvious decision in `docs/decisions.md` (newest at top).

## Notes / gotchas

- Don't over-reach into FR #46 (rendering) or editing — v1 is view/copy/download/playground.
- Keep the extension sets in sync: `.scad` only needs to be added to `infer_role`
  (`SOURCE_EXTENSIONS`) and `_ALLOWED_FILE_EXTENSIONS`. It must **not** go into
  `MODEL_EXTENSIONS`, `MESH_EXTENSIONS`, or `MESH_ANALYSIS_EXTENSIONS` (it is not a mesh).
- The dev worker has no hot-reload, but this task adds no worker/task code, so no
  `make worker-restart` needed.
