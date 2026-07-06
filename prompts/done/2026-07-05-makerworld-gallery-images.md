---
name: 2026-07-05-makerworld-gallery-images
status: done
created: 2026-07-05
model: sonnet
completed: 2026-07-05
result: >
  Implemented MakerWorld gallery images via NEXT_DATA (design_pictures replaces
  DOM-scraped images), generic query-string dedupe by base URL, width-hint thumbnail
  filter (< 400 px), and comment-path filter. 11 new tests added (814 passed).
  Backend verify green. No deviations.
---

# Task: Clean up scraped image set — NEXT_DATA gallery for MakerWorld + generic dedupe/junk filters

Owner testing: FlareSolverr's rendered DOM makes `_extract_images` pick up near-duplicates
and junk on MakerWorld. Verified live against the whistle import
(`https://makerworld.com/en/models/2999228-...`), which stored 6 images:
- the og:image social card (`...w_1200` crop) — visually a re-encode of gallery photo #1
  (different file hash, so URL-dedupe can't catch it),
- 3 real gallery photos (`...w_1000/format,webp`),
- a `w_100` print-profile thumbnail (`/instance/...w_100...`),
- a user photo from the **comments section** (`/comment/...w_400...`).

Verified authoritative source in the same `__NEXT_DATA__` blob we already parse
(`props.pageProps.design`, see `_enrich_from_next_data` in
`backend/app/storage/scraper.py`, added earlier today):
`designExtension.design_pictures[].url` — the official ordered gallery with CLEAN
full-res base URLs (no `x-oss-process` params). `coverUrl` equals picture[0]'s base URL.

## Before you start

- Read `CLAUDE.md`. Code: `backend/app/storage/scraper.py` — `_extract_images` (~275),
  `_enrich_from_next_data` (added today; extend it), `extract_metadata_from_html`.
- Backend-only. **Do NOT touch anything under `frontend/` and do NOT run frontend
  builds/tests** — other agents are working there. Gate on `make verify-backend` only.
- Expect unrelated dirty files under `frontend/` and `prompts/` in `git status` —
  ignore them; if a backend file you need is dirty, stop and report.

## What to do

1. **MakerWorld gallery via NEXT_DATA (authoritative when present):** in
   `_enrich_from_next_data`, when `design.designExtension.design_pictures` yields ≥1
   URL, REPLACE `result.image_urls` with that ordered list (capped at `max_images`).
   Keep `coverUrl` first if it's not already picture[0]. These are base URLs without
   resize params — use them as-is.
2. **Generic hygiene in `_extract_images`** (applies to all sites, static + FlareSolverr
   paths, when NEXT_DATA doesn't provide a gallery):
   - **Dedupe by base URL ignoring the query string** (currently dedupe is exact-URL,
     so `?w_1200` vs `?w_1000` of the same file both survive). Keep the
     highest-priority occurrence (existing bucket order already encodes priority).
   - **Drop tiny variants:** parse a width hint from common resize params
     (`x-oss-process=image/resize,w_N` incl. URL-encoded form, `?w=N`, `width=N`) and
     skip candidates with width < 400 — they're thumbnails. No width hint → keep.
   - **Drop comment-section images:** skip URLs whose *path* contains `/comment/` or
     `/comments/` (path segment match, not substring of the whole URL — don't false-
     positive on a model literally named "comment"). Keep this a small, documented
     denylist; it's heuristic by nature.
3. **Tests** (extend the existing scraper/NEXT_DATA tests in
   `backend/tests/test_flaresolverr.py`): NEXT_DATA gallery replaces DOM-scraped
   images and preserves order/cap; query-string dedupe keeps one of `?w_1200`/`?w_1000`
   same-base pairs; `w_100` variant dropped; `/comment/` path dropped; no-width-hint
   URL kept; sites without NEXT_DATA keep current behavior otherwise.
4. **Changelog** `[Unreleased] → ### Fixed`: scraped image cleanup — MakerWorld official
   gallery via NEXT_DATA; size-variant dedupe; thumbnail + comment-image filtering
   (same commit).
5. `make verify-backend` green.

## Conventions to honor

- scraper.py style: best-effort, never-raise; pinned ruff 0.8.4 passes.
- `fix:` prefix. Changelog same commit. No `Co-authored-by:`. Never `git add -A`.

## When done

1. Update frontmatter; move (`mv` + note if untracked) to `prompts/done/` or
   `prompts/failed/`.
2. `docs/decisions.md` entry (newest at top): NEXT_DATA gallery is authoritative when
   present; width/comment filters are heuristic and generic; og:image visual-dupe can
   only be fixed via the authoritative gallery (hash differs).
3. **Spawned agent: do NOT commit or push; stage nothing.** Report: file list, proposed
   `fix:` one-liner, verify-backend outcome, deviations. Remind the orchestrator that
   the worker needs a restart after commit.
