<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)"  srcset="docs/images/logo-horizontal-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/images/logo-horizontal-light.png">
  <img alt="PartFolder 3D" src="docs/images/logo-horizontal-light.png" width="420">
</picture>

### A fast, self-hosted library manager for your 3D-printing & CAD files

</div>

> [!WARNING]
> 🚧 **Early development — no working code yet.** PartFolder 3D is in the design/planning
> phase. There is nothing to install or run today. This README describes the *intended*
> product, not a shipping one. Watch/star to follow along.

<div align="center">

![Status](https://img.shields.io/badge/status-planning-blue)
![Stage](https://img.shields.io/badge/stage-pre--alpha-orange)
![Code](https://img.shields.io/badge/code-none%20yet-lightgrey)
![License](https://img.shields.io/badge/license-AGPL--3.0-blue)
![PRs](https://img.shields.io/badge/PRs-not%20yet-inactive)

</div>

---

## Overview

**PartFolder 3D** is a self-hosted, Docker-based web application for managing a
personal, household, or team library of 3D-printing and CAD assets — `3MF`, `STL`,
`OBJ`, `Blender`, `Fusion`, `STEP`, and more. It aims to be a **simpler, faster
alternative** to existing tools.

The core idea: a **shared, multi-user catalog** where files live in stable, safe
locations on disk, while discovery happens through a fast, modern web UI driven by a
rich tagging system. Every item carries a **portable YAML sidecar**, so its full
metadata travels with the files — enabling manual re-import, instance-to-instance
transfer, and resilience against database loss.

> [!NOTE]
> All features below are **planned**. None of this is implemented yet — see the
> [Roadmap](#roadmap--status).

### Why / design principles

1. **Simple over clever.** Defaults should "just work."
2. **The filesystem is a peer source of truth.** People edit, print, and add files
   outside the app — so the system continuously reconciles **DB ⇄ sidecar ⇄ disk**.
3. **Never destroy or lose data.** Stable storage, no risky auto-moves, sidecars
   everywhere, integrity checks.
4. **Optional everything (except the basics).** AI, scraping, backups, extra
   libraries — all optional and skippable.
5. **Fast and crisp.** Modern UI, instant search, responsive grid/table views.

---

## Planned features

> Everything in this section is **planned**, not built.

### 📚 Catalog, search & browse
- Shared multi-user catalog — everyone sees the same items, files, and images.
- Full-text search across **tags, titles, and descriptions** (PostgreSQL FTS).
- **Table** and **grid** catalog views; per-user **favorites** (star / filter / sort).
- Item page: image carousel + default-image picker, full metadata, source link,
  license, full directory path with a configurable **path-prefix rewrite** and copy
  button to jump to the source folder on your machine.
- Theme: dark / light / **system default**, with a persisted per-user override.

### 🏷️ Tagging
- **Flat canonical tags** with popularity counts.
- Optional **categories / namespaces** (e.g. `type:keychain`, `feature:mmu`).
- **Aliases / synonyms** to fold source-site and AI tags onto canonical tags.
- **New-tag approval queue** keeps the vocabulary clean.
- **Virtual tag-browse tree** derived from the most-used tags, N levels deep
  (default 4) — purely a DB/UI construct; tags never move files on disk.

### 📥 Import & inbox
- **Inbox folder drop** — drop model files + a URL/link + an optional sidecar; a
  watcher detects it and queues an import wizard.
- **"Add Asset" web wizard** — drag-drop upload with source URL, tags, description.
- **Source-URL-only** import — fetch public metadata/images where permitted.
- **Import from another instance's share link** — pull assets + metadata and
  reconcile against your library and canonical tags.
- Wizard suggests an **editable title** before commit (becomes the on-disk name and
  slug), loads sidecars, scrapes permitted sources, and enforces required tags.

### 🖼️ Rendering & thumbnails
- Headless **CPU** mesh rendering to PNG for **STL / 3MF / OBJ / PLY** at v1.
- Blender / Fusion / STEP / CAD: generic icon + any scraped/manual image (optional
  add-on renderer containers later).
- Renders cached per file hash; re-rendered automatically when a file changes.

### 🔄 Reconciliation / scan engine
- Bidirectional **sidecar ⇄ DB sync**; conflicts raised as Issues.
- Detect **new / removed / extra** files; re-render on file change.
- **Orphans, dead links & integrity** checks (hash verification).
- Per-behavior **Auto** vs. **Review** modes, a **Change Log**, an **Issues** page,
  and a live **job/queue monitor**.
- **Atomic, all-or-nothing** directory operations with crash-safe rollback.
- Per-item **"Rescan disk"** button for on-demand reconciliation.

### 🖨️ Print history
- Per-item print records (all fields optional): note + **private/public** visibility,
  date, and logging user.
- Attach **gcode / 3mf-project** and **finished-print photos**.
- Optional **structured settings** (printer, filament, nozzle, layer height, rating).
- **Best-effort gcode parsing** for filament required + estimated print time.
- Aggregate **print stats** (totals, success rate, filament used, most-printed).

### 🔗 Sharing
- Per-design **tokenized share links** — public, read-only, optionally downloadable.
- **Full-site share link** (admin) for temporary account-less browse/download.
- Configurable default expiry, per-link override, and revocation.
- Links are **machine-ingestible** by other PartFolder 3D instances.
- **Share audit** — creation, expiry, revocation, and view/download access events.

### 🤖 AI (optional)
- Providers you supply keys for: **Anthropic Claude**, **OpenAI**, **local LLM
  (Ollama / OpenAI-compatible)**.
- Tag suggestion/matching, description cleanup, web-scrape summarization.
- Prefers existing canonical tags; routes a few genuinely new tags to the queue.
- **Manual-only always works** with zero AI configured.

### 🛠️ Admin & multi-user
- First-run wizard creates the admin; **no open registration** — users join via a
  **tokenized invite link** (7-day expiry, revocable, with invite history).
- Email is **required** and is the login identity. Auth layer designed to accept
  **SSO (OIDC/SAML)** later without a rewrite.
- Admin **password-reset** links; user management (create/disable, roles).
- **Scheduled backup of DB + config** (library files are *not* backed up by design).
- Full-catalog **JSON export**; library, tag, and site-capability administration.
- **Scheduled-jobs** view (last run / next run / running now) + manual triggers.

### 🔌 API
- **Full REST API** covering everything the UI can do.
- Auth via **per-user API keys**; **OpenAPI/Swagger** docs auto-generated by FastAPI.

### 🔐 Security
- All secrets (user API keys, site tokens, AI keys, invite/reset tokens) are
  **encrypted at rest** with an instance key — the DB never stores readable secrets.

---

## Architecture

### Container layout (docker-compose)

```
                       ┌─────────────────────────────────────────┐
        :8973  ───────▶│  nginx   (single entry point / proxy)   │
                       │   • serves built frontend               │
                       │   • proxies /api → backend              │
                       │   • streams file downloads              │
                       └───────────────┬─────────────────────────┘
                                       │
                       ┌───────────────▼──────────┐   ┌──────────────────┐
                       │  backend  (FastAPI REST) │   │  frontend (build │
                       │  auth · API · OpenAPI    │   │  artifact: React)│
                       └───────┬───────────┬──────┘   └──────────────────┘
                               │           │
                  ┌────────────▼──┐   ┌────▼───────────────────────────┐
                  │  db (Postgres)│   │  redis (job queue / scheduler) │
                  │ catalog·users │   └────┬───────────────────────────┘
                  │ tags·history  │        │
                  └───────────────┘   ┌────▼─────────────────────────────┐
                                      │ worker  scans · imports · renders │
                                      │ AI tagging · scraping · backups   │
                                      └───────────────────────────────────┘
```

| Container  | Role |
|------------|------|
| `nginx`    | Single external entry point / reverse proxy; serves frontend, proxies `/api`, streams downloads. |
| `frontend` | Build artifact (served by nginx) — React + TypeScript + Vite + Tailwind + shadcn/ui. |
| `backend`  | FastAPI app — REST API, auth, OpenAPI docs. |
| `worker`   | Background jobs — scans, imports, thumbnail rendering, AI tagging, scraping, backups, sync. |
| `redis`    | Job queue + scheduling broker. |
| `db`       | PostgreSQL — catalog, users, tags, history, jobs, capabilities. |

Default external port: **`8973`** (nginx), changeable in `docker-compose.yml`.

### Storage model

Files are **never organized by tags on disk** — tags live in the DB and drive a
*virtual* browse tree, so re-tagging never moves bytes.

```
./data/        -> /data          # app-owned: DB data, config, backups, inbox, thumbnail cache, logs
./<library>/   -> /<libraryname> # one or more library mounts (local disk or NAS)
```

Each item lives in a **stable, sharded directory** keyed by a short hash:

```
/<library>/<shard>/<itemname>-<key>/
    <itemname>-<key>.yml     # sidecar — canonical, portable, full metadata mirror
    model files (stl / 3mf / obj / blend / f3d / step / …)
    project.zip              # optional
    images/                  # scraped + uploaded images
    renders/                 # generated PNG thumbnails
    prints/                  # gcode / 3mf-project, print photos
    source.url               # optional link file
```

- `<shard>` — a key-prefix shard (e.g. `ab/`) that scales to 100k+ items.
- `<key>` — a 6–8 char base32 hash, the item's **stable, unique identity**. The
  `itemname-<key>` directory and matching URL slug share it, so duplicate titles
  never collide.
- The layout is **stable**: the only operation that ever moves files is a **title
  rename** (atomic, all-or-nothing). Because everything resolves by the invariant
  `<key>`, **share links, downloads, and API references survive a rename.**

### YAML sidecars

Every item carries a `<itemname>-<key>.yml` sidecar — a portable, full mirror of its
metadata that lives next to the files. Sidecars make items self-describing, support
manual re-import and instance-to-instance transfer, and let the catalog be rebuilt
even after database loss. The reconciliation engine keeps **DB ⇄ sidecar ⇄ disk** in
sync, raising an Issue when they genuinely conflict.

---

## Tech stack

| Layer        | Technology |
|--------------|------------|
| Frontend     | React · TypeScript · Vite · Tailwind CSS · shadcn/ui |
| Backend      | Python · FastAPI · OpenAPI/Swagger |
| Database     | PostgreSQL (full-text search) |
| Jobs / queue | Redis + worker (arq / RQ) |
| Reverse proxy| nginx |
| Rendering    | trimesh + pyrender / VTK (CPU-only, v1) |
| Packaging    | Docker + docker-compose |
| AI (optional)| Anthropic Claude · OpenAI · Ollama / OpenAI-compatible |

---

## Roadmap / status

Honest snapshot — this project is at the **planning** stage.

- [x] Product Requirements Document drafted (`PRD.md`, 18 sections)
- [x] Brand assets — logo, icons, favicons, colors (`docs/images/`)
- [ ] Repository scaffolding (docker-compose, services, CI)
- [ ] Data model + database migrations
- [ ] Authentication, invites, password reset, API keys
- [ ] Storage layout, sidecar read/write, sharding
- [ ] Reconciliation / scan engine (Auto vs. Review, Issues, Change Log)
- [ ] Import wizard + inbox watcher
- [ ] Mesh rendering / thumbnail pipeline (STL / 3MF / OBJ / PLY)
- [ ] Catalog UI — search, tag tree, table/grid views, favorites
- [ ] Print history + gcode parsing + stats
- [ ] Sharing (per-item & full-site links) + share audit
- [ ] AI-assisted tagging (optional providers)
- [ ] Admin tools — backups, JSON export, scheduled jobs
- [ ] Full REST API + OpenAPI docs
- [ ] First-run setup wizard

Indicative phases drawn from the PRD: data model → storage/sidecars → reconciliation
engine → import/render → UI → print history/sharing → AI/admin → API polish. The PRD
also tracks an explicit [out-of-scope / future](PRD.md) list (native CAD rendering,
GPU rendering, SSO, email delivery, OctoPrint integration, federated sync).

---

## Getting started

> [!WARNING]
> **Nothing to run yet.** There is no code, no published image, and no
> `docker-compose.yml` in this repository today. The steps below describe the
> **intended** future experience.

<details>
<summary><strong>Planned — not yet functional</strong></summary>

```bash
# (planned) clone and start the stack
git clone https://github.com/crzykidd/partfolder3d.git
cd partfolder3d
docker compose up -d
```

Then open **http://localhost:8973** and complete the **first-run wizard**:

1. Create the admin account + instance basics (name, external URL/port, time zone).
2. *(Optional, skippable)* add a first library path, set storage layout and tag-tree
   depth, configure an AI provider, and seed tags / a backup schedule.

The default external port is **`8973`** and is changeable in `docker-compose.yml`.

</details>

---

## Contributing

Early days! 🌱 Ideas, questions, and use-case feedback are **very welcome** — please
open an issue or start a discussion. There is **no code to contribute to yet**, so
we are not accepting code PRs at this stage. Watch or star the repo to follow
progress.

---

## License

Licensed under the **GNU Affero General Public License v3.0** (AGPL-3.0) — see
[`LICENSE`](LICENSE). In short: you're free to use, modify, and self-host PartFolder 3D,
but if you run a modified version as a network service, you must make your source
available under the same license.

© 2026 crzykidd

---

## Acknowledgements & brand

Logos, icons, and favicons live in [`docs/images/`](docs/images/) (see that folder's
[README](docs/images/README.md) for usage, the auto dark/light `<picture>` snippet,
and app `<head>` / `manifest.json` references).

**Brand colors**

| Token | Hex | Use |
|-------|-----|-----|
| Teal (primary) | `#0FA4AB` | accent, calibration cube, "3D" badge |
| Navy (ink) | `#091D35` | flat icon body, light-mode wordmark, tiles |

<div align="center">

<sub>PartFolder 3D — design/planning phase · built by <code>crzykidd</code></sub>

</div>
