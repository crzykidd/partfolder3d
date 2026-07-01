---
name: 2026-06-30-issue-resolution-framework-backend
status: done
created: 2026-06-30
model: sonnet            # backend — migration + engine + endpoints
completed: 2026-06-30
result: >
  Migration 0020 (target_path + composite dedup index), _issue_exists helper wired to all
  8 detector sites in reconcile.py, ISSUE_ACTIONS mapping + available_actions on IssueOut,
  POST /api/issues/{id}/action endpoint with ignore/delete/import handlers (sidecar prefill
  + raw-YAML fallback), legacy resolve/ignore endpoints preserved. 43 tests pass (21 new in
  test_issue_resolution.py + 22 existing in test_phase6_reconcile.py). Ruff clean, alembic
  round-trip clean.
---

# Task: Issue resolution framework (Phase 1, backend) — dedup/suppression + actionable resolve

Reconcile "Issues" currently can't be truly resolved: `POST /issues/{id}/resolve` only flips
`status` to `resolved` and takes NO corrective action, and the daily reconcile scan has NO
dedup — so it re-creates the same Issue on the next run and it "comes back." "Ignore" is
broken the same way (no suppression). This phase builds the backend **foundation** for a
general per-type resolution framework, fixes dedup/suppression for ALL issue types, and
implements the **orphaned-directory** actions (import / delete-to-trash / ignore). Frontend
and the other issue types' corrective actions are separate later phases.

## Before you start
- Read `prompts/startnewsession.md` and `CLAUDE.md` (spawned agent on `dev`: do NOT commit/
  push — prepare the tree, report back). Do NOT edit `docs/decisions.md` — report the note back.
- Read fully (investigation already mapped these — verify before editing):
  - `backend/app/worker/reconcile.py` — the reconcile engine. 8 issue types created here.
    Key: `_scan_orphan_dirs` (~lines 881-929) creates an `orphan` Issue (item_id=None,
    detail="Directory has no matching DB item: {dir}") for every on-disk dir with no Item —
    **with no dedup**. The other detectors (`_behavior_sidecar_sync` orphan ~178-193,
    missing_file ~434, corruption ~587, dead_link ~609, conflict ~231/287, sidecar_error
    ~729, other ~859) have the same create-without-dedup pattern.
  - `backend/app/models/issue.py` — `Issue` (fields: issue_type, severity, status
    [open|resolved|ignored], item_id, detail, suggested_action, resolved_at, timestamps);
    `IssueType` (conflict, dead_link, corruption, orphan, missing_file, extra_file,
    sidecar_error, other); `IssueStatus`.
  - `backend/app/routers/issues.py` — `resolve_issue` (~107-122) and `ignore_issue`
    (~125-139): both just flip status. This is where the action endpoint goes.
  - Import-session machinery for the `import` action: `backend/app/routers/import_sessions/*`
    and `backend/app/worker/tasks/import_session.py` — find how an ImportSession is created
    from an on-disk directory (the inbox-scan path already does this). The `import` action must
    create/prepare an ImportSession for the orphan dir, **carrying its existing sidecar data**
    so the wizard can prefill. Reuse existing creation logic; do not reinvent scraping.
  - Trash mechanism for the `delete` action: `backend/app/routers/items.py` item
    delete-to-trash (the session notes mention `private_data/data/app/trash`, cross-device
    safe move). Reuse the same trash move helper for directories.
  - A recent migration (e.g. `0019_job_lifecycle.py`) for house style. Head is **0019**.

## Working tree check
`git status --porcelain` first. Expect clean `dev` at commit `1311eb6` or later. If any file
you need has unrelated uncommitted changes, list them and ask.

## What to do

### 1. Migration 0020 + model
- Add `target_path: str | None` to `Issue` (indexed) — the logical target the issue concerns
  (orphan-dir: the directory path; missing_file/corruption: the file path; orphan-item:
  the item dir; dead_link: leave null or the item; etc.). Add an index on
  `(issue_type, target_path, status)` to support dedup lookups.
- Correct `downgrade()`. Verify up/down/up on ephemeral PG.

### 2. Populate target_path + dedup/suppression in the reconcile engine
- Every detector that creates an Issue must set `target_path` to the relevant path/id.
- Add a small helper (e.g. `_issue_exists(db, issue_type, target_path) -> bool`) that returns
  True if an Issue with the same `(issue_type, target_path)` exists with status **open OR
  ignored**. Before creating any Issue, call it and **skip creation when it returns True**.
  Effect: no duplicate open issues, and `ignored` becomes a durable suppression (the scan
  never re-creates an ignored issue). A `resolved` issue does NOT suppress — if the condition
  genuinely recurs after being resolved, a fresh issue is correct (actionable resolve removes
  the condition, so this should be rare).
- Apply this dedup to ALL detectors in `reconcile.py`, not just `_scan_orphan_dirs`.

### 3. Action framework (generic, extensible)
- Define a mapping `ISSUE_ACTIONS: dict[IssueType, list[str]]` (action ids available per type).
  For this phase, fully specify **orphan** → `["import", "delete", "ignore"]`; give every other
  type at least `["ignore"]` (their corrective actions land in a later phase). Also keep a
  generic `resolve` where it still makes sense, but prefer explicit actions.
- Expose `available_actions: list[str]` on `IssueOut` (compute from the issue's type) so the
  frontend can render the right buttons.
- Add `POST /api/issues/{id}/action` (admin + CSRF) with body `{ "action": str }`. Validate the
  action is in the issue's `available_actions` (422 otherwise). Dispatch to a handler:
  - **ignore** (any type): set `status=ignored`, `resolved_at=now`. (Now durable via §2.)
  - **orphan → delete**: move `target_path` (the directory) to trash using the SAME trash
    helper item-delete uses (cross-device safe). Guard: the path must resolve inside a known
    library mount (no traversal). Then set the issue `status=resolved`, `resolved_at=now`.
    Return the updated issue.
  - **orphan → import**: create/prepare an ImportSession for `target_path`, adopting the
    directory's existing sidecar (`*.yml`) data if present so the wizard can prefill. Return a
    payload the frontend can use to open the wizard (e.g. `{ "import_session_id": ... }`).
    Do NOT auto-create the Item — the user reviews in the wizard. Leave the issue `open` (it
    resolves naturally on next scan once the dir becomes a real item), OR mark it resolved when
    the session is created — pick the option that won't leave a dangling issue if the user
    abandons the wizard; document your choice in the report.
  - Keep the existing `resolve`/`ignore` endpoints working (or route them through the new
    handler) so nothing breaks; note what you did.

## Conventions to honor
- No new dependencies. Match surrounding style + the lazy `# noqa: PLC0415` import pattern.
- Reuse existing helpers (trash move, import-session creation) — do not duplicate them.
- Frontend is OUT OF SCOPE (Phase 2). Backend + tests only.

## Verification — CPU-CAPPED (a prior run buried the host CPU; obey strictly)
- `backend/.venv/bin/ruff check backend/` from repo root (pinned 0.8.4; ignore explicit-
  `--config`-only findings).
- Ephemeral PG (`postgres:16-alpine` on :5433, creds partfolder3d/testpass/partfolder3d),
  `alembic upgrade head` FIRST. Migration round-trip: upgrade head → downgrade -1 → upgrade head.
- Run ONLY the relevant test file(s), niced + thread-capped:
  `export OMP_NUM_THREADS=2 LP_NUM_THREADS=2 ; nice -n 19 backend/.venv/bin/pytest
  backend/tests/test_issue_resolution.py <plus any existing reconcile/issues test files> -p no:cacheprovider -q`.
  NEVER the full suite; NEVER a real render/scan of a huge tree — use small fixtures.
- Add `backend/tests/test_issue_resolution.py` (mocked, small fixtures): dedup skips creating a
  duplicate when an open/ignored issue exists for the same (type, target_path); ignore is
  durable (a second scan does not re-create); orphan→delete moves the dir to trash + resolves;
  orphan→import creates an ImportSession carrying sidecar data; action validation returns 422
  for an action not in available_actions.
- Tear down the ephemeral PG (`docker rm -f pf3d-test-pg`) when done.

## When done
1. Update frontmatter (`status`, `completed: 2026-06-30`, `result`).
2. `git mv` into `prompts/done/` (or `prompts/failed/`).
3. Do NOT edit `docs/decisions.md` — report your note (schema, dedup rule, action framework,
   the import-action issue-status choice) back.
4. Do NOT commit/push. Report: files changed, decision note, one-line `feat:`-prefixed commit
   message, ruff result, alembic round-trip result, capped pytest counts. Confirm PG torn down.
