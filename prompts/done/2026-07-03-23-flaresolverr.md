---
name: 2026-07-03-23-flaresolverr
status: completed
created: 2026-07-03
model: sonnet            # coding task
completed: 2026-07-05
result: Pluggable fallback-scraper framework implemented — FlareSolverr client, generic priority-based dispatcher, per-backend enable/priority/timeout/test-connection settings, usage tracking + retention cron + manual clear, admin UI cards, 20 new tests, all 799 backend + 366 frontend tests green.
---

# Task: Add FlareSolverr as a fallback-scraper backend (issue #23)

> ⚠️ **SCOPE EXPANDED — re-scope before dispatch.** The owner grew this from "add FlareSolverr"
> into a **pluggable scraper-backends framework** (each scraper enable/disable + prioritize +
> per-scraper timeout + usage tracking with retention/manual-clear + test-connection, and AgentQL
> retrofitted into it). **`docs/scrapers-spec.md` is now the authoritative design** — implement to
> that, not just the FlareSolverr-only steps below (which remain valid as the FlareSolverr slice).

Add [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) as a free, self-hosted
alternative/companion to the existing AgentQL Cloudflare-fallback scraper. Both backends
can be enabled at once, tried in a configurable order (default: FlareSolverr first, since
it's free). This requires introducing a real "fallback scraper backend" seam where today
`_try_agentql_fallback` is hardcoded.

## Before you start

- Read `CLAUDE.md` (operating model), `prompts/startnewsession.md`, and `standards.md`.
- Read `docs/decisions.md` (append a decision entry at the end of this task).
- Verify DB migrations on an ephemeral Postgres per the memory note
  (`docker run postgres:16-alpine` on :5433) — this task adds **no new tables/columns**
  (settings are rows in the existing `settings` table; `ScraperUsage` already has a
  `provider` column), so no Alembic migration is needed. Confirm this is still true
  before deciding.
- **Do not commit.** You are a spawned agent: prepare the tree and report the proposed
  ONE commit (files + message) back to the orchestrator. Never `git add -A`, never push.

## Context — current architecture (traced, file:line)

- **Static scraper:** `backend/app/storage/scraper.py::scrape_url()` (208-334). Sets
  `result.blocked=True` on HTTP 401/403/429/503 (263-264) — the trigger for a fallback.
- **HTML → ScrapeResult extraction is currently INLINED** inside `scrape_url` (283-328),
  using helpers `_parse_html` (135), `_og` (112), `_meta_name` (124), `_extract_images`
  (147), `_extract_tags` (169). There is **no** single "parse HTML into ScrapeResult"
  function to reuse — you must extract one (see step 1).
- **Fallback orchestration:** `backend/app/worker/tasks/import_session.py::_try_agentql_fallback()`
  (13-164), called from `process_import_session` at **line 297**. It reads settings,
  enforces budget, calls `agentql_scrape` in a thread executor, records a `ScraperUsage`
  row (`provider="agentql"`), and returns a `ScrapeResult`. On success the caller sets
  `session.scrape_note = "Fetched via AgentQL"` (311).
- **AgentQL client:** `backend/app/storage/agentql_client.py::agentql_scrape()` — POSTs
  to AgentQL, maps structured JSON to a `ScrapeResult`. Has an injectable test seam
  (`_agentql_caller`) so no network in tests. **Mirror this shape** for FlareSolverr.
- **AgentQL settings** (JSON rows in `settings` table): `agentql.enabled`,
  `agentql.api_key_enc`, `agentql.free_allowance`, `agentql.budget_mode`,
  `agentql.monthly_cap_usd`, `agentql.per_call_usd`.
- **Admin API:** `backend/app/routers/agentql.py` — `GET/PUT /api/admin/agentql`,
  `GET /api/admin/scraper-usage`. Registered in `backend/app/main.py:166`.
- **Frontend:** `frontend/src/lib/api/agentql.ts` (API client) and the `AgentQLCard`
  component in `frontend/src/pages/admin/SiteCapabilitiesPage.tsx` (line 404), rendered
  at route `/admin/ai/sites`.
- **Usage model:** `backend/app/models/scraper_usage.py` — has a `provider` string column
  already; reuse it (`provider="flaresolverr"`, `est_cost_usd=0.0`).
- **SSRF guard:** `backend/app/storage/ssrf_guard.py::assert_safe_url`. `scrape_url` runs
  it on the target URL before fetching. **Important:** the FlareSolverr `base_url` is an
  internal Docker host (e.g. `http://flaresolverr:8191`) and would be *rejected* by the
  SSRF guard — do **not** guard `base_url`. Do guard the *target* URL (see step 2).

## What to do

### 1. Refactor scraper.py to expose a reusable HTML→ScrapeResult helper

Extract the inline block in `scrape_url` (roughly lines 283-334) into a module-level
helper, e.g.:

```python
def extract_metadata_from_html(html: str, url: str, domain: str, max_images: int) -> ScrapeResult:
    """Parse resolved HTML into a ScrapeResult (title/desc/images/tags/creator/license)."""
```

- Move the title/description/source_site/images/tags/creator/license logic there.
- Have `scrape_url` call it after it fetches HTML (keep behavior identical).
- This is the exact seam FlareSolverr needs: FlareSolverr returns resolved HTML but no
  structured metadata, so it reuses this helper. Keep the extraction behavior byte-for-byte
  the same (run the existing `test_agentql.py` + any scraper tests to confirm no regression).

### 2. New client: `backend/app/storage/flaresolverr_client.py`

Model it on `agentql_client.py`:

```python
def flaresolverr_scrape(
    url: str,
    base_url: str,
    *,
    max_timeout_ms: int = 60000,
    max_images: int = 20,
) -> ScrapeResult:
    ...
```

- POST to `f"{base_url.rstrip('/')}/v1"` with body
  `{"cmd": "request.get", "url": url, "maxTimeout": max_timeout_ms}`,
  `Content-Type: application/json`.
- httpx.Client timeout must **exceed** `max_timeout_ms` (FlareSolverr blocks up to that
  long solving the challenge). Use e.g. `(max_timeout_ms / 1000) + 15` seconds.
- Response shape: top-level `{"status": "ok"|"error", "message": ..., "solution": {...}}`.
  The resolved HTML is at `solution.response` (a string); `solution.status` is the
  upstream HTTP status; `solution.url` the final URL. On `status != "ok"` or a non-2xx
  `solution.status`, return `ScrapeResult(blocked=True, note=...)`.
- On success, call `extract_metadata_from_html(html, url, domain, max_images)` from step 1
  to build the `ScrapeResult`. Set `blocked=False` when any of title/description/images
  came back; else `blocked=True` with a "still protected" note (mirror agentql lines
  177-181).
- **SSRF:** run `assert_safe_url(url)` on the *target* url at the top (so FlareSolverr
  can't be abused as an SSRF proxy); do **not** guard `base_url`. Catch
  `SSRFBlockedError` → blocked result.
- **Injectable test seam:** add `_flaresolverr_caller` mirroring agentql's `_agentql_caller`
  so tests never hit the network.
- Never raise; all errors → `blocked=True` with a clear `note` prefixed `FlareSolverr:`.

### 3. New admin settings (rows in `settings` table, JSON values)

- `flaresolverr.enabled` → bool (default `false`)
- `flaresolverr.base_url` → string (e.g. `"http://flaresolverr:8191"`; no default / empty)
- `flaresolverr.max_timeout_ms` → int (default `60000`)
- `scraper.fallback_order` → ordered list, default `["flaresolverr", "agentql"]`
  (governs which backend is tried first). See open question Q1/Q5 on UI shape.

No API key, no billing/budget settings for FlareSolverr.

### 4. Introduce the fallback-backend seam in `import_session.py`

Replace the single hardcoded `_try_agentql_fallback` call (line 297) with a dispatcher:

```python
async def _try_fallback_scrapers(url, db, scrape_max_images=20) -> ScrapeResult | None:
    # read scraper.fallback_order (default ["flaresolverr", "agentql"])
    # for each backend in order:
    #   flaresolverr -> _try_flaresolverr_fallback(...)
    #   agentql      -> _try_agentql_fallback(...)   (existing, unchanged internals)
    #   if result is not None and not result.blocked: return result
    # return the last blocked result (so its note is surfaced)
```

- Keep `_try_agentql_fallback` as-is (it becomes one backend).
- Add `_try_flaresolverr_fallback(url, db, ...)`: read `flaresolverr.enabled` /
  `.base_url` / `.max_timeout_ms`; if disabled or no base_url → return a blocked
  `ScrapeResult` with a helpful note (mirror agentql's disabled/no-key returns). Call
  `flaresolverr_scrape` in a thread executor (sync HTTP), like agentql at 139-141.
  Record a `ScraperUsage` row (`provider="flaresolverr"`, `success=not sr.blocked`,
  `est_cost_usd=0.0`) — see open question Q2.
- In `process_import_session`, set `session.scrape_note` per the backend that succeeded:
  `"Fetched via FlareSolverr"` or `"Fetched via AgentQL"`. Derive the label from the
  winning backend (e.g. have the dispatcher return `(result, backend_name)` or stamp
  `result.source_site`/a note). Keep the both-blocked path (319-334) surfacing the last
  note.

### 5. Admin API — expose FlareSolverr settings + fallback order

Add to `backend/app/routers/agentql.py` (or a small new `scraper_settings` router —
prefer extending the existing one so the admin page stays cohesive, but a new router is
acceptable if cleaner):

- `GET/PUT /api/admin/flaresolverr` returning `{enabled, base_url, max_timeout_ms}`
  (base_url is not a secret — return it plainly, unlike the AgentQL key).
- Expose `scraper.fallback_order` get/set (either on the flaresolverr endpoint payload or
  a dedicated `GET/PUT /api/admin/scraper-fallback-order`). Validate that the order list
  only contains known backend names (`flaresolverr`, `agentql`).
- Reuse `_get_setting` / `_set_setting` helpers already in that router.

### 6. Frontend admin UI

- `frontend/src/lib/api/agentql.ts` (or a new `frontend/src/lib/api/flaresolverr.ts`):
  add `getFlareSolverrSettings` / `updateFlareSolverrSettings` and (if separate) fallback
  order getters, mirroring the AgentQL client. Export via `frontend/src/lib/api/index.ts`.
- Add a `FlareSolverrCard` in `SiteCapabilitiesPage.tsx` next to `AgentQLCard` (line 404),
  reusing the same `Card`/`Field`/`AuroraInput`/`AuroraToggle`/`Button` primitives:
  enabled toggle, base_url text input, max-timeout number input, short helper copy
  ("free, self-hosted; runs your own FlareSolverr container"). Add a control for the
  fallback order (see Q5 — recommend a simple "Try FlareSolverr first / Try AgentQL
  first" two-button toggle rather than a drag list).
- **Verify the frontend with `npx vite build`** (tsc + vitest miss esbuild parse errors —
  per memory note).

### 7. Tests

Add `backend/tests/test_flaresolverr.py` mirroring `test_agentql.py`:
- Client maps a mocked FlareSolverr `solution.response` HTML into the right ScrapeResult
  (via the seam `_flaresolverr_caller`) — no network.
- Dispatcher order: FlareSolverr tried first when both enabled; falls through to AgentQL
  when FlareSolverr returns blocked; respects `scraper.fallback_order`.
- Disabled / missing base_url → blocked result with a clear note, and AgentQL still tried.
- A `scraper_usage` row with `provider="flaresolverr"` is recorded (if Q2 = yes).
- `GET/PUT /api/admin/flaresolverr` endpoints (admin-only; base_url round-trips).
- Confirm the `extract_metadata_from_html` refactor didn't regress `scrape_url`.

### 8. Docs + changelog

- `CHANGELOG.md` `[Unreleased] → ### Added`: FlareSolverr fallback backend + configurable
  fallback order (same commit — per the "changelog every commit" memory rule).
- Update any scraper/admin docs that enumerate the fallback (grep `docs/` for "AgentQL").
- Append a `docs/decisions.md` entry (newest at top) recording: the backend-seam
  abstraction, why base_url is SSRF-exempt but the target URL is guarded, the default
  order, and the Q2 usage-tracking decision.

### 9. FlareSolverr service in the dev compose file

Add a `flaresolverr` service to `docker-compose.dev.yml` (owner decision — dev compose
only for now; leave the prod `docker-compose.yml` alone and note that in `decisions.md`):

```yaml
  flaresolverr:
    image: ghcr.io/flaresolverr/flaresolverr:latest
    restart: unless-stopped
    environment:
      - LOG_LEVEL=info
```

No published ports — the worker reaches it internally at `http://flaresolverr:8191`.
Mention that URL in the admin card's helper copy / placeholder so setup is copy-paste.

### 10. Live end-to-end validation (best effort — don't block the task on it)

FlareSolverr is self-hosted, so validate for real: `docker run -d --name pf3d-flaresolverr-test
-p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest`, then exercise the client/test-connection
path against `http://localhost:8191` (a plain `request.get` of a benign page is enough; a real
Cloudflare-protected page is a bonus, but external-site behavior must not fail the task).
**Remove the container when done** (`docker rm -f pf3d-flaresolverr-test`). Record the outcome
in your report. Note for the live stack: this task edits worker files — the owner's running
worker needs `make worker-restart` after the commit lands (mention it in the report; don't
restart the owner's stack yourself).

## Conventions to honor

- Backend: pinned `ruff 0.8.4` + `backend/pyproject.toml` config must pass. Match existing
  style (sync httpx client + thread executor, `# noqa: PLC0415` on in-function imports,
  never-raise best-effort fallbacks).
- Frontend: Tailwind + CSS-var theme + Radix + lucide + TanStack Query + `apiFetch` CSRF
  only — no Mantine, no toast lib. Gate on `npx vite build`.
- Worker has no hot-reload — if you manually test, restart `python worker.py` after edits.
- Conventional-commit prefix `feat:`. No `Co-authored-by:` trailers. Doc + changelog land
  in the SAME commit as the code.

## Open questions (resolve with owner before/while implementing)

1. **Default fallback order** — FlareSolverr first, then AgentQL (assumed, since
   FlareSolverr is free)? Confirm.
2. **Usage tracking for FlareSolverr** — record `scraper_usage` rows
   (`provider="flaresolverr"`, cost $0) for the admin dashboard/observability, or skip
   entirely since there's no billing? (Plan assumes: record, cost 0.)
3. **Timeouts** — FlareSolverr `maxTimeout` default 60000ms; our httpx timeout =
   maxTimeout + 15s. Good defaults? Should max_timeout be user-configurable (plan says
   yes) or fixed?
4. **SSRF** — confirm the intended posture: `base_url` exempt (it's an internal host),
   target URL still guarded via `assert_safe_url`. Agree?
5. **Order UI shape** — simple two-button "Try X first" toggle (recommended) vs a
   reorderable list? Where does it live — on the FlareSolverr card, the AgentQL card, or
   a shared "Fallback scrapers" section header?
6. **Connection test** — add a "Test connection" button (POST a cheap request / hit
   FlareSolverr's health) to validate base_url in the UI? Nice-to-have; in scope?
7. **Endpoint layout** — extend `routers/agentql.py` (rename to `scraper_settings`?) or
   add a separate `flaresolverr` router? Plan leans toward extending for cohesion.

## Owner decisions (2026-07-05) — all open questions RESOLVED, do not re-ask

1. **Q1 order:** default `flaresolverr` first, `agentql` second (free before paid). Confirmed.
2. **Q2 usage:** record `scraper_usage` rows for every backend (`provider="flaresolverr"`,
   `est_cost_usd=0.0`). Confirmed — plus the spec's retention cron + manual clear.
3. **Q3 timeouts:** 60s default solve timeout, per-scraper `timeout_s` configurable
   (AgentQL gets one too, per the spec). Confirmed.
4. **Q4 SSRF:** target URL guarded; each scraper's own configured host exempt. Confirmed.
5. **Q5 UI shape:** **build it generic for N future backends** — a "Scrapers" admin section
   rendering one card per registry entry (enable toggle, priority, timeout, backend-specific
   fields, Test connection, usage stats + clear), exactly as `docs/scrapers-spec.md` §6
   describes. Priority = an explicit, editable order control (numeric input or up/down
   arrows — no drag-and-drop lib; keep to existing Aurora primitives). The two-button
   toggle idea is REJECTED in favor of the generic control.
6. **Q6 test connection:** yes, in scope for every backend.
7. **Q7 layout:** implementer's choice, but prefer generalizing the existing router/card
   into the scrapers framework (spec §6) over bolting on a parallel one; keep the admin
   page cohesive. `docs/scrapers-spec.md` is authoritative wherever it and the older
   steps above disagree.

## When done

1. Update this file's frontmatter: `status`, `completed`, `result`.
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record decisions in `docs/decisions.md` (newest at top).
4. **Spawned agent:** do NOT commit. Prepare the tree; report the file list + a one-line
   `feat:` message back to the orchestrator for the `y/n`. Never `git add -A`, never push.
