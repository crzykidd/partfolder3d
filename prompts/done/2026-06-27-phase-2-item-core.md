---
name: 2026-06-27-phase-2-item-core
status: completed
created: 2026-06-27
model: sonnet            # coding against a locked plan + settled specs
completed: 2026-06-27
result: >
  All Phase 2 exit criteria met. 70 new tests pass (46 storage, 24 API);
  124 total tests green. SQLAlchemy 2.0 async models, Alembic 0003 migration,
  storage path layer, YAML sidecar, file inventory + SHA-256, atomic rename
  journal engine, Library/Item CRUD endpoints implemented. Bugs fixed:
  directory fsync (os.O_RDONLY), COOKIE_SECURE=False in test conftest,
  CJK slug expectation (text-unidecode transliterates to ASCII).
---

# Task: Phase 2 — Libraries, storage, sidecar, item core

Make items exist on disk + DB with portable sidecars and a safe, atomic rename. Backend +
REST API only — **no UI** (that's Phase 3). This is **Phase 2** of
[`docs/build-plan.md`](../docs/build-plan.md).

**Exit criteria (build plan):** create/list/rename/delete items via API; sidecars written +
valid; rename is atomic with rollback; renaming preserves `<key>` and all links.

## Before you start — READ THE BINDING SPECS

These three docs are **settled and binding**. Implement to them exactly; do not
re-litigate. If something is genuinely underspecified, make the smallest reasonable choice
and record it in `docs/decisions.md`.

- [`docs/sidecar-schema.md`](../docs/sidecar-schema.md) — **§1** the portable YAML sidecar
  (schema_version 1, no surrogate IDs, SHA-256, flat canonical tags, relative paths,
  ISO-8601 UTC); **§2** title→on-disk-name sanitization (NFKD→ASCII→lowercase→`[a-z0-9-]`,
  empty→`item`, 80-char cap, collision-proof via the invariant `-<key>` suffix).
- [`docs/atomic-moves.md`](../docs/atomic-moves.md) — the journaled rename: atomic
  `os.replace()` is the commit point; locked-file-safe (rename is the first mutating step);
  **roll-forward** after commit; FS journal at `/data/journal/<key>.json`; startup recovery
  sweep; **bulk = N isolated per-item transactions**.
- Also read [`docs/build-plan.md`](../docs/build-plan.md) **Phase 2** + the **Locked
  build-time technical decisions**, and [`PRD.md`](../PRD.md) §3 (storage model, physical
  layout, path display/prefix), §4 (data model), §8.5 (atomic moves), §8.6 (per-item
  rescan).

Read [`CLAUDE.md`](../CLAUDE.md) (work on `dev`, conventional commits, no `Co-authored-by:`,
never `--no-verify`) and the **existing Phase 0/1 backend** so you extend it idiomatically:
`backend/app/main.py`, `config.py`, `db.py`, `crypto.py`, `models/` (typed `Mapped[...]`
style, `base.py`), `backend/alembic/` (migration style — note the raw-SQL enum pattern in
`0002`), `backend/tests/conftest.py` (ephemeral-Postgres + temp-DATA_DIR fixtures).

## Working tree check

Run `git status --porcelain`. Expect a clean tree on `dev` (only this prompt file may be
untracked). If anything the plan touches is dirty, list it and ask before proceeding.

## Scope & split guidance

Backend-only, so it should fit one pass — but it is large. If you judge it too big for one
clean, well-tested pass, **STOP and report a proposed split** (e.g. `2a` =
models+storage+sidecar+inventory, `2b` = move-engine+recovery+item-CRUD) with a written `2b`
handoff, rather than half-doing it.

## What to do

### 1. Models + migration (`0003`)
Add SQLAlchemy 2.0 async typed models, then **one Alembic migration** that
`upgrade head` AND `downgrade` cleanly against Postgres 16 (follow the `0002` enum pattern):
- **Library** — id, name, mount_path (unique), enabled, created_at.
- **Item** — id, **key** (unique, the stable identity), title, slug, description, source_url,
  source_site, license, **creator_id** (nullable FK → Creator), default_image_id (nullable),
  library_id (FK), dir_path, schema_version (int, =1), created_at, updated_at.
- **File** — FK Item; path (relative to item dir), role
  (`model`/`zip`/`image`/`render`/`gcode`/`photo`/`other`), size, **sha256**, mtime.
- **Image** — FK Item; path (relative), source (`scraped`/`uploaded`), is_default, order.
- **Creator** — id, name, profile_url (nullable), source_site (nullable), **user_id**
  (nullable FK → `users`), created_at. (Per [`creator`](../docs/sidecar-schema.md) rules.)
- **Tag** — canonical name (unique), category (nullable), popularity_count, status
  (`active`/`pending`), created_by (nullable), created_at.
- **TagAlias** — alias string (unique) → canonical Tag.
- **ItemTag** — Item ↔ Tag association.
> Phase 2 only needs the **models + simple attach/detach** for Tag/Creator on an item and
> their persistence to the sidecar. **Do NOT build** the virtual tag tree (Phase 3), tag
> **reconciliation**/alias-matching/approval (Phase 5), or AI. No Print/Share/Job/Issue
> models yet.

### 2. Storage path layer
- **Key generation:** unique **6–8 char base32** short hash (lowercase, unambiguous
  alphabet), generated with `secrets`, **uniqueness-checked against the DB with retry**.
  Document the exact alphabet/length in `decisions.md`.
- **Shard** = key-prefix (e.g. first 2 chars → `ab/`). Document the derivation.
- **Title sanitization** exactly per `sidecar-schema.md` §2 (add a transliteration dep such
  as `text-unidecode`/`python-slugify` — pick one, pin it). Path = `<library>/<shard>/
  <slug-body>-<key>/`. The item dir is created at item-create time.
- A path/key module is the single source of truth for deriving dir/shard/slug.

### 3. Sidecar read/write
- Read + write the YAML sidecar exactly per `sidecar-schema.md` §1 (schema_version 1; emit
  the regenerated header comment; relative paths; flat canonical tag names; creator
  descriptive with `is_original`; ISO-8601 UTC). Round-trip safe (write→read→equivalent).
- Use a YAML lib (`PyYAML` or `ruamel.yaml` — pick one, pin it). Lenient reader (ignore
  unknown keys; tolerate missing optional keys).

### 4. File inventory + hashing
- Walk the item dir; record each file as a `File` row with role inferred from
  location/extension (`renders/`→render, `images/`→image, `prints/`→gcode/photo, model
  extensions→model, `*.zip`→zip, else other). **SHA-256** (lowercase hex).
- **Cheap-first drift:** treat a file as unchanged when size+mtime match; only re-hash when
  they change or on an explicit integrity/rescan pass.

### 5. Atomic move / journal engine
- Implement the **journaled-operation helper** exactly per `atomic-moves.md`: per-item lock
  → write `/data/journal/<key>.json` (fsync) → atomic `os.replace()` (commit) →
  finish-forward sidecar+DB → clear journal. Refuse cross-device (`EXDEV`) renames.
- **Startup recovery sweep** (called from app/worker startup): for each stale journal,
  finish-forward if new dir exists, roll back if old dir exists, else leave it and create an
  Issue placeholder/log (no Issue model yet — log clearly + leave the journal).
- **Bulk = N isolated per-item transactions** (no global lock); a failed item is reported
  and skipped, never rolling back siblings.

### 6. Item CRUD API
- `POST /api/items` — create: assign key, create dir, write sidecar, inventory files,
  attach given tags/creator. (No wizard, no scrape, no render.)
- `GET /api/items` (list, paginated) and `GET /api/items/{key}` (detail).
- `PATCH /api/items/{key}` — metadata updates; **a title change triggers the atomic
  rename** via the move engine (dir + sidecar + DB + slug), preserving `<key>` and all refs.
- `DELETE /api/items/{key}` — explicit delete. Decide + document whether the on-disk dir is
  hard-deleted or moved to `/data/trash/`; recommend trash-then-purge to honor "never lose
  data" — record the call in `decisions.md`.
- `POST /api/items/{key}/rescan` — per-item rescan (PRD §8.6): re-inventory/re-hash changed
  files + resync sidecar (no rendering yet).
- `POST/GET/DELETE /api/libraries` — register/list/disable library mounts (admin).
- Auth: reuse Phase 1 deps (`get_current_user`, `require_admin`, CSRF for cookie calls;
  Bearer for API keys). Item writes require auth; library management is admin-only.

### 7. Tests
Extend `backend/tests/` (pytest + ephemeral Postgres + temp DATA_DIR). Cover at least:
key-gen uniqueness + retry; shard/slug derivation; **title sanitization edge cases**
(accents, CJK/emoji→`item`, reserved names, length cap, identical-title collisions);
**sidecar round-trip**; file inventory + SHA-256 + size/mtime drift skip; **atomic rename
happy path**; **rollback when a pre-commit step fails**; **crash recovery from a stale
journal** (both finish-forward and roll-back branches); **bulk isolation** (one bad item
doesn't roll back the rest); item CRUD incl. rename-preserves-key. `ruff check backend/`
clean.

## Conventions to honor

- Match the locked decisions + the binding specs + existing Phase 0/1 structure exactly.
- No features beyond Phase 2 (no UI, search, tag tree, reconciliation, import wizard,
  scraping, rendering, print/share/AI). Favorites are Phase 3.
- Secrets out of the repo; document any new env in `.env.example`; real `.env` gitignored.
- Verify locally: `ruff check backend/`, `pytest`, `alembic upgrade head` **and**
  `downgrade base` against ephemeral Postgres, `docker compose config --quiet` (+ dev
  override). Note honestly anything you could not verify. Keep CI green.

## When done

1. Update this file's frontmatter (`status`, `completed: 2026-06-27`, one-line `result`).
2. `git mv` it into `prompts/done/` (or `prompts/failed/`); if you split, also write the
   `2b` handoff from `prompts/TEMPLATE.md`.
3. Add `docs/decisions.md` entries (newest at top) for non-obvious calls: key alphabet/
   length, shard derivation, slugify lib + YAML lib choices, delete=hard-vs-trash, any
   role-inference rules.
4. **You are a spawned agent: do NOT commit, push, change branch, or touch branch
   protection.** Prepare the tree and **report back** to the orchestrator with: the complete
   file list; a proposed one-line `feat:` commit message; exact local check results (ruff /
   pytest / alembic up+down / compose); whether you completed the full phase or split it
   (+ the 2b path and what remains); any decision you made or anything you could not verify.
