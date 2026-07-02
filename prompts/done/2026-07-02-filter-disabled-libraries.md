---
name: 2026-07-02-filter-disabled-libraries
status: done
created: 2026-07-02
model: sonnet
completed: 2026-07-02
result: >
  Filtered destination pickers in AddAssetModal (both Upload and From-URL tabs) to
  enabled libraries only. Default selection naturally picks the first enabled library.
  Added a distinct "all libraries disabled" empty-state message. Backend guard was
  already present (sessions.py lines 141-151). Updated CHANGELOG [Unreleased]. Both
  npm run build and vitest (280 tests) pass.
---

# Task: Don't offer disabled libraries as a destination when adding items (issue #9)

Deleting a library is a soft-delete (`enabled = false`), but disabled libraries still appear in the
library selector when adding new items — so users can target a library they just "deleted." Only
**enabled** libraries should be selectable as a destination for new content; disabled ones must
still appear in the admin Libraries page (for management/re-enable), just never in an add/import
picker.

## Before you start

- Backend: `backend/app/routers/libraries.py` — `DELETE /{lib_id}` sets `enabled = False`;
  `GET /api/libraries` returns ALL libraries (incl. disabled). `LibraryOut` includes `enabled: bool`.
- Frontend destination selectors:
  - `frontend/src/components/AddAssetModal.tsx` — takes `libraries: LibraryOut[]`, defaults to
    `libraries[0]`, and renders them all without checking `enabled` (both the Upload and From-URL
    tabs).
  - Import wizard — `frontend/src/pages/ImportWizardPage.tsx` (and any target-library picker there).

## What to do

1. **Filter destination pickers to enabled libraries only.** In every place that selects a *target*
   library for NEW content (AddAssetModal upload + URL tabs, import wizard), use only
   `libraries.filter(l => l.enabled)`. Fix the default selection (`libraries[0]`) to pick the first
   ENABLED library, and guard submit so a disabled library can't be chosen.
2. **Leave the admin Libraries page showing all libraries** (enabled + disabled) — that page manages
   them; don't filter it.
3. Optional hardening (do if low-risk): have the backend reject item creation targeting a disabled
   library with a clear 4xx, so the rule is enforced server-side too. If you add it, keep it small
   and tested; otherwise note it as a follow-up.

## Conventions to honor

- **Changelog:** `CHANGELOG.md [Unreleased]` (Fixed: disabled libraries no longer offered as a
  destination for new items).
- **Verify:** `docker exec partfolder3d-frontend-1 sh -c 'cd /app && npm run build'` + `npm test`
  (vitest). If you touch the backend, also `backend/.venv/bin/ruff check backend/` and the relevant
  pytest against the ephemeral Postgres at
  `postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d` (run `alembic upgrade
  head` first) — note if no PG is reachable.

## When done

1. Frontmatter, then `git mv` into `prompts/done/` or `failed/`.
2. Record non-obvious decisions in `docs/decisions.md` if any.
3. **Spawned agent: do NOT commit/push.** Prepare the tree, run the gates, report paths to stage +
   a one-line `fix:` message (reference issue #9) + verification. Orchestrator commits on `dev`.
   Never `git add -A`.
