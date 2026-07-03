# PartFolder 3D — Product Requirements Document

**Status:** Living spec — product intent & requirements; feature-level detail in [`docs/features-overview.md`](docs/features-overview.md) + [`CHANGELOG.md`](CHANGELOG.md).
**Last amended:** 2026-07-03
**Owner:** manderse

> **Scope of this document.** This PRD states durable product **intent & requirements** —
> the *what* and *why*. It is **not** a per-endpoint feature inventory or a roadmap. The
> surrounding docs each own a different slice:
> - **This PRD** — durable product intent & requirements.
> - **GitHub issues** — near-term / active planned features ("what we're building now").
> - [`docs/features-overview.md`](docs/features-overview.md) — the as-built feature catalog.
> - [`CHANGELOG.md`](CHANGELOG.md) — release history.
> - [`docs/decisions.md`](docs/decisions.md) — design-decision history.

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

The catalog is **fully shared**: all users see the same items, tags, files, and images. Per-user data (non-exhaustive) includes: private print notes, **favorites**, API keys, theme preference, navigation-layout choice, dashboard layout, and per-library path prefixes.

**Registration & identity.** Email is **required** and serves as the username / login identifier. There is no open registration — users join via an **admin invite link** (§13). The auth layer is designed so **SSO (OIDC/SAML)** can slot in later without a rewrite (§17).

---

## 3. Architecture

### 3.1 Containers (docker-compose)

| Container | Role |
|-----------|------|
| `nginx` | Single external entry point / reverse proxy. Serves built frontend, proxies `/api` to backend, handles file download streaming. |
| `frontend` | (Build artifact served by nginx) React + TypeScript + Vite + Tailwind + a custom `components/ui/` kit + minimal Radix primitives (shadcn-inspired CSS-var theming; no Mantine). |
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
    <itemname>-<key>.yml        # sidecar (canonical, portable, full mirror — schema: docs/sidecar-schema.md)
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
- Storage layout is **stable**: a given item keeps its path for life, with **one exception** — a user **renaming the item's title** renames the `itemname-<key>` directory (only the `itemname` part changes; `<key>` never changes). **Nothing else moves files:** tag changes and reconciliation never move or rename directories. Because all references resolve by the invariant `<key>`, **share links, downloads, and API references survive a rename.** The rename obeys the atomic-move guarantee in §8.5. (Layout is a current decision; can be migrated later — files are self-describing via sidecars.)

### 3.3 Path display & "open source" workflow
- Item pages show the full path to the item directory.
- User-configurable **path prefixes** rewrite the displayed path to match the user's own machine/NAS mapping, with a **copy button** to quickly open the source folder in their OS file explorer. Prefixes are set **per library × per OS** (a Windows and a POSIX prefix per library), so the same catalog resolves correctly from mixed clients.

---

## 4. Data Model (high level)

- **User** — id, email, name, role, password hash, theme pref, created.
- **ApiKey** — per-user token(s) stored **hashed** (SHA-256, shown once at creation), label, scopes, last used.
- **Favorite** — User ↔ Item (per-user stars).
- **Invite** — token, email, created_by, expires_at (default 7 days), status (pending/accepted/expired/revoked), accepted_at.
- **PasswordResetToken** — user, token, expires_at (default 1 day), used, revoked.
- **AiProvider** — provider (claude/openai/ollama), endpoint, model, api_key (encrypted), enabled.
- **Library** — id, name, mount path, enabled.
- **Item** — id, key, title, slug, description, source URL, source site, license, **creator (optional → Creator)**, default image, library, dir path, file inventory + hashes, schema_version, timestamps.
- **File** — belongs to Item; filename, type, size, hash, mtime, role (model/zip/image/render/gcode/photo/other).
- **Image** — belongs to Item; path, source (`scraped`/`uploaded`/`render`/`embedded`/`captured`), is_default, order.
- **Creator** — the model's designer/author. id, name, profile_url (optional), source_site (optional), `user_id` (optional FK to **User** — set when the creator is a local user who **self-designed** the item). **Optional and best-effort on an Item:** auto-filled from scraped source metadata when the site exposes it, otherwise set manually or left blank — never required. Deduplicated/mergeable like **Tag** (same designer across sites → one Creator). Powers **browse-by-creator** and the per-user **"everything I have created"** view (Items whose Creator is linked to the current user). Marking an item as your own design (import wizard / Add Asset) binds its Creator to **your** user account.
- **Tag** — canonical name, optional category/namespace, popularity count, status (active/pending), created_by.
- **TagAlias** — alias string → canonical Tag (for reconciling source-site/AI tags).
- **ItemTag** — Item ↔ Tag association.
- **PrintRecord** — Item, user, date, note, visibility (private/public), optional structured settings, attached gcode/3mf-project, attached photo(s), optional gcode-derived **filament required** (length/weight) + **estimated print time** (parsed best-effort). All fields optional. Creatable via UI or REST API (future OctoPrint feed).
- **ShareLink** — scope (single **item** *or* **full-site**), Item ref (null for site link), token, expires_at, created_by, revoked.
- **ShareAuditEvent** — share link, timestamp, IP, user-agent, action (view/download). Powers the share audit trail.
- **SiteCapability** — domain, `can_scrape_metadata`, `can_scrape_images`, `requires_token`, `is_manual_only`, notes, `last_probed_at`. Per-domain download credentials live in a separate **SiteToken** (`encrypted_token`).
- **Job** — type, status, progress, payload, log, created/started/finished, error.
- **Issue** — type, severity, item ref, description, status (open/resolved/ignored), suggested action.
- **ChangeLogEntry** — human-readable record of automated/approved changes.
- **Setting** — instance + per-subsystem settings (incl. per-scan Auto/Review modes). Sidecar⇄DB conflicts are surfaced as **Issues** and resolved per-item (Keep-DB / Keep-sidecar), not via a global conflict-mode switch (§8.1).
- **Secrets at rest:** the DB never stores readable secrets. One-way credentials — **user API keys** and **invite/reset tokens** — are stored **hashed** (shown once, never recoverable). Reusable credentials that must be replayed — **site download tokens** and **AI provider keys** — are stored **encrypted** with an instance key.

---

## 5. Tagging System

> Acknowledged as the hardest part to get right. Goal: maximum flexibility with minimum friction.

### 5.1 Tag structure
- **Flat canonical tags** with a **popularity count**.
- **Categories/namespaces** (optional) — e.g. `type:keychain`, `theme:animals`, `feature:mmu`, `printer:bambu`. Used for smarter filtering/browse; not required on every tag.
- **Aliases/synonyms** — map source-site tags and AI suggestions onto canonical tags (e.g. `multicolor` → `mmu`). Central to reconciliation.
- **New-tag approval queue** — AI/import-suggested *new* tags land in a pending state; admin/curator approves before they become canonical. Keeps vocabulary clean.

### 5.2 Tag cloud & popularity browse
- Tags drive browse via a **popularity-weighted tag cloud** (plus a sortable tag list) —
  **no hierarchy**. Clicking a tag filters the catalog; multiple tags stack (AND).
- **Popularity counts** size the cloud and provide a catalog **sort** option. Pure DB/UI
  construct — **tags never affect on-disk layout** (files are never organized by tags; §3.2).

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
2. **"Add Asset" button (web wizard).** Drag-drop file(s) to upload. Fields: optional source URL, tags (**encouraged**, not enforced), optional description/license/images, optional **creator** (or a **"this is my own design"** toggle that attributes it to the current user — §4 Creator).
3. **Source URL only.** Attempt to fetch metadata/images (and files where permitted). If the site needs auth, trigger **site setup** (see 6.3).
4. **Import from another instance's share link.** Paste a share link → download all assets/metadata and reconcile against your library settings & canonical tags.

### 6.2 Import wizard (a job)
Both intake paths — manual **Add Asset** and **inbox-folder** ingest — run as a **background job that drives a completion wizard** (the inbox case enqueues a job that surfaces the wizard rather than auto-finalizing).
- **Suggests a title** (from the inbox folder name, sidecar, scraped source, or filename) that the user can **edit/correct before commit**; the final, user-confirmed title becomes the on-disk `itemname` and the URL slug. The item directory is **not created/named until the wizard is committed**, so a corrected title yields the right path the first time.
- Detects/loads sidecar if present.
- Scrapes source URL for description, images, tags, license, **and creator/designer** where permitted (reconciled/deduped against existing Creators; §4).
- Generates render thumbnail(s) for server-rendered mesh files (STL/OBJ/PLY); 3MF instead surfaces its embedded slicer thumbnail (§7).
- Lets user scroll images and **set a default image**.
- Reconciles tags (§5.3); tags are **encouraged** but not enforced at commit (a zero-tag item may be committed).
- Assigns stable storage path + writes sidecar.
- AI is **optional** at every step; manual path always works.

**Import-session lifecycle & bulk import.** Both intake paths run through a persisted
**import session** rather than a one-shot form: an import can be staged, revisited, and
committed later, a **default library** applies when none is chosen, and rendering can be
toggled **per commit** (render on / off). Multiple staged items can be **bulk-committed**
in one action, and share-link imports carry granular pull flags for public print history
(§10). Endpoint-level detail is in `docs/features-overview.md`.

### 6.3 Site capabilities (learned table)
- First time a new source **domain** is hit, probe it and record capabilities.
- Per-site flags: anonymous image/file fetch allowed? token supported? files require manual upload?
- Site setup flow prompts the user: provide a token, or accept that files must be supplied manually.
- Over time builds a reusable per-domain capability table.
- **Legal note:** most model sites' ToS restrict automated downloading and gate files behind login. Default behavior: scrape only public metadata/images where permitted; for files rely on user-supplied tokens or manual asset drop. Respect robots/ToS.
- **Scraper backends are pluggable.** A direct HTTP/HTML scrape is the default; an optional **AgentQL** fallback handles sites the direct path can't parse, governed by admin budget controls (free-only / usage caps) with usage surfaced to the admin. Backend design is specified in [`docs/scrapers-spec.md`](docs/scrapers-spec.md).

---

## 7. Rendering / Thumbnails

- Headless mesh rendering to PNG for **STL / OBJ / PLY** (backend: **vtk-osmesa**, CPU-only).
- **3MF is not server-rendered** by design — it instead surfaces the **embedded slicer thumbnail**, supplemented by an in-browser viewer capture (below). This avoids re-deriving a preview a slicer already produced.
- Blender / Fusion / STEP / CAD: generic icon + any scraped/manual image for now; optional add-on renderer containers later.
- Renders stored in the item's `renders/` dir; cache keyed to file hash.
- Re-render triggered when a model file's hash/mtime changes (see §8).
- **Render mode** is an admin setting (`all` / `no_images` / `off`) governing how aggressively the worker auto-generates previews.

### 7.1 File analysis & 3D preview
Beyond thumbnails, the system extracts intent-level metadata from model files and offers an
interactive preview:
- **Mesh analysis** — best-effort filament estimate and part color count derived from geometry.
- **3MF metadata** — parses sliced-project metadata and embedded slicer thumbnails.
- **Object Breakdown** — a per-item view of the objects/parts a model contains.
- **In-browser 3D viewer** — a three.js viewer (`preview_3d`) lets a user rotate a model in
  the browser and **capture the current view** as an item Image, useful where the server
  can't render the format.

Feature-level detail is in [`docs/features-overview.md`](docs/features-overview.md).

---

## 8. Reconciliation / Scan Engine

A first-class subsystem. The filesystem is a peer source of truth: users open/edit/print/save and add files outside the app.

### 8.1 Behaviors
1. **Sidecar ⇄ DB sync (bidirectional).** Sidecar edited on disk → pull in; DB changed → write sidecar out; conflicts → Issue.
2. **Re-render thumbnails on file change.** Track hash/mtime; regenerate PNGs for changed model files.
3. **Detect new / removed / extra files.** Ingest files added manually (extra STL, gcode, photo); flag missing/removed files.
4. **Orphans, dead links & integrity.** Item dirs with no DB record (and vice versa); verify file hashes for corruption. **Source-URL ("dead link") validation is intended but not yet enabled** — the check exists in the reconcile engine but no scheduled caller currently runs it; wiring it behind a setting is future intent (active scope tracked in GitHub issues).

### 8.2 Auto vs. Review
- Each behavior has a setting: **Auto** (apply automatically) or **Review** (queue for approval).
- Review items appear in a **review list**; user approves → worker applies.

### 8.3 Visibility
- **Change Log** — human-readable record of every automated/approved change.
- **Issues page** — problems found (conflicts, dead links, corruption, orphans) with status + suggested action.
- **Job/Queue monitor** — live view of queued/active/failed jobs with progress, so the user can confirm the system is working or spot a hung/failed job. Jobs also have a **lifecycle**: they can be **cancelled, restarted/retried, archived, and cleared**, with a **retention** policy trimming old records and crash recovery reaping jobs left running when the worker died.
- **Worker resource limits.** The worker's throughput is bounded so a large library can't overwhelm the host: overall in-flight jobs and the render / analyze concurrencies are each capped (env-configurable: `WORKER_MAX_JOBS`, `RENDER_CONCURRENCY`, `ANALYZE_CONCURRENCY`), alongside container CPU/memory limits.

### 8.4 Schedule & scheduled-jobs management
- Recurring jobs run on a **fixed daily schedule** and can be **triggered manually** at any time. Per-job **configurable cron** is future intent (retention count is the tunable knob today); inotify/file-watching is a possible later enhancement.
- A **Scheduled Jobs** view lists every recurring job — reindex, rescan/reconcile, cleanup, backup, etc. — each showing **last run** (time + outcome), **next run**, and whether it is **running now**.
- Any job can be **run manually** on demand from this view, independent of its schedule.
- This complements the live job/queue monitor (§8.3): that view shows in-flight work; this view manages recurring jobs.

### 8.5 Atomic moves & rollback
- Any operation that changes on-disk directory structure (today: only a **title rename**, §3.2) is **all-or-nothing**.
- The atomic **`os.replace()` directory rename is the commit point** (the rename keeps `<key>`/`<shard>` invariant, so it's a single same-volume atomic syscall — never a copy). **Before** the commit — including a locked/in-use directory or permission error — **nothing is changed** and it reports a **clear, user-facing error** with the reason. **After** the commit, the small idempotent sidecar + DB updates **complete forward** (a failed sidecar write self-heals via the scheduled Sync job). Cross-device renames are refused, never copied.
- **No half-moved state ever persists.** Implementation uses a filesystem **journal** (`/data/journal/<key>.json`) so an interrupted move (process crash) is detected and finished-forward or rolled back on startup/next scan. **Bulk operations are N isolated per-item transactions** — a single bad/locked item fails alone (as an Issue) and never corrupts or blocks the rest. The contract generalizes to **any** future structure-changing operation. Full spec: [`docs/atomic-moves.md`](docs/atomic-moves.md).

### 8.6 Per-item rescan
- An item page has a **Rescan disk** button to reconcile just that one item immediately — re-hash files, re-render changed models, ingest added files, resync the sidecar — without waiting for the scheduled scan.

### 8.7 Local-modification / upstream-source tracking
Because the filesystem is a peer source of truth, a user may edit a model after importing it
from an upstream source. The system tracks that divergence as intent:
- An item records an **upstream baseline** (the source it was imported from and the version
  seen then). When reconciliation detects the local files have changed relative to that
  baseline, the item is flagged **locally modified**; a user can also set an explicit
  **modified override** to assert or clear that state.
- **Public share pages surface a "modified" notice** so anyone browsing a shared item knows
  it diverges from the upstream original rather than being a faithful copy.

This keeps provenance honest without blocking edits. Field-level detail is in
[`docs/features-overview.md`](docs/features-overview.md).

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
- Share links are also **machine-ingestible**: another PartFolder 3D instance can paste the link to import the full design (metadata + files) and reconcile against its own library. When importing from another instance, the wizard **asks whether to pull public print history**, with granular choices — **public notes / gcode / print photos / structured settings** (defaults: notes + photos + settings on, **gcode off** since gcode files can be large). Private records never transfer.
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
- **Tag list / popularity tag cloud** with click-to-search; filter/stack multiple tags (AND).
- **Creator** — click a creator to see all their models; a per-user **"My Creations"** view lists everything you designed yourself (Items whose Creator is linked to your account; §4).
- **Two catalog views:**
  - **Table view** — small default-image icon + key details per row.
  - **Grid view** — larger image cards.
- **Favorites** — star/unstar items; **filter** the catalog to your favorites (per-user).
- **Item page** — image carousel (scroll, set default), full metadata, tags, **creator (linked)**, source link, license, full dir path + prefix-rewrite + copy button, downloads, print history, share-link control, and **in-place file/image maintenance** (upload / rename / delete files and images; uploaded ZIPs are auto-extracted).
- **Theme:** dark / light / **system default**. System default applied first; user can override and the choice persists.
- **Personalized home & navigation (per-user).** A configurable **dashboard** of widgets/tiles, a choice of **navigation layout** (top vs. side nav), and a **Quick Start** entry point for new users — each a per-user preference (§2). Feature-level detail is in [`docs/features-overview.md`](docs/features-overview.md).
- Crisp, modern, fast.

---

## 13. Admin Features

- **Reindex** library / trigger full scan.
- **Scheduled backup** of **DB + config** (fixed daily schedule + manual run, tunable retention count, target under `./data/backups`; configurable cron is future intent). **Library files are NOT backed up** by design — prominent UI callout that the user must own their library backup strategy (libraries can be very large, e.g. 10GB+).
- **Export full details as JSON** (admin export of the entire catalog).
- **User management** (create/disable, roles).
- **Invites** — generate a tokenized invite link (valid **7 days**, revocable) to onboard a user; **invite history** shows status (pending/accepted/expired/revoked), who, and when. Email is required and is the user's login identity. (Emailing invites directly is a future enhancement; for now the link is handed off manually.)
- **Password reset** — admin generates a reset link for a user, valid **1 day**, revocable. (Emailed automatically in a future version.)
- **Full-site share link** management + **share audit** review (§10).
- **Library management** (add/remove mounts, enable/disable, purge/re-enable).
- **Tag administration** (approval queue, aliases, categories, merges).
- **Site capabilities** management (tokens, flags).
- **Settings** for scan Auto/Review modes, AI providers, ports/URL, path prefix defaults, share-link defaults, render mode, and scraper budget controls.

---

## 14. AI Integration

- Providers (all optional, user supplies keys/endpoints): **Anthropic Claude**, **OpenAI**, **Local LLM (Ollama / OpenAI-compatible)**.
- Uses: tag suggestion/matching, description cleanup, web-scrape summarization.
- Rules: prefer existing canonical tags/aliases; suggest only a small number of genuinely new tags → approval queue.
- **Manual-only must always work** with zero AI configured (falls back to limited matching + heavier wizard).
- **AI usage & cost tracking** — AI calls are metered per provider with an admin usage/cost summary, so operators can see spend at a glance.
- **Provider keys and per-site scraping tokens are stored encrypted at rest** (§4). (User API keys are stored **hashed**, not encrypted — see §4.)

---

## 15. API

- **Full REST API** — everything the UI can do (search, items, tags, import, print records, share links, admin).
- Auth via **per-user API keys** managed in settings.
- **OpenAPI/Swagger** docs auto-generated by FastAPI.

---

## 16. First-Run Setup Wizard

- **Required:** create admin account + instance basics (instance name, external URL/port confirmation, time zone).
- **Skippable to Settings later:** first library path + storage layout; AI provider config; tag seed + backup schedule.

---

## 17. Out of Scope / Future (long-term vision)

> This is the **long-term** vision boundary, not the near-term plan. **Active / near-term
> scope is tracked in GitHub issues**, not in this list.

- Blender/Fusion/STEP/CAD native thumbnail rendering (add-on containers later).
- GPU-accelerated rendering (CPU-only currently).
- Symlink-based tag-path mirror on disk (revisit if filesystem-tag browsing is desired).
- Granular per-library ACLs / per-user private libraries.
- Collections/sets per user (favorites themselves already shipped).
- **Per-user public "maker profile" page** — browse-by-creator + the per-user "My Creations" view are current features (§4/§12), but a dedicated public profile page per maker is deferred.
- Open public registration (toggle could be added later).
- **SSO (OIDC/SAML)** — auth layer is designed to accept it later.
- **Email delivery** of invites / password-resets (SMTP).
- **OctoPrint / printer API integration** to auto-log print records.
- Federated multi-instance sync beyond share-link import.

---

## 18. Design-decision history

Design-decision history has moved to [`docs/decisions.md`](docs/decisions.md).
