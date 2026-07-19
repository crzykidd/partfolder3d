---
name: 2026-07-17-manyfold-1-config
status: done          # pending | in-progress | done | failed
created: 2026-07-17
model: sonnet
completed: 2026-07-17
result: Added ManyfoldInstance model/migration 0023, manyfold_client.py OAuth token-fetch helper, admin CRUD + test-connection router at /api/admin/manyfold, and test_manyfold_admin.py (19 tests); make verify-backend passes (839 tests).
---

# Task: Manyfold connector — Part 1: per-instance config + admin API

Add first-class configuration for **Manyfold** instances (a self-hosted 3D-model
organizer with an OAuth2 API). An admin registers one or more Manyfold instances by
domain, pasting an OAuth **client ID** and **client secret**; later parts of this feature
(Parts 2 & 3) use these credentials to import a model straight from a Manyfold URL.

This is **Part 1 of 3** — it builds ONLY the config storage + admin API + a token-fetch
helper + a working "test connection". The connector/worker/download (Part 2) and the
frontend (Part 3) are separate prompts. Stay in scope.

## Context you need (read first)

- `docs/architecture.md` — module map + gotchas. Add a row for the new pieces.
- `backend/app/crypto.py` — `encrypt(plaintext)` / `decrypt(ciphertext)` (Fernet). Use
  these for the client secret. **Never** store the secret in plaintext.
- `backend/app/routers/site_capabilities.py` — the closest existing admin router. Mirror
  its **admin-auth dependency**, its per-domain token endpoints (`POST/DELETE
  {domain}/token`, which `encrypt()` a secret), and its response shape (secret is
  write-only; never returned).
- `backend/app/models/site_capability.py` — `SiteToken` shows the encrypted-secret column
  pattern (`encrypted_token`).
- `backend/app/routers/agentql.py` + `backend/app/routers/scrapers.py` — how a provider's
  admin router is registered and guarded; the "test connection" pattern
  (`flaresolverr_health`) with a **monkeypatchable seam** for tests.
- `backend/app/storage/flaresolverr_client.py` — the client module shape with a
  `_flaresolverr_caller` test seam. You will create the analogous `manyfold_client.py`
  (token-fetch only in this part).
- `backend/tests/test_flaresolverr.py` — the test pattern (`_setup_and_login`, admin PUT
  settings, monkeypatch the client seam, assert). Model `test_manyfold_admin.py` on it.
- **Verify discipline / gotchas:** `CLAUDE.md` (top). Backend gate is `make verify-backend`
  (ephemeral PG on :5433, pinned ruff 0.8.4, alembic upgrade head, `pytest -n auto`).

## Manyfold API facts (authoritative — from the real source)

- **OAuth grant is `client_credentials` only.** Token endpoint: `POST {base_url}/oauth/token`
  with form body `grant_type=client_credentials&client_id=…&client_secret=…&scope=public read`.
  Response: `{"access_token","token_type":"Bearer","expires_in":7200,"scope","created_at"}`.
  Token lifetime 2h. Request scope **`public read`** by default (needs `read` to see
  owner-private models; `public` alone runs anonymous).
- Errors: `401` bad/missing creds, `403` scope not granted. The instance must be a recent
  Manyfold (OAuth landed ~v0.107.0).
- The admin creates these credentials at `{base_url}/oauth/applications` on their instance.

## Working tree check

Run `git status --porcelain`. The only expected dirty file is this prompt. If any file you
plan to touch has uncommitted changes, list it and stop. Surface unrelated dirty files
once as awareness.

## What to do

1. **Model** — `backend/app/models/manyfold.py`, `ManyfoldInstance` (table
   `manyfold_instances`):
   - `id` PK.
   - `base_url` — full origin, e.g. `https://manyfold.crzynet.com` (used for API calls).
     Normalize on write: strip trailing slash, lowercase host, require http/https.
   - `domain` — host only, e.g. `manyfold.crzynet.com`, **unique index** (used in Part 2
     to match an import URL's domain → this instance). Derive from `base_url`.
   - `display_name` (nullable), `client_id` (string; an identifier, store plaintext),
     `client_secret_enc` (Fernet ciphertext — nullable so a row can exist pre-secret, but
     require it on create), `scopes` (default `"public read"`), `enabled` (bool, default
     true), `last_connected_at` (nullable — set on a successful test-connection),
     `notes` (nullable), `created_at`/`updated_at`.
   - Register the model wherever models are imported for metadata (match how other models
     are wired so Alembic autogenerate/`Base.metadata` sees it).
2. **Migration** — create `backend/alembic/versions/0023_manyfold_instances.py`
   (down_revision = `0022`). Latest on disk is `0022`; **use exactly `0023`** — migration
   numbers are serialized and this is the assigned number. Create the table + unique index
   on `domain`.
3. **Token-fetch helper** — `backend/app/storage/manyfold_client.py`:
   - `get_access_token(base_url, client_id, client_secret, *, scopes="public read",
     timeout_s=...) -> str` — POST the token endpoint, return the bearer token; raise a
     clear typed error on 401/403/network. Put the actual HTTP call behind a module-level
     `_manyfold_token_caller` seam (like `_flaresolverr_caller`) so tests monkeypatch it.
   - The instance `base_url` is **admin-trusted config** → do **not** SSRF-guard calls to
     it (mirror how FlareSolverr's configured `base_url` is exempt). (Part 2 handles the
     redirect-to-object-storage SSRF surface for file downloads — out of scope here.)
   - Keep this file small; Part 2 will extend it with model fetch + downloads.
4. **Admin router** — `backend/app/routers/manyfold.py`, prefix `/api/admin/manyfold`,
   admin-guarded exactly like `site_capabilities.py`:
   - `GET /` list instances (no secret).
   - `POST /` create (base_url, display_name, client_id, client_secret, scopes) →
     encrypt secret, derive+store domain, reject duplicate domain (409).
   - `GET /{id}` one instance (no secret).
   - `PATCH /{id}` update fields; if `client_secret` present, re-encrypt (rotate); allow
     enable/disable; re-derive domain if base_url changes (guard uniqueness).
   - `DELETE /{id}`.
   - `POST /{id}/test-connection` → decrypt secret, call `get_access_token(...)`; on
     success set `last_connected_at` and return `{ok: true, scope: "<granted>"}`; on
     failure return a structured error (401/403/timeout reason). Never echo the secret.
   - Register the router in `backend/app/main.py` next to the other admin routers.
5. **Schemas** — Pydantic response models mask the secret: expose `has_secret: bool` and
   `client_id`, **never** the secret. Request models accept `client_secret` write-only.
6. **Tests** — `backend/tests/test_manyfold_admin.py` (mirror `test_flaresolverr.py`):
   create; list/get never leak the secret (assert `has_secret` true, no secret field);
   duplicate-domain 409; PATCH rotates secret + toggles enabled; DELETE; test-connection
   success and failure by monkeypatching `_manyfold_token_caller`. Ensure `pytest -n auto`
   clean.

## Conventions to honor

- Match surrounding style; map-not-copy from the reference files above.
- **CHANGELOG.md** `[Unreleased]` gets an entry in THIS commit (e.g. under Added:
  "Manyfold instance configuration (admin) — register instances with OAuth client
  credentials; test-connection"). Same commit as the code.
- **docs/architecture.md**: add rows for the Manyfold config model / admin router /
  client module so the module map stays current.
- Record any non-obvious decision (e.g. base_url-vs-domain split, secret masking approach)
  at the top of `docs/decisions.md`, newest first.
- Backend secret handling matches the project's existing encrypted-secret convention
  (Fernet via `app.crypto`), never plaintext, never returned by the API.

## When done

1. Run **`make verify-backend`** and make it pass (ephemeral PG, ruff, alembic, pytest -n
   auto). Do not skip — the migration must `alembic upgrade head` cleanly.
2. Update this file's frontmatter (`status: done`/`failed`, `completed`, one-line
   `result`) and `git mv` it into `prompts/done/` (success) or `prompts/failed/`.
3. **You are a spawned agent: do NOT commit or push.** Prepare the working tree, then
   report back to the orchestrator: the exact list of files changed, a proposed
   Conventional-Commit one-liner (`feat: …`), and the `make verify-backend` result. The
   orchestrator auto-commits on `dev`.
