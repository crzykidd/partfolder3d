# PartFolder 3D — Product Requirements Document

**Status:** Draft v1.0
**Date:** 2026-06-27
**Owner:** manderse

---

## 1. Summary

PartFolder 3D is a self-hosted, Docker-based web application for managing a personal/household/team library of 3D printing and CAD assets (3MF, STL, OBJ, Blender, Fusion, STEP/CAD, etc.). 

Core idea: a **shared, multi-user catalog** where files are stored in stable, safe locations on disk, while discovery happens through a fast, modern web UI driven by a rich tagging system. Every item carries a **portable YAML sidecar** so its full metadata travels with the files — enabling manual re-import, instance-to-instance transfer, and resilience against database loss.

### Design principles
1. **Simple over clever.** Defaults should "just work."
2. **The filesystem is a peer source of truth.** Users will edit/print/add files outside the app. The system continuously reconciles DB ⇄ sidecar ⇄ disk.
3. **Never destroy or lose data.** Stable storage, no risky auto-moves, sidecars everywhere, integrity checks.
4. **Optional everything (except the basics).** AI, scraping, backups, extra libraries — all optional and skippable.
5. **Fast and crisp.** Modern UI, instant search, responsive grid/table views.

---

## 2. Personas & Roles

- **Admin** — created in first-run wizard. Manages users, libraries, settings, jobs, backups, tag vocabulary, site capabilities. Full access.
- **User (standard)** — invited/created by an admin (no open registration). Full read/search of the shared catalog; can import, tag, add print records, generate share links, manage own API keys and own private print notes.

The catalog is **fully shared**: all users see the same items, tags, files, and images. Per-user data is limited to: private print notes, **favorites** (v1), API keys, and theme preference.

**Registration & identity.** Email is **required** and serves as the username / login identifier. There is no open registration — users join via an **admin invite link** (§13). The auth layer is designed so **SSO (OIDC/SAML)** can slot in later without a rewrite (§17).

---

## 3. Architecture

### 3.1 Containers (docker-compose)

| Container | Role |
|-----------|------|
| `nginx` | Single external entry point / reverse proxy. Serves built frontend, proxies `/api` to backend, handles file download streaming. |
| `frontend` | (Build artifact served by nginx) React + TypeScript + Vite + Tailwind + shadcn/ui. |
| `backend` | FastAPI app (REST API, auth, OpenAPI docs). |
| `worker` | Background job processor (arq/RQ) — scans, imports, thumbnail rendering, AI tagging, scraping, backups, sync. |
| `redis` | Job queue + scheduling broker. Lightweight. |
| `db` | PostgreSQL — catalog, users, tags, history, jobs, site capabilities. |

**External port:** `8973` (nginx), changeable in `docker-compose.yml`.

### 3.2 Storage model (local-path / Docker volumes)

```
./data/        -> /data        # app-owned: db data, config, backups, inbox, thumbnails cache, logs
./<library>/   -> /<libraryname>  # one or more library mounts (local disk or NAS)
```

- Multiple libraries supported. Each is mounted as its own `/<libraryname>` path and registered in the UI/settings.
- **Files are NOT organized by tags on disk.** Tags live in the DB and drive a *virtual* browse tree in the UI. This decouples "how humans find things" from "where bytes live" — re-tagging never moves files.

#### Physical layout (per library)

```
/<library>/<shard>/<itemname>-<key>/
    <itemname>-<key>.yml        # sidecar (canonical, portable, full mirror)
    model files (stl/3mf/obj/blend/f3d/step/...)
    project.zip (optional)
    images/                      # scraped + uploaded images
    renders/                     # generated PNG thumbnails
    prints/                      # gcode/3mf-project, print photos
    source.url / link file (optional)
    (sub-directories allowed — anything under itemname-key/ belongs to that item)
```

- `<shard>` = key-prefix shard (e.g. `ab/`) — even distribution, scales to 100k+ items, avoids one giant flat folder.
- `<key>` = **short hash** (6–8 char base32), unique per item. The `itemname-<key>` directory name — and the matching URL **slug** (`title`-`key`) — is the item's stable, unique identity. Two items with the same title differ by key, so names never collide. Anything inside the dir (including nested dirs) is part of that item.
- Storage layout is **stable**: a given item keeps its path for life, with **one exception** — a user **renaming the item's title** renames the `itemname-<key>` directory (only the `itemname` part changes; `<key>` never changes). **Nothing else moves files:** tag changes and reconciliation never move or rename directories. Because all references resolve by the invariant `<key>`, **share links, downloads, and API references survive a rename.** The rename obeys the atomic-move guarantee in §8.5. (Layout is a v1 decision; can be migrated later — files are self-describing via sidecars.)

### 3.3 Path display & "open source" workflow
- Item pages show the full path to the item directory.
- A user-configurable **path prefix** (e.g. `C:\prints\`) rewrites the displayed path so it matches the user's own machine/NAS mapping, with a **copy button** to quickly open the source folder in their OS file explorer.

---

## 4. Data Model (high level)

- **User** — id, email, name, role, password hash, theme pref, created.
- **ApiKey** — per-user token(s) (encrypted), label, scopes, last used.
- **Favorite** — User ↔ Item (per-user stars).
- **Invite** — token, email, created_by, expires_at (default 7 days), status (pending/accepted/expired/revoked), accepted_at.
- **PasswordResetToken** — user, token, expires_at (default 1 day), used, revoked.
- **AiProvider** — provider (claude/openai/ollama), endpoint, model, api_key (encrypted), enabled.
- **Library** — id, name, mount path, enabled.
- **Item** — id, key, title, slug, description, source URL, source site, license, **creator (optional → Creator)**, default image, library, dir path, file inventory + hashes, schema_version, timestamps.
- **File** — belongs to Item; filename, type, size, hash, mtime, role (model/zip/image/render/gcode/photo/other).
- **Image** — belongs to Item; path, source (scraped/uploaded), is_default, order.
- **Creator** — the model's designer/author. id, name, profile_url (optional), source_site (optional), `user_id` (optional FK to **User** — set when the creator is a local user who **self-designed** the item). **Optional and best-effort on an Item:** auto-filled from scraped source metadata when the site exposes it, otherwise set manually or left blank — never required. Deduplicated/mergeable like **Tag** (same designer across sites → one Creator). Powers **browse-by-creator** and the per-user **"everything I have created"** view (Items whose Creator is linked to the current user). Marking an item as your own design (import wizard / Add Asset) binds its Creator to **your** user account.
- **Tag** — canonical name, optional category/namespace, popularity count, status (active/pending), created_by.
- **TagAlias** — alias string → canonical Tag (for reconciling source-site/AI tags).
- **ItemTag** — Item ↔ Tag association.
- **PrintRecord** — Item, user, date, note, visibility (private/public), optional structured settings, attached gcode/3mf-project, attached photo(s), optional gcode-derived **filament required** (length/weight) + **estimated print time** (parsed best-effort). All fields optional. Creatable via UI or REST API (future OctoPrint feed).
- **ShareLink** — scope (single **item** *or* **full-site**), Item ref (null for site link), token, expires_at, created_by, revoked.
- **ShareAccessLog** — share link, timestamp, IP, user-agent, action (view/download). Powers the share audit trail.
- **SiteCapability** — domain, supports_anonymous_fetch, supports_token, token (encrypted), files_require_manual, notes, last_probed.
- **Job** — type, status, progress, payload, log, created/started/finished, error.
- **Issue** — type, severity, item ref, description, status (open/resolved/ignored), suggested action.
- **ChangeLogEntry** — human-readable record of automated/approved changes.
- **Setting** — instance + per-subsystem settings (incl. per-scan Auto/Review modes, sidecar⇄DB conflict mode).
- **Secrets at rest:** all credential fields above (user API keys, site tokens, AI provider keys, invite & reset tokens) are **encrypted in the database** using an instance key; the DB never stores readable secrets.

---

## 5. Tagging System

> Acknowledged as the hardest part to get right. Goal: maximum flexibility with minimum friction.

### 5.1 Tag structure
- **Flat canonical tags** with a **popularity count**.
- **Categories/namespaces** (optional) — e.g. `type:keychain`, `theme:animals`, `feature:mmu`, `printer:bambu`. Used for smarter filtering/browse; not required on every tag.
- **Aliases/synonyms** — map source-site tags and AI suggestions onto canonical tags (e.g. `multicolor` → `mmu`). Central to reconciliation.
- **New-tag approval queue** — AI/import-suggested *new* tags land in a pending state; admin/curator approves before they become canonical. Keeps vocabulary clean.

### 5.2 Virtual tag-browse tree
- The browse hierarchy (e.g. `mmu / animals / keychain`) is **derived from most-used tags in order**, **N levels deep** (default **4**, configurable in settings).
- No physical directory hierarchy is created from tags. Pure DB/UI construct.

### 5.3 Tag reconciliation on import
1. If a **sidecar** is present, read its tags first.
2. If a **source URL** exposes tags, map them via aliases onto canonical tags.
3. **With AI:** match against existing tags + suggest a *small* number of genuinely new tags (→ approval queue) based on web-scraped file/description content.
4. **Without AI:** limited matching against existing tags/aliases + the import wizard asks the user to supply required tags (heavier manual wizard).

### 5.4 Tag changes & sidecar updates
- When a user changes tags, the sidecar is updated (on-demand or queued background update).
- The scheduled **Sync** job validates sidecar ⇄ DB consistency.

---

## 6. Import / Inbox

### 6.1 Intake methods
1. **Inbox folder drop (filesystem).** User creates a folder (e.g. "Ladybug Keychain") under the inbox, drops in model files + a URL/link file + optionally a **sidecar from another instance**. A watcher/scan detects it and queues an import wizard task. A present sidecar is used to pre-fill and match.
2. **"Add Asset" button (web wizard).** Drag-drop file(s) to upload. Fields: optional source URL, required tags, optional description/license/images, optional **creator** (or a **"this is my own design"** toggle that attributes it to the current user — §4 Creator).
3. **Source URL only.** Attempt to fetch metadata/images (and files where permitted). If the site needs auth, trigger **site setup** (see 6.3).
4. **Import from another instance's share link.** Paste a share link → download all assets/metadata and reconcile against your library settings & canonical tags.

### 6.2 Import wizard (a job)
Both intake paths — manual **Add Asset** and **inbox-folder** ingest — run as a **background job that drives a completion wizard** (the inbox case enqueues a job that surfaces the wizard rather than auto-finalizing).
- **Suggests a title** (from the inbox folder name, sidecar, scraped source, or filename) that the user can **edit/correct before commit**; the final, user-confirmed title becomes the on-disk `itemname` and the URL slug. The item directory is **not created/named until the wizard is committed**, so a corrected title yields the right path the first time.
- Detects/loads sidecar if present.
- Scrapes source URL for description, images, tags, license, **and creator/designer** where permitted (reconciled/deduped against existing Creators; §4).
- Generates render thumbnail(s) for mesh files (STL/3MF/OBJ now).
- Lets user scroll images and **set a default image**.
- Reconciles tags (§5.3); enforces required tags.
- Assigns stable storage path + writes sidecar.
- AI is **optional** at every step; manual path always works.

### 6.3 Site capabilities (learned table)
- First time a new source **domain** is hit, probe it and record capabilities.
- Per-site flags: anonymous image/file fetch allowed? token supported? files require manual upload?
- Site setup flow prompts the user: provide a token, or accept that files must be supplied manually.
- Over time builds a reusable per-domain capability table.
- **Legal note:** most model sites' ToS restrict automated downloading and gate files behind login. Default behavior: scrape only public metadata/images where permitted; for files rely on user-supplied tokens or manual asset drop. Respect robots/ToS.

---

## 7. Rendering / Thumbnails

- Headless mesh rendering to PNG for **STL / 3MF / OBJ / PLY** at v1 (trimesh + pyrender/VTK or similar).
- Blender / Fusion / STEP / CAD: generic icon + any scraped/manual image at v1; optional add-on renderer containers later.
- Renders stored in the item's `renders/` dir; cache keyed to file hash.
- Re-render triggered when a model file's hash/mtime changes (see §8).

---

## 8. Reconciliation / Scan Engine

A first-class subsystem. The filesystem is a peer source of truth: users open/edit/print/save and add files outside the app.

### 8.1 Behaviors
1. **Sidecar ⇄ DB sync (bidirectional).** Sidecar edited on disk → pull in; DB changed → write sidecar out; conflicts → Issue.
2. **Re-render thumbnails on file change.** Track hash/mtime; regenerate PNGs for changed model files.
3. **Detect new / removed / extra files.** Ingest files added manually (extra STL, gcode, photo); flag missing/removed files.
4. **Orphans, dead links & integrity.** Item dirs with no DB record (and vice versa); validate source URLs still resolve; verify file hashes for corruption.

### 8.2 Auto vs. Review
- Each behavior has a setting: **Auto** (apply automatically) or **Review** (queue for approval).
- Review items appear in a **review list**; user approves → worker applies.

### 8.3 Visibility
- **Change Log** — human-readable record of every automated/approved change.
- **Issues page** — problems found (conflicts, dead links, corruption, orphans) with status + suggested action.
- **Job/Queue monitor** — live view of queued/active/failed jobs with progress, so the user can confirm the system is working or spot a hung/failed job.

### 8.4 Schedule & scheduled-jobs management
- Scans run on a **configurable schedule** (default **daily**; inotify/file-watching is a possible later enhancement) and can be triggered manually.
- A **Scheduled Jobs** view lists every recurring job — reindex, rescan/reconcile, cleanup, backup, etc. — each showing **last run** (time + outcome), **next run**, and whether it is **running now**.
- Any job can be **run manually** on demand from this view, independent of its schedule.
- This complements the live job/queue monitor (§8.3): that view shows in-flight work; this view manages recurring jobs.

### 8.5 Atomic moves & rollback
- Any operation that changes on-disk directory structure (today: only a **title rename**, §3.2) is **all-or-nothing**.
- It either completes fully — directory renamed, sidecar + DB paths + file references updated, change-log entry written — or, on **any** failure mid-operation (file locked, directory open/in use, partial copy, permission error), it **rolls back to the exact prior state** and reports a **clear, user-facing error** with the reason.
- **No half-moved state ever persists.** Implementation uses a journaled stage→verify→commit so an interrupted move (process crash) is detected and finished or undone on the next scan. The contract generalizes to **any** future structure-changing operation.

### 8.6 Per-item rescan
- An item page has a **Rescan disk** button to reconcile just that one item immediately — re-hash files, re-render changed models, ingest added files, resync the sidecar — without waiting for the scheduled scan.

---

## 9. Print History

Per item, all fields optional but all supported:
- **Note** + **visibility flag** (private/public) + **date** + logging user.
  - Private example: "Printed for my niece." Public example: "0.20 with organic supports works best."
- **Attached gcode / 3mf-project** stored in the item's `prints/` dir.
- **Structured print settings** (optional): printer, material/filament, nozzle, layer height, supports, success/fail, rating.
- **Photo of the finished print** (separate from model renders).

Public notes are visible to all users on the design and on public share pages; private notes are visible only to their author.

### 9.1 gcode metadata
On gcode upload, the slicer header comments are parsed **best-effort** to extract **filament required** (length/weight) and **estimated print time**; values are stored on the record and feed the stats below. Slicers vary (Prusa/Orca/Cura/Bambu), so fields are present when found and gracefully absent otherwise.

### 9.2 Print stats
An aggregate **print stats** view over records — total prints, success/fail rate, filament used, total/avg print time, most-printed items.

### 9.3 External print sources (future)
Print records can be created via the REST API, enabling future integrations (e.g. **OctoPrint**) to auto-log prints.

---

## 10. Sharing

- Per-design **share link**: tokenized URL, **public read-only** (no login required).
- Exposes: images, description, public tags, **public** print notes; allows **file/zip download**. Private notes hidden.
- Admin sets a **default expiry (X days)**, overridable per link. Links are **revocable**.
- Share links are also **machine-ingestible**: another PartFolder 3D instance can paste the link to import the full design (metadata + files) and reconcile against its own library. When importing from another instance, the wizard **asks whether to pull public print history**, with granular choices — **public notes / gcode / print photos / structured settings** (default: notes + photos; ask before large gcode). Private records never transfer.
- **Full-site share link (admin):** admin can mint a **read-only, downloadable** link to the **entire catalog**, expiring after X days, revocable — temporary browse/download access without an account.
- **Share audit (all links):** every share link records creation (who/when), expiry, revocation, and **access events** (timestamp, IP/user-agent where available, view vs. download). Admins can review who accessed what, when.

---

## 11. Download

- Download **individual files** directly.
- **Queue a ZIP** of the entire item directory for download (built by worker, streamed via nginx).
- A **checkbox to include print history** in the ZIP (public notes/settings + gcode + print photos); **off by default** so a normal download is just model files/images. The owner's own private records are included only for their own logged-in download, never on public share-link downloads.
- **ZIP retention is short-lived:** a queued ZIP **expires after ~1 day** and is **invalidated immediately if anything in the item directory changes**, so a download never serves stale contents.

---

## 12. Search & Browse UI

- **Search** across tags, titles, descriptions (PostgreSQL full-text).
- **Tag list** with click-to-search; filter/stack multiple tags; browse via virtual tag tree.
- **Creator** — click a creator to see all their models; a per-user **"My Creations"** view lists everything you designed yourself (Items whose Creator is linked to your account; §4).
- **Two catalog views:**
  - **Table view** — small default-image icon + key details per row.
  - **Grid view** — larger image cards.
- **Favorites** — star/unstar items; filter and sort the catalog by your favorites (per-user).
- **Item page** — image carousel (scroll, set default), full metadata, tags, **creator (linked)**, source link, license, full dir path + prefix-rewrite + copy button, downloads, print history, share-link control.
- **Theme:** dark / light / **system default**. System default applied first; user can override and the choice persists.
- Crisp, modern, fast.

---

## 13. Admin Features

- **Reindex** library / trigger full scan.
- **Scheduled backup** of **DB + config** (cron-style schedule, retention count, target under `./data/backups`). **Library files are NOT backed up** by design — prominent UI callout that the user must own their library backup strategy (libraries can be very large, e.g. 10GB+).
- **Export full details as JSON** (admin export of the entire catalog).
- **User management** (create/disable, roles).
- **Invites** — generate a tokenized invite link (valid **7 days**, revocable) to onboard a user; **invite history** shows status (pending/accepted/expired/revoked), who, and when. Email is required and is the user's login identity. (Emailing invites directly is a future enhancement; for now the link is handed off manually.)
- **Password reset** — admin generates a reset link for a user, valid **1 day**, revocable. (Emailed automatically in a future version.)
- **Full-site share link** management + **share audit** review (§10).
- **Library management** (add/remove mounts, layout/depth settings).
- **Tag administration** (approval queue, aliases, categories, merges).
- **Site capabilities** management (tokens, flags).
- **Settings** for scan Auto/Review modes, AI providers, schedules, ports/URL, path prefix default, share-link defaults, tag-tree depth.

---

## 14. AI Integration

- Providers (all optional, user supplies keys/endpoints): **Anthropic Claude**, **OpenAI**, **Local LLM (Ollama / OpenAI-compatible)**.
- Uses: tag suggestion/matching, description cleanup, web-scrape summarization.
- Rules: prefer existing canonical tags/aliases; suggest only a small number of genuinely new tags → approval queue.
- **Manual-only must always work** with zero AI configured (falls back to limited matching + heavier wizard).
- **All provider keys are stored encrypted at rest** (§4); the same applies to per-site scraping tokens and user API keys.

---

## 15. API

- **Full REST API** — everything the UI can do (search, items, tags, import, print records, share links, admin).
- Auth via **per-user API keys** managed in settings.
- **OpenAPI/Swagger** docs auto-generated by FastAPI.

---

## 16. First-Run Setup Wizard

- **Required:** create admin account + instance basics (instance name, external URL/port confirmation, time zone).
- **Skippable to Settings later:** first library path + storage layout + tag-tree depth; AI provider config; tag seed + backup schedule.

---

## 17. Out of Scope (v1) / Future

- Blender/Fusion/STEP/CAD native thumbnail rendering (add-on containers later).
- GPU-accelerated rendering (CPU-only in v1).
- Symlink-based tag-path mirror on disk (revisit if filesystem-tag browsing is desired).
- Granular per-library ACLs / per-user private libraries.
- Collections/sets per user (favorites themselves ship in v1).
- **Per-user public "maker profile" page** — browse-by-creator + the per-user "My Creations" view ship in v1 (§4/§12), but a dedicated public profile page per maker is deferred.
- Open public registration (toggle could be added later).
- **SSO (OIDC/SAML)** — auth layer is designed to accept it later.
- **Email delivery** of invites / password-resets (SMTP).
- **OctoPrint / printer API integration** to auto-log print records.
- Federated multi-instance sync beyond share-link import.

---

## 18. Resolved Decisions & Remaining Notes

**Resolved:**
1. **Key format** — short hash (6–8 char base32). Item dir and URL **slug** are both `title`-`key`, so identical titles never collide (§3.2).
2. **Rendering** — **CPU-only** in v1; GPU is a possible later option (§7, §17).
3. **ZIP retention** — expire after ~1 day; invalidate on any change in the item dir (§11).
4. **Sidecar ⇄ DB conflict resolution** — admin setting, default **last-write-wins**; options: `last-write` / `manual-optional` / `manual-required-when-both-changed` (§8.2).
5. **Scan schedule** — default **daily**; inotify/file-watching is a later enhancement (§8.4).
6. **Per-item rescan** — on-demand "Rescan disk" button on each item (§8.6).
7. **Secrets** — all tokens/keys **encrypted at rest** (§4, §14).

**Remaining implementation notes:**
- **Instance encryption key** provisioning & rotation (first-run generates it; losing it means re-entering all secrets).
- **Move journaling / crash recovery** for an interrupted directory rename (§8.5).
- **Title sanitization** rules for deriving `itemname` from a user-entered title (allowed chars, length cap, collision-proofed by `<key>`).
