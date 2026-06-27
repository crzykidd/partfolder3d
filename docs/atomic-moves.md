# Atomic moves & the move journal

Authoritative spec for the **journaled, all-or-nothing directory rename** (PRD §8.5).
Implemented in **Phase 2** and reused by any future structure-changing operation. The
design goal, stated by the project owner: **never leave the library in a half-applied
mess** — the specific failure mode that plagues bulk "fix" operations in comparable tools
(e.g. Manyfold), where a single locked file mid-batch corrupts the whole library.

---

## 1. What can move, and why it's simple

The only operation that changes on-disk structure today is a **title rename** (PRD §3.2).
A rename changes only the `itemname` portion of `<itemname>-<key>/`; **`<key>` — and
therefore the `<shard>` it derives from — never changes.** So the old and new directories
share the same parent, which means the move is a **single atomic `os.replace()` syscall on
one volume**, not a copy. There is no partial-copy state to recover from: the rename either
happened or it didn't.

**Same-volume only.** If a rename ever resolves cross-device (`EXDEV`), **abort with a
clear error** — never silently fall back to a copy. (Cross-volume library migration is a
separate, explicit tool, not this operation.)

## 2. The transaction

The rename coordinates three resources — the directory name, the sidecar inside it, and the
DB row (+ a ChangeLogEntry). The **atomic `os.replace()` is the commit point.**

1. **Preflight (verify) — nothing mutated yet.** Acquire the per-item lock; assert the new
   dir does not exist, the old dir exists, and the parent is writable.
2. **Write journal** → `/data/journal/<key>.json` (`state: renaming`, old/new dir, old/new
   title + slug, timestamp); `fsync` the file and its parent dir.
3. **`os.replace(old_dir, new_dir)`** — atomic. **← commit point.**
4. **Rewrite the sidecar** in the new dir (write temp + atomic replace + fsync).
5. **DB transaction:** update `title` / `slug` / `dir_path`, insert the ChangeLogEntry;
   commit.
6. **Delete the journal file** (and fsync the dir) = done.

## 3. Failure & recovery semantics (roll-forward; atomic rename = commit)

- **Any failure at steps 1–3 (pre-commit), including a locked/in-use directory:**
  `os.replace()` raises atomically, so **nothing has changed**. Delete the journal entry,
  release the lock, and report a **clear, user-facing error** naming the cause/file. This
  is the **locked-file protection** — the first mutating step is the all-or-nothing one.
- **Failure at steps 4–5 (post-commit):** the hard part already succeeded and these steps
  are local + idempotent, so **roll forward** — retry them. A sidecar write that still
  fails is non-fatal: the scheduled **Sync** job re-derives the sidecar from the DB, so it
  **self-heals**. If the DB update is irrecoverable, leave the journal and raise an Issue.
- **Crash recovery (runs at worker startup; safe to re-run during the scheduled scan and
  per-item Rescan):** for each stale `/data/journal/*.json`, probe reality:
  - **new dir exists, old gone** → rename committed → **finish forward** (idempotent
    sidecar + DB sync), then delete the journal.
  - **old dir exists, new gone** → rename never happened → **roll back** (ensure DB/sidecar
    reflect the old name), then delete the journal.
  - **both or neither exist** → ambiguous → **do not guess**: keep the journal and raise an
    Issue (Phase 6) for the admin.

## 4. Bulk operations — isolation is the whole point

A bulk rename/fix is **N independent per-item journaled transactions**, never one big
transaction. Therefore:

- A failure on one item (locked file, permission error) fails **only that item** — recorded
  as an Issue — and **never rolls back, blocks, or corrupts** the items already committed or
  the ones still to come.
- There is **no global batch lock** and no all-or-nothing-across-the-batch behavior: each
  item is atomic on its own, so a partial batch is always a set of cleanly-renamed items
  plus a list of clearly-reported failures — never a half-applied mess.

## 5. Generalization

The above is implemented behind a single **journaled-operation helper** (acquire lock →
write journal → atomic mutation → finish-forward metadata → clear journal, with the startup
recovery sweep). PRD §8.5's contract "generalizes to any future structure-changing
operation," so new such operations must go through this helper rather than mutating the
filesystem directly.
