---
name: 2026-07-20-prinnit-scraper
status: done          # pending | in-progress | done | failed
created: 2026-07-20
model: sonnet            # coding task
completed: 2026-07-20
result: >
  Implemented backend/app/storage/prinnit_client.py (pure scrape_prinnit()
  function) and wired a domain short-circuit into process_import_session
  (backend/app/worker/tasks/import_session.py) right after the Manyfold
  check. Added backend/tests/test_prinnit.py (28 tests) covering URL parsing,
  designer resolution, design lookup, full field mapping incl. the
  print-details block, image ordering/cap, graceful fall-through, and the
  worker wiring. Updated CHANGELOG.md [Unreleased], docs/architecture.md
  (new module-map row), and docs/decisions.md. make verify-backend green.
---

# Task: Add a prinnit.com metadata connector to the import scraper

Add first-class support for importing designs from **prinnit.com** (a paid 3D-model
marketplace). Today pasting a prinnit design URL into the import wizard yields a garbage
title ("ForgeCore Home") because the site is a client-rendered React SPA with no
Open Graph tags — the generic scraper only sees an empty shell. This task makes a prinnit
design URL pre-fill the wizard with the real title, description, creator, tags, gallery
images, and print details, using prinnit's **fully public (no-auth) JSON API**.

The `.3mf` file itself stays gated — the user downloads it after purchase and uploads it
in the wizard. This connector fetches **metadata + public images only**, never files.

## Context — the API is already reverse-engineered (do NOT re-derive)

The orchestrator captured the exact API shapes. Two saved fixtures (use them as the basis
for your test fixtures — copy into the repo test tree, do NOT hit the network in tests):

- `/tmp/claude-1000/-home-manderse-projects-partfolder3d/9157b636-edc0-4951-a7f1-e8cb8c9ed48c/scratchpad/fixture_designers.json`
  — the `GET /designers` response trimmed to the one designer (ForgeCore).
- `/tmp/claude-1000/-home-manderse-projects-partfolder3d/9157b636-edc0-4951-a7f1-e8cb8c9ed48c/scratchpad/fixture_design.json`
  — the full design object for the reference design.

**URL shape:** `https://prinnit.com/<DesignerName>/design/<designId>`
Example: `https://prinnit.com/ForgeCore/design/368d6R3a5jom3AZQqKxgEKF3BvC`
(`ForgeCore` = designer name, `368d6R3a5jom3AZQqKxgEKF3BvC` = designId.)

**Resolution flow (all GET, no auth, `api.prinnit.com`):**
1. `GET https://api.prinnit.com/designers` → `{"designers": [ {sub, designerName, ...}, ... ]}`.
   Find the entry whose `designerName` matches the URL's `<DesignerName>` **case-insensitively**
   (the site lowercases for lookups). Take its `sub` (a Cognito UUID).
   - Small site: this returns all designers (currently 3). Still, do not assume ordering;
     match by name. If no match → return None (fall through to generic path).
2. `GET https://api.prinnit.com/designs/<sub>` → a JSON **array** of that designer's designs
   (currently ~137 items, ~1.2 MB). Find the element whose `designId == <designId>`.
   - This is the only public per-designer endpoint; the app itself loads the whole list and
     indexes client-side. 1.2 MB fetched once per import is acceptable, but cap the response
     body defensively (reuse the scraper's existing byte-cap pattern / `guarded_fetch`).
   - There is **no** per-design public endpoint (`/design/<id>`, `/v1/...` all return AWS
     API-Gateway `403 {"message":"Missing Authentication Token"}` = route-not-found).
3. Map the matched design object → an enriched `ScrapeResult`.

**Field mapping (design object → ScrapeResult):**
- `title` → `title`
- `description` (HTML) → `description`. **Then append print details** (owner decision — see
  "Scope" below).
- `tags` (list[str]) → `raw_tags`
- creator: `<DesignerName>` from the URL → `creator_name`;
  `creator_profile_url` = `https://prinnit.com/<DesignerName>` (the store page).
  `source_site` = `prinnit.com`.
- images → `image_urls`: use `photosUrls[].original` (the full-res gallery, ordered) followed
  by `descriptionPhotosUrls[].original`. These are public `images.prinnit.com` `.webp` URLs,
  directly hotlinkable (HEAD-verified 200). De-dupe; cap at `max_images`. First gallery image
  is the default/cover.
- license: not present in the API → leave `None`.

**Scope — "basic + append print details" (owner-chosen):** after the HTML description, append
a compact, human-readable block built from these fields when present (all live on the design
object): `printTime` (**appears to be minutes** — render like "35h 17m"; note the unit
assumption in a code comment), `printDifficulty`, `weight` (grams), `minPrinterDimensions`
`{x,y,z}` (mm), `isMultiColor`/`amsRequired`, and the `filaments[]` list
(`brandName` + `productName` + `filamentType`, e.g. "Polymaker Jungle Green (PLA)"). Also
include `videoUrl` if present. Keep it clean HTML or simple text consistent with how the
description field is later rendered — check how `session.description` is displayed in the
wizard before choosing markup. Do not invent fields not in the fixture.

## Before you start

- **Read** `docs/architecture.md` (the "Scrapers / fallback backends" and "Import sessions"
  rows) and `CLAUDE.md` (verify discipline).
- **Read these files to match existing patterns:**
  - `backend/app/storage/scraper.py` — the `ScrapeResult` dataclass, `extract_domain`,
    `guarded_fetch`/SSRF usage, byte caps, `sanitize_for_log`. Your connector reuses these.
  - `backend/app/worker/tasks/import_session.py` — study `_maybe_manyfold_import` (the
    domain-matched short-circuit precedent) and the `process_import_session` scrape block
    (~lines 699-796) where `scrape_url` runs and its `ScrapeResult` flows into the shared
    downstream population code (title/desc/tags/creator/image_urls, ~lines 745-889).
  - `backend/app/models/scraper_usage.py` — record a `ScraperUsage(provider="prinnit", ...)`
    row on success/failure the way the other backends do.
  - `backend/tests/test_manyfold_import.py` and `test_flaresolverr.py` — test style (mock the
    HTTP layer; no live network).

- **Design — keep it light (this is NOT a Manyfold-scale connector):** prinnit needs no auth,
  no DB config, and downloads no files, so an enriched `ScrapeResult` that flows through the
  existing downstream code is the right shape — NOT a full session-populating connector.
  Concretely:
  1. New module `backend/app/storage/prinnit_client.py` with a pure function
     `scrape_prinnit(url, *, timeout, max_images) -> ScrapeResult | None`. Returns `None` when
     the URL isn't a prinnit design URL or the design can't be resolved (so the caller falls
     through to the normal path). Never raises — on error return a `ScrapeResult` with `note`
     set, or `None`; mirror `scrape_url`'s "never raises" contract. Route all HTTP through the
     existing SSRF-guarded fetch with byte caps.
  2. In `process_import_session`, add a **domain short-circuit** right after the Manyfold check:
     if `extract_domain(url) == "prinnit.com"`, call `scrape_prinnit(...)`; if it returns a
     non-None, non-blocked result, use it as `sr` and **skip** `scrape_url` and the fallback
     chain (like the Manyfold branch skips them). Record `ScraperUsage(provider="prinnit")`.
     Let the existing downstream code handle image_urls/tags/creator so images land as the
     normal `is_url` image rows — do not download images yourself.
     - Keep `SiteCapability` recording sane for prinnit (it will always "scrape" successfully
       via the connector). Follow the least-surprising path; if unsure, mirror what the
       Manyfold short-circuit does (it bypasses the capability probe).
  3. Add `"prinnit": "Prinnit"` to the backend-label map if a note references it; not a
     fallback backend, so do **not** add it to `_try_fallback_scrapers`' priority list.

- **Working tree check:** run `git status --porcelain`; the only expected dirty file is this
  prompt. Surface anything else before touching it.

## What to do

1. Implement `backend/app/storage/prinnit_client.py` per the design above.
2. Wire the short-circuit into `backend/app/worker/tasks/import_session.py`.
3. Add tests `backend/tests/test_prinnit.py`: URL parsing, designer→sub resolution,
   design lookup, full field mapping incl. the print-details block, image ordering/cap,
   and graceful fall-through (unknown designer, unknown designId, HTTP error) → `None`.
   Mock the HTTP layer using the saved fixtures; **no live network in tests**.
4. Update `CHANGELOG.md` `[Unreleased]` (a `feat:` entry) **in this same change** — see
   changelog convention below.
5. Add a short row/note to `docs/architecture.md` so prinnit is discoverable in the module
   map (alongside the other scraper backends / connectors).

## Conventions to honor

- **Verify before commit is mandatory.** Run `make verify-backend` (ephemeral PG + pinned
  ruff 0.8.4 + alembic + `pytest -n auto`) and get it green. No frontend changes expected, so
  `verify-frontend` is not required unless you touch FE. **Worker code changed → after any
  manual/live testing run `make worker-restart`** (not needed for the pytest gate).
- No DB migration is needed (no schema change) — do not create one.
- Match surrounding code style: `noqa: PLC0415` for function-local imports, `sanitize_for_log`
  on any URL in logs, type hints, "never raises" for the connector.
- **Changelog:** every `feat`/`fix` updates `CHANGELOG.md [Unreleased]` in the SAME commit.
- Commit prefix: `feat:`. No `Co-authored-by:` trailer.

## When done

1. Update this file's frontmatter: `status`, `completed` (2026-07-20 or the run date), `result`.
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record non-obvious decisions in `docs/decisions.md` (newest at top) — e.g. the
   enriched-ScrapeResult-vs-connector choice, the whole-designer-list fetch tradeoff, the
   `printTime`-is-minutes assumption.
4. **You are a spawned agent: do NOT commit and do NOT push.** Prepare the working tree, then
   report back to the orchestrator: the exact file list, a one-line `feat:` commit message, and
   the `make verify-backend` result (pass/fail with the test count). The orchestrator handles
   the commit + push to `dev`.
