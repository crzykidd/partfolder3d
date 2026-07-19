---
name: 2026-07-17-manyfold-2-connector
status: done             # pending | in-progress | done | failed
created: 2026-07-17
model: sonnet
completed: 2026-07-17
result: Manyfold connector — worker short-circuits scrape on a matched instance, fetches model via OAuth, downloads all images + 3D files into wizard staging (selected flag, migration 0024, commit skips deselected); SSRF-reguarded redirect downloads. make verify-backend green (845 passed).
---

# Task: Manyfold connector — Part 2: API client + worker import path + asset download

Make pasting a Manyfold model URL into the import wizard pull that model's metadata,
images, and 3D files down into the import session — using the OAuth credentials stored by
**Part 1** (`ManyfoldInstance`). This is **Part 2 of 3**. Part 1 (config model + admin API
+ token helper) is already merged; Part 3 (frontend) is separate. Stay in scope.

## Context you need (read first)

- **Part 1 output**: `backend/app/models/manyfold.py` (`ManyfoldInstance`:
  `base_url`, `domain`, `client_id`, `client_secret_enc`, `scopes`, `enabled`),
  `backend/app/storage/manyfold_client.py` (has `get_access_token(...)` + a
  `_manyfold_token_caller` seam). You EXTEND this client here.
- `backend/app/worker/tasks/import_session.py` — the import worker. Key spots:
  `process_import_session` (~330-641) calls `scrape_url` (~424-432), then the fallback
  chain `_try_fallback_scrapers` (~278-327); it records `SiteCapability`, reconciles tags
  (`reconcile_tags`), creates `ImportSessionImage` rows for scraped image URLs (~598-610),
  sets `pending_wizard`. You add a Manyfold branch **before** `scrape_url` that short-
  circuits this whole path when the URL's domain matches an enabled instance.
- `backend/app/routers/import_sessions/commit.py` — `_commit_session_inner` (~78-386):
  moves staged `ImportSessionFile`s into the item dir (~119-141), image step (~218-336)
  downloads `is_url` images / copies local ones and creates `Image` rows. You (a) make it
  skip **unselected** files and (b) confirm Manyfold's locally-staged images commit
  correctly (see step 6).
- `backend/app/models/import_session.py` — `ImportSessionFile` (`staged_path`,
  `original_name`, `role`, `size` — you ADD `selected`), `ImportSessionImage`
  (`path`, `is_url`, `source`, `order`, `is_default`), and `ImportSession`
  (`title`, `tag_state`, `default_image_path`, `creator_id`, …). Check whether it has a
  license field; if not, do not invent one — put the SPDX id in `scrape_note` or skip.
- `backend/app/storage/scraper.py` — `ScrapeResult` and how the static path populates the
  session, for parity of which fields land where.
- `backend/app/routers/import_sessions/helpers.py` — `_ensure_creator`,
  `reconcile_tags`, `extract_domain`. Reuse these; do not reimplement.
- `backend/app/storage/ssrf_guard.py` — `assert_safe_url`, `guarded_fetch`,
  `sanitize_for_log`. Used for the download SSRF re-guard.
- `backend/app/models/scraper_usage.py` — record a `ScraperUsage(provider="manyfold", …)`
  row on a Manyfold import (the `provider` column is already multi-backend).
- Staging: find how an **upload** session's staging directory is created/rooted (grep
  `staging` in the import routers/worker). Manyfold downloads go into that same per-session
  staging area so commit moves them like any uploaded file.
- Tests: `backend/tests/test_flaresolverr.py` (seam-mock pattern),
  `backend/tests/test_phase5_import.py` / `test_bulk_import.py` (import worker + commit
  patterns). Model your new `test_manyfold_import.py` on these.
- **Verify discipline**: `CLAUDE.md`. Backend gate `make verify-backend`. **Worker has NO
  hot-reload** — irrelevant to the gate (tests import the task directly) but note it in any
  live-run instructions.

## Manyfold API facts (authoritative — from the real source)

- **Auth**: reuse Part 1's `get_access_token(base_url, client_id, client_secret,
  scopes="public read")`. Cache the token in-process keyed by instance (2h `expires_in`);
  refetch on expiry or 401.
- **Model fetch**: `GET {base_url}/models/{model_id}` with headers
  `Authorization: Bearer <tok>` **and** `Accept: application/vnd.manyfold.v0+json` (without
  the Accept header you get HTML). `model_id` is the slug in the URL, e.g.
  `https://host/models/4jlf2g117t4p` → `4jlf2g117t4p`. Returns JSON-LD (schema.org):
  `name` (title), `caption`, `description` (long notes), `keywords` (**array of tag
  strings**), `spdx:license` (`{licenseId: "CC-BY-4.0", ...}`; may be absent), `sensitive`
  (bool NSFW), `creator` (**ref only** `{"@id": creatorUrl}`), `isPartOf` (collection
  refs), `links` (`[{url,text}]`), `preview_file` (ref to the preview image file),
  `hasPart` (**array of ALL files** incl. images: each `{"@id","@type":"3DModel","name",
  "encodingFormat"}`).
- **File detail**: `hasPart` entries carry no download URL — GET each entry's `@id` with
  the JSON Accept header → `{filename, encodingFormat, contentUrl, contentSize,
  previewable, ...}`. `contentUrl` is the binary download URL.
- **Classify** each file by `encodingFormat`: starts with `image/` → image; otherwise a
  3D asset (`model/stl`, `model/3mf`, `model/step`, `application/*`, etc.).
- **Binary download**: `GET {contentUrl}` with `Authorization: Bearer <tok>` and **NO**
  manyfold Accept header (the path extension selects the format). **May 302-redirect to an
  object-storage URL on another host** — your client must follow cross-host redirects. Add
  `?download=true` to force attachment disposition. Local-storage instances stream bytes
  directly with no redirect.
- **Creator**: resolve `creator.@id` with a GET (JSON Accept) to get `{name, slug,
  caption, description, links}` for the real creator name/profile. Best-effort — if it
  fails, fall back to no creator.
- **Version**: API is `v0`, "subject to breaking changes"; build defensively (tolerate
  missing keys). OAuth requires a recent Manyfold (~v0.107.0+).

## Working tree check

Run `git status --porcelain`. Only this prompt should be dirty. If a file you plan to edit
has uncommitted changes, list it and stop.

## What to do

1. **Extend `manyfold_client.py`** (map-not-copy the flaresolverr client shape; keep the
   `_manyfold_*` test seam(s)):
   - `parse_model_id(url) -> str | None` — pull the slug from `.../models/{id}` (tolerate
     trailing path/query).
   - `fetch_model(base_url, model_id, token, *, timeout_s) -> ManyfoldModel` — GET the
     model JSON; return a dataclass: `title, caption, description, tags: list[str],
     license_id: str | None, creator_name, creator_profile_url, links, sensitive: bool,
     preview_file_id, files: list[ManyfoldFile]`. Each `ManyfoldFile`: `id, name, filename,
     encoding_format, content_url, content_size, is_image`. Populate `content_url`/`size`
     by fetching each file's detail JSON.
   - `download_file(url, token, dest_path, *, max_bytes, timeout_s)` — stream to
     `dest_path`; **follow redirects, and on each redirect hop run
     `assert_safe_url(target)`** so a redirect to a private/internal host is refused
     (prevents SSRF); allow the configured instance host itself. Enforce `max_bytes`
     (reuse the image/file size caps the codebase already defines). Use `sanitize_for_log`
     in any logging.
   - `resolve_creator(base_url, creator_id, token)` best-effort helper.
   - Put HTTP behind seam(s) for tests (a callable the test monkeypatches, like
     `_manyfold_token_caller`).
2. **Migration `0024`** — `backend/alembic/versions/0024_import_session_file_selected.py`
   (down_revision = `0023`). Add `selected` boolean to `import_session_files`, NOT NULL,
   `server_default=true`. **Use exactly `0024`** (assigned number).
3. **`ImportSessionFile.selected`** column in the model (default True).
4. **Worker branch** — in `process_import_session`, BEFORE `scrape_url`, add
   `_maybe_manyfold_import(session, url, db) -> bool`:
   - `extract_domain(url)` → look up an **enabled** `ManyfoldInstance` by `domain`. No
     match → return False (fall through to the normal scrape path — unchanged).
   - `parse_model_id(url)`; if the domain matches a Manyfold instance but the URL isn't a
     `/models/{id}` page, set a clear `scrape_note` ("Manyfold instance recognized but this
     isn't a model URL") and still return True (don't fall through to a doomed scrape) —
     OR return False with that note; pick the least-surprising behavior and record it in
     `docs/decisions.md`.
   - Decrypt the secret (`app.crypto.decrypt`), get a token (cached), `fetch_model`.
   - Populate the session the SAME way the static-scrape path does: `title`, description,
     creator (via `_ensure_creator` with `source_site=domain`), `default_image_path`.
     `reconcile_tags(tags)` → `session.tag_state` (so **all** Manyfold tags land in the
     wizard's tag picker). SPDX license → wherever the scrape path stores license (or
     `scrape_note` if there's no field).
   - Ensure the session's staging dir exists; **download every image** into it →
     `ImportSessionImage(is_url=False, source="scrape", path=<abs staged>, order=…,
     is_default=<matches preview_file>)`. **Download every 3D file** into it →
     `ImportSessionFile(staged_path=<abs>, original_name=filename, role="model",
     size=content_size, selected=True)`.
   - `ScraperUsage(provider="manyfold", source_url=url, success=True/…)`.
   - `scrape_note` = human summary ("Imported N files + M images via Manyfold").
   - Set `pending_wizard`. **Return True and skip `scrape_url` + the fallback chain
     entirely.**
   - On any Manyfold error (auth/network/parse): set `error`/`scrape_note` with a clear
     reason (sanitized), record a failed `ScraperUsage`, and DO fall through to the normal
     scrape only if that makes sense — otherwise leave the session in a clear failed/manual
     state. Record the choice in `docs/decisions.md`.
5. **File-selection API** — in `backend/app/routers/import_sessions/`:
   - Ensure the session detail response includes its `files` (staged files) with
     `id, original_name, role, size, selected`. If the existing schema omits files, add
     them.
   - Add an endpoint to toggle selection, e.g. `PATCH
     /api/import-sessions/{id}/files/{file_id}` `{selected: bool}` (or a bulk variant).
     Auth/ownership guarded like the other session endpoints.
6. **Commit** — in `_commit_session_inner`: **skip `ImportSessionFile` rows with
   `selected=False`** when moving staged files into the item (leave their bytes in staging;
   don't move them). Confirm Manyfold's locally-staged images (`is_url=False`,
   `source="scrape"`) are committed correctly by the existing image step and produce
   `Image(source=scraped)`; if the current code only downloads `is_url=True` scrape images
   and doesn't copy local `source="scrape"` ones, extend it minimally so local Manyfold
   images commit. Re-run the item file inventory as the existing code does.
7. **Tests** — `backend/tests/test_manyfold_import.py`:
   - Monkeypatch the client seam(s) to return a canned model (2 images + 2 files, one
     `presupported` duplicate) with no real HTTP.
   - Assert: domain match routes to the Manyfold path and **`scrape_url` is NOT called**;
     title/description/creator set; **all tags** land in `tag_state`; images staged as
     local `ImportSessionImage`; files staged as `ImportSessionFile` with `selected=True`;
     a `ScraperUsage(provider="manyfold")` row written; `pending_wizard`.
   - Deselecting a file (PATCH) then committing → that file is NOT in the item; selected
     files + images ARE. Non-Manyfold domains still take the normal path (regression).
   - Redirect SSRF guard: a download that 302s to a private host is refused.
   - Keep `pytest -n auto` green.

## Conventions to honor

- Map-not-copy; match surrounding style. Reuse `_ensure_creator`, `reconcile_tags`,
  `extract_domain`, the SSRF guard, and the existing size-cap constants — don't reinvent.
- **CHANGELOG.md `[Unreleased]`** entry in THIS commit (Added: "Import a model directly
  from a configured Manyfold instance — pulls metadata, tags, images, and 3D files into
  the wizard").
- **docs/architecture.md**: update the import/scraper rows to note the Manyfold primary
  path + the `selected` staged-file flag.
- **docs/decisions.md** (newest first): record the non-obvious calls — Manyfold as a
  *primary* path that bypasses the scrape/fallback chain; redirect SSRF re-guard (and the
  private-object-storage caveat); the not-a-model-URL behavior; the download-during-
  processing choice.
- **Do NOT put real credentials anywhere.** Tests use mocked seams only. Live validation
  against the owner's real instance is done separately by the orchestrator.

## When done

1. Run **`make verify-backend`** to green (ephemeral PG, ruff, alembic `upgrade head` with
   BOTH new migrations, pytest -n auto).
2. Update this file's frontmatter + `git mv` into `prompts/done/` (or `prompts/failed/`).
3. **Spawned agent: do NOT commit or push.** Report back: files changed, a proposed
   `feat:` one-liner, the verify result, and any decisions/deviations.
