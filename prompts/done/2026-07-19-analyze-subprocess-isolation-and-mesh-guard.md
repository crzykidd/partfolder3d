---
name: 2026-07-19-analyze-subprocess-isolation-and-mesh-guard
status: done             # pending | in-progress | done | failed
created: 2026-07-19
model: sonnet            # opus = research/planning, sonnet = coding
completed: 2026-07-19
result: >
  analyze_item now runs mesh analysis in a spawned subprocess with a
  RLIMIT_AS memory bound + wall-clock timeout (fix #2), and oversized meshes
  (> ANALYZE_MAX_TRIANGLES) are skipped as a stored low-confidence stub
  instead of a full load (fix #4). make verify-backend green: 865 passed.
  Fix #3 (dedup) and issue #37 remain open.
---

# Task: Subprocess-isolate analyze + guard huge meshes (issue #37, fixes #2 & #4)

`analyze_item` currently loads meshes with trimesh **inline in the worker process**, so a
mesh large enough to exceed the worker's memory cap OOM-kills the WHOLE worker (SIGKILL —
uncatchable), taking down all background jobs. Fix #1 (the orphan-requeue cap, already
shipped in commit `00d6f2b`) stops the resulting infinite loop, but the worker still dies
on every such file. This task makes the worker **survive** a poison mesh:

- **Fix #2 — subprocess-isolate analyze**, mirroring how render already works
  (`backend/app/worker/render_subprocess.py`): run the trimesh-heavy analysis in a fresh
  spawned child process with a wall-clock timeout AND a per-child memory bound, so a
  crash/OOM/timeout fails only that one file's analysis and the worker keeps running.
- **Fix #4 — guard very large meshes**: cap by triangle count so an oversized mesh is
  skipped-with-a-flag rather than attempted to a full (slow, memory-hungry) load.

**Scope: fixes #2 and #4 of issue #37 ONLY.** Do NOT do fix #3 (dedup concurrent analyze
jobs) — that's a separate follow-up prompt. Do NOT close issue #37 (fix #3 remains).

## Before you start

- Read `CLAUDE.md` (verify-before-commit gates; worker has NO hot-reload) and skim
  `docs/architecture.md` for the worker/render/analyze area.
- **Read the model to mirror:** `backend/app/worker/render_subprocess.py` — copy its
  structure (spawn context, pre-created temp out/err files, `asyncio.to_thread(proc.join,
  timeout)`, terminate→kill escalation, `__CAP_SKIP__:` sentinel, `finally` cleanup +
  belt-and-suspenders kill). Also read `backend/app/worker/render_mesh.py` around the
  `RenderCapSkip` / `max_triangles` check (~line 283) for the cap pattern.
- **Read the code you're changing:** `backend/app/worker/tasks/analysis.py`
  (`_analyze_item_body` — note it calls `analyze_file(...)` in TWO places: the unsliced-3MF
  branch and the generic/STL branch) and `backend/app/worker/mesh_analysis.py`
  (`analyze_file` is the public entry that does `trimesh.load` — this is the OOM point).
- Config lives in `backend/app/config.py` (see the `RENDER_TIMEOUT_S`, `RENDER_CPU_THREADS`,
  `RENDER_MAX_TRIANGLES`, `ANALYZE_CONCURRENCY` settings to sit alongside).
- **No Alembic migration** — no schema change. **This is a `dev`-branch autonomous run.**

## Working tree check

Run `git status --porcelain` first. Expected clean. If any of the files you'll touch
(`analysis.py`, `mesh_analysis.py`, `config.py`, tests, `CHANGELOG.md`, `docs/decisions.md`)
have uncommitted changes, list them and stop. This prompt file is exempt.

## Key design decisions (follow these — they are the point of the task)

1. **A per-child `RLIMIT_AS` is the crux, not just spawning a subprocess.** The container
   has ONE cgroup memory cap shared by all processes; if the analyze child balloons, the
   cgroup OOM-killer might kill the PARENT worker, not the child — so a bare subprocess does
   NOT guarantee isolation. In the child entry point, BEFORE importing trimesh, call
   `resource.setrlimit(resource.RLIMIT_AS, (limit, limit))` with `limit =
   ANALYZE_MEM_LIMIT_MB * 1024 * 1024`. Then an over-limit allocation raises a **catchable**
   `MemoryError` in the child (or the child dies alone) → clean per-file failure, parent
   survives. Guard against setting it absurdly low (numpy/trimesh import needs headroom) —
   enforce a floor (e.g. never below 1024 MB) and default `ANALYZE_MEM_LIMIT_MB = 4096`.
   NOTE: `RLIMIT_AS` bounds virtual address space (can exceed RSS); the 4 GiB default gives
   room to import the stack and load a normal mesh. Verify the import + a small-mesh analyze
   actually succeed under the limit in your test.

2. **Move the trimesh-heavy work — the `analyze_file()` call — into the child.** The child
   entry takes `(path_str, density, infill, source_hash, max_triangles, out_file, err_file)`,
   sets the RLIMIT + numeric-thread caps, imports `analyze_file` from
   `app.worker.mesh_analysis`, runs it, and writes the returned FileAnalysis **dict as JSON**
   to `out_file` (the dict is already JSON-serialisable — it's stored in JSONB). Do NOT move
   the 3MF embedded-thumbnail reconcile or `read_3mf` slicer-metadata read into the child —
   those stay in `_analyze_item_body` (they're cheap and do async DB writes). Only the
   `analyze_file(...)` volume/geometry call is isolated.

3. **Cap (#4) lives inside the child, mirroring render's `RenderCapSkip`.** Add a
   `max_triangles` (default from `ANALYZE_MAX_TRIANGLES`, e.g. 2_000_000) check. Since face
   count isn't known until load, do the check right after trimesh load inside `analyze_file`
   (or in the child wrapper): if total faces across loaded geometry exceed the cap, raise a
   new `MeshTooLargeError` / signal `__CAP_SKIP__:` to the parent. The parent turns a
   cap-skip into a **stored low-confidence stub result** (NOT a hard error), e.g.
   `{"analyzed_at": ..., "source_hash": <sha>, "objects": [], "total_objects": 0,
   "total_colors": 0, "total_est_grams": 0.0, "low_confidence": True,
   "analysis_skipped": "too_large", "note": "mesh exceeds N-triangle analyze cap"}`. Store it
   sha-keyed exactly like a normal result so it is cached and never retried, and count it as
   `skipped` (not `errors`) in the body's tallies. This means an oversized mesh gets a
   visible "too large to analyze" state instead of an infinite retry or a silent gap.

4. **Exceptions**, mirroring render's trio: `AnalyzeTimeout` (child exceeded
   `ANALYZE_TIMEOUT_S`, killed), `AnalyzeCapSkip` (over the triangle cap — handled as the
   stub above, not an error), `AnalyzeError` (child failed / OOM'd — per-file failure). The
   existing per-file `try/except` in `_analyze_item_body` already increments `errors` and
   continues; make sure a timeout/OOM path lands there (worker survives, file marked failed),
   while a cap-skip lands in the stub-store path.

## What to do

1. **Config** (`backend/app/config.py`): add `ANALYZE_TIMEOUT_S: int = 300`,
   `ANALYZE_MEM_LIMIT_MB: int = 4096`, `ANALYZE_MAX_TRIANGLES: int = 2_000_000`, placed near
   the render caps. Add matching entries to `.env.example` and any settings docs table if one
   exists (grep for `RENDER_MAX_TRIANGLES` to find where render settings are documented —
   mirror exactly). If the settings are surfaced in an admin UI/schema, do NOT add UI — env
   config is fine for this pass (note it in decisions).

2. **New module** `backend/app/worker/analyze_subprocess.py`: mirror
   `render_subprocess.py`. Provide `async def run_analyze_subprocess(path, *, density_g_cm3,
   infill_pct, source_hash, timeout_s, mem_limit_mb, max_triangles) -> dict` returning the
   FileAnalysis dict, and raising `AnalyzeTimeout` / `AnalyzeCapSkip` / `AnalyzeError`. Use
   `multiprocessing.get_context("spawn")`, pre-created temp files, `asyncio.to_thread` for the
   join, terminate→kill escalation, JSON out-file, `__CAP_SKIP__:` err sentinel, `finally`
   cleanup. In the child, set numeric-thread env caps (mirror `startup()` in `worker.py`:
   `OMP_NUM_THREADS` etc. from `RENDER_CPU_THREADS`) and the `RLIMIT_AS` before importing
   trimesh.

3. **Wire it into `_analyze_item_body`** (`analysis.py`): replace BOTH `analyze_file(...)`
   call sites with `await run_analyze_subprocess(file_path, density_g_cm3=..., infill_pct=...,
   source_hash=current_sha, timeout_s=settings.ANALYZE_TIMEOUT_S,
   mem_limit_mb=settings.ANALYZE_MEM_LIMIT_MB, max_triangles=settings.ANALYZE_MAX_TRIANGLES)`.
   Wrap so `AnalyzeCapSkip` → store the low-confidence stub + count as skipped; `AnalyzeTimeout`
   / `AnalyzeError` → fall into the existing per-file error handling (increment `errors`, log,
   continue — worker survives). Keep the sliced-3MF branch (`_build_sliced_analysis`) as-is —
   it doesn't call trimesh.

4. **`mesh_analysis.py`**: add the `max_triangles` cap check (raise a
   `MeshTooLargeError` defined here, or return a sentinel the child converts to `__CAP_SKIP__`).
   Keep `analyze_file`'s existing signature working for current callers/tests — add
   `max_triangles: int | None = None` as an optional param (None = no cap) so existing tests
   that call `analyze_file` directly are unaffected.

5. **Tests** (find existing analyze tests first: `grep -rln "analyze_file\|analyze_item\|
   mesh_analysis" backend/tests` and reuse their fixtures — there are small real STL/3MF
   fixtures somewhere under `backend/tests`). Add tests for the new module/paths:
   - `run_analyze_subprocess` on a small real mesh fixture returns a well-formed FileAnalysis
     dict (same shape as `analyze_file`).
   - Cap-skip: call with a tiny `max_triangles` (e.g. 1) on a real fixture → raises
     `AnalyzeCapSkip` (and, via the body, produces the low-confidence stub — a body-level test
     or a direct assertion on the stub shape).
   - Timeout path: either a genuinely small `timeout_s=0`-style test or monkeypatch the child
     target to sleep — assert `AnalyzeTimeout` and that the parent doesn't hang.
   - `analyze_file(..., max_triangles=1)` raises the too-large error; `max_triangles=None`
     behaves as before.
   - A body-level test that an `AnalyzeError`/timeout for one file marks it errored but does
     NOT crash the task and DOES still finalize the Job (worker-survives contract).
   Keep tests fast — no giant fixtures; use tiny meshes with a tiny cap to exercise the cap,
   and monkeypatching for timeout/OOM rather than real 5 GiB allocations.

6. **CHANGELOG.md** — add `### Fixed` bullets under `[Unreleased]` (same section fix #1
   already created) in the SAME commit, e.g.:
   - `- Mesh analysis now runs in an isolated subprocess with a memory + wall-clock bound, so a
     pathologically large model can no longer OOM-kill the whole worker (issue #37).`
   - `- Very large meshes (> configurable triangle cap) are skipped and flagged low-confidence
     instead of attempting an unbounded load (issue #37).`

## Verify (gate before reporting)

- `make verify-backend` MUST be green (ephemeral PG :5433 → pinned ruff 0.8.4 → alembic →
  `pytest -n auto`). Iterate until it passes; report the final pass/fail + test count.
- No frontend changes → `verify-frontend` not required.
- Do NOT restart the live dev worker or stack — the orchestrator runs the live test loop after
  commit. (Remember: the worker has no hot-reload; this is just a don't-touch-prod note.)

## Conventions to honor

- Match `render_subprocess.py` style closely (docstrings, `# noqa: PLC0415` deferred imports,
  spawn rationale comment). Match `worker.py`/`analysis.py` logging phrasing.
- Conventional-commit prefix `fix:`. Reference `(issue #37)` — do NOT `closes #37` (fix #3
  still open). No `Co-authored-by:` trailers. Changelog + any docs ship in the same commit.

## When done

1. Update this file's frontmatter: `status`, `completed`, `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Prepend the non-obvious decisions to `docs/decisions.md` (why RLIMIT_AS is required on top
   of subprocess isolation; cap-skip-as-stub UX choice; env-only config for now).
4. **You are a spawned agent: do NOT commit and do NOT push.** Prepare the working tree, then
   report back to the orchestrator: (a) exact file list (incl. the new module + prompt move),
   (b) a one-line `fix:` commit message referencing `(issue #37)` (NOT closing it), (c) the
   `make verify-backend` result. Flag any deviations from this prompt.
