# PartFolder 3D — Phased Build Plan

> ⚠️ **HISTORICAL — this is the original pre-Phase-0 roadmap, kept for provenance.**
> The "Locked build-time technical decisions" below were fixed *before* Phase 0 and some
> have since been superseded — most notably the **render stack**, which collapsed to a
> single **`vtk-osmesa`** backend in v0.2.0 (pyrender/PyOpenGL/EGL removed). Treat every
> row here as "what we decided going in," not "what runs today." For current, authoritative
> state see [`decisions.md`](decisions.md) (supersessions), [`features-overview.md`](features-overview.md)
> (as-built catalog), and [`../CHANGELOG.md`](../CHANGELOG.md).

Durable roadmap for building the whole product in [`PRD.md`](../PRD.md). Each phase is a
shippable increment with explicit exit criteria. The central Opus planning session drives
this by writing a handoff prompt per phase (or per slice of a large phase) and dispatching
a Sonnet agent (see [`CLAUDE.md`](../CLAUDE.md) operating model).

> **Status (historical):** Phases 0–10 were delivered in the v0.1.0 alpha; the product has
> since shipped through **v0.3.0** (3MF reading + in-browser 3D viewer, ZIP auto-extraction,
> item file management, bulk import, worker resource limits, and more — see the CHANGELOG).
> Phase prompts live in `prompts/`; completed ones in `prompts/done/`. Full decision history
> in [`decisions.md`](decisions.md).

---

## Locked build-time technical decisions

These fill gaps the PRD intentionally left open. Recorded here + in
[`decisions.md`](decisions.md). Veto-able before Phase 0; re-litigating after costs rework.

| Area | Decision |
|---|---|
| Backend | Python 3.12, FastAPI, **SQLAlchemy 2.0 async** + asyncpg, Pydantic v2, **Alembic** migrations. Deps in `backend/requirements.txt` (CI references it). |
| Job queue | **arq** (async, Redis-backed) — fits async FastAPI. |
| UI auth | Server-side session via **httpOnly secure cookie** (opaque token, server-stored), CSRF double-submit. Password hashing **argon2id**. Programmatic API uses **per-user API keys** (Bearer). Auth wrapped behind a provider interface so **SSO (OIDC/SAML)** slots in later. |
| Secrets at rest | **Fernet** (`cryptography`); instance key auto-generated at first run into `/data/config/secret.key` (mode 0600), **never in DB**. Rotation = re-encrypt-all utility (later). |
| Version file | `backend/app/version.py` → `__version__ = "0.1.0"` (bare, per release-prep). Frontend shows it via `/api/version`. **Start at 0.1.0.** |
| DB | PostgreSQL 16. |
| Frontend | Vite + React 18 + TS + Tailwind + **shadcn/ui**; **TanStack Query** (data), **React Router** (routing), **TanStack Table** (table view), **TanStack Virtual** (large lists). Theme = CSS vars, system→light/dark, persisted per-user + localStorage. |
| Mesh render | `trimesh` for parsing (STL/OBJ/PLY). ~~offscreen render via **pyrender + EGL** with a **VTK offscreen** fallback~~ — **SUPERSEDED in v0.2.0:** the render stack collapsed to the single **`vtk-osmesa`** wheel (pyrender/PyOpenGL/EGL removed); `.3mf` is not server-rendered (embedded slicer thumbnails are used instead). See [`decisions.md`](decisions.md) 2026-07-02. |
| Image footprint | Root `Dockerfile` = backend+worker image (`ghcr.io/crzykidd/partfolder3d`). nginx serves the built frontend. CPU-only. |
| Testing | Backend **pytest**; frontend **vitest** (added as components land) + `tsc --noEmit` in CI. Lint: **ruff** (backend), tsc/eslint (frontend). |

---

## Dependency shape

```
Phase 0  Scaffolding & dev loop  ──┬─────────────────────────────────────────────
Phase 1  Identity / first-run / settings        (needs 0)
Phase 2  Libraries / storage / sidecar / item core (needs 1)
Phase 3  Catalog UI: search, browse, item page  (needs 2)
Phase 4  Worker + rendering/thumbnails          (needs 2; UI hooks need 3)
Phase 5  Import / inbox wizard                  (needs 2,4; tag reconc.)
Phase 6  Reconciliation / scan engine           (needs 2,4)
Phase 7  Print history + sharing                (needs 2,3; instance-import closes 5)
Phase 8  AI tagging (optional)                  (needs 5)
Phase 9  Admin, backup, export, API completeness (needs 1-7)
Phase 10 Hardening + v1 release                 (needs all)
```

---

## Phase 0 — Repo scaffolding & dev loop

**Goal:** `docker compose up` serves a themed app shell at `:8973` talking to a live API.
This is also what flips the CI guards on (backend → lint/migration/test, frontend → tsc,
Dockerfile → image build/publish) and lets us add the 2 CodeQL required checks.

**Deliverables**
- Monorepo: `backend/`, `frontend/`, `docker-compose.yml`, `docker-compose.dev.yml`,
  root `Dockerfile`, `.env.example`, `nginx/` config.
- Backend: FastAPI app skeleton (`backend/app/`), `version.py` (0.1.0), `/health`,
  `/api/version`, OpenAPI on; SQLAlchemy async engine + session; Alembic initialized with
  an empty baseline migration; settings via Pydantic settings reading `/data` + env.
- Services in compose: `db` (Postgres 16), `redis`, `backend`, `worker` (arq, empty queue),
  `frontend` build, `nginx` (proxy `/api` → backend, serve frontend, port 8973).
- Frontend: Vite+React+TS+Tailwind+shadcn init; app shell + nav; **theme (system/light/
  dark)** toggle; a page that fetches and shows `/api/version`.
- Tooling: `ruff` config + one passing `pytest`; `vitest` baseline + `tsc --noEmit` clean.
- **Remove the CI bootstrap guards** for the pieces now present (backend/frontend/compose/
  Dockerfile), and **add the 2 CodeQL contexts to `main` required checks** once source exists.

**Exit criteria:** compose stack boots; browser shows themed shell + version from API;
all 6 CI checks pass for real on the dev→main PR; CodeQL green and now required.

## Phase 1 — Identity, first-run, settings

**Goal:** a fresh instance bootstraps an admin, supports login, invites, and settings.

**Models:** User, ApiKey, Invite, PasswordResetToken, Setting, AiProvider (encrypted).
**Deliverables:** Fernet encryption layer + first-run key gen; argon2 auth; httpOnly
session login/logout + CSRF; per-user API keys; **first-run wizard** (admin + instance
basics; later steps skippable/stubbed); admin **user management**, **invites** (7-day,
revocable, history), **password reset** (1-day); settings framework; per-user theme persist.
**Exit:** first-run → admin login → invite a user → accept → settings editable; API-key auth works.

## Phase 2 — Libraries, storage, sidecar, item core

**Goal:** items exist on disk + DB with portable sidecars and a safe rename.

**Models:** Library, Item, File, Image, **Creator** (optional designer; nullable `user_id` link
for self-designed; deduped/mergeable like Tag — §4), Tag, TagAlias, ItemTag.
**Deliverables:** Library mounts; **storage path layer** (shard, short-hash key gen,
`itemname-<key>` dirs, title sanitization); **YAML sidecar read/write** (`schema_version`);
file inventory + hashing; **atomic journaled move/rename engine** (§8.5) used by title
rename; item CRUD API (create/list/get/update-title→rename/delete) — no wizard yet.
**Exit:** create/list/rename/delete items via API; sidecars written + valid; rename is
atomic with rollback; renaming preserves key/links.

## Phase 3 — Catalog UI: search, browse, item page

**Goal:** the catalog is usable in the browser.

**Deliverables:** Postgres full-text search (titles/desc/tags); tag list + click-to-search;
**popularity tag cloud** (sort + click-to-filter, no hierarchy); **table + grid views**; **favorites**
(star/filter/sort); **browse-by-creator + per-user "My Creations" view** (§4/§12);
**item page** (carousel + set-default, metadata, tags, creator, source/license,
full path + prefix-rewrite + copy, downloads incl. **queued ZIP** with ~1-day/invalidate
retention).
**Exit:** browse/search/filter; open an item; set default image; download a file and a ZIP.

## Phase 4 — Worker jobs + rendering/thumbnails

**Goal:** background jobs run and items get auto thumbnails.

**Deliverables:** arq worker wired; **Job** model; **job/queue monitor** UI; **scheduled-
jobs view** (last/next/running, run-now); **mesh thumbnail rendering** (STL/3MF/OBJ/PLY →
`renders/`, hash-keyed cache, re-render on change). **Begin with a headless-render spike.**
**Exit:** uploading/registering a model produces a PNG render; jobs visible + manually runnable.

## Phase 5 — Import / inbox wizard

**Goal:** the core intake flow end-to-end.

**Deliverables:** **inbox folder watcher/scan**; **"Add Asset" upload**; **import wizard
job** (title-correctable, sidecar pre-fill/match); **tag reconciliation** (existing/alias
match + required tags; manual path always works); **creator capture** (scraped/deduped, or
a "my own design" toggle → current user); **URL scrape** (metadata/images/creator) +
**site-capabilities** table + site-setup (token/manual); render on import. *(Import-from-
another-instance share link is stubbed here, completed in Phase 7.)*
**Exit:** drop a folder OR use Add Asset → wizard → committed item with tags, images,
render, sidecar at the right path.

## Phase 6 — Reconciliation / scan engine

**Goal:** the filesystem is reconciled as a peer source of truth.

**Deliverables:** sidecar⇄DB bidirectional sync; re-render on file change; detect
new/removed/extra files; orphans/dead-links/integrity; **Auto vs Review** per behavior +
review list; **Change Log**; **Issues page**; **per-item Rescan disk** button.
**Exit:** out-of-band edits/additions/deletions are detected and (auto or after review)
reconciled; conflicts + problems surface on the Issues page.

## Phase 7 — Print history + sharing

**Goal:** print records, stats, and external sharing with audit.

**Deliverables:** **PrintRecord** (note + private/public, gcode upload + **parse
filament/time**, photo, structured settings); **print stats**; **share links** (per-design
+ full-site), public read-only page + downloads, **share audit**, expiry/revoke;
**download-includes-print-history** checkbox; **instance-to-instance import** completes
Phase 5's stub (granular public-history pull).
**Exit:** log a print, see stats; mint a share link, open it logged-out, download; audit
shows access; another instance can ingest a share link.

## Phase 8 — AI tagging (optional)

**Goal:** optional AI assist; manual must still work with zero AI.

**Deliverables:** AiProvider integration (Claude/OpenAI/Ollama); tag suggestion/matching +
**new-tag approval queue**; description cleanup; web-scrape summarization; wired into the
import wizard + tag admin.
**Exit:** with a provider configured, the wizard suggests canonical-first tags + a few new
ones into the approval queue; with none configured, everything still works.

## Phase 9 — Admin, backup, export, API completeness

**Deliverables:** reindex; **scheduled DB+config backup** + retention (loud "back up your
own library" callout); **JSON export**; **tag administration** (approval/aliases/categories/
merges); **site-capabilities** management; **full REST API** parity + per-user API-key UI;
OpenAPI polish.
**Exit:** admin can back up, export, manage tags/sites/users; API covers all UI actions.

## Phase 10 — Hardening & v1 release

**Deliverables:** test coverage pass; security review (SAST already gating); performance
at ~100k items; first-run/UX polish; fill the `release-prep`/`release-cut` placeholders;
cut the release (`/release-prep` → merge → `/release-cut`).
**Exit:** a tagged GitHub release with published images; CHANGELOG as source of truth.

---

## Cross-cutting, applied every phase

- Work on `dev`; conventional commits; no `Co-authored-by:`; docs ship with code.
- Each phase: add/extend tests; keep CI green; remove any remaining CI bootstrap guards
  the phase makes real.
- Update `docs/decisions.md` for non-obvious calls; keep `PRD.md` authoritative (amend if a
  phase forces a product change).
- Honor the §18 remaining notes when their phase arrives: encryption-key provisioning
  (Phase 1), move journaling/crash recovery (Phase 2/6), title sanitization (Phase 2).
