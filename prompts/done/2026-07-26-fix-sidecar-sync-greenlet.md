---
name: 2026-07-26-fix-sidecar-sync-greenlet
status: done          # pending | in-progress | done | failed
created: 2026-07-26
model: sonnet             # coding task (bug fix)
completed: 2026-07-26
result: >
  Deduped reconcile.py::_write_sidecar_for_item to delegate to the corrected
  item_helpers._write_item_sidecar (after eagerly loading item.creator);
  fixes the MissingGreenlet crash and the latent render/embedded image
  duplication drift. Regression test added in test_phase6_reconcile.py.
  item_helpers.py needed no changes — it was already correct.
---

# Task: Fix the reconcile sidecar-sync `greenlet_spawn` crash (recurring `sidecar_error` issues)

The nightly reconcile scan files `sidecar_error` issues with the opaque detail
`Sidecar sync error: greenlet_spawn has not been called; can't call await_only()` for
items whose DB row is newer than their sidecar. **"Retry rescan" re-runs the same code and
fails identically.** Live examples (dev DB): items #9, #12, #13, #20. This is a real
async-SQLAlchemy bug (an illegal lazy load), NOT missing files.

## Root cause (already diagnosed — confirm, then fix)

There are **two** sidecar writers that have diverged:
- `backend/app/services/item_helpers.py::_write_item_sidecar` — the API create/update path.
  It is **correct**: it eager-loads `item.creator` and does
  `await db.refresh(item, attribute_names=["created_at", "updated_at"])` **before** the
  synchronous `build_sidecar(item, ...)` call, precisely to avoid the `MissingGreenlet`
  lazy-reload of flush-expired scalars.
- `backend/app/worker/reconcile.py::_write_sidecar_for_item` — the reconcile-scan path
  (called from `_behavior_sidecar_sync`'s "DB is newer → push DB state to sidecar" branch,
  ~line 288). It calls `build_sidecar(item, ...)` **without** that refresh, and the scan
  loads items with a bare `select(Item)` (lines ~1017/1161/1184) with **no**
  `selectinload(Item.creator)`. So `build_sidecar` (`storage/sidecar.py`, reads
  `item.creator` at ~L330 and `item.created_at`/`updated_at` at ~L343/346) triggers a lazy
  load with no async greenlet → the crash. The `except Exception` at reconcile.py ~L909
  turns it into the `sidecar_error` issue (detail at ~L922).
  reconcile.py's own comment (~L157) admits it's "a pre-existing duplicate ... kept in sync
  manually" — that manual sync is what failed.

## Before you start

- **Read `prompts/startnewsession.md`, `CLAUDE.md`, and `docs/architecture.md`.** Skim the
  v0.7.2 reconcile / corruption-vs-edit decision and the item_helpers greenlet comment.
- **DO NOT run the full `make verify` / backend `pytest` gate** (shared ephemeral test PG
  `pf3d-pg-v` on :5433 is a single instance — a second concurrent pytest run corrupts it;
  the ORCHESTRATOR runs the authoritative gate). Your only local check: **`ruff`
  (pinned 0.8.4 + `backend/pyproject.toml`) on changed files**. **Never background a check
  and exit.** This is BACKEND-ONLY — no frontend, no migration.
- **Do NOT edit `CHANGELOG.md`, `docs/architecture.md`, or `docs/decisions.md`** — another
  agent is concurrently editing those in this same working tree. Leave a short note in your
  report of the CHANGELOG line + decisions entry you'd write, and the **orchestrator will
  add them** when it commits. (This is a deliberate deviation from the usual "docs ship in
  the same commit" rule to avoid a concurrent-edit collision; the orchestrator still lands
  them in the same commit.) Ignore any unrelated dirty files you see from that other agent
  (it is touching `downloads.py`, `DownloadsPanel.tsx`, `CHANGELOG.md`, `docs/*`) — touch
  ONLY the files this task needs.

## Working tree check

Run `git status --porcelain`. You WILL see unrelated in-progress changes from a concurrent
agent (downloads.py, DownloadsPanel.tsx, CHANGELOG.md, docs/) — **ignore those, do not
touch them.** Only confirm the files YOU need (reconcile.py, item_helpers.py, backend
tests) aren't mid-edit by someone else; they shouldn't be.

## What to do

1. **Eliminate the divergent duplicate.** Prefer making `reconcile.py::_write_sidecar_for_item`
   delegate to the corrected `item_helpers` writer (`_write_item_sidecar` /
   `_build_sidecar_data`) so there is a single source of truth and it can't drift again.
   If a full merge is too invasive (e.g. subtle differences in image/file exclusion — note:
   both already exclude `generated_from_file_id`; item_helpers also excludes
   `ImageSource.render`/`embedded`), then at minimum replicate BOTH guards in the reconcile
   writer:
   - `await db.refresh(item, attribute_names=["created_at", "updated_at"])` before
     `build_sidecar`, AND
   - ensure `item.creator` is loaded in the async context (either add
     `selectinload(Item.creator)` to the scan's item-load queries, or load creator
     explicitly before the sync build — e.g. via `db.refresh(..., ["creator"])` or
     `await item.awaitable_attrs.creator`).
   Pick the cleaner approach and record it in your report. Verify the resulting image/file
   exclusion behavior still matches what the sidecar should contain (don't regress the
   #46 generated-asset exclusion or the render/embedded image exclusion).
2. **Regression test** (backend): construct an item whose DB row is newer than its sidecar
   (so the "DB → sidecar" push branch runs) and whose `creator`/timestamps are NOT
   eager-loaded / are flush-expired — i.e. reproduce the exact scan conditions — then run
   the reconcile sidecar-sync path and assert: **no `sidecar_error` issue is created**, the
   sidecar file is written, and no exception escapes. Confirm the test FAILS without your
   fix and PASSES with it (mention this in your report). Follow existing reconcile test
   patterns/fixtures.
3. **Confirm the retry path is fixed too.** The per-issue "Retry rescan"
   (`routers/issues.py`, forces `sidecar_sync: auto`) and the per-item rescan
   (`routers/items/core.py`) both re-run this code — a test or a clear argument that they
   now succeed (and the existing open `sidecar_error` issues resolve on the next
   successful sync) is required. Note whether resolution of already-open issues is
   automatic on success or needs anything else.

## Conventions to honor

- Conventional-commit `fix:` prefix; **no `Co-authored-by:` trailer**.
- (CHANGELOG / docs handled by the orchestrator per "Before you start" — just report the
  text you'd use.)

## When done

1. Set this file's frontmatter: `status: done` (or `failed`), `completed: 2026-07-26`,
   `result:` one line.
2. `git mv` this file into `prompts/done/` (success) or `prompts/failed/` (failure).
3. **You are a spawned agent: do NOT commit, do NOT push, do NOT run the full gate, and do
   NOT touch CHANGELOG/docs.** Run only `ruff` on changed files, prepare the working tree,
   move the prompt, and **report back**: exact file list, a proposed one-line `fix:` message,
   the CHANGELOG `[Unreleased]` line + a `docs/decisions.md` entry text for the orchestrator
   to add, the dedupe approach you chose, confirmation the regression test fails-without /
   passes-with the fix, and whether the existing open `sidecar_error` issues auto-resolve on
   the next successful sync. **The orchestrator runs the authoritative `make verify-backend`,
   adds the CHANGELOG/docs, then commits + pushes on `dev`.**
