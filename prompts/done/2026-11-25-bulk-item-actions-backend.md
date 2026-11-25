---
name: 2026-11-25-bulk-item-actions-backend
status: done             # pending | in-progress | done | failed
created: 2026-11-25
model: sonnet
completed: 2026-11-25
result: Added bulk-print-records, bulk-tags, bulk-delete, bulk-rescan + tests; ruff clean; pytest not run (orchestrator gate)
---

# Task: Backend bulk item endpoints — log print, add/remove tags, delete, rescan

The catalog is getting multi-select (a separate frontend prompt runs concurrently against the
contract below). Add the backend bulk endpoints. Bulk **move** already exists
(`POST /api/items/move`, `routers/items/move.py`) — do not change it; mirror its
partial-success / per-item-isolation pattern.

## Before you start

- Read `CLAUDE.md`, `docs/architecture.md` (Items + Print history rows, gotchas),
  `backend/app/routers/items/move.py` (`bulk_move_items`, `BulkMoveRequest/Response`),
  `backend/app/routers/items/core.py` (`update_item` tag handling ~L427, `delete_item` ~L569,
  `rescan_item` ~L609), `backend/app/routers/print_records.py` (`PrintRecordIn`,
  `create_print_record`, `_record_to_out`, `_validate_visibility`),
  `backend/app/routers/items/helpers.py` (`_write_item_sidecar`), `routers/items/__init__.py`.
- **Single-segment paths only.** `/api/items/bulk/rescan` would be captured by
  `POST /{key}/rescan`. Use the paths below exactly.
- **No migration.** Pinned ruff 0.8.4 + `backend/pyproject.toml`.
- **Do NOT run `make verify`, `pytest`, or anything touching the test PG `pf3d-pg-v`** — the
  orchestrator runs the one authoritative gate. Run only `backend/.venv/bin/ruff check` (pinned
  0.8.4 — use `make`/scripts' invocation if unsure) and a byte-compile/import check.
- **Do NOT edit `CHANGELOG.md` or docs** — the orchestrator adds those at commit time.
- Do not touch `frontend/`.

## Working tree check

`git status --porcelain`; if any file you need is dirty, stop and report. Unrelated dirty files
(e.g. a concurrent frontend agent's, or `prompts/*`): note once, don't block.

## API contract (shared with the frontend prompt — implement exactly)

All: session cookie **or** API key Bearer like the single-item equivalents, `csrf_protect`,
same auth dependency as the single-item endpoint. `keys`: 1..500 unique item keys
(dedupe server-side, preserve order; 422 if empty or > 500).

Shared response for partial-success endpoints:
```json
{ "succeeded": ["key1", "key2"], "failed": [{ "key": "key3", "error": "Item not found." }] }
```
(`BulkItemResult` — if `BulkMoveResponse` already has an equivalent shape, reuse/generalize it
without changing move's wire format.)

1. `POST /api/items/bulk-print-records` — body `{ "keys": [...], "record": <PrintRecordIn> }`.
   **All-or-nothing, single transaction**: if any key is missing → 404 with
   `{"detail": "Items not found.", "missing": [...]}` (or a detail string listing them) and NOTHING
   is created. Creates one identical `PrintRecord` per item (same fields as `create_print_record`,
   `logged_by_id` = current user). Response 201 `{ "created": n, "records": [PrintRecordOut, ...] }`.
   Factor the field mapping into a shared helper used by both single and bulk create.
2. `POST /api/items/bulk-tags` — body `{ "keys": [...], "add": [names], "remove": [names] }`
   (at least one non-empty, 422 otherwise; normalize names the same way `update_item` does).
   **Add/remove semantics** (NOT replace): for each item, new set = (current − remove) ∪ add.
   Extract `update_item`'s tag-resolution logic (new names land `pending` unless
   `tags.auto_approve`; existing tags matched by name keep status) into a shared helper and reuse
   it — behavior of `PATCH /{key}` must not change. Same write-through as PATCH: DB + sidecar
   (`_write_item_sidecar`) + FTS + the "legit local edit" marking so reconcile sees no drift.
   Per-item isolation (own session/transaction like bulk move); unchanged items count as succeeded.
3. `POST /api/items/bulk-delete` — body `{ "keys": [...] }`. Same semantics as `delete_item`
   (move dir to trash, delete row) per item, per-item isolation, partial success. Factor the
   single-item body into a helper both use.
4. `POST /api/items/bulk-rescan` — body `{ "keys": [...] }`. Same as `rescan_item` (reconcile
   engine, `file_changes`/`sidecar_sync` = `auto`, `source="per_item_rescan"` or a new
   `"bulk_rescan"` source if the ChangeLog/source enum permits without a migration). Per-item
   isolation. If there is an existing arq task that runs a per-item reconcile, prefer enqueuing
   (return succeeded = enqueued) and say so; otherwise run inline sequentially. Cap rescan at
   **100** keys (422 above) since it's heavy.

## What to do

1. Add request/response schemas to `routers/items/schemas.py` (or alongside move's).
2. Implement endpoints 2–4 in a new `routers/items/bulk.py` (register it in `routers/items/__init__.py`
   with the same prefix as move; check registration order so `/bulk-*` isn't shadowed). Endpoint 1
   lives in `print_records.py` (path `/api/items/bulk-print-records`) — make sure no
   `/api/items/{key}` GET/POST route captures it (it's POST; only `POST /api/items` and
   `POST /api/items/{key}/...` exist — verify).
3. Tests in a new `backend/tests/test_bulk_item_actions.py`, following the fixtures/style of
   `test_phase7_print_history.py` and the bulk-move tests: happy path for each; bulk print 404 creates
   nothing; tags add+remove incl. pending-vs-auto_approve and sidecar contents updated; partial success
   (one bad key) for tags/delete/rescan; 422 on empty/oversize keys; CSRF required; dedupe. Plus a
   regression test that `PATCH /{key}` tag-replace still works after the refactor (existing tests may
   already cover — check).
4. `ruff check` clean. You cannot run pytest — reason carefully about fixtures; the orchestrator will run it.

## When done

1. Update frontmatter (`status`, `completed`, `result`); `git mv` this file to `prompts/done/` (or `failed/`).
2. Record non-obvious decisions (e.g. rescan inline-vs-enqueue, helper extraction) in
   `docs/decisions.md` — this one doc edit IS allowed, newest at top.
3. Do **not** commit. Report: files changed, the final endpoint list + any contract deviation
   (frontend must match), and anything the orchestrator should check when running the gate.
