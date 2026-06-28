---
name: 2026-06-27-phase-8-ai-tagging
status: completed        # pending | completed | failed
created: 2026-06-27
model: sonnet            # coding against a locked plan
completed: 2026-06-27
result: "Phase 8a (backend) complete: AI client layer (anthropic+openai SDKs), provider CRUD, three action endpoints, 28 new tests (299 total); frontend deferred to 8b."
---

# Task: Phase 8 — AI tagging (optional)

Add **optional AI assist** for tagging, description cleanup, and web-scrape summarization,
wired into the import wizard and tag admin. **AI is optional at every step — the manual path
must always work with zero AI configured.** This is **Phase 8** of
[`docs/build-plan.md`](../docs/build-plan.md) and PRD **§14** (+ §5.1/§5.3).

**Exit criteria (build plan):** with a provider configured, the wizard suggests
canonical-first tags + a few new ones into the approval queue; with none configured,
everything still works.

## Before you start

- Read [`docs/build-plan.md`](../docs/build-plan.md) **Phase 8** + the **Locked build-time
  technical decisions**.
- Read [`PRD.md`](../PRD.md): **§14** (providers — **Anthropic Claude / OpenAI / Local LLM
  (Ollama / OpenAI-compatible)**; uses: tag suggestion/matching, description cleanup,
  web-scrape summarization; **prefer existing canonical tags/aliases; suggest only a small
  number of genuinely new tags → approval queue**; **manual-only must always work**; **keys
  encrypted at rest**), **§5.1** (aliases + new-tag approval queue — `TagStatus.pending`),
  **§5.3** (the AI reconciliation path, items 3), **§13** (admin AI-provider settings).
- Read [`CLAUDE.md`](../CLAUDE.md) operating rules and [`docs/decisions.md`](../docs/decisions.md).
- **Read the existing code you will build on / reuse — do NOT reinvent it:**
  - `backend/app/models/ai_provider.py` — **`AiProvider`** already exists (Phase 1, config-only):
    `provider` (`AiProviderType`: claude/openai/ollama), `endpoint`, `model`, `api_key_encrypted`
    (Fernet via `crypto.encrypt`), `enabled`. Phase 8 adds the CRUD admin endpoints (if absent)
    + the call layer + feature wiring.
  - The crypto helper that `ai_provider.py` references (`crypto.encrypt`/`decrypt`) — reuse it;
    never store or log keys in plaintext.
  - `backend/app/models/tag.py` — `Tag`, `TagStatus` (incl. `pending`), `TagAlias`. AI suggestions
    map onto canonical tags via aliases and land new ones in `pending` (approval queue).
  - `backend/app/routers/import_sessions.py` — the Phase 5 import wizard + tag-reconciliation
    (`tag_state`) and the scraper (`storage/scraper.py`). The AI path **augments** §5.3: AI
    suggestions feed the same reconciliation/approval flow the manual path uses.
  - `backend/app/routers/tags.py` — tag admin + `POST /api/tags/{id}/approve`.
  - Frontend: `ImportWizardPage.tsx` (tag step), `PendingTagsPage.tsx`, settings/admin pages,
    `frontend/src/lib/api.ts`, routing — for the AI-provider settings UI and AI suggestions UI.

## Working tree check

`git status --porcelain` — expect a clean tree on `dev` (only this prompt untracked). Phase 7
is committed (`a11dc83`). Surface anything unexpected before proceeding.

## Scope & split guidance

**Medium-large — plan to split.** Do the **backend (8a) first and completely**; the **frontend
(8b)** (AI-provider settings UI, AI suggestions in the wizard, AI actions in tag admin) may
split to `2026-06-27-phase-8b-*.md`. If the backend is a clean full pass but the frontend won't
fit, **STOP after the backend, write the 8b handoff, and report.** Mirror Phases 5–7.

**Out of scope (later phase) — do NOT build:** Phase 9 (admin/backup/export/full API) and
Phase 10 (hardening/release) features beyond what Phase 8 needs.

## What to do

### 1. AI client layer (provider abstraction)
- A single service module (e.g. `backend/app/ai/` or `backend/app/storage/ai.py`) that, given an
  **enabled** `AiProvider`, dispatches a structured request to the right backend. **Locked tech
  guidance — follow it:**
  - **Claude** → the official **`anthropic`** Python SDK (`import anthropic`;
    `client = anthropic.Anthropic(api_key=...)`; `client.messages.create(...)` or, for
    JSON-shaped tag output, `client.messages.parse(...)` / `output_config={"format":
    {"type":"json_schema","schema":{...}}}`). **Default model `claude-opus-4-8`** when
    `AiProvider.model` is unset — use the exact string, no date suffix. **Do NOT send
    `temperature`/`top_p`/`top_k` or `thinking:{type:"enabled",budget_tokens:…}`** — they 400 on
    4.8; omit them (thinking is off by default; you may set `thinking={"type":"adaptive"}` only
    for the harder summarization). Set a sensible `max_tokens`.
  - **OpenAI** *and* **Ollama** → the **`openai`** Python SDK. Ollama exposes an OpenAI-compatible
    API, so both use `OpenAI(base_url=..., api_key=...)` + `chat.completions.create(...)`; for
    Ollama point `base_url` at the configured `endpoint` (its `/v1`) and the key may be a
    placeholder. Use the stored `model`.
  - Add `anthropic` and `openai` to `backend/requirements.txt` (pin versions).
- **Robustness:** every AI call is **best-effort** — on error/timeout/malformed output it returns
  a clear "no suggestion" result and the **manual path proceeds unaffected**. AI failure must
  **never** block item creation, import commit, or crash the worker. Decrypt the key only at call
  time; never log it. Make the network call mockable/injectable for tests (do **not** hit real
  provider APIs in unit tests).

### 2. AI features
- **Tag suggestion/matching (§5.3 item 3):** given item content (title, description, scraped
  text, filenames), return **canonical-first** matches against existing `Tag`s/`TagAlias`es plus
  a **small** number (cap it, e.g. ≤5) of genuinely new tag suggestions. New ones land in the
  **approval queue** (`TagStatus.pending`) — never auto-canonical. Use a **structured JSON
  schema** so the output is parseable. Feed results into the same `tag_state`/reconciliation
  flow the manual path uses.
- **Description cleanup:** an endpoint/task that returns a cleaned-up description (the user
  accepts/edits — never auto-overwrites silently).
- **Web-scrape summarization:** summarize the Phase 5 scraped content into a description draft.
- Each is **opt-in** and additive to the manual flow.

### 3. Provider config + wiring
- **AI-provider admin CRUD** (if not already present): create/list/update/delete/enable an
  `AiProvider`, key write-only (encrypted), test-connection optional. Admin-gated. Reuse the
  settings/auth patterns. If a migration is needed, use the next number and verify
  `alembic upgrade head` + `downgrade base`.
- **Wire AI into the import wizard** (an optional "Suggest tags / clean up description /
  summarize" action that calls the AI layer) and **tag admin** (e.g. AI-assisted alias/merge
  suggestions if it fits cleanly; keep minimal).

### 4. API (admin/authenticated; reuse Phase 1 auth deps)
- Provider CRUD + enable/test; AI actions (suggest-tags, cleanup-description, summarize) callable
  from the import-session context. All gracefully no-op (clear response) when no provider enabled.

### 5. Frontend — MAY SPLIT TO 8b
- **AI-provider settings** (admin): pick provider, endpoint, model, key (write-only), enable,
  test. **Wizard AI actions:** buttons to suggest tags / clean description / summarize, surfacing
  results into the existing tag/description steps (user accepts/edits; nothing auto-applied).
  **Tag admin:** surface AI suggestions into the pending-approval flow. `npx tsc --noEmit` clean;
  vitest for non-trivial logic. **The UI must fully work with no provider configured** (AI
  controls hidden/disabled, manual path intact).

## Conventions to honor

- Match locked decisions + existing Phase 0–7 structure; reuse crypto, tag/alias, import-session,
  scraper, settings, and auth code.
- **Manual-only must always work with zero AI** — this is the headline contract. AI is additive,
  best-effort, and never on the critical path for creating/committing items.
- **All provider keys encrypted at rest** (reuse the Fernet helper); never log or return keys.
  Network calls are mockable and OFF by default in unit tests (no real provider calls).
- Secrets out of the repo; document any new env in `.env.example` (keys are DB-stored encrypted,
  not env — say which).
- Verify locally what you can: `ruff check backend/`, `pytest`, `npx tsc --noEmit`, `vitest`,
  `alembic upgrade head` + `downgrade base`, `docker compose config --quiet`.
  **Bring up an ephemeral Postgres** for any migration + DB tests (do this for every schema
  phase): `docker run -d --name pf3d-test-pg -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p 5433:5432 postgres:16-alpine`
  then `export DATABASE_URL="postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d"`,
  run `alembic upgrade head && alembic downgrade base && alembic upgrade head`, then `pytest`.
  Recreate the scratchpad venv at
  `/tmp/claude-1000/-home-manderse-projects-partfolder3d/bd4b77b1-dcc4-4fbf-8dc0-d3990161f59a/scratchpad/venv`
  if gone (system Python is PEP-668; pip-install requirements.txt incl. `python-multipart` +
  the new `anthropic`/`openai`, plus ruff/pytest). Tear the container down when done.

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-27`, one-line `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`); **if you split, write the 8b handoff**
   (`prompts/2026-06-27-phase-8b-*.md`). **Frontend prompts must state the real UI stack
   explicitly: Tailwind + CSS-variable theme + minimal Radix (dropdown/slot) + lucide-react +
   TanStack Query + the `apiFetch`/`apiFetchForm` CSRF wrapper — NO Mantine, NO toast library.**
3. Add `docs/decisions.md` entries (newest at top): provider-dispatch design (anthropic SDK vs
   openai SDK for OpenAI+Ollama), default Claude model, structured-output schema for tag
   suggestions, the best-effort/degrade-gracefully contract, and key-encryption reuse.
4. **You are a spawned agent: do NOT commit, push, or change branch.** Prepare the tree and
   **report back** with: complete file list; proposed one-line `feat:` commit message; exact
   local check results (incl. ephemeral-PG migration round-trip if a migration was added +
   pytest count); full-phase vs. split (+ 8b path + remaining); confirmation that the manual
   path still works with no provider configured; any decision made or thing you could not verify
   (e.g. real provider calls).
