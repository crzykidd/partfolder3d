---
name: 2026-07-19-dedup-concurrent-analyze-jobs
status: done             # pending | in-progress | done | failed
created: 2026-07-19
model: sonnet            # opus = research/planning, sonnet = coding
completed: 2026-07-19
result: Implemented claim-time supersede (primary) + enqueue-time opt-in skip guards for analyze jobs; make verify-backend green (870 tests). All four #37 fixes now present in CHANGELOG — closeable.
---

# Task: Dedup concurrent/duplicate analyze jobs per item (issue #37, fix #3)

When the worker restarted mid-analyze, the orphan-requeue path created a **duplicate**
analyze job for the same item while another was still queued/running — so the same
expensive mesh analysis ran twice concurrently. Fix #1 (retry cap, shipped) and fix #2/#4
(subprocess isolation + mesh guard, shipped) already stop the infinite loop and the OOM.
This task removes the remaining waste: **prevent two analyze jobs for the same item from
running concurrently / being queued redundantly.**

**Scope: fix #3 of issue #37 ONLY**, and **scope the dedup to the `analyze` job type
only** — do NOT change render/extract behavior (render is already guarded by
`RENDER_CONCURRENCY=1` + subprocess isolation + supersede-on-success). This is the LAST of
the four #37 fixes, so when done you MAY `closes #37` (confirm the other three are in — see
CHANGELOG `[Unreleased]`: retry cap + subprocess isolation + mesh guard should all be
present; if any is missing, do NOT close, just reference the issue).

## Before you start

- Read `CLAUDE.md` (verify gates; worker has no hot-reload) and skim `docs/architecture.md`
  worker/jobs section.
- **Read the enqueue path:** `backend/app/services/item_helpers.py` —
  `_write_queued_row_and_enqueue` (the shared helper that writes a `queued` Job row in a
  `db.begin_nested()` savepoint then enqueues) and `_enqueue_analyze` (the analyze-specific
  wrapper).
- **Read the task/claim path:** `backend/app/worker/tasks/analysis.py` — `analyze_item` →
  `_analyze_item_inner` (claims the Job via `claim_or_create_job`, defines `_finish`, then
  runs `_analyze_item_body`). The dedup check goes in `_analyze_item_inner` right AFTER the
  claim, BEFORE `_analyze_item_body`.
- **Read the Job model** (`backend/app/models/job.py`) — note `status` already includes
  `superseded` in its documented flow, and there's a `_supersede_ancestors` helper in
  `backend/app/worker/job_tracker.py` you can learn from (but you're superseding the CURRENT
  job, not ancestors).
- **No Alembic migration** — a query-based best-effort guard, no schema change. This is a
  `dev`-branch autonomous run.

## Working tree check

`git status --porcelain` — expected clean. If `item_helpers.py`, `analysis.py`,
`job_tracker.py`, tests, `CHANGELOG.md`, or `docs/decisions.md` are dirty, list and stop.
This prompt file is exempt.

## Design (follow this)

Two guards, both scoped to `type == "analyze"`:

1. **Claim-time guard (PRIMARY — this is what actually prevents 2× expensive work).**
   In `_analyze_item_inner`, immediately after the job is claimed/created (you have
   `job_id`), run a check: is there ANOTHER `analyze` Job for this `item_id` currently in
   `status == "running"` whose `id != job_id`? If yes:
   - Mark THIS job `superseded` (status=`superseded`, `finished_at=now`, a short
     `error`/log like `"deduped: another analyze job for this item is already running"`).
     Add a tiny helper (e.g. `mark_superseded(db, job_id, reason)` in `job_tracker.py`, or
     inline it) — do NOT abuse `finish_job` (which only does succeeded/failed).
   - Return immediately WITHOUT running `_analyze_item_body` (skip the expensive work).
   - Log at info: `"analyze_item: item=%s deduped — concurrent analyze already running, superseding"`.
   Guard correctness notes: this is best-effort (a tight race where two claims happen in the
   same instant may both see zero peers — acceptable; fix #1 already bounds any residual
   waste and the sha-cache means the second pass mostly no-ops). Match by `Job.item_id ==
   item_id` (analyze sets the FK) OR `payload["item_id"].astext == str(item_id)` — prefer the
   FK column here since the claimed analyze row always sets it; if unsure, match either.
   IMPORTANT: exclude the current `job_id` from the "other running" query, and only count
   `running` (not `queued`) peers, so a job never supersedes itself.

2. **Enqueue-time guard (opt-in — reduces redundant queued rows / queue churn).**
   Add a `dedup_active: bool = False` param to `_write_queued_row_and_enqueue`. When True,
   BEFORE writing the queued row, query for an existing NON-terminal (`status IN ('queued',
   'running')`) Job of this `job_type` for this `item_id`; if one exists, log
   `"%s: dedup — active job already exists for item %s, skipping enqueue"` and return early
   (write NO row, enqueue NOTHING). Do the check inside the same `db.begin_nested()` savepoint
   as the row write so it's consistent with the insert. Pass `dedup_active=True` ONLY from
   `_enqueue_analyze` — render (`_enqueue_render`) and extract (`_enqueue_extract_archives`)
   keep `dedup_active=False` (unchanged behavior). When `db is None` (caller with no session)
   the guard can't run — that's fine, fall through to the plain enqueue (claim-time guard #1
   still catches the dup).
   Refresh-miss caveat (note in decisions): if an analyze is already running and a file
   genuinely changed, skipping the new enqueue means the change isn't re-analyzed until the
   next item event or the daily `library_reconcile_scan` — acceptable and self-healing; the
   sha-cache also means a redundant run would mostly no-op anyway.

## What to do

1. Implement guard #1 (claim-time) in `backend/app/worker/tasks/analysis.py` +
   the `mark_superseded` helper (wherever cleanest — `job_tracker.py` is the natural home).
2. Implement guard #2 (enqueue-time opt-in) in
   `backend/app/services/item_helpers.py` and pass `dedup_active=True` from `_enqueue_analyze`.
3. **Tests** (find existing coverage first: `grep -rln "_enqueue_analyze\|analyze_item\|
   claim_or_create_job\|_write_queued_row" backend/tests` — e.g. `test_queued_visibility.py`
   exercises the queued-row/claim seam; mirror its fixtures/patterns). Add:
   - Claim-time: seed a `running` analyze Job for an item, then run `analyze_item` (or
     `_analyze_item_inner`) for the same item → the new job ends `superseded` and the
     expensive body did NOT run (assert via a mock/patch of `_analyze_item_body` or
     `run_analyze_subprocess`, or by asserting no File.object_analysis was written).
   - Claim-time no-op: with NO other running analyze job, the job runs normally (not
     superseded) — guard doesn't false-positive, and a job never supersedes itself.
   - Enqueue-time: with an existing `queued` (or `running`) analyze Job for the item,
     `_enqueue_analyze` writes NO new row and calls `pool.enqueue_job` zero times; with no
     existing active job it enqueues exactly once (existing behavior).
   - Enqueue-time does NOT affect render: `_enqueue_render` still enqueues even when an
     active render job exists (dedup_active defaults False).
4. **CHANGELOG.md** — add a `### Fixed` bullet under `[Unreleased]` in the SAME commit, e.g.:
   `- Analyze jobs are now deduped per item: a second analyze for the same item is skipped at
   enqueue and superseded at claim time, so a restart or double-enqueue can't run the same
   expensive mesh analysis twice (issue #37).`
5. If (and only if) all four #37 fixes are confirmed present, the commit/PR may eventually
   `closes #37` — but per project rules DO NOT commit yourself; just note in your report that
   this completes #37 so the orchestrator uses `closes #37` in the commit.

## Verify (gate before reporting)

- `make verify-backend` MUST be green. Iterate until it passes; report final pass/fail +
  test count. No frontend changes → no `verify-frontend`.
- Do NOT restart the live worker/stack — the orchestrator runs the live test loop after commit.

## Conventions to honor

- Match the surrounding style: `# noqa: PLC0415` deferred imports, savepoint pattern in
  `_write_queued_row_and_enqueue`, logging phrasing in `analysis.py`/`item_helpers.py`.
- Conventional-commit prefix `fix:`. This is the final #37 fix — in your report, tell the
  orchestrator whether all four are present so it can decide `closes #37` vs `(issue #37)`.
  No `Co-authored-by:` trailers. Changelog + docs in the same commit.

## When done

1. Update this file's frontmatter: `status`, `completed`, `result` (one line).
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. Prepend the non-obvious decisions to `docs/decisions.md` (claim-time-supersede as the
   real guard vs enqueue-time as churn-reduction; the refresh-miss/self-heal caveat;
   best-effort-not-transactional rationale; analyze-only scope).
4. **You are a spawned agent: do NOT commit and do NOT push.** Prepare the working tree, then
   report back: (a) exact file list (incl. prompt move), (b) a one-line `fix:` commit message
   — say whether it should `closes #37` (all four fixes present) or reference `(issue #37)`,
   (c) the `make verify-backend` result, (d) any deviations.
