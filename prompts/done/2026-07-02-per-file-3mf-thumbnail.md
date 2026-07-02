---
name: 2026-07-02-per-file-3mf-thumbnail
status: done
created: 2026-07-02
model: sonnet
completed: 2026-07-01
result: >
  _reconcile_embedded_thumbnail now returns str|None (the item-relative path).
  analyze_item injects thumbnail_path into object_analysis for both sliced and
  unsliced 3MF paths; cached analyses are backfilled on next run.
  FileObjectAnalysis TS interface gets thumbnail_path?: string | null.
  ThreeMfPanel drops embeddedThumbnail prop, reads analysis.thumbnail_path directly.
  DownloadsPanel removes firstEmbeddedImage threading and images prop.
  3 new backend tests (all pass). Frontend tsc/vitest/vite build all clean.
---

# Task: Associate each 3MF's embedded thumbnail with its own File and show it per-file

Today the embedded 3MF thumbnail is extracted and saved as an **item-level** Image
(`ImageSource.embedded`) with no link back to the specific `.3mf` File it came from. The UI
(Phase C) therefore shows the *first* embedded image for every 3MF panel — wrong when an item
has 2+ 3MFs. Make each 3MF file carry a reference to its OWN embedded thumbnail and render it
as that file's thumbnail in the file tree and the 3MF collapsible panel.

## Before you start

- Read `docs/decisions.md` top entries (2026-07-02 render-backend fix, 2026-07-01 rework) and
  `prompts/startnewsession.md` (verify discipline; render-backend gotcha).
- Key current code:
  - `backend/app/worker/tasks/analysis.py` — `analyze_item` + `_reconcile_embedded_thumbnail`
    (writes `<item_dir>/thumbs/embedded/<sha256-of-png>.png` and creates the Image row). The 3MF
    branch calls it best-effort at ~lines 300-310; the analysis result dict is stored into
    `File.object_analysis` at ~line 335. `_build_sliced_analysis` (sliced) and `analyze_file`
    (unsliced) build that dict.
  - `backend/app/worker/threemf.py` — `read_3mf` returns `thumbnail_bytes` (+ which entry).
  - `backend/app/routers/items.py` — `FileOut` / `FileObjectAnalysis` schema.
  - `frontend/src/lib/api/items.ts` — `FileObjectAnalysis` TS interface + `fileDownloadUrl`.
  - `frontend/src/pages/item/ThreeMfPanel.tsx`, `DownloadsPanel.tsx`, `file-tree.ts` — the UI.
- **Frontend stack:** Tailwind + CSS-var theme + Radix + lucide + TanStack Query; `apiFetch`
  wrappers; NO Mantine, NO toast lib. Keep new deps at zero.

## Working tree check

`git status --porcelain`; cross-reference the files below; ask before touching anything already
dirty. Untracked sibling prompts are unrelated — ignore.

## What to do

1. **Backend — record the per-file thumbnail path.** Have `_reconcile_embedded_thumbnail`
   return the thumbnail's item-relative path (e.g. `thumbs/embedded/<sha>.png`). In the 3MF
   branch of `analyze_item`, capture that path and put it into the analysis result dict as
   `thumbnail_path` BEFORE it's written to `File.object_analysis` — for BOTH the sliced
   (`_build_sliced_analysis`) and unsliced (`analyze_file`) result paths. Keep it best-effort:
   if the thumbnail step fails, `thumbnail_path` is simply absent (null). Make the field
   generic (a plain relative path) so STL/OBJ renders could populate it later.
   - Note the cached-analysis path (~lines 280-292) also reconciles the thumbnail — make sure a
     cached 3MF still ends up with `thumbnail_path` set (re-run the association, or don't skip
     when `thumbnail_path` is missing from an otherwise-cached result).
2. **API.** Add `thumbnail_path: str | None` to the `FileObjectAnalysis` schema in
   `routers/items.py` (and confirm it serializes through `FileOut`). Mirror it in the frontend
   `FileObjectAnalysis` TS interface.
3. **Frontend — show it per file.** In the 3MF panel and the file-tree row for a `.3mf` (and
   any file whose `object_analysis.thumbnail_path` is set), render a small `<img>` using
   `fileDownloadUrl(itemKey, object_analysis.thumbnail_path)` as that file's thumbnail. Remove
   the Phase-C "first embedded image" best-effort fallback so panels no longer share one image.
   Graceful when `thumbnail_path` is null (no image / neutral placeholder).
4. Leave the item-level default-image priority chain unchanged (curated still outranks embedded).
   This task is about per-file display, not the item card.

## Conventions to honor

- **Changelog:** add an `[Unreleased]` entry (Added/Fixed: per-file 3MF thumbnails).
- **Verify:** backend `ruff check backend/` + pytest on the ephemeral PG at
  `postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d` (run `alembic upgrade
  head` first; the full suite ~18 min — let it finish). Add/extend a test that a 3MF File's
  `object_analysis.thumbnail_path` is populated. Frontend: `tsc` + `vitest` + **`npx vite
  build`**. No new migration expected (object_analysis is JSONB).

## When done

1. Frontmatter (`status`/`completed`/`result`), then `git mv` into `prompts/done/` or
   `prompts/failed/`.
2. Record non-obvious decisions in `docs/decisions.md`.
3. **Spawned agent: do NOT commit/push.** Prepare the tree, verify, and report back the paths to
   stage, a one-line conventional-commit message, and verification results. Orchestrator
   auto-commits on `dev`. Never `git add -A`.
