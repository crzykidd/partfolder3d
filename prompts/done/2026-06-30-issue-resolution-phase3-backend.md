---
name: 2026-06-30-issue-resolution-phase3-backend
status: done
created: 2026-06-30
model: sonnet            # backend — extend action framework to all issue types
completed: 2026-06-30
result: >
  All 7 new corrective action handlers added to POST /api/issues/{id}/action.
  actions_for() context-aware for orphan (item_id null vs set).
  IssueOut.model_validator updated to use actions_for().
  ISSUE_ACTIONS dict updated with full action sets per type.
  61/61 tests pass (test_issue_resolution.py + test_phase6_reconcile.py).
  ruff clean. Ephemeral PG torn down. No new migration needed.
  keep_sidecar: implemented directly (read sidecar, apply fields, re-write sidecar).
  retry: calls reconcile_one_item; resolves if no errors, updates detail otherwise.
---

# Task: Issue resolution Phase 3 (backend) — corrective actions for the remaining issue types

Phase 1 built the action framework + orphan-directory actions. This phase adds corrective
actions for the other issue types so each can be truly resolved (not just ignored). Reuse
existing reconcile/item helpers wherever possible. Backend + tests only (frontend is 3b).

## Before you start
- Read `prompts/startnewsession.md` and `CLAUDE.md` (spawned agent on `dev`: do NOT commit/
  push — prepare the tree, report back). Do NOT edit `docs/decisions.md` — report the note back.
- Read fully:
  - `backend/app/routers/issues.py` — Phase 1's `ISSUE_ACTIONS`, `IssueOut.available_actions`
    (currently computed from `issue_type` only via a model_validator), and the
    `POST /api/issues/{id}/action` endpoint with its `ignore`/`delete`/`import` handlers. You
    extend this.
  - `backend/app/models/issue.py` — Issue (issue_type, item_id, target_path, status, detail).
  - `backend/app/worker/reconcile.py` — how each issue type is detected (so you know what
    `target_path`/`item_id` mean per type) AND the existing apply/sidecar-sync helpers to reuse
    for `conflict` (sidecar↔DB) resolution. Look for the sidecar-sync behavior + any
    `apply_review_item`/`_write_item_sidecar` reuse.
  - `backend/app/services/item_helpers.py` — `_write_item_sidecar` (rewrite sidecar from DB),
    tag/search helpers.
  - `backend/app/routers/items.py` — item delete + File-row handling (reuse patterns; don't
    duplicate).

## Working tree check
`git status --porcelain` first. Expect clean `dev` at `f041cd9` or later. If files you need
have unrelated uncommitted changes, list them and ask.

## What to do

### 1. Make `available_actions` context-aware (not type-only)
`orphan` has TWO cases that need different actions:
- **item_id IS NULL** (directory with no DB item) → `["import", "delete", "ignore"]` (Phase 1).
- **item_id IS SET** (a DB item whose directory is missing on disk) → `["delete_item", "ignore"]`
  (import/trash-the-dir make no sense — there's no dir).
Refactor the actions computation into a function `actions_for(issue) -> list[str]` that takes
the whole Issue (type + item_id) instead of the type-only map, and update `IssueOut` to use it.

### 2. Add corrective action handlers to `POST /api/issues/{id}/action`
Validate each against `actions_for(issue)` (422 otherwise). Each handler performs the real fix,
then sets the issue `status=resolved`, `resolved_at=now`. New actions:
- **`delete_item`** (orphan, item_id set): delete the DB Item and its child rows (Files, Images,
  Tags links, etc.). The directory is already gone — do NOT attempt a trash move of a missing
  path. Reuse the item-deletion DB logic; tolerate the absent directory.
- **`remove_record`** (missing_file): delete the `File` DB row whose path == the issue's
  `target_path` for that item (the file is gone; accept it).
- **`accept`** (corruption): recompute the sha256 of the on-disk file at `target_path` and update
  the `File.sha256` to match (accept the changed file). If the file no longer exists, 409.
- **`clear_source`** (dead_link): clear the item's `source_url` (and `source_baseline` if that
  would otherwise dangle). 
- **`keep_db`** and **`keep_sidecar`** (conflict): `keep_db` → rewrite the sidecar from the DB
  (`_write_item_sidecar`); `keep_sidecar` → apply the on-disk sidecar to the DB (reuse the
  reconcile sidecar-sync apply path). If the existing apply machinery is not cleanly reusable
  for `keep_sidecar`, it's acceptable to implement `keep_db` + `ignore` and leave a clear note
  that `keep_sidecar` should route through the existing Changes/Review flow — document whichever
  you choose.
- **`retry`** (sidecar_error): re-run the single-item reconcile for that item (reuse
  `rescan_item`/`reconcile_one_item`); resolve if it succeeds, else leave open with the error.
  If not cleanly reusable, fall back to `ignore` only and note it.
- `other` (and `extra_file` if it's ever produced): `ignore` only.

Guard all filesystem/DB access defensively (missing item/file/dir → 404/409, not a 500). Keep
path access inside known library mounts where a path is involved.

### 3. Keep Phase 1 behavior intact
`ignore` stays durable; `orphan` (item_id null) keeps `import`/`delete`; the legacy
`/resolve` + `/ignore` endpoints keep working. Don't regress dedup/suppression.

## Conventions to honor
- No new dependencies. Match style + the `# noqa: PLC0415` lazy-import pattern. Reuse helpers.
- Frontend is OUT OF SCOPE (Phase 3b). Backend + tests only.

## Verification — CPU-CAPPED (obey strictly; a prior run buried the host CPU)
- `backend/.venv/bin/ruff check backend/` from repo root (0.8.4; ignore explicit-`--config`-only findings).
- Ephemeral PG (`postgres:16-alpine` :5433, partfolder3d/testpass/partfolder3d), `alembic upgrade head` FIRST. (No new migration expected — no schema change.)
- Run ONLY the relevant test files, niced + capped:
  `export OMP_NUM_THREADS=2 LP_NUM_THREADS=2 ; nice -n 19 backend/.venv/bin/pytest
  backend/tests/test_issue_resolution.py backend/tests/test_phase6_reconcile.py -p no:cacheprovider -q`.
  NEVER the full suite; NEVER a real render/large scan — small fixtures, mocked.
- Extend `test_issue_resolution.py`: available_actions branches on orphan item_id; each new
  action performs its fix + resolves; 422 for an action not permitted for that issue; 404/409
  guards for missing target. Tear down the ephemeral PG (`docker rm -f pf3d-test-pg`) after.

## When done
1. Update frontmatter (`status`, `completed: 2026-06-30`, `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`).
3. Do NOT edit `docs/decisions.md` — report the note (final action set per type + any fallback
   choices for keep_sidecar/retry) back.
4. Do NOT commit/push. Report: files changed, decision note, one-line `feat:`-prefixed commit
   message, ruff result, capped pytest counts. Confirm PG torn down. **Also list the final
   action id → label intent per type so the frontend (Phase 3b) can render them.**
