# PartFolder 3D — Backup & Restore

Operator guide for backing up and recovering a PartFolder 3D instance.

> **Scope:** this covers the built-in **DB + config** backup. **Library binary files
> (STL/OBJ/3MF/images) are intentionally NOT included** — you back those up yourself,
> from wherever you mounted them. This is by design: the library is usually large and
> already lives on your own storage/NAS.

---

## What a backup contains

The scheduled job (and the manual "Run backup now" action) produces a single
`backup_<UTC-timestamp>.tar.gz` archive containing exactly three things:

| Entry | What it is |
|-------|------------|
| `metadata.json` | Timestamp, app version, and the list of exported tables. |
| `db.json.gz` | Every row of every application table, dumped as JSON (via asyncpg) and gzip-compressed. This is the whole database: items, files, images, tags, users, sessions, api keys, ai providers, print records, share links, jobs, settings, etc. |
| `config/secret.key` | The instance **Fernet encryption key** — the key that decrypts every encrypted secret in `db.json.gz`. |

There is no `pg_dump` binary in the archive — the dump is an in-process JSON export, so
restore is a data re-import, not a binary `pg_restore` (see [Restore](#restore) below).

### ⚠️ Treat backups as highly sensitive

A backup archive bundles the **encryption key together with the encrypted secrets it
protects**. `db.json.gz` holds Fernet-encrypted user API keys, AI-provider keys, site
tokens, session tokens, and password-reset tokens; `config/secret.key` is the key that
decrypts all of them. **One leaked backup = full secret disclosure for the instance.**

- Store backups somewhere access-controlled and encrypted at rest.
- Do not commit them to a repo, drop them in a shared folder, or email them.
- The download endpoint is admin-only. The backup job also writes each archive
  `0600` (owner read/write only) and the `./data/backups/` directory `0700`, so
  other local users on the host cannot read them. Preserve those restrictive
  permissions when you copy an archive elsewhere.

---

## Where backups live

Backups are written inside the container to `/data/backups/`, which is the
bind-mounted `./data/` directory on the host — so on the host they are at:

```
./data/backups/backup_<UTC-timestamp>.tar.gz
```

The nightly job runs at **04:00 UTC**; retention keeps the **most recent N** archives
(default **10**, configurable in the admin UI). Older archives (and their DB records) are
pruned automatically.

## How to create / download a backup

In the app: **Admin → Data & Backups**.

- **Run backup now** — enqueues an immediate backup job.
- **Download** — pulls the `.tar.gz` for a backup record. Admin-only
  (`GET /api/admin/backups/{id}/download`).
- **Retention** — set how many archives to keep (`PUT /api/admin/backups/settings`).

Because retention prunes the on-host copies, **copy the archive you care about off the
host** (to your encrypted backup store) rather than relying on `./data/backups/` alone.

The full backup lifecycle (create / list / download / delete / retention) is exposed
under `POST|GET|DELETE /api/admin/backups...` for scripted use.

---

## Restore

> **There is no automated restore endpoint or "restore" button in the app today.** The
> backup format is designed for a **manual** restore (or a rebuild from sidecars). The
> steps below are the supported recovery paths; verify against your own environment
> before relying on them in an emergency.

You have two independent recovery paths, depending on what you lost:

### A. Restore the database from a backup archive

Use this when you still have your library files but the Postgres database is lost or
corrupt (fresh DB, wrong migration, etc.).

1. **Stop the stack** (or at least the backend/worker) so nothing writes while you
   restore: `docker compose down` (keep your volumes).
2. **Restore the encryption key first.** Extract `config/secret.key` from the archive and
   place it at `./data/config/secret.key` (mode `0600`, owned by your `PUID:PGID`).
   Without the *matching* key, every encrypted secret in the dump is unrecoverable — the
   catalog will restore but API keys / AI-provider keys / tokens will not decrypt.
3. **Bring up a clean database and apply migrations.** Start the stack; the backend
   entrypoint runs `alembic upgrade head` automatically, creating the current schema on
   the empty DB.
4. **Re-import the data.** Decompress `db.json.gz` and load its rows back into the tables.
   The dump is a plain `{ "<table>": [ {row}, … ], … }` JSON document with the tables in
   FK-safe insertion order (see `metadata.json` → `tables`). There is **no built-in
   importer**, so this is a manual step — e.g. a short script using the same asyncpg
   connection that inserts each table's rows in the listed order (bytea columns are
   hex-encoded; timestamps are ISO-8601 strings). Load into the freshly-migrated schema
   from step 3.
5. **Restart** the backend + worker and verify: log in, open a few items, confirm
   encrypted secrets (API keys, AI providers) still work — if they don't, the
   `secret.key` from step 2 didn't match the dump.

### B. Rebuild from on-disk sidecars (DB-loss resilience)

Use this when you have **no usable database backup** but you still have the library on
disk. This is the whole point of the per-item YAML sidecars: every item directory carries
a `<itemname>-<key>.yml` that is a full, portable mirror of its metadata, so the catalog
can be rebuilt from the filesystem alone.

1. Stand up a **fresh instance** (empty DB, migrations applied on startup) pointed at your
   existing library mount(s). Complete the first-run wizard and register each library on
   **Admin → Content → Libraries** with the same container mount path.
2. Run a **library scan** (reconcile). Every on-disk item directory that has a sidecar but
   no matching DB row is surfaced on the **Issues** page as an **orphan**.
3. For each orphan, use the **Import** action — it opens the import wizard **prefilled
   from the sidecar**, reconstructing the item (title, tags, creator, source/license,
   files) into the database. Tags reconcile against your canonical vocabulary as usual.

Path B recovers the **catalog** (items, tags, creators, sources) because that lives in the
sidecars. It does **not** recover data that was never written to sidecars — users,
sessions, API keys, AI-provider config, print records, share links, and other
instance/account state. For those, you need Path A (a real backup). In practice: keep DB
backups for account/settings/history, and rely on sidecars as the last-resort catalog
rebuild if a backup is ever unavailable.

---

## Recommended routine

- Let the nightly DB backup run, and **copy the latest archive off the host** to encrypted
  storage on your own schedule.
- **Back up your library mount(s)** separately (the app never touches your existing
  file-level backups of those).
- Before any upgrade, take a fresh backup (see [Upgrading](../README.md#upgrading)) and
  keep the `secret.key`/archive somewhere you can find it.
