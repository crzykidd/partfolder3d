---
name: 2026-07-26-view-pdf-inline
status: done          # pending | in-progress | done | failed
created: 2026-07-26
model: sonnet             # coding task
completed: 2026-07-26
result: Added opt-in `inline=true` (PDF-only, extension + %PDF- magic-number gated) to
  `download_file` + a "View PDF" iframe modal in DownloadsPanel.tsx. Backend/frontend
  checks (ruff, tsc, npm run build, full vitest suite) all clean; backend pytest left
  to the orchestrator per the shared ephemeral-PG rule.
---

# Task: View PDF files in-app without downloading first

Let a user open a catalog item's `.pdf` file **inline in the app** (browser-native PDF
viewer in a modal + open-in-new-tab) instead of being forced to download it. PDFs are
common for printed instructions/assembly guides. Browsers render `application/pdf`
natively — **no PDF.js or any new library**. This is "approach B": serve the bytes with
an inline disposition (PDF-only, safely) and add a View affordance in the UI.

## Before you start

- **Read `prompts/startnewsession.md`, `CLAUDE.md`, and `docs/architecture.md`.** The
  close precedents to mirror: the `.scad` **"Show SCAD"** modal and DownloadsPanel's
  **"View in 3D"** button (both in `frontend/src/pages/item/`).
- **Match the existing stack:** Tailwind + CSS-var theme + minimal Radix + lucide +
  TanStack Query + `apiFetch` (CSRF). **No new dependency** — the browser renders PDF.
- **DO NOT run the full `make verify` / backend `pytest` gate.** The shared ephemeral test
  PG (`pf3d-pg-v` on :5433) is a single instance — a second concurrent pytest run corrupts
  it. The ORCHESTRATOR runs the authoritative gate. Your local checks are limited to fast,
  DB-free ones: **`ruff` (pinned 0.8.4 + `backend/pyproject.toml`) on changed files** and
  **`tsc`/`npm run build`** for the frontend. **Never background a long check and exit.**
- **No migration, no worker, no Docker change** are expected. Detect PDFs by the `.pdf`
  extension — do **not** add a new `FileRole` (avoid a migration). If you find a compelling
  reason a role is needed, STOP and flag it rather than adding one.

## Working tree check

Run `git status --porcelain` and cross-reference the files below. If any have uncommitted
changes, list them and ask before touching. Surface unrelated dirty files once; they don't
block. This prompt file is exempt.

## What to do

### Backend — `backend/app/routers/downloads.py`
1. The single-file serve route is `download_file` (`GET /{key}/files/{path:path}`). It
   currently forces a save: `FileResponse(..., filename=requested.name,
   media_type="application/octet-stream")` → `Content-Disposition: attachment`.
2. Add an opt-in **`inline: bool = False`** query parameter. When `inline=true` **AND** the
   resolved file is a **PDF** (extension `.pdf` and/or magic-byte `%PDF-` sniff — reuse the
   sniffing style from `routers/import_sessions/sessions.py` `sniff_image_ext` if it fits):
   - serve with `media_type="application/pdf"`,
   - `Content-Disposition: inline` (NOT attachment — do not pass `filename=` in a way that
     forces attachment; set the header explicitly if needed),
   - add header **`X-Content-Type-Options: nosniff`**.
3. **Security — load-bearing, do not widen:** inline is allowed **only** for PDFs. For any
   other type, or when `inline` is false/absent, keep the **existing**
   `attachment` + `application/octet-stream` behavior exactly. Serving arbitrary
   user-uploaded files inline **same-origin** is an XSS vector (an uploaded `.html`/`.svg`
   would run script in the app origin and could exfiltrate the session cookie). If
   `inline=true` is requested for a non-PDF, ignore the inline request and fall back to the
   safe attachment response (don't error — just don't serve it inline). Keep the existing
   path-traversal containment barrier (`is_relative_to(item_dir)`) intact.
4. Tests (in the existing downloads test module): inline PDF → `application/pdf` + `inline`
   disposition + `nosniff`; inline requested on a non-PDF → still `attachment`/octet-stream;
   default (no `inline`) unchanged; auth still required; path traversal still refused.

### Frontend — `frontend/src/pages/item/DownloadsPanel.tsx`
5. For a file whose path ends in `.pdf` (case-insensitive), add a **"View PDF"** button
   next to the existing per-file actions (mirror the **View in 3D** button's placement and
   styling; lucide icon e.g. `FileText`/`Eye`). Opening it shows a **modal** containing an
   `<iframe src="/api/items/{itemKey}/files/{file.path}?inline=1" title="...">` sized to a
   large viewport (mirror the Show SCAD / model-viewer modal chrome: Escape to close,
   backdrop, `createPortal(..., document.body)` per the v0.7.2 modal-portal fix so a
   sibling card's `backdrop-filter` can't trap z-index).
   - The `<iframe>` src is a same-origin URL; the **session cookie authenticates it
     automatically** (no `apiFetch`/blob needed for the embed). Verify this works; if the
     browser blocks it, fall back to the blob-object-URL approach (`apiFetch` → blob →
     `URL.createObjectURL`) — note which you used.
   - Include an **"Open in new tab"** link (same `?inline=1` URL, `target="_blank"
     rel="noopener"`) and keep the existing **Download** action as the fallback.
6. Add vitest coverage: the View PDF button appears only for `.pdf` files, opens the modal,
   and the iframe points at the `?inline=1` URL. Follow existing DownloadsPanel test
   patterns.

## Conventions to honor

- Conventional-commit `feat:` prefix; **no `Co-authored-by:` trailer**.
- **Update `CHANGELOG.md` `[Unreleased]` in the SAME change.**
- Doc updates ship with the code: note the new inline-serving behavior + the PDF-only
  safety constraint in `docs/architecture.md` (downloads row) and a `docs/decisions.md`
  entry (why PDF-only inline; the XSS rationale for not widening it).

## When done

1. Set this file's frontmatter: `status: done` (or `failed`), `completed: 2026-07-26`,
   `result:` one line.
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record the non-obvious decision (PDF-only inline allowlist + XSS rationale; iframe-src
   vs blob approach) in `docs/decisions.md`, newest at top.
4. **You are a spawned agent: do NOT commit, do NOT push, and do NOT run the full test
   gate.** Run only ruff (changed files) + `tsc`/`npm run build`, prepare the working tree,
   move the prompt, and **report back**: exact file list, a proposed one-line `feat:`
   message, ruff/tsc result, whether you used the iframe-src or blob approach (and why),
   and anything the owner should test manually. **The orchestrator runs the authoritative
   `make verify`, then commits + pushes on `dev`.**
