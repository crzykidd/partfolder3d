---
name: 2026-06-29-feat-per-library-os-path-prefix
status: done
created: 2026-06-29
model: sonnet
completed: 2026-06-29
result: >
  Implemented per-library × per-OS path prefixes end-to-end.
  Migration 0017 adds users.path_prefixes JSONB and migrates legacy path_prefix.
  GET/PUT /api/me/path-prefixes endpoints added. detectOS + rewriteLocalPath
  added to catalog-utils.ts. SettingsPage.tsx replaced with per-library table +
  OS override control. ItemPage.tsx PathDisplay uses library-specific prefix.
  QuickStartPage.tsx updated to use new API. All checks pass: ruff clean,
  pytest 11/11 new + all existing tests green, tsc clean, vitest 214/214, vite build OK.
---

# Task: Per-library × per-OS local path prefixes (browser-auto-pick) — replaces the single per-user prefix

The current local-path display is a **single** per-user string (`users.path_prefix`) — it can't
handle **multiple libraries on different mounts**, nor **the same user on a Mac AND a PC**
(different roots + `/` vs `\`). Rework it into a per-user map keyed by **library** and **OS**, with
the browser auto-picking the right one.

## Confirmed model
Per user, store a map: `{ "<library_id>": { "windows": "<path>"|null, "posix": "<path>"|null } }`.
The frontend detects whether the browser is Windows vs Mac/Linux and uses that library's matching
prefix + separator style; a manual OS override (stored per-browser in localStorage) covers edge
cases. Rewrite strips the library's container `mount_path` and substitutes the local prefix.

## What exists
- `users.path_prefix` (String, nullable) + `GET/PUT /api/me/path-prefix` (`app/routers/me.py`).
- `rewritePath(dirPath, prefix)` + `toPathStyle(path, style)` in
  `frontend/src/lib/catalog-utils.ts`. Callers: `ItemPage.tsx` (`getPathPrefix` →
  `rewritePath(dirPath, prefix)`), `settings/SettingsPage.tsx` (the path-prefix section + preview),
  `settings/QuickStartPage.tsx` (a "configured?" status badge).
- `ItemDetail`/`ItemSummary` expose `library_id`. `listLibraries()` returns each library's
  `id` + `mount_path` (the container path, e.g. `/library/main`).

## Working tree check
`git status --porcelain` clean on `dev`.

## Backend — migration 0017
- Add `users.path_prefixes` (JSONB, nullable) holding the map above. **Migrate** any existing
  `users.path_prefix` value into it best-effort: apply it to **all** current libraries under the
  OS inferred from the string (contains `\` → windows else posix). You may keep `path_prefix`
  (deprecated, unused) or drop it — if you drop it, update all references. `alembic upgrade head`
  must pass; document downgrade.
- Endpoints (`app/routers/me.py`): `GET /api/me/path-prefixes` → the map;
  `PUT /api/me/path-prefixes` (CSRF) accepts the full map (validate library ids exist/are enabled,
  ignore unknown). Keep the response small. Remove/redirect the old `/path-prefix` endpoint and
  update the OpenAPI/docstring. (If easier, keep the old GET returning a flattened/legacy value for
  safety, but the new map is the source of truth.)

## Frontend
- **`catalog-utils.ts`**:
  - `detectOS(): 'windows' | 'posix'` from `navigator.userAgentData?.platform` (preferred) or
    `navigator.platform`/`userAgent` (Win → windows; Mac/iOS/Linux → posix). Pure + unit-testable
    (allow passing a UA string in tests).
  - Rework the rewrite to: `rewriteLocalPath(containerPath, libraryMountPath, localPrefix, os)` —
    strip `libraryMountPath` from the front of `containerPath`, join the remainder onto
    `localPrefix`, and normalize separators to `os` via the existing `toPathStyle`. Keep a
    backward-compatible `rewritePath` (or update its tests) so nothing breaks; prefer the new
    function for per-library use. Handle missing prefix → return the raw container path.
- **`SettingsPage.tsx`** — replace the single-prefix section with a **per-library table**: one row
  per library (show name + `mount_path`), each row with a **Windows path** input and a
  **Mac/Linux path** input, plus a small **live preview** per row (sample item path rewritten for
  the current browser OS). A manual **OS override** control (This browser: Windows / Mac·Linux /
  Auto) stored in localStorage, affecting previews + display app-wide. Save via
  `PUT /api/me/path-prefixes`. Clear copy explaining it's per-library and auto-detects your machine.
- **`ItemPage.tsx`** — use the item's `library_id` → look up that library's `mount_path` (from
  `listLibraries`) + the user's prefix map entry for that library + the detected/overridden OS →
  render the local path. If no prefix for that library/OS, show the raw container path (as today).
- **`QuickStartPage.tsx`** — keep the "path display configured" status working against the new map
  (configured = any library has any prefix). Update `api.ts` types/functions
  (`getPathPrefixes`/`setPathPrefixes`, the map types); remove the old `getPathPrefix` usage.
- Reuse `@/components/ui` + Aurora. NO new deps. Don't touch `frontend/src/pages/examples/`.

## Verify
- Backend: `ruff check backend/`; **ephemeral Postgres** for migration 0017 + tests (docker
  one-liner; `alembic upgrade head`; `pytest`; tear down; recreate the scratchpad venv if gone).
  Tests: PUT/GET round-trips the map; the migration moves an old `path_prefix` into the map.
- Frontend: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes (update the existing
  `rewritePath` tests in `catalog.test.ts`; add `detectOS` + per-library rewrite tests); **and
  `npx vite build` MUST succeed**. Do NOT commit `dist/`.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: the per-library×per-OS map model, browser OS detection + manual override,
   mount-path stripping, migration of the legacy single prefix.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `feat:`
   commit message; check results (ruff / pytest+count / alembic 0017 / tsc / vitest / **vite
   build**); migration-restart note; confirmation legacy prefix migrated; anything unverified.
