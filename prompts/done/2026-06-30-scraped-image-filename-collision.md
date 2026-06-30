---
name: 2026-06-30-scraped-image-filename-collision
status: completed
created: 2026-06-30
model: sonnet            # backend bug fix + tests
completed: 2026-06-30
result: Added _scraped_image_ext helper + rewrote image download loop to use scraped_{order:02d}{ext} filenames; 27/27 tests pass.
---

# Task: Fix scraped-image filename collision on import commit

When an import session is committed, scraped URL images are saved to disk using a
filename derived from the URL's **last path segment**. MakerWorld (and other OSS-backed
CDNs) serve every gallery image from a URL ending in the same processing directive
(e.g. `.../image/format,webp`), so **all images resolve to the same filename and
overwrite each other** — leaving one file on disk referenced by N `Image` rows. Symptom:
a model imports with (say) 9 gallery images but the gallery shows the same single image 9×.

Real-world repro confirmed: the "Dahlia" item (`private_data/data/library/ey/dahlia-eymipoa`)
has 9 sidecar image entries all pointing to `images/format,webp`, with exactly one file on disk.

## Before you start

- Read `prompts/startnewsession.md` (current state) and the project `CLAUDE.md` operating rules.
- The bug is at `backend/app/routers/import_sessions/sessions.py` in the commit handler's
  "7. Handle images" loop (around line 609-636). The offending line:
  ```python
  img_name = Path(si.path).name.split("?")[0] or f"img_{img_order}.jpg"
  ```
- **Reference the correct pattern already used for manual uploads** at
  `backend/app/routers/items.py` ~lines 1040-1063: it derives a safe extension from
  Content-Type (falling back to the URL/file suffix) and uses a **unique filename** so
  uploads never collide. Mirror that approach for scraped images.

## Working tree check

Run `git status --porcelain` first. Expect a clean tree on `dev` plus possibly this
prompt file and a running Explore agent's scratch. If any file you need to edit
(`sessions.py`, its tests) has unrelated uncommitted changes, list them and ask before
touching. This prompt file is exempt.

## What to do

1. In `backend/app/routers/import_sessions/sessions.py`, fix the scraped-image download
   so **each image gets a unique, collision-free filename**:
   - Restructure the loop so the HTTP response is available **before** choosing the
     filename, so the extension can come from the response `Content-Type`.
   - Name the file by its **order index** to guarantee uniqueness within the commit,
     e.g. `f"scraped_{img_order:02d}{ext}"`.
   - Derive `ext` from `Content-Type` first (map `image/png→.png`, `image/jpeg→.jpg`,
     `image/webp→.webp`, `image/gif→.gif`), then fall back to the URL path suffix
     (strip any `?query` first — note MakerWorld's `format,webp` segment has NO dot, so
     Content-Type is the reliable source), then fall back to `.jpg`.
   - Keep the rest of the loop intact (the `Image(...)` row, `order`, `is_default`,
     `img_order += 1`, the `except Exception` warn-and-continue). Preserve behavior on
     non-200 responses (skip, don't write).
   - Add a small module-level helper (e.g. `_scraped_image_ext(url, content_type) -> str`)
     rather than inlining, mirroring the items.py extension logic. Reuse a shared
     constant for the CT→ext map if one already exists; otherwise a local dict is fine.
2. **Do NOT change** the staged/inbox (`else:` non-URL) branch — those filenames don't collide.
3. Add test coverage:
   - Find the existing import-session commit tests (grep `tests/` for the commit endpoint /
     `is_url` image handling) and see how they mock the image fetch (httpx). Follow that pattern.
   - Add a test that commits a session with **multiple scraped URL images whose URLs share
     the same basename** (e.g. two URLs both ending `/image/format,webp` but differing
     earlier in the path) and assert: (a) each produces a **distinct file on disk**, and
     (b) the resulting `Image.path` values are **all unique**. If the existing tests don't
     already mock httpx in a way you can extend, add a focused unit test for the new
     `_scraped_image_ext` helper at minimum, plus the commit-level test if feasible.

## Conventions to honor

- Match surrounding style (the in-function `import httpx as _httpx  # noqa: PLC0415`
  lazy-import pattern is already there — keep it).
- No new dependencies.
- Backend verify discipline (REQUIRED before reporting done):
  - `ruff check backend/` with the **pinned ruff 0.8.4 + `backend/pyproject.toml`** config
    (unpinned/no-config gives FALSE UP042/F841 — do not report those as real).
  - Spin up an **ephemeral Postgres** (`docker run` `postgres:16-alpine` on `:5433`,
    user/pass/db `partfolder3d`/`testpass`/`partfolder3d`), run `alembic upgrade head`
    FIRST (conftest needs the schema), then run the import-session test module + your new
    test. Report exact pass counts.
- No migration needed (no schema change).

## Recovery note for the orchestrator (not your job to do)

The already-imported Dahlia item is corrupted on disk (1 file, 9 rows) — the code fix
does NOT retroactively repair it. The owner must delete + re-import that item after the
fix lands. Mention this back in your report.

## When done

1. Update this file's frontmatter: `status`, `completed` (2026-06-30), `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record the root-cause + fix as a one-line entry (newest at top) in `docs/decisions.md`.
4. **You are a spawned agent: do NOT commit.** Prepare the working tree and report back to
   the orchestrator: the file list, a one-line `fix:`-prefixed commit message, and your
   verify results (ruff + ephemeral-PG pass counts).
