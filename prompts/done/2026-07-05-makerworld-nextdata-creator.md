---
name: 2026-07-05-makerworld-nextdata-creator
status: done
created: 2026-07-05
model: sonnet
completed: 2026-07-05
result: >
  Added _enrich_from_next_data helper to backend/app/storage/scraper.py.
  Called from extract_metadata_from_html after normal extraction.
  4 new tests in test_flaresolverr.py (happy path, malformed JSON, meta-wins,
  non-MakerWorld shape). CHANGELOG and decisions.md updated.
  803/803 backend tests pass.
---

# Task: Extract MakerWorld creator/title/tags from `__NEXT_DATA__` (owner test feedback)

Live testing found MakerWorld URL imports (fetched via FlareSolverr) leave the Designer
(creator) blank and keep the SEO-suffixed title. MakerWorld is a Next.js SPA: it has NO
author meta tags, no JSON-LD, and no "by <Creator>" title pattern — the data lives only
in the `<script id="__NEXT_DATA__">` JSON blob. Verified live against
`https://makerworld.com/en/models/2990447-knitted-goose`:

- `props.pageProps.design.designCreator.name` = `"Smoggy3D"` (also `.handle` = `"Smoggy3D"`;
  profile URL is `https://makerworld.com/en/@<handle>`)
- `props.pageProps.design.title` = clean model title (og:title is
  `"Knitted Goose - Free 3D Print Model - MakerWorld"` — suffixed)
- `props.pageProps.design.categories[].name` = e.g. `["Animals", "Miniatures"]` — tag
  candidates

## Before you start

- Read `CLAUDE.md`. Relevant code: `backend/app/storage/scraper.py` —
  `extract_metadata_from_html()` (the shared HTML→ScrapeResult helper all HTML-returning
  backends use: static httpx path AND FlareSolverr), `_creator_from_title` (~line 195),
  the #27 title-cleanup logic, `_extract_tags`.
- This is backend-only. **Do NOT run `make verify-frontend` and do NOT touch any
  frontend file** — another agent is concurrently working in `frontend/`. Gate on
  `make verify-backend` only.
- No Alembic migration. No new dependencies (stdlib `json` + the existing HTML parser).

## Working tree check

Run `git status --porcelain` first. **Expect unrelated dirty files under `frontend/`
and possibly `prompts/` from a concurrently running agent — ignore them completely; do
not touch, stage, or report them as a problem.** If a BACKEND file you need to edit is
dirty, stop and report back.

## What to do

1. In `extract_metadata_from_html`, add a best-effort enrichment step: if the HTML
   contains `<script id="__NEXT_DATA__" ...>`, parse its JSON (guard everything —
   malformed/huge JSON must never break the scrape; wrap in try/except, cap the blob
   size at something sane like 5 MB before parsing).
2. From the parsed blob, look for the MakerWorld shape `props.pageProps.design`:
   - `designCreator.name` → use for `creator_name` **only if** the existing meta/title
     heuristics found nothing (existing signals win; this is a fallback).
   - `designCreator.handle` → `creator_profile_url = "https://makerworld.com/en/@<handle>"`
     (same only-if-empty rule).
   - `design.title` → **prefer over** the og:title-derived title when non-empty (it's
     the clean, unsuffixed one). Run it through the existing title-cleanup anyway.
   - `design.categories[].name` → append to tags (dedupe against existing, keep the
     existing tag normalization/limits).
   Keep the structure open for other Next.js sites later: implement as a small helper
   (e.g. `_enrich_from_next_data(result, html)`) with the makerworld path lookup inside,
   not inline spaghetti in the main function.
3. Domain-gate sensibly: the `design.*` path lookup is MakerWorld's shape — it is
   inherently harmless on other sites (path simply won't exist), so a hard domain check
   is optional; prefer shape-checking over domain-checking so mirrors/regional domains
   still work.
4. **Tests** (`backend/tests/` — extend the scraper/flaresolverr test file that already
   has HTML fixtures): a minimal HTML fixture with a `__NEXT_DATA__` script containing
   the design shape → creator_name/profile_url/title/tags come out right; malformed
   JSON → scrape still succeeds with meta-only data; existing meta-author still wins
   over NEXT_DATA when both present; non-MakerWorld NEXT_DATA (different shape) → no
   effect.
5. **Changelog** `[Unreleased] → ### Fixed`: MakerWorld imports now pre-fill Designer
   (creator), clean title, and category tags via `__NEXT_DATA__` (same commit).
6. `make verify-backend` green. (Backend only — see constraint above.)

## Conventions to honor

- Match scraper.py style (best-effort, never-raise enrichment; `# noqa: PLC0415` for
  in-function imports). Pinned ruff 0.8.4 must pass.
- `fix:` prefix. Changelog same commit. No `Co-authored-by:`. Never `git add -A`.

## When done

1. Update frontmatter (`status`, `completed`, `result`).
2. `git mv` this file into `prompts/done/` or `prompts/failed/`.
3. Note in `docs/decisions.md` (newest at top): NEXT_DATA enrichment is shape-gated
   not domain-gated; existing meta signals win over embedded JSON.
4. **Spawned agent: do NOT commit or push.** Prepare the tree (backend + docs +
   changelog + prompt move ONLY — stage nothing, touch nothing under `frontend/`) and
   report back: file list, proposed `fix:` one-liner, verify-backend outcome,
   deviations. Note for the orchestrator: worker restart will be needed after commit
   (scraper runs in the worker).
