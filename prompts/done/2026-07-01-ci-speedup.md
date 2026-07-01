---
name: 2026-07-01-ci-speedup
status: done
created: 2026-07-01
model: sonnet            # CI / infra
completed: 2026-07-01
result: >
  Added pip caching (migration-check + test jobs) and npm caching (new frontend job).
  Restructured: lint → ruff-only; new parallel frontend job (npm ci + tsc + vitest);
  test → backend-only (no node, pytest without -v). YAML valid. pytest-xdist not
  implemented — tests commit to the shared DB, parallel workers would collide.
  Required-checks caveat: add "CI / Frontend" to main branch protection before
  next dev→main PR.
---

# Task: Speed up CI (dependency caching + parallelize frontend; investigate pytest-xdist)

The CI `Test` job takes ~17 min while every other job finishes in <1 min. Root causes: (1) NO
dependency caching — every run re-installs the full heavy Python stack (`vtk==9.3.1` ~100MB+,
`pyrender`, `trimesh`, `numpy`, `lxml`, `Pillow`) and runs a fresh `npm ci`; (2) backend pytest
and the frontend `npm ci`+vitest run sequentially in the SAME job; (3) `npm ci` runs TWICE
(once in `lint` for tsc, once in `test` for vitest); (4) 528 backend tests run serially on a real
Postgres. This task does the safe, high-value speedups and *investigates* the risky one.

## Before you start
- Read `prompts/startnewsession.md` and `CLAUDE.md` (spawned agent on `dev`: do NOT commit/push
  — prepare the tree, report back). Do NOT edit `docs/decisions.md` — report the note back.
- Read `.github/workflows/ci.yml` fully. Current jobs: `lint` (ruff + node/tsc), `config-validate`,
  `migration-check` (pip install + alembic, uses postgres service), `test` (pip install + alembic
  + `pytest -v` + node + `npm ci` + `npm test`), plus image-build/compose. `setup-python@v6` and
  `setup-node@v5` are used with NO `cache:` key.
- Read `backend/conftest.py` / test fixtures to judge pytest-xdist feasibility (step 4).

## Working tree check
`git status --porcelain` first. Expect clean `dev` at `ef0a387` or later. If `.github/workflows/
ci.yml` or `backend/requirements.txt` have unrelated uncommitted changes, list them and ask.

## What to do

### 1. Dependency caching (safe, biggest win)
- On every `setup-python@v6` step that installs backend deps (jobs `migration-check`, `test`),
  add `cache: 'pip'` with `cache-dependency-path: backend/requirements.txt`.
- On every `setup-node@v5` step, add `cache: 'npm'` with
  `cache-dependency-path: frontend/package-lock.json`.

### 2. Restructure so frontend runs in parallel + npm ci runs once (safe)
- **`lint` job → ruff only.** Remove its node/`npm ci`/`tsc` steps (they move to the new frontend job).
- **New `frontend` job** (runs in parallel, no Postgres): `setup-node@v5` (with npm cache) →
  `npm ci` → `npx tsc --noEmit` → `npm test` (vitest), `working-directory: frontend`.
- **`test` job → backend only.** Remove its node/`npm ci`/`npm test` steps; keep
  setup-python (with pip cache) + `alembic upgrade head` + pytest. Drop `-v` from the pytest
  invocation (verbose output adds time/noise); keep everything else identical.
- Keep `config-validate`, `migration-check`, image-build, compose jobs as-is (just add caching
  where they setup-python).

### 3. Validate the workflow YAML
- Parse `.github/workflows/ci.yml` with `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"`
  to confirm it's valid. (You cannot run GitHub Actions here — the real proof is the next CI run;
  the orchestrator will push and watch it.)

### 4. INVESTIGATE pytest-xdist (do NOT force it)
- Determine whether the suite can run under `pytest-xdist -n auto` safely. Key question: do tests
  **commit** data to the shared Postgres (e.g. fixtures that `await db.commit()` and use fixed
  keys/names like `key="rel9999"`, fixed library names)? If parallel workers share ONE database,
  committed rows collide (unique constraints, cross-test visibility) → flakes/failures.
- If it would require non-trivial changes (per-worker databases, converting commit-based fixtures
  to rollback), **do NOT implement it** — just report: feasibility, what would be needed, and the
  rough expected payoff. Only implement xdist if it's genuinely low-risk (e.g. the conftest already
  isolates per test/worker) — and if you do, add `pytest-xdist` to `backend/requirements.txt` and
  `-n auto` to the pytest step, and explain why it's safe.

## Important note for the report
Restructuring jobs changes the **check names** GitHub sees: `lint` no longer covers the frontend,
and a new `frontend` check appears. On `dev` this just runs, but **`main` branch protection's
required-status-checks list will need the new `frontend` check added** (owner action) before the
next `dev → main` PR can merge. Call this out clearly so the orchestrator can flag it.

## When done
1. Update frontmatter (`status`, `completed: 2026-07-01`, `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`).
3. Do NOT edit `docs/decisions.md` — report the note back.
4. Do NOT commit/push. Report: files changed, the YAML-validity result, the pytest-xdist
   feasibility finding + recommendation, the required-checks caveat, a one-line `ci:`-prefixed
   commit message, and a short estimate of expected time savings.
