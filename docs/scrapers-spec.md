# Pluggable fallback scrapers — spec

**Status:** design (not yet implemented). Tracks [issue #23](https://github.com/crzykidd/partfolder3d/issues/23).
**Supersedes** the FlareSolverr-only plan in `prompts/2026-07-03-23-flaresolverr.md` (that prompt should
be re-scoped to this spec before dispatch).

## Goal

The Cloudflare-fallback scrape path is currently hardcoded to a single backend (AgentQL). Generalize it
into a set of **interchangeable scraper backends**, each independently **enable/disable**-able,
**prioritized**, **timeout-configurable**, **usage-tracked**, and **testable**. AgentQL and FlareSolverr
are the first two backends; adding a third later must be a small, additive change. **FlareSolverr is its
own scraper, not an AgentQL variant.**

## Current architecture (to refactor)

- `backend/app/storage/scraper.py::scrape_url()` — plain `httpx` GET (the primary path). On a blocked
  response (401/403/429/503) it sets `blocked=True`. Its HTML→metadata extraction (title/desc/images/tags)
  is **inlined** — must be pulled out into a reusable helper (see below).
- `backend/app/worker/tasks/import_session.py::_try_agentql_fallback()` — **hardcodes** the AgentQL call.
  This is the seam to replace with a backend dispatcher.
- `backend/app/storage/agentql_client.py` — AgentQL client (API key, per-call billing, `_agentql_caller`
  test seam). The shape to mirror for other backends.
- `backend/app/models/scraper_usage.py` — already has a **`provider` column** (so usage tracking is
  multi-backend-ready; no schema change needed for usage).
- Settings today: `agentql.*` JSON rows; admin API `backend/app/routers/agentql.py`; frontend
  `AgentQLCard` on `/admin/ai/sites`.

## Design

### 1. Scraper backend interface

Each backend is a module exposing a common async interface — given a URL, return a `ScrapeResult` (or
`None`/raise on failure):

```
async def scrape(url: str, *, timeout_s: float) -> ScrapeResult | None
```

- **AgentQL** — structured query; maps its response to `ScrapeResult` directly.
- **FlareSolverr** — POST `{"cmd":"request.get","url":…,"maxTimeout":…}` to `<base_url>/v1`; reads
  resolved HTML from `solution.response`, then runs the **shared HTML→metadata helper**.
- Backends that return raw HTML (FlareSolverr, plain httpx) share one extraction helper; AgentQL maps
  its structured result. **Refactor step 1:** extract `extract_metadata_from_html(html, base_url)` out of
  `scrape_url` so all HTML backends reuse it.

A small **registry** maps backend name → module. Adding a backend = new client module + one registry entry
+ its settings; the admin UI renders it generically.

### 2. Fallback dispatch

Replace `_try_agentql_fallback()` with a dispatcher: when the primary `scrape_url()` is blocked, iterate
**enabled** backends in ascending **priority** order, calling each until one succeeds. Log each attempt.

### 3. Per-scraper settings

Common knobs, one set per backend, namespaced `scraper.<name>.*` (settings key-value rows — no migration):

- `scraper.<name>.enabled` — bool. User enables/disables each scraper independently.
- `scraper.<name>.priority` — int. Order in the fallback chain (lower = tried first).
- `scraper.<name>.timeout_s` — per-scraper request timeout. **Applies to AgentQL too** (add it), not just
  FlareSolverr.
- Backend-specific config under the same namespace:
  - AgentQL: `scraper.agentql.api_key` (migrate/alias existing `agentql.*`), free-allowance tracking.
  - FlareSolverr: `scraper.flaresolverr.base_url` (no API key, no billing).

### 4. Usage tracking + retention

- **Track usage of every scraper** — each call writes a `scraper_usage` row: `provider`, timestamp, URL,
  success/failure, cost (AgentQL: per-call \$; FlareSolverr: \$0). AgentQL already tracks; extend to all.
- **Auto-clear after X days** — a retention setting (e.g. `scraper.usage_retention_days`, default 30) with
  a daily cron that hard-deletes older rows (mirror the existing **job-history-retention** cron pattern).
- **Manual clear** — an admin "Clear usage" action (per-scraper and/or all).

### 5. Test connection

- **Every scraper has a "Test connection"** action (admin button + backend endpoint):
  - AgentQL → validate the API key / quota with a cheap probe.
  - FlareSolverr → hit `<base_url>/v1` (or a health cmd) and confirm it responds.
  - Generic: the registry exposes a `test()` per backend; the UI shows pass/fail + message.

### 6. Admin UI

A **"Scrapers"** admin section (generalize the current `AgentQLCard`): one card per registered backend
with — enable toggle, priority, timeout, backend-specific fields, **Test connection** button, and usage
stats with a **Clear** action. Renders each registry entry generically so a new backend needs no bespoke UI.

## Cross-cutting

- **SSRF:** keep guarding the *target* URL; **exempt each scraper's own configured host** (e.g. the
  FlareSolverr `base_url` — an internal Docker host the SSRF guard would otherwise reject).
- **Migrations:** `scraper_usage.provider` exists; per-scraper config is settings key-value → **no schema
  change expected** (unless a dedicated scrapers table is preferred over settings rows — settings avoids a
  migration and is the recommendation).
- **Extensibility test:** the design is "done right" when adding a hypothetical third backend is: one client
  module + one registry entry + its `scraper.<name>.*` settings, with zero changes to the dispatcher, UI, or
  usage/retention code.

## Where to look (for the implementer)

- `backend/app/storage/scraper.py` (extract the metadata helper), `agentql_client.py` (interface to mirror),
  `worker/tasks/import_session.py::_try_agentql_fallback` (the dispatch seam).
- `backend/app/models/scraper_usage.py` (usage rows, `provider`), the job-retention cron (retention pattern).
- `backend/app/routers/agentql.py` + `frontend/.../SiteCapabilitiesPage.tsx` `AgentQLCard` (generalize to a
  Scrapers admin section).
