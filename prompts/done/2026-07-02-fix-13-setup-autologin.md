---
name: 2026-07-02-fix-13-setup-autologin
status: completed
created: 2026-07-02
model: sonnet            # coding fix
completed: 2026-07-02
result: >
  Suspect A ruled out (FastAPI 0.115.6 commits before sending response bytes).
  Suspect B confirmed as primary cause: fire-and-forget invalidateQueries +
  synchronous navigate meant AuthGuard saw user===null before me refetch resolved.
  Fixed SetupPage and LoginPage onSuccess to async + await refetchQueries before
  navigate. Added confirm-password field (local state, not sent to API). Added
  explicit await db.commit() in run_setup as belt-and-suspenders. 6 new vitest
  tests + 1 new backend test, all green. npm run build clean, 286 vitest pass,
  16 backend tests pass.
---

# Task: Fix #13 — first-run wizard doesn't auto-login (bounced to /login)

On a fresh install, completing the first-run setup wizard drops the user on the login
screen instead of landing them in the app logged in. The backend already *attempts*
auto-login (`setup.py:116-119` creates a session + sets the `pf3d_session`/`pf3d_csrf`
cookies), so the failure is that the session isn't **effective** by the time the client
lands on `/`. There are two co-equal suspects — a **backend transaction-commit-ordering**
bug and a **frontend navigation race**. **Reproduce first to determine which (possibly
both), then fix.** Also add a **confirm-password** field to the setup form (owner request).

GitHub issue: **#13**.

## Before you start

- Read `startnewsession.md` and `CLAUDE.md`. `dev`-branch fix, prefix `fix:`.
- **Changelog mandatory in the same commit** (`CHANGELOG.md` `[Unreleased]`).
- Frontend verify discipline: **`npm run build`** (`tsc -b && vite build`, catches strict
  project-reference errors `npx tsc --noEmit` misses) + `npx vitest run`. If you touch the
  backend, also `ruff check backend/` (pinned ruff **0.8.4** + `backend/pyproject.toml`).
- **Scope your backend testing to the setup area only** — run just the setup/auth tests you
  add or touch (e.g. `pytest backend/tests/test_setup*.py` or the setup test module), NOT
  the whole suite. The orchestrator runs the full backend suite once at the end after both
  batched fixes land. (Memory "batch-fix-testing".)

## Working tree check

`git status --porcelain`; cross-reference the files below. Stop if any are dirty (list
them). This prompt file is exempt.

## Diagnosis (two co-equal suspects — CONFIRM by repro before fixing)

The prod deploy is **same-origin** (nginx serves the SPA and proxies `/api/`), so cookies
flow on same-origin `fetch()` by default and **normal login works on prod** — which rules
out a pure cookie/`credentials` problem as the whole story.

### Suspect A — backend: the setup session isn't committed before the client's `/me`
`run_setup` (`backend/app/routers/setup.py:70-121`) only `await db.flush()`es (lines 100,
114) and calls `create_session(db, user.id)` (line 117) — the real `COMMIT` happens later,
in the `get_db` dependency's teardown. FastAPI runs yield-dependency teardown code, and if
the session-row commit lands **after** the `201` response (with `Set-Cookie`) is already on
the wire, the browser's near-instant `GET /api/auth/me` can reach the backend on a
different pooled connection **before the session row is committed** → `get_session` finds
nothing → `401` → AuthGuard bounces to `/login`. This matches the report ("user + password
created in the DB, but you're not actually logged in"). **Check `get_db` (find it in
`backend/app/` — likely `db.py`/`database.py`/`deps.py`): does it `commit()` after `yield`,
and does that run before or after the response is sent?** If this is the cause, fix by
making the setup session **durable before returning** — e.g. `await db.commit()` at the end
of `run_setup` (after `create_session`, before building the response), so `/me` can never
beat it. Verify this doesn't double-commit destructively with `get_db` (a redundant commit
on an already-committed session is a harmless no-op; confirm).

### Suspect B — frontend: navigation race (identical shape to a latent LoginPage bug)

- `frontend/src/pages/SetupPage.tsx` `onSuccess` (~lines **116–123**) does:
  `queryClient.setQueryData(['setupStatus'], {initialized:true})` →
  `queryClient.invalidateQueries({queryKey:['me']})` (**fire-and-forget, not awaited**) →
  `navigate('/', {replace:true})` (**synchronous**).
- The `me` query lives in `frontend/src/context/AuthContext.tsx:56` (no `enabled` gate;
  `staleTime:0`). On a fresh install it already resolved once to `null` (401 → caught →
  null). `invalidateQueries` starts a refetch but **`user` stays the stale `null`** and
  `isLoading` stays **false** during a background refetch (data already exists).
- `frontend/src/components/AuthGuard.tsx:35–44`: with `isLoading===false` and `user===null`
  it immediately `<Navigate to="/login">`. So AuthGuard bounces to `/login` **before** the
  `me` refetch (which would return the now-authenticated user) resolves.
- `LoginPage.tsx` uses the exact same fire-and-forget pattern (~lines 124–130) — apply the
  same fix there so it's robust too.

### Confirm the cause first (do not fix blind)
Bring up a **fresh** dev stack with an empty DB and reproduce:
`cp .env.example .env` then `docker compose -f docker-compose.dev.yml up --build`, open
http://localhost:8973, complete the wizard, observe whether you land in the app or on
/login. (dev uses `COOKIE_SECURE=false`.) In the browser devtools Network tab, inspect the
`POST /api/setup` and the follow-up `GET /api/auth/me`, and decide which suspect it is:
- `POST /api/setup` **has** `Set-Cookie: pf3d_session=...`, the `/me` request **sends** that
  cookie, but `/me` returns **401** → **Suspect A (backend commit ordering)**. Confirm by
  re-requesting `/me` a moment later (e.g. reload) — if it then returns 200, the session
  just wasn't committed yet. Fix per Suspect A.
- `/me` returns **200** (authenticated) but you still land on `/login` → **Suspect B
  (frontend race)** — AuthGuard rendered/redirected before the refetch resolved. Fix per
  Suspect B.
- `/me` has **no** cookie at all → cookie-path problem (see "If neither suspect fits").

It may be **both** A and B — fix whichever the repro shows, and apply the Suspect B
await-before-navigate change regardless since it's a correct hardening either way.

## What to do

**0. Backend durability (do this if Suspect A is confirmed — and it's safe/correct to do
regardless).** In `run_setup` (`backend/app/routers/setup.py`), ensure the auto-login
session is **committed before the response returns** so a following `/me` can never miss
it — e.g. `await db.commit()` after `create_session(...)` / before returning
`SetupResponse`. First read the `get_db` dependency to understand the existing commit
semantics and avoid a harmful double-commit; if `get_db` already commits post-yield-before-
send, document that finding and prefer the frontend fix. Add a backend test if you change
this (see Tests).

1. **Make setup auto-login deterministic.** In `SetupPage.tsx` `onSuccess`, **await the
   `me` refetch before navigating**. Make `onSuccess` async and:
   - keep `setQueryData(['setupStatus'], {initialized:true})`,
   - replace the fire-and-forget invalidate with an awaited refetch, e.g.
     `await queryClient.refetchQueries({queryKey:['me']})` (or
     `await queryClient.invalidateQueries({queryKey:['me']})`, whichever reliably repopulates
     the AuthContext `user` before nav — verify the resulting `user` is non-null),
   - **then** `navigate('/', {replace:true})`.
   - Guard the mutation UI so the button shows pending across the await (don't leave the
     user staring at a frozen form). Handle refetch failure gracefully (fall back to
     `/login`, don't hang).
2. **Apply the same await-before-navigate fix to `LoginPage.tsx`** — same latent race.
3. **Defensive hardening (low-risk, do it):** add `credentials: 'include'` to the two
   `fetch()` calls in `frontend/src/lib/api/core.ts` (lines ~**60** and ~**96**,
   `apiFetch` and `apiFetchForm`). Harmless for same-origin; correct if the deploy is ever
   cross-origin. This is hardening, **not** the primary fix — don't let it substitute for
   the real fix.

4. **Add a confirm-password field to the setup form (owner request).** In
   `frontend/src/pages/SetupPage.tsx`, add a second password input ("Confirm password")
   alongside the existing `admin_password` field (it's on step 1 of the two-step form —
   match the existing field markup/labels/error styling; it's local UI state, NOT part of
   the `form` payload sent to the backend). Client-side validation in the existing
   `validate()` (~line 135): require the two to match, and surface a field error
   ("Passwords do not match") that blocks submission — mirror how `admin_password`'s
   ≥8-char error is shown today. Do not send the confirm value to the API; the backend
   contract is unchanged.

### If neither suspect fits (repro shows a missing cookie / different failure)
The cookie isn't sticking at all. Investigate and fix the real cause (update this prompt's
notes to match what you found): `set_session_cookie` attributes in
`backend/app/auth/sessions.py` (SameSite/Secure/path), `COOKIE_SECURE` handling in
`backend/app/config.py`, and whether the `POST /api/setup` response's `Set-Cookie` is
preserved through nginx. Don't guess — let the repro decide.

## Tests (required)

- Add a **vitest** regression test for `SetupPage` `onSuccess`: assert it does **not**
  navigate to `/` until the `me` query has been (re)fetched — i.e. the refetch is awaited
  before `navigate`. Mock the mutation + queryClient/router; make the test fail against the
  current fire-and-forget code. Add the equivalent for `LoginPage` if practical.
- Add a **vitest** test for the confirm-password field: mismatched passwords block submit
  with the "Passwords do not match" error; matching passwords allow submit.
- If you change backend commit behavior (Suspect A), add a backend test that
  `POST /api/setup` results in an **immediately committed** session — e.g. a second request
  reading `/api/auth/me` with the returned cookie succeeds (run against the ephemeral PG;
  bring one up per the `#14`/session gotchas if needed).
- Keep the existing suite green (`npm run build` + `npx vitest run`, ~280 passing).

## Conventions to honor

- Match the existing React Query + router idioms; don't introduce new state libs (no
  Mantine, no toast lib — memory "frontend-stack-no-mantine").
- `fix:` prefix (the auto-login fix dominates); the confirm-password field rides along in
  the same commit. In `CHANGELOG.md [Unreleased]`, note the auto-login fix under **Fixed**
  and the confirm-password field under **Added**. Changelog + any docs in the **same
  commit**.
- Record the confirmed root cause (Suspect A and/or B) and the fix decision in
  `docs/decisions.md` (newest at top), referencing #13. If the repro shows a different
  cause, record what it actually was.

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. `git mv` to `prompts/done/` (success) or `prompts/failed/` (failure).
3. Record the decision in `docs/decisions.md`.
4. **Spawned agent — do NOT commit.** Prepare the tree and report back: file list +
   one-line `fix:` message + verification (what the repro showed, `npm run build` result,
   vitest pass count + new test name, confirmation the new test fails without the fix). The
   orchestrator auto-commits on `dev`.
