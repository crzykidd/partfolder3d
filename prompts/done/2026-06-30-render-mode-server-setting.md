---
name: 2026-06-30-render-mode-server-setting
status: done
created: 2026-06-30
model: sonnet            # backend + frontend
completed: 2026-06-30
result: >
  render.mode DB setting wired into render_item gate (DB-first, env fallback).
  Settings API validates value in {all,no_images,off}. SettingsPage.tsx adds
  RenderModeRow select. 9+10 tests green; ruff/tsc/vitest/vite-build all clean.
---

# Task: Make RENDER_MODE an admin-editable server setting

`RENDER_MODE` (all / no_images / off) is currently an env/config value only. Promote it to a
DB-backed server setting editable in the admin settings UI — mirroring how
`estimate.filament_density_g_cm3` and `share_default_expiry_days` work (a `Setting` key/value
row that overrides the config default). The env `RENDER_MODE` becomes the fallback default.

## Before you start
- Read `prompts/startnewsession.md` and `CLAUDE.md` (spawned agent on `dev`: do NOT commit/
  push — prepare the tree, report back). Frontend stack: Tailwind + CSS-var Aurora theme +
  lucide + TanStack Query + `apiFetch` CSRF wrapper; no Mantine/toast.
- Read fully:
  - `backend/app/worker/tasks/render.py` — `render_item`. It has a RENDER_MODE gate near the
    top reading `settings.RENDER_MODE` ("off" → skip, "no_images" → skip if item has images).
    This gate must now read the DB setting first, falling back to `settings.RENDER_MODE`.
  - `backend/app/worker/tasks/analysis.py` — shows the pattern for reading a `Setting` row with
    a config fallback (`estimate.filament_density_g_cm3`). Mirror it.
  - `backend/app/models/setting.py`, `backend/app/routers/settings.py` — the Setting model +
    settings API (`GET /api/settings`, `PUT /api/settings/{key}`). Confirm whether keys are
    whitelisted; if so, add the new key.
  - `backend/app/services/item_helpers.py` — `_enqueue_render`'s "off" short-circuit reads
    `settings.RENDER_MODE`.
  - `frontend/src/pages/settings/SettingsPage.tsx` + `frontend/src/lib/api/settings.ts` —
    where the existing server settings (filament density etc.) are edited; add the control here.

## Working tree check
`git status --porcelain` first. A parallel agent is editing `DataTable.tsx` /
`TagAdminPage.tsx` (tags sort) — NOT the files above; ignore its changes, don't stage/revert.
If any file you need has unrelated uncommitted changes, list them and ask.

## What to do
1. **Setting key:** use `render.mode`, string value in {`all`,`no_images`,`off`}. Add a small
   backend helper `get_render_mode(db) -> str` (or inline, mirroring the density read): read
   the `render.mode` Setting; if absent/invalid, fall back to `settings.RENDER_MODE` (which is
   itself defaulted to "all"). Validate the value is one of the three; unknown → treat as "all".
2. **Authoritative gate in `render_item`:** replace the direct `settings.RENDER_MODE` read in
   the gate with the DB-setting-aware value (open a session / reuse one as the surrounding code
   does). Keep the gate semantics identical (off → return before creating a Job row;
   no_images → skip when the item already has images).
3. **`_enqueue_render` off-short-circuit:** update it to consult the DB setting too when a
   session is readily available; if not trivial, it's acceptable to leave it on the env default
   (render_item remains authoritative, so correctness is preserved) — but note which you chose.
4. **Settings API:** ensure `render.mode` is gettable/settable via the existing settings
   endpoints (add to any key whitelist/validation if one exists). If the settings API validates
   values per key, validate `render.mode` ∈ {all,no_images,off}.
5. **Admin UI:** in `SettingsPage.tsx` (same section as the other server settings), add a
   labeled **select** with three options mapped to the values:
   - `all` → "Render all models"
   - `no_images` → "Render only when a model has no images"
   - `off` → "Disable rendering"
   Load the current value via the settings API and PUT on change (optimistic or refetch;
   include a small saved/confirmation affordance consistent with the page). Add the
   get/set helper(s) to `api/settings.ts`. Match the page's existing gating (these server
   settings are admin-scoped — mirror the filament-density control's placement/gating exactly).

## Verification — CPU-CAPPED (a prior run buried the host CPU)
Backend:
- `backend/.venv/bin/ruff check backend/` from repo root (pinned 0.8.4; ignore explicit-`--config`-only findings).
- Ephemeral PG on :5433 (`postgres:16-alpine`, creds partfolder3d/testpass/partfolder3d),
  `alembic upgrade head` FIRST. Run **only** the relevant test file(s), niced + thread-capped:
  `export OMP_NUM_THREADS=2 LP_NUM_THREADS=2 ; nice -n 19 backend/.venv/bin/pytest
  backend/tests/test_render_reliability.py -p no:cacheprovider -q` plus any settings test.
  Add a mocked test: with a `render.mode` Setting of "off", `render_item` creates no Job row;
  with "all" (or no row) it proceeds. **No real renders. Tear down the PG (`docker rm -f
  pf3d-test-pg`) when done.** No new migration (Setting is generic key/value — no schema change).
Frontend:
- `npx tsc --noEmit`, relevant `npx vitest run`, and `npx vite build`.
Report all results (ruff, capped pytest counts, tsc/vitest/vite build).

## When done
1. Update frontmatter (`status`, `completed: 2026-06-30`, `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`).
3. Do NOT edit `docs/decisions.md` — report your note (setting key, precedence, enqueue choice) back.
4. Do NOT commit/push. Report: files changed, note, one-line `feat:` message, and all verify results.
