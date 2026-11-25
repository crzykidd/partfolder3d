# Security audit — container images + dependencies (2026-11-25)

Research-only audit of the **currently published** v0.8.1 build. Nothing in the
codebase was changed. Raw scanner JSON was kept in a scratch dir and is not committed.

**Tooling:** Trivy 0.76.2 (`aquasec/trivy:latest`, run via docker, `--scanners vuln
--severity CRITICAL,HIGH`), pip-audit (throwaway venv, run against `pip freeze` of the
published backend image, 77 packages), `npm audit --json` in `frontend/` (read-only).

**Measured vs. estimated:** every number below is **measured** (a real image was built
and scanned) unless it is marked *(est.)*. "Candidate" images were built in scratch as
`pf3d-audit-*` and deleted after scanning. Each backend candidate also passed a smoke
test: VTK offscreen render to PNG (111 distinct grey levels, so it really rendered),
`openscad -o cube.stl` (where openscad was installed), and imports of
Pillow/cryptography/FastAPI/Starlette/lxml/trimesh. **The smoke test is not the app's
test suite.** No `make verify` was run.

**How we count:** *unique CVEs* means distinct CVE/GHSA IDs. *Instances* means
(CVE × package) pairs. One util-linux CVE, for example, shows up in 9 binary packages.
Trivy's per-package counts are the instance numbers. The headline uses unique CVEs.

---

## 1. Executive summary

| | CRITICAL | HIGH |
|---|---:|---:|
| **Shipped today, all 5 images (unique CVEs, union)** | **23** | **190** |
| Backend `partfolder3d:latest` | 14 | 135 |
| Frontend `partfolder3d-frontend:latest` (build-time only, see §2) | 4 | 47 |
| nginx `partfolder3d-nginx:latest` | 6 | 35 |
| `postgres:16-alpine` (third-party) | 1 | 26 |
| `redis:7-alpine` (third-party) | 0 | 0 |

**What's behind the numbers.**

1. **The images are stale.** Backend and frontend were built 2026-07-27 and nginx
   2026-07-22. That is four months with no rebuild. Rebuilding nginx with **no code
   change** takes it from 6/35 to **0/0**, because the floating `nginx:1.30-alpine` tag
   now resolves to 1.30.8. Rebuilding the backend unchanged removes about 40% of its
   OS findings.
2. **Nearly all language-package findings come from five stale pins.** These are
   Pillow 11.1.0 (5 CRIT, 37 HIGH), cryptography 44.0.0, python-multipart 0.0.20,
   starlette 0.41.3 (via fastapi 0.115.6) and anyio 4.7.0, plus the transitive
   PyJWT, certifi and dnspython. After a rebuild with bumped pins, the backend image
   has **zero** language-package findings.
3. **What's left can't be fixed by us.** It is Debian-trixie OS packages that Debian
   has marked `affected` with no fix yet: 85 HIGH instances (34 unique) and 1 CRIT
   (libxml2 CVE-2026-6653, no fix). They clear on their own as Debian ships fixes,
   provided we keep rebuilding.

**Fixable now:** **21 of 23 CRITICAL** and **130 of 190 HIGH** (unique) go away with
changes that are all within our control (23/190 → 2/60). What remains:

* backend: 1 CRIT + 34 HIGH that Debian has marked no-fix
* postgres: 1 CRIT + 26 HIGH, the third-party image's `gosu` Go stdlib findings, which
  only upstream can fix

| Image | Now C / H (unique) | After recommended fixes C / H (unique) | Basis |
|---|---:|---:|---|
| backend | 14 / 135 | **1 / 34** | measured (rebuild + pin bumps) |
| backend + drop Debian `openscad` (headless build) | — | **1 / 26** | measured without openscad; headless binary's runtime libs measured (+0); the binary itself *(est.)* |
| backend on Ubuntu 24.04 | — | **0 / 0** | measured, but see the caveat in §4 |
| frontend | 4 / 47 | **0 / 0** | measured (alpine-only prod stage) |
| nginx | 6 / 35 | **0 / 0** | measured (plain rebuild) |
| postgres:16-alpine | 1 / 26 | 1 / 26 | measured; 17/18-alpine are identical (all `gosu` Go stdlib) |
| redis:7-alpine | 0 / 0 | 0 / 0 | measured |

**Recommendation in one line:** keep `python:3.12-slim` on Debian trixie, but **pin
it to `-trixie`**. Rebuild on a schedule, bump the stale pins, split dev deps out of
the runtime image, and make the frontend's prod stage alpine-only. Treat
"PyPI `vtk` ≥9.4 (EGL)" as the strategic follow-up, because **OSMesa is disappearing
from Debian**.

---

## 2. Per-image findings (current published build)

Instance counts, split by package class and fix availability (Trivy):

| Image (OS) | Class | CRIT fix | CRIT no-fix | HIGH fix | HIGH no-fix |
|---|---|---:|---:|---:|---:|
| backend (Debian 13.6) | OS | 5 | 1 | 131 | 85 |
| | Python | 8 | 0 | 54 | 0 |
| frontend (Alpine 3.24.1) | OS | 0 | 0 | 5 | 0 |
| | Node + Go (esbuild binary) | 4 | 0 | 45 | 0 |
| nginx (Alpine 3.24.1) | OS | 6 | 0 | 39 | 0 |
| postgres:16-alpine (3.24.4) | OS | 0 | 0 | 1 | 0 |
| | Go stdlib in `gosu` | 1 | 0 | 25 | 0 |
| redis:7-alpine (7.4.12) | — | 0 | 0 | 0 | 0 |

**The frontend image only matters at build time.** At runtime it runs once (about a
second) to `cp` four static files into the `frontend_dist` volume, then exits. It never
listens on a port and never parses untrusted input. Every finding in it is
`node_modules` dev tooling (vite, vitest, tinypool, esbuild's Go stdlib), npm's own
bundled deps (tar, pacote, sigstore), or Alpine libs. **None of that code reaches the
browser.** Its 821 MB is what a pull costs. Treat it as low risk, but it is also the
cheapest image to fix: 821 MB → 15 MB, 0/0.

### 2.1 Backend attribution (`partfolder3d:latest`, instances)

| Source | CRIT | HIGH | Notes |
|---|---:|---:|---|
| Debian base (python:3.12-slim layer) | 4 fix + 0 | ~150 | perl-base (3 CRIT), krb5 ×4 libs (56), util-linux family, expat, sqlite, openssl, ncurses, zlib, gzip, apt. All the fixed ones clear on rebuild (13.6 → 13.8). |
| VTK / OSMesa stack (`libosmesa6`, `libgl1`, `libglib2.0-0`, LLVM 19) | 1 fix (glib) + 1 no-fix (libxml2, pulled by libllvm19) | ~45 | glib CRIT is fixed in deb13u4. libxml2 CRIT CVE-2026-6653 has no Debian fix. |
| `openscad` and its forced Qt5 GUI tree | 1 fix (libbrotli1) | 18 no-fix | Qt5 core/dbus/gui/network/printsupport/widgets (12), libcups2 (2), libxi6 (2), libxrender1, libsndfile1. Also about 210 MB (1.73 → 1.52 GB measured). |
| pip packages | 8 | 54 | Pillow 5C/37H, PyJWT 1C/6H, anyio 1C, certifi 1C, cryptography 4H, python-multipart 3H, starlette 3H, dnspython 2H |

The base-image numbers come from scanning fresh bases and diffing candidates: the
`noscad` candidate, and plain `python:3.12-slim` at 0 C / 54 H instances. The split
between the base and the VTK stack is approximate because the two share libraries.

---

## 3. Per-finding notes

### 3.1 Every CRITICAL in the shipped build

**Backend: OS packages**

| CVE | Package | Fix | Reachability / note |
|---|---|---|---|
| CVE-2026-111497 | libbrotli1 1.1.0-2+b7 | 1.1.0-2+deb13u1 | Brotli decoder OOB write. Pulled by the openscad/Qt tree. Unlikely to be reached; clears on rebuild. |
| CVE-2026-58016 | libglib2.0-0t64 | 2.84.4-3~deb13u4 | GDBus introspection underflow. We run no D-Bus. Clears on rebuild. |
| CVE-2026-13221, -42496, -8376 | perl-base 5.40.1-6 | 5.40.1-6+deb13u1 | Perl regex and Archive::Tar. Perl only runs under dpkg/apt at build time. Clears on rebuild. |
| CVE-2026-6653 | libxml2 2.9.14 (Debian) | **none** | DoS via crafted XML. The **system** libxml2 is linked by LLVM/Mesa, shared-mime-info and openscad, **not** by our XML parsing: the `lxml` wheel bundles its own libxml2. Not reachable from untrusted 3MF input. Residual. |

**Backend: Python**

| CVE / GHSA | Package (pin → fix) | Reachability | Upgrade risk |
|---|---|---|---|
| CVE-2026-112393, -112398, -112403, -112900, -96639 | Pillow 11.1.0 → **13.0.0** | Pillow is **not imported by app code**. It arrives through `vtk-osmesa → matplotlib`, and trimesh uses it to decode textures embedded in OBJ/3MF/GLB. **Untrusted model files can reach it in the worker.** That path is partly mitigated by the analyze subprocess's RLIMIT_AS, but heap overflows are in scope. | Two majors (11 → 13). We don't call Pillow directly, so risk is low. Smoke-tested OK alongside vtk-osmesa 9.3.1, matplotlib and trimesh 4.5.3. |
| CVE-2026-102268 | PyJWT 2.13.0 → 2.15.1 | Transitive via `arq → redis 5.3.1`. Our app never decodes JWTs, so **not reachable**. | Minor. Add a constraint floor. |
| CVE-2026-63374 | anyio 4.7.0 → 4.14.2 | TLS IDN hostname spoofing. **Reachable**: httpx outbound calls to AI providers and scrape targets go through anyio. | Minor. anyio is pinned directly (`anyio[trio]`, a test dep). |
| GHSA-6q48-6c7w-9gw2 | certifi 2026.7.22 → ≥2026.10.18 | Compromised emSign root CAs in the trust store. **Reachable** for every outbound HTTPS call. | None (data-only). |

**frontend** (build-time only): tinypool CVE-2026-104848/-104849 (via vitest),
tar CVE-2026-59873 (npm's bundled tar), and Go stdlib CVE-2025-68121 in the esbuild
binary. None of them runs at runtime. All disappear with the alpine-only prod stage.

**nginx**: nginx 1.30.4 has five CRITs (CVE-2026-97205, -123633, -123007, -121810,
-113425; fixed in 1.30.6 / 1.30.7), and brotli-libs has CVE-2026-111497. **This
image is internet-facing, so this is the most urgent CRIT group.** A plain rebuild picks
up nginx 1.30.8 and clears all of them. Measured result: 0/0.

**postgres:16-alpine**: CVE-2025-68121 is Go stdlib inside `gosu` (the entrypoint's
privilege drop). The docker-library maintainers treat gosu stdlib findings as not
exploitable in this use (gosu makes no network or TLS calls). 17-alpine and 18-alpine
carry the same gosu, with identical 1/26 counts. **No action. Not a reason to change
major versions.**

### 3.2 HIGHs that have a fix

* **nginx image (39 instances):** nginx 1.30.4 (5 more HIGH), libexpat (×9), libuuid
  (×7), pcre2 (×5), libxslt (×3), openssl/libssl/libcrypto, curl/libcurl, libxml2,
  libx11, tiff, zlib, musl. **All clear on rebuild** (measured 0).
* **Backend OS (131 instances):** krb5 ×4 libs (14 CVEs each), util-linux family,
  libexpat, pcre2, glib, sqlite, openssl, zstd, zlib, gzip, apt, perl. All of them
  clear on rebuild plus the trixie point release (measured: 1 fixable left, then 0
  with `apt-get upgrade`).
* **Backend Python (54 instances):**
  * **Pillow** (37 HIGH: DoS, OOB read/write, two "arbitrary code execution" via the
    JPEG encoder and crafted images, bundled libopenjp2): fix is 13.0.0. Reachable
    as described above.
  * **python-multipart** 0.0.20 → ≥0.0.30 (latest is 0.0.34). CVE-2026-24486 is an
    arbitrary file write via path traversal, plus two DoS. **Reachable**: Add Asset
    multipart upload and the import wizard. **Highest-priority Python fix.**
  * **starlette** 0.41.3 → ≥1.3.1. CVE-2025-62727 is Range-header DoS, which is
    **reachable** because our `FileResponse` downloads and share links serve Range.
    CVE-2026-48818 is UNC-path SSRF (Windows-only, not applicable). CVE-2026-54283
    means `request.form()` limits get ignored (reachable on uploads). starlette is
    pulled by **fastapi** (0.115.6 → 0.165.0), so fastapi must be bumped to get it.
  * **cryptography** 44.0.0 → 50.0.x. Its bundled-OpenSSL GHSA and subgroup attack
    don't affect us: we only use `Fernet`, so the PKCS#7 and X.509 findings are not
    reachable. Low exposure, but the version is six majors stale. Upgrade risk is low
    because the Fernet API is stable.
  * **PyJWT** (6): not reachable, see above.
  * **dnspython** 2.8.0 → 2.9.2 (2 DoS). Pulled by `email-validator`, which we don't
    call with `check_deliverability`. Low.
* **frontend (50 instances):** all build tooling or npm internals. Gone with the
  alpine prod stage.
* **postgres (26):** gosu Go stdlib. No action (see above).

### 3.3 Dependency audit (pip-audit + npm audit)

**pip-audit** (published image freeze): **133 advisories in 9 packages.**

| Package | Pin | Advisories | Fixed in | Latest | Reachable? | Upgrade risk |
|---|---|---:|---|---|---|---|
| pillow | 11.1.0 (direct) | 72 | 13.0.0 | 13.0.0 | Yes, worker texture decode | 2 majors, low (not used directly) |
| pyjwt | 2.13.0 (transitive) | 15 | 2.15.0 | 2.15.1 | No | minor |
| starlette | 0.41.3 (via fastapi) | 14 | 1.3.1 | 1.10.0 | Yes (Range, form limits) | **Major (0.x → 1.x)**, the real risk. Starlette 1.0 removed deprecated APIs (`on_startup`/`on_shutdown` → lifespan, some `TemplateResponse` signatures). Needs full verify. |
| cryptography | 44.0.0 (direct) | 12 | 50.0.0 | 50.0.2 | Barely (Fernet only) | majors, low |
| python-multipart | 0.0.20 (direct) | 12 | 0.0.31 | 0.0.34 | **Yes (uploads)** | patch-level, low |
| anyio | 4.7.0 (direct, test) | 2 | 4.14.2 | 4.16.0 | Yes (outbound TLS) | minor |
| certifi | 2026.7.22 (transitive) | 2 | 2026.10.18 | 2026.11.20 | Yes | none |
| dnspython | 2.8.0 (transitive) | 2 | 2.9.2 | 2.9.2 | Low | minor |
| pytest | 8.3.4 (dev) | 2 | 9.0.3 | — | **Should not be in the runtime image** | — |

**Stale pins without a current CVE** (latest in brackets). These are worth moving
while we're in there, each in its own step:

* fastapi 0.115.6 [0.165.0]; uvicorn 0.32.1 [0.54.0]; alembic 1.14.0 [1.20.1];
  pydantic-settings 2.7.0 [2.16.3]; asyncpg 0.30.0 [0.32.0]; SQLAlchemy 2.0.36
  [2.1.9: a minor with deprecations, keep on 2.0.x for now]; arq 0.26.1 [0.28.0];
  argon2-cffi 23.1.0 [25.1.0]; lxml 6.1.1 [6.1.3]; PyYAML 6.0.2 [6.0.4].
* **Major-version lag. Don't fold these into a security pass:** anthropic 0.112.0
  [2.14.0], openai 1.109.1 [3.59.0], selectolax 0.4.10 [1.0.2], trimesh 4.5.3
  [5.2.2]. These are API-breaking jumps. Track them as separate feature-level tasks.
* **passlib 1.7.4 is unmaintained** (last release 2020). We only use it as an argon2
  wrapper next to `argon2-cffi`. Consider calling `argon2-cffi` directly *(follow-up,
  not a CVE)*.
* **vtk-osmesa 9.3.1 is a dead end.** It is the newest build Kitware's wheel index has
  ever published, and there are **no cp313+ wheels**. See §4.2.
* **Dev/test deps ship in the production image.** `backend/requirements.txt` includes
  ruff, pytest, pytest-asyncio, pytest-xdist and `anyio[trio]`, so the runtime image
  carries pytest's 2 advisories and about 15 extra packages for no reason.

**npm audit** (`frontend/`): 12 vulnerable packages: **2 critical, 7 high, 3 moderate.**

| Package | Severity | Direct? | Fix | Ships to browser? |
|---|---|---|---|---|
| vitest (→ tinypool, @vitest/mocker) | critical | direct (dev) | vitest 5.1.2 (**semver-major**) | No (test runner) |
| tinypool | critical | transitive (dev) | via vitest 5 | No |
| vite 6.4.3 | high | direct (dev) | 6.4.4 (in range) | No (build tool, plus dev server) |
| react-router / react-router-dom 7.18.0 | high | direct | 7.18.2 (in range) | **Yes**, but the advisory is RSC-mode CSRF and we're a plain SPA. Not applicable; bump anyway. |
| postcss, nanoid, source-map-js, browserslist | high | transitive (dev) | `npm update` in range | No |
| fflate 0.6.10, baseline-browser-mapping, @vitest/mocker | moderate | transitive | in range / vitest 5 | fflate (via drei → three-stdlib) is probably tree-shaken. Our 3MF viewer uses three's own vendored fflate. Worst case is a client-side infinite loop on a malicious 3MF, which only hangs the viewer's tab. |

Net: **no npm finding is reachable in the production bundle.** One `npm update`
within current ranges clears 10 of the 12. vitest 5 is a separate dev-only major bump.

---

## 4. Base-image evaluation ("is it the best?")

**Hard constraints for the backend image:**

* glibc manylinux wheels (vtk-osmesa, so musl/alpine is out)
* system OSMesa (`libosmesa6`) for vtk-osmesa
* an `openscad` binary for `.scad → .stl`
* works under an arbitrary `PUID:PGID` (already handled by `HOME=/tmp`)
* one-command deploy

All backend candidates below use the **same bumped pins**
(`fastapi 0.165.0`, `Pillow 13.0.0`, `cryptography 50.0.2`, `python-multipart 0.34`,
`anyio 4.16`, floors on PyJWT/certifi/dnspython, dev deps removed) so that only the
base differs.

| Candidate | OS | C / H unique | C / H instances | Size | Render + openscad smoke | Verdict |
|---|---|---:|---:|---:|---|---|
| **published :latest** | Debian 13.6 | 14 / 135 | 14 / 270 | 1.76 GB | (baseline) | stale |
| same Dockerfile, rebuilt, **old pins** | Debian 13.6* | 10 / 95 | 10 / 184 | 1.77 GB | pass | rebuilding alone isn't enough |
| **`python:3.12-slim` (trixie) + bumped pins** | Debian 13.8 | **1 / 34** | 1 / 86 | 1.73 GB | pass | **recommended** |
| … + `apt-get upgrade` | Debian 13.8 | 1 / 33 | 1 / 85 | 1.73 GB | pass | marginal (+1). Rebuild cadence does the same job. |
| … without `openscad` | Debian 13.8 | 1 / 26 | 1 / 68 | 1.52 GB | render pass | openscad (Debian) = +8 unique / +18 inst HIGH, +210 MB |
| … with the runtime libs a headless openscad needs (boost, gmp, mpfr, double-conversion, fontconfig, harfbuzz, libzip, tbb), no Qt | Debian 13.8 | 1 / 26 | 1 / 68 | 1.55 GB | n/a | headless-build proxy: **+0 findings, +30 MB** (binary itself *est.*) |
| `python:3.12-slim-bookworm` + bumped pins | Debian 12.15 | 4 / 56 | 4 / 138 | 1.66 GB | pass | **worse**: older base, 4 no-fix CRIT (zlib, sqlite, glib, libxml2) |
| `python:3.13-slim` + PyPI `vtk 9.7.2` | Debian 13.8 | 1 / 39 | 1 / 91 | 1.91 GB | pass (OSMesa **and** EGL) | no CVE gain (+5 H from the 3.13 base, +180 MB); strategic, see §4.2 |
| `python:3.12-slim` + PyPI `vtk 9.7.2` | Debian 13.8 | 1 / 34 | 1 / 86 | 1.92 GB | pass | same CVEs as vtk-osmesa, +190 MB |
| `ubuntu:24.04` + distro python3.12 venv | Ubuntu 24.04 | **0 / 0** | 0 / 0 | 1.69 GB | pass | lowest *reported* count (see caveat) |
| Chainguard / Wolfi python | Wolfi | — | — | — | **not feasible** | Wolfi has **no `openscad` package and its `mesa` ships no libOSMesa** (checked via `apk`). The free Chainguard tier is latest-Python only, but vtk-osmesa is cp312 only. Distroless also kills the entrypoint shell script. |

\* The "rebuilt, old pins" candidate picked up a locally cached 13.6 base. A fresh-base
rebuild with old pins lands between that row and the recommended row *(est.)*.

**Ubuntu caveat.** Ubuntu 24.04 scans to 0 CRIT/HIGH, but much of that is **severity
triage, not fewer bugs.** Trivy reports Ubuntu's own priorities, and the same image has
166 MEDIUM + 23 LOW findings, against Debian's 238 MEDIUM + 177 LOW. Many CVEs that
NVD/Debian rate HIGH, Ubuntu rates medium. The real exposure difference is smaller
than 34 → 0.

Switching also has costs:

* We leave the official `python` image: distro python 3.12.3 + a venv, versus
  python.org 3.12.13.
* Python-version agility gets worse.
* `DEBIAN_FRONTEND` / `PATH` / venv plumbing changes in the Dockerfile.

One plus: noble still ships libosmesa6, with LTS support to 2029.

**Verdict:** a reasonable option, but not the first move. Revisit it if the 34
residual Debian no-fix HIGHs become a reporting problem (for example, a user's scanner
policy).

### 4.1 Backend recommendation

**Stay on `python:3.12-slim`, but pin the codename: `python:3.12-slim-trixie`.**

* The floating `python:3.12-slim` tag already moved from bookworm to trixie under us.
  The next Debian (forky) **has no `libosmesa6` at all**: we checked `debian:sid`, and
  Mesa upstream dropped OSMesa. An unpinned tag would one day break rendering at build
  time. Trixie has security support to about 2028 (LTS to 2030).
* Python 3.13 buys nothing today. vtk-osmesa has no cp313 wheels, and the 3.13 base
  scans slightly worse.
* bookworm is strictly worse (measured).

### 4.2 Strategic: the OSMesa runway

The Kitware `vtk-osmesa` wheel line stops at **9.3.1 / cp312**. Mesa removed OSMesa,
so Debian after trixie won't ship `libosmesa6`.

Measured in this audit: the **stock PyPI `vtk` 9.7.2** wheel renders headless in a
container, on **Python 3.13**, through **either** `vtkOSOpenGLRenderWindow` (with
libosmesa6) **or** `vtkEGLRenderWindow` (Mesa llvmpipe via `libegl1 libegl-mesa0
libgl1-mesa-dri`, with **libosmesa6 removed**). Both produced a real image (111 grey
levels). Selection works through `VTK_DEFAULT_OPENGL_WINDOW`.

That is the migration path off the dead wheel. It also unblocks Python 3.13+. It is
**not** a CVE fix (size +~180 MB, same CVE counts), so it is a planned follow-up, not
urgent.

This contradicts an assumption recorded in `requirements.txt` and the Dockerfile
comments: "the stock PyPI `vtk` wheel only ships vtkXOpenGLRenderWindow". That was true
for VTK ≤9.3. Record it in `docs/decisions.md` when the migration is done.

### 4.3 OpenSCAD's Qt5 weight

Debian's `openscad` (2021.01, four years old) hard-depends on the Qt5 GUI stack. It
costs **8 unique / 18 instance HIGH (all no-fix) + ~210 MB** (measured).

| Option | CVE impact | Effort / risk |
|---|---|---|
| **A. Headless source build in a multi-stage builder** (OpenSCAD master with `-DHEADLESS=ON -DNULLGL=ON`, Manifold backend), copying `/opt/openscad` plus about 10 runtime libs into the runtime stage | Runtime libs measured at **+0 findings**, +30 MB. Net −8 unique HIGH vs. today. The binary itself is not scanned *(est.)* | Medium. Build time adds about 10–20 min uncached in CI (gha cache helps). Must pin an OpenSCAD commit or tag. Also a large functional upgrade (2021.01 → 2025.x: Manifold makes compiles much faster), which can change output for edge-case `.scad` files. Needs a `.scad` regression smoke test. *(A trial build in this audit was blocked by the session's permission policy on cloning/building external source, so it was not measured.)* |
| B. Official OpenSCAD AppImage, extracted | Qt is bundled *inside* the AppImage, which **hides** the CVEs from Trivy instead of removing them | Low effort, but worse in substance (opaque libs, x86_64 only). **Not recommended.** |
| C. Separate optional `partfolder3d-scad` image or sidecar | Removes openscad from the main image entirely (−8 unique) | Breaks the "one command, zero manual steps" deployment rule unless it's always in compose. Adds IPC. **Not recommended.** |
| D. Keep Debian openscad | 0 | Accept 18 no-fix HIGH instances that sit in GUI libs openscad never loads for STL export (`-o out.stl` doesn't initialise Qt). Low *actual* exposure. |

**Recommendation:** D for now, since its risk is cosmetic. Do **A** as an optional later
task, mostly for the speed and size win, with the CVE drop as a bonus.

### 4.4 nginx / postgres / redis / node tags

* **nginx `1.30-alpine`:** correct line. 1.30 is the current stable branch (1.31 is
  mainline). The floating minor already picks up 1.30.8; the image is just stale.
  **Fix the cadence, not the tag.**
* **postgres `16-alpine`:** fine. 16 is supported to November 2028. 17 and 18 scan
  identically (1/26, all gosu). A major bump would need pg_upgrade or dump/restore for
  every self-hoster. **Don't move for CVEs.** If we ever move, do it for features, with
  a documented upgrade path.
* **redis `7-alpine`:** resolves to 7.4.12, 0/0. **License note:** Redis 7.4+ is
  RSALv2/SSPL, and 8.x adds AGPLv3 as a third option. 7.2 was the last BSD release.
  We pull the official image and don't redistribute or modify it, so the end-user
  impact is nil. `valkey/valkey:8-alpine` (BSD, protocol-compatible, 0/0 measured) is
  the clean-licence alternative if that ever matters. **No change needed.**
* **node `22-alpine` (frontend build):** Node 22 is maintenance LTS until April 2027.
  `node:24-alpine` (active LTS) scans 0/6 against 22's 0/10, all npm internals. Optional
  bump, and only the builder stage needs it once the prod stage is alpine-only.

---

## 5. Prioritized remediation plan (handoff-sized tasks)

Ordered by risk reduced per unit of effort. No task creates an Alembic migration.

### Task 1: Rebuild cadence + image scanning in CI *(highest leverage)*

* **Files:** `.github/workflows/publish.yml` (add a weekly `schedule:` that rebuilds
  `dev` and `main`/`latest`, or `docker/build-push-action` with `pull: true` /
  `no-cache-filters` on the base stage so base-image updates are always pulled);
  a new `.github/workflows/image-scan.yml` or a step in `ci.yml` (Trivy action,
  CRITICAL/HIGH, `ignore-unfixed: true`, SARIF upload to code-scanning, report-only
  first). Doc: `docs/architecture.md` (CI section), CHANGELOG `[Unreleased]`.
* **Owner decision needed:** whether scheduled rebuilds may republish `:latest` with
  no release. That is common practice for base-image refreshes, but it changes what
  users pull without a version bump. The alternative is to cut a patch release when
  the scan goes red.
* **Risk:** low (CI only). **Expected reduction:** stops the slide. On its own it
  would have cleared nginx 6/35 → 0/0 and about 40% of backend OS findings.
* **Verify:** no `make verify` needed. A workflow dry run is enough.

### Task 2: Backend security pin bumps + dev/runtime requirements split

* **Files:**
  * `backend/requirements.txt`: runtime-only. Bump Pillow 13.0.0, python-multipart
    0.0.34, fastapi to current (pulls starlette ≥1.3.1), uvicorn, cryptography 50.x,
    lxml 6.1.3. Add floors: `PyJWT>=2.15.1`, `certifi>=2026.11.20`, `dnspython>=2.9.2`,
    `anyio>=4.14.2`.
  * new `backend/requirements-dev.txt` (`-r requirements.txt` plus ruff, pytest\*,
    `anyio[trio]`, httpx).
  * `.github/workflows/ci.yml` and `dev-checks.yml` (install the dev file; the ruff
    grep points at the dev file).
  * `scripts/verify-backend.sh` (if it installs deps).
  * `docker-compose.dev.yml` (if the dev backend needs test deps in-container).
  * CHANGELOG.
* **Risk:** **medium, because of starlette 0.x → 1.x via fastapi.** Starlette 1.0
  removed deprecated APIs. Check for `on_startup`/`on_shutdown`, `@app.on_event`,
  `TemplateResponse(name, {...})` argument order, and `request.form()`
  limits/behaviour on the upload routes. If it bites, split the work:
  * **2a**: Pillow, multipart, cryptography, floors, dev split (low risk). This alone
    takes the backend's language CRITs from 8 to 0 and covers the reachable
    file-write CVE.
  * **2b**: fastapi/starlette (medium risk).
* **Expected reduction (measured, with a fresh base):** backend 14/135 → **1/34**
  unique. All 62 language-package instances go to 0.
* **Verify:** **full `make verify`**, plus a **built-image render and openscad smoke
  test** (thumbnail render of an STL and a 3MF, a `.scad` compile), plus an upload
  smoke test (Add Asset, import wizard).

### Task 3: Pin the backend base codename

* **Files:** `Dockerfile` (`FROM python:3.12-slim-trixie`, with a comment on the OSMesa
  removal in forky). Could fold into Task 2.
* **Risk:** none today. It prevents a future silent render break.
  **Expected reduction:** 0 now. It is a guard.
* **Verify:** image build plus render smoke.

### Task 4: Frontend prod stage → alpine-only

* **Files:** `frontend/Dockerfile`: the `prod` stage becomes `FROM alpine:3.24`, then
  `COPY --from=builder /app/dist`, `package.json`, `docker-entrypoint.sh`.
  `frontend/docker-entrypoint.sh` reads the version with `node -p`, so switch it to a
  build-time `VERSION` file or a `sed`/`grep` over package.json (it falls back to
  "unknown" without node, which is not fatal). Optionally bump the builder to
  `node:24-alpine`. CHANGELOG.
* **Risk:** low. The `dev` target is untouched, and compose uses the prod target with
  the same CMD.
* **Expected reduction (measured):** 4/47 → **0/0**, and 821 MB → **15 MB**.
* **Verify:** `make verify-frontend`, then a fresh `docker compose up` to confirm the
  volume gets populated and nginx serves it.

### Task 5: npm in-range updates

* **Files:** `frontend/package-lock.json` (`npm update`, so vite 6.4.4,
  react-router 7.18.2, postcss, nanoid, browserslist, source-map-js), optionally
  `package.json` floors. CHANGELOG.
* **Risk:** low (in-range). **Expected reduction:** npm audit 12 → 2 (the vitest pair).
* **Verify:** `make verify-frontend`.

### Task 6 (optional): vitest 5 major

* **Files:** `frontend/package.json`, lockfile, possibly the vitest config and test
  setup.
* **Risk:** medium (test-runner API changes). **Expected reduction:** the last 2 npm
  critical advisories, which are dev-only.
* **Verify:** `make verify-frontend`.

### Task 7 (optional, later): PyPI `vtk` ≥9.7 with EGL, replacing `vtk-osmesa`

* **Files:**
  * `backend/requirements.txt`: `vtk==9.7.x`, and drop the `--extra-index-url`.
  * `Dockerfile`: `libegl1 libegl-mesa0 libgl1-mesa-dri` in place of `libosmesa6`,
    plus `ENV VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow`.
  * `backend/app/worker/render_*.py`: any window-class assumptions.
  * `docs/decisions.md`, `docs/architecture.md`, CHANGELOG.
* **Risk:** medium. Renderer differences could change thumbnails, and image size grows
  by about 180 MB. **Expected reduction:** 0 CVEs. It removes the dead-end dependency
  and unblocks Python 3.13 and post-trixie Debian.
* **Verify:** **full `make verify` + render smoke test across STL/OBJ/3MF, with a
  visual compare** of thumbnails against the current renderer.

### Task 8 (optional, later): Headless OpenSCAD multi-stage build

* **Files:** `Dockerfile` (a builder stage that compiles a pinned OpenSCAD release
  headless with Manifold; the runtime stage installs about 10 libs and drops the
  `openscad` apt package). Also `docs/decisions.md` and the Dockerfile comment that
  references this as a future slimming pass, plus CHANGELOG.
* **Risk:** medium. CI build time, OpenSCAD 2021 → 2025 behaviour changes.
  **Expected reduction:** −8 unique / −18 instance HIGH and about −180 MB net
  *(est. for the binary; runtime libs measured at +0)*.
* **Verify:** full `make verify` plus a `.scad` compile regression on a few real
  models (`test_scad_render.py` plus manual checks).

### Not recommended

* Switching to bookworm (worse), Chainguard/Wolfi (infeasible), postgres major bumps
  for CVEs (no gain), the OpenSCAD AppImage (hides CVEs instead of removing them), or
  `npm audit fix --force` (forces vitest 5 unreviewed).

### Expected end state after Tasks 1–5

| Image | C / H unique (now → after) |
|---|---|
| backend | 14/135 → **1/34** (all Debian no-fix; trends to 0 with cadence) |
| frontend | 4/47 → **0/0** |
| nginx | 6/35 → **0/0** (stays there only with Task 1) |
| postgres | 1/26 → 1/26 (upstream gosu; accepted) |
| redis | 0/0 → 0/0 |
| **Total (union)** | **23/190 → 2/60** (1 libxml2 no-fix + 1 gosu; 34 Debian no-fix + 26 gosu) |
