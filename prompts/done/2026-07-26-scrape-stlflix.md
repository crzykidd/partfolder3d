---
name: 2026-07-26-scrape-stlflix
status: done          # pending | in-progress | done | failed
created: 2026-07-26
model: sonnet             # coding task
completed: 2026-07-26
result: Added host-gated (domain endswith stlflix.com) Strapi __NEXT_DATA__ enrichment to scraper.py (_enrich_from_next_data_stlflix); title/description/gallery/tags/creator populate correctly; 5 new tests added to test_flaresolverr.py; CHANGELOG/docs deferred to orchestrator per concurrent-agent override.
---

# Task: Scrape stlflix.com product pages (extract from Next.js `__NEXT_DATA__`)

Importing a `platform.stlflix.com/product/<slug>` URL currently grabs only the **generic
site header** (`STLFLIX - The Ultimate STL Subscription`) instead of the actual product.
Fix the scraper to extract the real product metadata. **Backend-only**, contained to the
scraper.

## Root cause (already diagnosed — do not re-investigate the network)

stlflix is a **Next.js** site. The real product data is embedded in the page's
`<script id="__NEXT_DATA__" type="application/json">` blob, at **`props.pageProps`
directly** (NOT nested under a `design` key). The scraper's existing
`_enrich_from_next_data` (`backend/app/storage/scraper.py`) is **MakerWorld-shaped** — it
only reads `props.pageProps.design.*` and silently returns for any other shape — so it
skips stlflix entirely, and the scrape falls back to the site-wide generic
`og:title`/`og:description`.

**The base fetch already works** — the repo's `httpx` client follows the site's one
`NEXT_LOCALE` 307 redirect and gets the full 200 HTML with `__NEXT_DATA__` (verified:
`httpx.get(url, follow_redirects=True)` → 200, 189 KB, contains the product). **No cookie,
redirect, FlareSolverr, or AgentQL work is needed.** This is purely a data-extraction
mapping.

stlflix's `props.pageProps` is a **Strapi** shape — single relations are
`field.data.attributes.<x>`; collections are `field.data[].attributes.<x>`. Field map
(confirmed against `platform.stlflix.com/product/lion-rest`):

| Scrape field | `pageProps` path |
|---|---|
| title | `name` (a plain string, e.g. `"Lion Rest"`) |
| description | `description` (HTML — run through the scraper's existing description/text cleaner; strip tags) |
| images (ordered) | `gallery.data[].attributes.url`; prepend `thumbnail.data.attributes.url` (cover) if it differs; `hover.data.attributes.url` optional. URLs are clean absolute S3 URLs. `stl_preview.data` may be null. |
| tags | union of: `keywords` (a comma-separated **string** → split on `,`, trim), `tags.data[].attributes.name`, `sub_categories.data[].attributes.name`, `parent_categories.data[].attributes.name` (dedupe, cap consistent with existing tag handling) |
| creator | No per-model designer field (`collab.data` is null; `drop` is a release group, not a person). Decide: default `creator_name = "STLFLIX"`, or leave empty. Pick one, keep it simple, and note it. |
| source_site | stlflix / stlflix.com, consistent with how other sites set it |

## Before you start

- **Read `prompts/startnewsession.md`, `CLAUDE.md`, and `docs/architecture.md`.** Study the
  existing `_enrich_from_next_data` (MakerWorld) in `backend/app/storage/scraper.py` and how
  the scrape result fields (`title`, `description`, `image_urls`, `raw_tags`,
  `creator_name`, etc. — match the real `ScrapeResult` field names) are populated and how
  images/tags are deduped/capped elsewhere in that file — mirror those conventions.
- **DO NOT run the full `make verify` / backend `pytest` gate** (shared ephemeral test PG
  corruption risk). Local check: **`ruff` (pinned 0.8.4 + `backend/pyproject.toml`) on
  changed files** only. **Never background a check and exit.** No migration, no frontend.
- A saved sample of the real page HTML is available at
  `/tmp/claude-1000/-home-manderse-projects-partfolder3d/b9c92c20-cfc3-4786-95f3-060a381da0e8/scratchpad/stlflix.html`
  — use it to build a **trimmed** test fixture (do NOT commit the full 189 KB file; extract
  a minimal `__NEXT_DATA__` with representative name/description/gallery/tags/categories).

## What to do

1. **Add stlflix `__NEXT_DATA__` extraction** in `scraper.py`. Prefer a dedicated
   **host-gated** path (hostname endswith `stlflix.com`) rather than widening the
   MakerWorld shape-gated helper — the Strapi `.data.attributes` shape could false-positive
   on unrelated Next.js sites. A small helper to unwrap `x.data.attributes` (single) and
   `x.data[].attributes` (collection) will keep it clean. Populate title/description/
   images/tags/creator per the field map above. Follow the existing rule that NEXT_DATA
   product data **replaces** the generic og-derived title/description and the gallery
   **replaces** DOM-scraped images.
2. Ensure it's wired into the normal scrape flow so importing an stlflix product URL routes
   through it (mirror how MakerWorld enrichment is invoked at the end of the main scrape;
   check whether a host/priority registration is needed like other backends).
3. **Tests** (backend, follow existing scraper test patterns): given the trimmed stlflix
   `__NEXT_DATA__` fixture HTML, assert the scrape yields title `"Lion Rest"`, a non-generic
   description (tags stripped), the gallery image URLs in order, and the expected tags
   (from keywords + tags + sub/parent categories). Include a guard test that the MakerWorld
   path is unaffected (no regression) and that a non-stlflix page doesn't hit the stlflix
   branch.

## Conventions to honor

- Conventional-commit `feat:` prefix (new site support); **no `Co-authored-by:` trailer**.
- **Update `CHANGELOG.md` `[Unreleased]` in the SAME change**, and add an
  `docs/architecture.md`/`docs/decisions.md` note if the scraper's site-support list lives
  there. (If another agent is concurrently editing CHANGELOG/docs, the orchestrating prompt
  dispatch will tell you to skip them and report the text instead — otherwise include them.)

## When done

1. Set this file's frontmatter: `status`, `completed: 2026-07-26`, `result:` one line.
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record the creator-default decision + the host-gated-vs-shape-gated choice in
   `docs/decisions.md`.
4. **You are a spawned agent: do NOT commit, do NOT push, do NOT run the full gate.** Run
   ruff on changed files, prepare the tree, move the prompt, and **report back**: exact file
   list, a proposed one-line `feat:` message, ruff result, the creator default chosen, and
   what to test live (import `https://platform.stlflix.com/product/lion-rest` and confirm
   title/description/images/tags populate). **The orchestrator runs the authoritative
   `make verify-backend`, then commits + pushes on `dev`.**
