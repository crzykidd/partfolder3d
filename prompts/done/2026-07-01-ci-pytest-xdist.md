---
name: 2026-07-01-ci-pytest-xdist
status: done
created: 2026-07-01
model: sonnet
completed: 2026-07-02
result: >
  585/585 passed serial (19:05); 585/585 passed parallel -n auto (5:11, 3.7x speedup
  on 6-CPU host); ruff clean. Per-worker DBs gw0–gw5 created and migrated. First
  parallel run had 4 transient failures in test_phase7_sharing.py (sharing tests pass
  cleanly with -n 2 and in all subsequent runs; confirmed flaky, not a structural
  issue). Key non-obvious decision: backend/alembic/__init__.py shadows the installed
  alembic package on sys.path, so alembic is invoked via venv binary subprocess rather
  than programmatic import. See docs/decisions.md.
---

# Task: Parallelize the backend test suite with pytest-xdist (worker-safe DB isolation)

The backend `Test` CI job (~585 tests, ~20-30 min) is the release/PR bottleneck. Enable
`pytest-xdist` (`-n auto`) with **per-worker Postgres databases** so tests run in parallel
without contending on a shared DB. Target: 3-5× wall-clock reduction.

## Context you must know

- `backend/tests/conftest.py` currently uses **transaction-rollback isolation** on a single
  shared DB (`TEST_DB_URL` from `DATABASE_URL`, default
  `postgresql+asyncpg://partfolder3d:testpass@localhost:5433/partfolder3d`). The `db_session`
  fixture opens a connection, begins a txn, yields a session, rolls back. The `client` fixture
  overrides the app's `get_db` to yield that same session. **Some code paths (worker tasks like
  `analyze_item`) open their OWN `app.db … SessionLocal()`, which reads `DATABASE_URL`** — so a
  per-worker DB must be visible to BOTH the fixture engine AND the app's SessionLocal (i.e. set
  via the `DATABASE_URL` env var, early).
- Migrations use `alembic upgrade head` (migration head is 0021; includes raw SQL — enums, FTS,
  indexes — so prefer running **alembic**, not `metadata.create_all`, to build each worker DB).
- An ephemeral Postgres is RUNNING at the URL above (container `pf3d-verify-pg`); its
  `partfolder3d` role is a superuser and CAN `CREATE DATABASE`. Use `backend/.venv` for tools
  (`backend/.venv/bin/pytest`, `.venv/bin/ruff` — ruff pinned 0.8.4).

## What to do

1. **Add the dep:** `pytest-xdist` (pin a current version) to `backend/requirements.txt` near
   the other `pytest*` pins.
2. **Per-worker DB in `conftest.py`:**
   - Detect the xdist worker id from env `PYTEST_XDIST_WORKER` (e.g. `gw0`, `gw1`; unset/empty
     when running serially → use the base DB unchanged so non-parallel runs are unaffected).
   - Derive a per-worker DB name (e.g. base `partfolder3d` → `partfolder3d_gw0`) and set
     `os.environ["DATABASE_URL"]` to the per-worker URL **as early as possible** (top of
     conftest, before app modules import) so the app's `SessionLocal` and the fixtures agree.
   - A **session-scoped fixture** (autouse) that, when running under xdist: connects to a
     maintenance DB (`.../postgres`), `DROP DATABASE IF EXISTS` + `CREATE DATABASE` the
     per-worker DB (drop-and-create for a clean slate), then runs `alembic upgrade head` against
     it (programmatically via alembic's command/config API with the per-worker URL). Keep the
     serial path (no xdist) working exactly as today (assumes head already applied, as the
     current docstring says).
   - Ensure `TEST_DB_URL` and every engine/`SessionLocal` reference resolves to the per-worker
     URL. Watch for import-time capture of `DATABASE_URL` (if `app.db` builds its engine at
     import, you may need to set the env var before importing it, and/or rebuild the engine).
3. **CI:** in `.github/workflows/ci.yml`, change the backend `Test` job's pytest invocation to
   run in parallel (`-n auto`, or a fixed worker count if `auto` is flaky on the runner). Ensure
   the Postgres service the job uses grants CREATE DATABASE to its role (the standard `postgres`
   service user is a superuser — confirm). No production code changes.
4. **Keep serial runs working:** `pytest` with no `-n` must still pass unchanged (per-worker
   logic is a no-op without `PYTEST_XDIST_WORKER`).

## Conventions to honor

- **Changelog:** add a `[Unreleased]` entry (Changed: CI test suite parallelized). This is a
  dev-tooling change; keep it brief.
- **Verify (critical — this is the whole point):**
  - Serial still green: `DATABASE_URL=…5433… backend/.venv/bin/pytest -q` (or note it's long).
  - **Parallel green + faster:** `backend/.venv/bin/pytest -n auto -q` against the ephemeral PG.
    Report BOTH the pass count and the wall-clock vs. the serial ~20-30 min. All tests must pass
    with zero flakes; if a handful of tests are order/parallel-sensitive, fix them (or mark with
    a documented reason) rather than disabling xdist.
  - `ruff check backend/` clean.

## When done

1. Frontmatter (`status`/`completed`/`result`), then `git mv` into `prompts/done/` or
   `prompts/failed/`.
2. Record non-obvious decisions in `docs/decisions.md`.
3. **Spawned agent: do NOT commit/push.** Prepare the tree, run the verifications, and report
   back: paths to stage, a one-line conventional-commit message, and the parallel-vs-serial
   timing + pass counts. The orchestrator commits on the current feature branch. Never
   `git add -A`.
