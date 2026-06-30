---
name: 2026-06-29-feat-agentql-fallback-scraper
status: done
created: 2026-06-29
model: sonnet
completed: 2026-06-29
result: >
  Implemented optional AgentQL BYO-key REST fallback scraper (Phase 18).
  Migration 0018: scraper_usage table + scrape_note on import_sessions.
  AgentQL client (agentql_client.py) with injectable mock seam.
  Admin router (agentql.py): GET/PUT /api/admin/agentql + GET /api/admin/scraper-usage.
  Worker fallback wired in process_import_session (blocked → check budget → call agentql → record usage).
  Frontend: AgentQL card in SiteCapabilitiesPage + scrape_note banner in ImportWizardPage.
  All checks pass: ruff clean, alembic 0018 applied, 14 new tests + full suite passing, tsc clean, vitest 214 pass, vite build success.
---

# Task: Optional AgentQL fallback scraper (for Cloudflare-gated sites like MakerWorld) with local budget control

The built-in static scraper can't fetch Cloudflare-gated sites (MakerWorld returns a 403 "Just a
moment" JS challenge — verified). Add an **optional, admin-enabled, BYO-key** AgentQL fallback that
kicks in **only when the built-in scraper is blocked**, with **local usage/budget tracking** (AgentQL's
API exposes no usage/quota — verified — so we track our own calls). Off by default.

## Confirmed design
- AgentQL is invoked **only as a fallback** when the static scraper returns blocked/403/Cloudflare —
  never for sites we can already scrape (Printables/Thingiverse).
- The admin **declares their plan's free allowance** (default **50** = Starter) + per-call rate
  (default **$0.02**); we **count our own calls** and enforce the budget before each call. Our key is
  the sole consumer, so our count ≈ real usage; the AgentQL dashboard is authoritative (note it in UI).
- Budget window resets on a **day of month, fixed to the 1st for now** — store it as a config value
  the window math uses, but do NOT expose it in the UI yet (trivially editable later).
- Two budget modes: **free_only** (stop at the allowance) and **cap** (stop at a monthly $ ceiling).

## Reference — PROVEN working request (tested live against MakerWorld, HTTP 200, ~21s)
- AgentQL REST: `POST https://api.agentql.com/v1/query-data`, header `X-API-Key: <key>`.
- This exact body got past MakerWorld's Cloudflare and returned title + full description + 12 images
  — **stealth profile + tetra proxy is what beats Cloudflare**, so use these as the defaults:
  ```json
  {
    "query": "{ title description images[] { image_url } }",
    "url": "<source_url>",
    "params": { "mode": "standard", "browser_profile": "stealth", "wait_for": 6,
                "proxy": { "type": "tetra", "country_code": "US" } }
  }
  ```
- Response shape: `{ "data": { "title": str, "description": str, "images": [ {"image_url": str}, ... ] },
  "metadata": { "request_id": ... } }`. Map `data.title`→title, `data.description`→description,
  `data.images[].image_url`→image_urls in our `ScrapeResult`.
- Make the params (mode, browser_profile, wait_for, proxy on/off + country) sensible **configurable
  defaults** (stealth+tetra by default since that's what works for gated sites) — the proxy/stealth
  may affect cost, so allow turning the proxy off. You may extend the query to also grab
  tags/creator/license if reliable, but title/description/images is the required core.
- Calls take ~20s (browser+proxy+challenge) — fine for a fallback; set a generous client timeout
  (e.g. 120s).
- Existing static scraper: `app/storage/scraper.py` (`scrape_url(...) -> ScrapeResult` with
  `blocked`/`note`/`title`/`description`/`image_urls`/...). SSRF guard already there. Existing
  encrypted-secret pattern: `app/crypto.py` (`encrypt`/`decrypt`), used by AI provider keys.
- Settings mechanism: `app/routers/settings.py` (key-value instance settings). AI usage/cost +
  windowed-summary pattern: `app/models/ai_usage.py` + `app/routers/ai_usage.py` (reuse the shape/ideas).

## Working tree check
`git status --porcelain` clean on `dev`.

## Backend
### Settings (instance settings; encrypted key)
- `agentql_enabled` (bool, default false), `agentql_api_key` (encrypted; write-only in API),
  `agentql_free_allowance` (int, default 50), `agentql_budget_mode` (`free_only`|`cap`, default
  `free_only`), `agentql_monthly_cap_usd` (float, nullable), `agentql_per_call_usd` (float, default
  0.02). Reset day = a constant `AGENTQL_RESET_DAY = 1` (config, not a setting field for now).

### Usage tracking — migration 0018
- New table `scraper_usage`: `id`, `created_at` (timestamptz, indexed), `provider` (str, e.g.
  'agentql'), `source_url` (str), `success` (bool), `est_cost_usd` (float). One row per AgentQL call
  we make. `alembic upgrade head` must pass; document downgrade.
- A helper to compute the **current budget window** = from the most recent `AGENTQL_RESET_DAY` (the
  1st) at/before now → now, and aggregate `scraper_usage` in that window: `{calls, est_cost}`.

### AgentQL client + fallback + enforcement
- `app/storage/agentql_client.py`: `agentql_scrape(url, api_key) -> ScrapeResult` calling the REST
  API; map its response into the same `ScrapeResult` the static scraper returns. Best-effort: on any
  error (network/auth/quota/4xx/5xx) return a blocked/empty result with a clear `note`, never raise.
  Make it injectable/mockable for tests (like the AI `_anthropic_caller` seam) so tests never hit the
  network.
- Wire the fallback where scraping happens (import-session creation / the scrape entry point): if the
  static `scrape_url` returns **blocked** (403/Cloudflare/etc.) AND `agentql_enabled` AND a key is set
  AND **budget allows** (free_only: window calls < allowance; cap: window est_cost + per_call < cap) →
  call `agentql_scrape`, **record a `scraper_usage` row** (success + est_cost = per_call rate), and use
  its result. If budget is exhausted or AgentQL disabled → return the graceful blocked result with a
  helpful note ("MakerWorld blocks automated fetch; AgentQL budget reached / not enabled — enter
  details manually"). Recording must be best-effort (never break the import).
- Endpoints: GET/PUT admin settings for the AgentQL config (key write-only, never returned); a
  `GET /api/admin/scraper-usage` returning the current window `{calls, allowance, est_cost, mode,
  cap, resets_on}` for the admin UI.

## Frontend
- Admin UI (add a **Scraper / AgentQL** card — sensible home is `admin/SiteCapabilitiesPage.tsx`
  since it's scraping-related, or a new card; admin-gated): enable toggle, API key (write-only),
  free allowance, budget mode (Free only / Monthly $ cap) + cap field when in cap mode, per-call
  rate. Show **usage**: "X / 50 calls this month · ~$Y est · resets on the 1st", with a note "AgentQL
  dashboard is authoritative." Reuse `@/components/ui`.
- Import wizard: when a scrape was served by AgentQL, a subtle "fetched via AgentQL" note; when
  blocked + budget exhausted/disabled, the graceful "enter manually" message. Add api.ts
  functions/types.
- `@/components/ui` + Aurora, NO new deps, NO toast. Don't touch `frontend/src/pages/examples/`.

## Out of scope (note in report)
- The Playwright/SDK (local headless browser) mode — we use the **REST API** only (no Chromium in
  our image). Auto-detecting the plan from AgentQL (their API doesn't expose it).

## Verify
- Backend: `ruff check backend/` (run it yourself); **ephemeral Postgres** for migration 0018 +
  tests (docker one-liner; `alembic upgrade head`; **run pytest in the foreground to completion** —
  do NOT tear down PG mid-run; recreate the scratchpad venv if gone; tear down after). Tests (AgentQL
  client MOCKED — no network): fallback fires only when static scraper is blocked; budget enforcement
  stops calls at the free allowance and at the $ cap; a usage row is recorded per call; window math
  respects the reset day; key stored encrypted + never returned. Run a broad set (scraper/import +
  settings).
- Frontend: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite build`
  MUST succeed**. Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: AgentQL = optional BYO-key REST fallback; local usage tracking (no API
   usage endpoint); fixed reset day (1st) for now; fallback-only invocation; budget modes.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; check results (ruff / pytest+count / alembic 0018 / tsc / vitest / **vite build**);
   migration-restart note; the exact AgentQL request/response shape you implemented; confirmation
   fallback-only + budget enforcement work; anything unverified.
