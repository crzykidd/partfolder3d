---
name: 2026-06-27-phase-1-identity
status: completed
created: 2026-06-27
model: sonnet            # coding against a locked plan
completed: 2026-06-27
result: Backend identity layer complete (54 passing tests); frontend deferred to Phase 1b prompt
---

# Task: Phase 1 — Identity, first-run, settings

Build the identity layer on top of the Phase 0 shell: instance encryption key, password
auth, sessions, API keys, the first-run wizard, admin user management (invites + password
reset), a settings framework, and per-user theme persistence. This is **Phase 1** of
[`docs/build-plan.md`](../docs/build-plan.md).

**Exit criteria (from the build plan):** first-run → admin login → invite a user → accept
→ settings editable; API-key auth works.

## Before you start

- Read [`docs/build-plan.md`](../docs/build-plan.md): **Locked build-time technical
  decisions** (auth, secrets-at-rest, version file) and the **Phase 1** section. These are
  settled — do not re-litigate.
- Read [`PRD.md`](../PRD.md) §2 (personas/roles, registration & identity, SSO-later),
  §4 (data model — User, ApiKey, Invite, PasswordResetToken, AiProvider, Setting; secrets
  encrypted at rest), §13 (admin: user mgmt, invites 7-day, password reset 1-day, settings),
  §15 (API + per-user API keys), §16 (first-run wizard), §18 (remaining notes: instance
  encryption-key provisioning/rotation).
- Read [`CLAUDE.md`](../CLAUDE.md) (operating rules: work on `dev`, conventional commits,
  no `Co-authored-by:`, never `--no-verify`).
- Read the **existing Phase 0 backend skeleton** so you extend it idiomatically:
  `backend/app/main.py`, `config.py`, `db.py`, `version.py`, `backend/alembic/`,
  `backend/tests/`. Read the **frontend** shell: `frontend/src/App.tsx`,
  `components/ThemeProvider.tsx`, `pages/VersionPage.tsx`.

## Working tree check

Run `git status --porcelain`. Expect a clean tree (only this prompt file may be untracked)
on branch `dev`. If anything else overlaps the files below, list it and ask before
proceeding.

## Scope & split guidance (READ FIRST)

This is a large, security-sensitive phase. **Do the backend first and completely.** If you
judge the full phase (backend + all frontend UI) too big for one clean, well-tested pass,
**STOP after the backend is done and report a proposed split** — `1a` = backend identity
core (this prompt, sections 1–7), `1b` = frontend identity UI (section 8) — rather than
half-doing the UI. A clean backend with passing tests + a clear 1b handoff is a *success*,
not a failure.

## What to do

### 1. Instance encryption key + secrets layer
- On first run, generate a **Fernet** key (`cryptography`) into `/data/config/secret.key`,
  mode **0600**, created only if absent. **Never store the key in the DB.** (DATA_DIR comes
  from config; under tests point it at a temp dir.)
- A small `crypto`/`secrets` helper module: `encrypt(str) -> str`, `decrypt(str) -> str`,
  used for every credential field stored in the DB (API keys, AI provider keys, invite &
  reset tokens, future site tokens). Honor PRD §18: losing the key means re-entering secrets
  — document that in a code comment + `docs/decisions.md`.
- Rotation is a later utility — **do not build rotation now**; just leave a clear seam.

### 2. Models + migration
Add SQLAlchemy 2.0 (async, typed `Mapped[...]`) models, then **one Alembic migration**
(`alembic revision --autogenerate` reviewed by hand; it must `upgrade head` AND `downgrade`
cleanly against Postgres 16):
- **User** — id, email (unique, **required, = login identity**), name, role
  (`admin`/`user`), password_hash, theme_pref, is_active, created_at.
- **ApiKey** — per-user; label, the secret (see §4 below), scopes (nullable for now),
  last_used_at, created_at.
- **Invite** — token, email, created_by, expires_at (**default 7 days**), status
  (pending/accepted/expired/revoked), accepted_at.
- **PasswordResetToken** — user, token, expires_at (**default 1 day**), used, revoked.
- **Setting** — instance/per-subsystem settings (key/value; JSON value column is fine).
- **AiProvider** — provider (claude/openai/ollama), endpoint, model, api_key (**encrypted**),
  enabled. (Phase 1 only stores/encrypts config; no AI calls — that's Phase 8.)
Do **not** add Item/Tag/Library/etc. models yet (later phases). Favorites are Phase 3.

### 3. Password auth (argon2id)
- Hash with **argon2id** (`argon2-cffi`, or passlib's argon2). Sensible default params;
  centralize in one module. Verify + needs-rehash path.

### 4. Per-user API keys (Bearer)
- Generate a high-entropy key, shown to the user **once** at creation. Decide and **record
  in `docs/decisions.md`** how it's stored so it satisfies "encrypted at rest" (PRD §4) AND
  is verifiable: recommended = store a fast **lookup hash** (e.g. SHA-256 of the key) for
  O(1) verification PLUS the key **encrypted** via §1 so it can be redisplayed only if PRD
  requires (it doesn't — once-only display is fine, so a hash alone may suffice; if so,
  justify the deviation from "encrypted" for this field). Pick one, document why.
- `Authorization: Bearer <key>` authenticates programmatic API requests → resolves to a User.

### 5. Sessions (cookie) + CSRF
- Server-side session: **opaque token**, server-stored (DB or Redis — pick one, document),
  delivered as an **httpOnly, Secure, SameSite** cookie. Login (email+password) → set
  cookie; logout → invalidate. (`Secure` may be conditional on a config flag for local
  http dev — document the toggle.)
- **CSRF double-submit** for cookie-authenticated state-changing requests. Bearer/API-key
  requests are exempt from CSRF (no ambient cookie).
- Wrap auth behind a small **provider interface** so OIDC/SAML can slot in later (PRD §2,
  §17) — don't build SSO, just don't hard-wire password-only assumptions into call sites.

### 6. First-run + identity/admin API
- **First-run detection:** no users exist → instance is "uninitialized."
  - `GET /api/setup/status` → `{ initialized: bool }`.
  - `POST /api/setup` (allowed only while uninitialized) → creates the **admin** + instance
    basics (instance name, external URL/port, time zone). Later wizard steps (library, AI,
    tag seed, backup schedule) are **skippable/stubbed** — persist what's given, no-op the
    rest. Once initialized, this endpoint is locked.
- **Auth:** `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`.
- **User management (admin):** list/create/disable users, set role.
- **Invites (admin):** create tokenized invite (7-day, revocable); **invite history** with
  status; public `POST /api/invites/{token}/accept` (set name + password) → creates the User.
- **Password reset (admin-generated):** create reset link (1-day, revocable); public
  `POST /api/password-reset/{token}` to set a new password. (No email delivery — link is
  handed off manually, PRD §13/§17.)
- **Settings:** a small framework to read/update instance settings (admin) + **per-user
  theme** persistence (`GET/PUT /api/me/theme` or via `/api/auth/me`).
- Enforce **authorization**: admin-only endpoints reject non-admins; standard users can
  manage only their own API keys, theme, and (later) private data.

### 7. Backend tests
- Extend `backend/tests/` (pytest + pytest-asyncio, httpx ASGI transport, an ephemeral
  Postgres like Phase 0's migration check). Cover: first-run create-admin + lock; login/
  logout + bad creds; session-protected route + CSRF; API-key auth; invite create→accept;
  password reset; admin-only authorization (403 for standard user); theme persist;
  encrypt/decrypt round-trip + key file created at 0600. `ruff check backend/` clean.

### 8. Frontend identity UI  *(this is the 1a/1b split line — see Scope guidance)*
- **First-run wizard** page (shown when `setup/status.initialized == false`): create admin
  + instance basics; later steps visibly skippable.
- **Login** page; authenticated app gate; logout; "me" wiring via **TanStack Query**.
- **Admin area:** user management (list/create/disable/role); **invites** (create + copy
  link + history table); **password reset** link generation.
- **Settings** page: instance settings (admin) + **per-user theme** now persisted to the
  server (extend the Phase 0 `ThemeProvider`: server value is source of truth when logged
  in, localStorage remains the pre-login fallback).
- **API keys** UI: create (show once) / list / revoke.
- `npm run` `tsc --noEmit` clean; add **vitest** coverage for new non-trivial logic; keep
  the existing tests green.

## Conventions to honor

- Match the locked decisions + the Phase 0 structure exactly. No features beyond Phase 1
  (no items/tags/libraries logic, no AI calls, no rendering, no SSO, no email/SMTP).
- Secrets never in the repo or in the DB in cleartext. `.env.example` documents any **new**
  env (e.g. session backend choice, cookie-Secure dev toggle) — real `.env` stays gitignored.
- Verify locally what you can: `ruff check`, `tsc --noEmit`, `pytest`, `vitest`,
  `alembic upgrade head` **and** `downgrade base` against an ephemeral Postgres,
  `docker compose config --quiet` (+ the dev override). Note honestly anything you could
  **not** verify (e.g. full `docker compose up` boot).
- CI is now enforcing for real (Phase 0 removed the bootstrap guards) — keep all jobs green.

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-27`, one-line `result`).
2. `git mv` this file into `prompts/done/` (full phase) or — **if you split** — leave the
   completed-backend portion documented, `git mv` into `prompts/done/`, and **write the 1b
   frontend handoff** as a new `prompts/2026-06-27-phase-1b-frontend.md` from
   `prompts/TEMPLATE.md`. On failure use `prompts/failed/`.
3. Add `docs/decisions.md` entries (newest at top) for the non-obvious calls: API-key
   storage scheme, session store choice (DB vs Redis), cookie-Secure dev toggle, argon2
   params, encryption-key handling.
4. **You are a spawned agent: do NOT commit, push, change branch, or touch branch
   protection.** Prepare the working tree and **report back** to the orchestrator with:
   - the complete file list + a proposed one-line commit message (`feat:` prefix),
   - exact local check results (ruff / tsc / pytest / vitest / alembic up+down / compose),
   - whether you completed the full phase or split it (and, if split, the 1b prompt path
     and what remains),
   - any decision you had to make or anything you could not verify.
