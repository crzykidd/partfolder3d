---
name: 2026-07-02-library-folder-browser
status: done
created: 2026-07-02
model: sonnet
completed: 2026-07-02
result: >
  Implemented admin-only filesystem folder browser for library mount-path setup (issue #8).
  Backend: FS_BROWSE_ROOTS config + GET /api/admin/fs/browse endpoint with full
  allowlist/traversal guards. Frontend: FolderBrowser modal + Browse button in
  AddLibraryForm. 14/14 security+functional tests pass; ruff, npm build, vitest all green.
---

# Task: Filesystem folder browser for library setup (issue #8)

When creating a library (Admin → Content → Libraries), the **Mount path** field is free-text, so
operators have to guess the absolute container path. Add an **admin-only folder browser** so they
can navigate the container filesystem (within safe roots) and select the folder instead of typing
it. This is **security-sensitive** — read the Security section before writing the endpoint.

## Before you start

- Frontend form: `frontend/src/pages/admin/LibrariesPage.tsx` — `mountPath` is a plain text input.
- Existing safe-path pattern to mirror: `backend/app/routers/downloads.py` resolves a requested
  path and enforces containment with `Path.is_relative_to(...)` (do the same here).
- Admin gating: find how admin-only endpoints are protected (grep the routers for the admin
  dependency, e.g. `require_admin`/role checks) and reuse it.
- Config: `backend/app/config.py` (add a setting for the browsable roots).

## What to do

### Backend — a guarded directory-listing endpoint
1. New **admin-only** endpoint, e.g. `GET /api/admin/fs/browse?path=<abs>` → returns the immediate
   **child directories** of `path` (name + absolute path; optionally a `writable` flag). Files can be
   omitted (we only pick folders). Also return the resolved `path` and its parent (for up-navigation).
2. **SECURITY (do NOT skip):**
   - **Admin-only** — reuse the existing admin dependency; 403 for non-admins.
   - **Allowlist roots.** Add a config setting `FS_BROWSE_ROOTS` (default to the library mount base,
     e.g. `["/library"]`; also allow the DATA_DIR parent if useful). Every requested `path` MUST
     resolve (via `Path(path).resolve()`) to something **inside one of the allowlisted roots** —
     enforce with `is_relative_to`. Reject anything else with 400/403. **Never** allow browsing `/`,
     `/etc`, `/proc`, arbitrary absolute paths, or escaping via `..`/symlinks.
   - Default `path` (when omitted) = the allowlisted roots themselves (list them as the starting
     points). Do not leak existence of paths outside the allowlist.
   - Handle non-existent / non-directory / permission-denied paths gracefully (clear 4xx, no stack
     traces, no filesystem info leak).
3. Register the router; keep it small and well-tested.

### Frontend — a folder picker in the library form
4. In `LibrariesPage.tsx`, add a **Browse** affordance next to the Mount path field: opens a
   simple folder navigator (start at the allowed roots → list child dirs → click to drill down →
   "Up" to go back → "Select this folder" fills `mount_path`). Keep **manual text entry** as a
   fallback. Use `apiFetch` for the calls.

## Conventions to honor

- **Changelog:** `CHANGELOG.md [Unreleased]` (Added: folder browser for library mount-path setup).
- **Verify:**
  - Backend: `backend/.venv/bin/ruff check backend/` + pytest for the new endpoint against the
    ephemeral Postgres at `postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d`
    (run `alembic upgrade head` first). **Add tests for the security guards**: non-admin → 403;
    path outside the allowlist / `..` traversal → rejected; a listing inside an allowed root works.
    If no PG is reachable, say so — the orchestrator will verify.
  - Frontend: `docker exec partfolder3d-frontend-1 sh -c 'cd /app && npm run build'` + `npm test`.
- No new DB migration expected.

## When done

1. Frontmatter, then `git mv` into `prompts/done/` or `failed/`.
2. Record non-obvious decisions in `docs/decisions.md` (esp. the allowlist-root design).
3. **Spawned agent: do NOT commit/push.** Prepare the tree, run the gates, report paths to stage +
   a one-line `feat:` message (reference issue #8) + verification (incl. the security-guard tests).
   Orchestrator commits on `dev`. Never `git add -A`.
