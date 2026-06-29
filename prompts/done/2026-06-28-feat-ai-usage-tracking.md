---
name: 2026-06-28-feat-ai-usage-tracking
status: done
created: 2026-06-28
model: sonnet
completed: 2026-06-28
result: >
  Implemented end-to-end AI usage tracking. AiCallResult dataclass refactors
  real callers to return tokens; _dispatch normalizes str→AiCallResult for
  backward-compat test seam. AiUsage model + migration 0013 (created_at indexed).
  GET /api/ai-usage/summary (admin) with 24h/7d/30d windows + estimated cost from
  pricing.py. AiUsagePage frontend (Aurora). 389 backend tests pass; tsc/vitest/
  vite build clean. Cost: pricing.py seeds Claude rates; OpenAI unknown→null.
---

# Task: AI usage tracking — record token counts + show 24h/7d/30d usage in the UI

Record token usage from every AI call (Claude/OpenAI/Ollama) and surface windowed totals
(**last 24 hours / 7 days / 30 days**) in the admin UI. Builds on the Phase 8 AI layer.

## Stack / constraints
- Backend: FastAPI + SQLAlchemy async + alembic; reuse the Phase 8 AI client
  (`backend/app/ai/client.py`), provider model, and action endpoints
  (`backend/app/routers/ai_actions.py`, `ai_providers.py`).
- Frontend: Tailwind + Aurora CSS-vars + `@/components/ui` primitives + lucide + TanStack Query +
  `apiFetch`. **NO Mantine, NO toast, NO new deps.** Match the existing admin pages.
- **Preserve the best-effort AI contract**: usage recording must NEVER break or block an AI call,
  and the manual/no-AI paths must keep working.

## Working tree check
`git status --porcelain` clean on `dev`.

## What to build

### 1. Capture token usage from real AI responses
The AI client's real callers currently return only text. Extend them to also return token usage:
- **Claude** (`anthropic`): `response.usage.input_tokens`, `response.usage.output_tokens`.
- **OpenAI / Ollama** (`openai`): `response.usage.prompt_tokens`, `.completion_tokens`,
  `.total_tokens` (Ollama returns these too; if absent, default 0).
- Refactor so a call returns text + `(input_tokens, output_tokens)` (e.g. a small
  `AiCallResult` dataclass). **Keep the injectable test seam working**: the existing tests patch
  `_anthropic_caller` / `_openai_caller` to return a plain `str` — normalize in `_dispatch` so a
  `str` result is treated as text with 0/0 tokens (don't force every test to change). Update the
  real callers to return real usage.

### 2. Persist usage
- New model **`AiUsage`** (table `ai_usage`) + migration (next number, **0013**): `id`,
  `created_at` (timestamptz, **indexed** — windowed queries filter on it), `provider` (str),
  `model` (str | null), `action` (str: `suggest_tags` | `cleanup_description` | `summarize` |
  `test`), `input_tokens` (int), `output_tokens` (int), `total_tokens` (int), `user_id`
  (nullable FK → users, who triggered it), `success` (bool). `alembic upgrade head` +
  `downgrade base` must pass.
- Record a row on each AI call that actually hit a provider (success with real tokens; you may
  also record failed attempts with 0 tokens + success=false — your call, document it). Wire the
  recording into the action endpoints / `_dispatch` path where the db session + current user are
  available. **Recording failures must be swallowed** (log + continue) so usage tracking can
  never break an AI feature.

### 3. API
- `GET /api/ai-usage/summary` (admin-gated): returns, for each window **24h / 7d / 30d**,
  `{ calls, input_tokens, output_tokens, total_tokens }`, plus an optional per-provider (and/or
  per-model) breakdown. Compute with grouped SQL over `created_at` windows (one query or a few;
  keep it efficient — the `created_at` index supports it).

### 4. Frontend — AI Usage admin page
- `frontend/src/pages/admin/AiUsagePage.tsx` (Aurora, reuse `@/components/ui` `AdminPage`/
  `PageHeader`/`Card`/`DataTable`/`Badge`): three windowed cards/columns (24h / 7d / 30d) each
  showing total tokens (input/output/total) + call count, and a small breakdown table by
  provider/model. Empty-state when there's no usage yet. Add `getAiUsageSummary()` to `api.ts`,
  the route under `<AdminGuard>` in `App.tsx`, and an **AI Usage** item in the **Admin** nav
  group (`navConfig.ts`).
- *(Optional, if cheap)* also register an "AI Usage (30d)" stat tile in the widget registry
  (`@/lib/widgets`) so it can be added to the dashboard — only if it fits the existing pattern
  quickly; the admin page is the required deliverable.

## Verify
- Backend: `ruff check backend/`; **ephemeral Postgres** for migration 0013 + tests:
  `docker run -d --name pf3d-test-pg -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p 5433:5432 postgres:16-alpine`,
  `export DATABASE_URL="postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d"`,
  `alembic upgrade head && alembic downgrade base && alembic upgrade head`, then `pytest`. Add
  tests: a mocked AI call records an `AiUsage` row with the right tokens; the summary endpoint
  returns correct windowed totals; the no-provider/manual path still works. Recreate the
  scratchpad venv at
  `/tmp/claude-1000/-home-manderse-projects-partfolder3d/bd4b77b1-dcc4-4fbf-8dc0-d3990161f59a/scratchpad/venv`
  if gone. Tear the container down when done.
- Frontend: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite
  build` must succeed** (tsc+vitest miss babel/esbuild parse errors — the build is the real gate).
  Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: AiUsage model shape, how usage is captured (the AiCallResult refactor +
   str-normalization for the test seam), the summary-window query approach, record-failures-
   swallowed contract.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; exact check results (ruff / pytest+count / alembic 0013 round-trip / tsc /
   vitest / **vite build**); the migration-restart note (running container needs recreate for
   0013); confirmation the best-effort AI contract is preserved; anything you could not verify.
