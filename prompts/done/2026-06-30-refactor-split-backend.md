---
name: 2026-06-30-refactor-split-backend
status: done
created: 2026-06-30
model: sonnet
completed: 2026-06-29
result: >
  Behavior-preserving refactor complete. worker.py 1,741→159 lines (thin arq
  entrypoint; task functions moved to app/worker/tasks/{render,analysis,bundles,
  backup,import_session,reviews,scheduled}.py). items.py 1,350→1,184 lines (7
  shared helpers extracted to app/services/item_helpers.py; _effective_is_modified
  kept in items.py per test imports). import_sessions.py 1,648-line flat file →
  app/routers/import_sessions/ package ({schemas,helpers,sessions,site_caps}.py +
  __init__.py holding the combined router, the _share_link_fetcher module var, and
  import_from_share_link). No logic/route/task-name/query-key changes; no new deps;
  frontend untouched. arq task names preserved (registered by __name__).
  Backward-compat re-exports: worker._try_agentql_fallback,
  worker._reconcile_render_images, import_sessions.reconcile_tags,
  import_sessions._share_link_fetcher. Gate green: ruff clean; `import app.main` +
  `import worker` OK; alembic upgrade head OK on ephemeral PG; full pytest 481
  passed / 0 failed.
---

# Task: Split the big backend files (worker.py, items.py, import_sessions.py) — behavior-preserving

Three backend monoliths make every related task read thousands of unrelated lines:
- `backend/worker.py` (1,741) — ALL arq tasks in one file
- `backend/app/routers/items.py` (1,350) — item CRUD + shared helpers used by import + worker
- `backend/app/routers/import_sessions.py` (1,501) — create/upload/process/commit/share/site-caps

**Pure refactor — move code, change NOTHING about behavior, signatures, query keys, SQL, arq task
names, or routes. The full backend test suite must stay 100% green (it's the safety net).**

## Order & approach (do all in one task, but in this order to keep imports sane)

### 1. Extract shared helpers out of `items.py`
`items.py` defines helpers imported by `import_sessions.py` and `worker.py` (e.g.
`_get_or_create_tag`, `_attach_tags`, `_build_sidecar_data`, `_write_item_sidecar`,
`_update_search_vector`, `_enqueue_render`, `_enqueue_analyze`, and any others cross-imported).
Move these into a new module, e.g. `backend/app/services/item_helpers.py` (create the package).
Update EVERY import site (items.py, import_sessions.py, worker.py, tests) to the new location.
This decouples the routers/worker from the full items module.

### 2. Split `worker.py` → a `worker/` task package
- Keep `backend/worker.py` as the **arq entrypoint** (the `WorkerSettings` class + `main()` /
  `create_worker` + cron registration + the `SCHEDULED_JOB_REGISTRY`). Move the task *functions*
  into `backend/app/worker/tasks/` modules by domain, e.g.: `render.py` (`render_item`),
  `import_session.py` (`process_import_session` + `_try_agentql_fallback`), `analysis.py`
  (`analyze_item`), `bundles.py` (`build_zip_bundle` + cleanup), `backup.py` (`db_backup` +
  retention), `scheduled.py` (`exec_scheduled_job`, `inbox_scan`, cron wrappers), `reviews.py`
  (`apply_review_item`). `WorkerSettings.functions` imports them from the new modules.
- **CRITICAL:** arq registers tasks by their function `__name__` — keep the function names EXACTLY
  the same (e.g. `render_item`, `process_import_session`), and ensure `WorkerSettings.functions`
  lists the same callables. `redis.enqueue_job("render_item", …)` calls must still resolve. Do NOT
  change `create_worker(WorkerSettings)` usage. Reuse the existing `app/worker/` package
  (`reconcile.py`, `mesh_analysis.py`, `render_mesh.py`) — put new task modules alongside or under
  `app/worker/tasks/`.

### 3. Split `import_sessions.py` by sub-domain
- Carve the router into focused modules under e.g. `app/routers/import_sessions/` (a package with
  `__init__.py` that assembles/exports the `router`) OR sibling routers — your call, but the mounted
  API paths must be **identical** and `app/main.py`'s router include must still work. Group:
  create/upload/process, get/list/patch, commit, cancel+delete+image-delete, share-link import,
  site-capabilities. Keep one `APIRouter` (or merge sub-routers into the one main.py includes).

## Hard rules
- Behavior-preserving ONLY. No logic, signature, route, task-name, or query-key changes. Don't
  "improve" anything while moving. NO new deps. Don't touch `frontend/`.
- If a move would require a real logic change to work, STOP and report instead of guessing.

## Verify (this is the gate — run it fully)
- `ruff check backend/` from repo root (config in `backend/pyproject.toml`).
- App import: `python -c "import app.main"` and `python -c "import worker"` both succeed.
- **Full backend suite on ephemeral Postgres** (NOT a subset): `docker run -d --name pf3d-test-pg
  -e POSTGRES_USER=partfolder3d -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=partfolder3d -p
  5433:5432 postgres:16-alpine`; set `DATABASE_URL`; `alembic upgrade head`; **`pytest` (whole
  suite) run in the FOREGROUND to completion — do NOT tear down PG mid-run** (must be the full
  ~465-pass count, 0 failures). Recreate the scratchpad venv at the session path if gone; tear down
  PG after the run finishes.

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: the helper extraction + worker/task package + import_sessions split (token-efficiency; no behavior change; arq task names preserved).
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list + resulting line counts
   for worker.py / items.py / import_sessions.py; one-line `refactor:` commit message; check results
   (ruff / app-import / alembic / **full pytest pass count**); confirmation arq task names + routes
   unchanged; anything unverified.
