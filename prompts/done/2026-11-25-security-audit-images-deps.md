---
name: 2026-11-25-security-audit-images-deps
status: done             # pending | in-progress | done | failed
created: 2026-11-25
model: opus
completed: 2026-11-25
result: "Report at docs/security-audit-2026-11-25.md. Shipped 23 CRIT / 190 HIGH unique across 5 images (backend 14/135, frontend 4/47 build-only, nginx 6/35, postgres 1/26 gosu, redis 0/0); measured after-fix 2/60. Images 4 months stale; stale Pillow/multipart/starlette/cryptography pins. Recommend pin python:3.12-slim-trixie + rebuild cadence + pin bumps + alpine frontend prod stage; 8 remediation tasks."
---

# Task: Security audit — container images + dependencies (crit/high now vs. fixable)

The owner wants to know, given recent vulns: how many critical/high CVEs are in the
**current shipped build**, how many we can actually fix (and how), and whether our base
images are the best choice. **This is research only — make NO code/Dockerfile/dependency
changes.** Output is a report + a recommended remediation plan the orchestrator will turn
into follow-up coding prompts.

## Before you start

- Read `CLAUDE.md`, `docs/architecture.md` (deployment/image sections), `Dockerfile`,
  `frontend/Dockerfile`, `nginx/Dockerfile`, `docker-compose.yml`, `backend/requirements.txt`,
  `frontend/package.json` + `package-lock.json`, `.github/workflows/*` (how images build/publish).
- Images in play: `ghcr.io/crzykidd/partfolder3d` (backend+worker, `python:3.12-slim` +
  libosmesa6/libgl1/libglib2.0-0/libfreetype6/**openscad** (~370 MB Qt5 deps) + pip reqs),
  `ghcr.io/crzykidd/partfolder3d-frontend` (`node:22-alpine`, build-only; ships dist to a volume),
  `ghcr.io/crzykidd/partfolder3d-nginx` (`nginx:1.30-alpine`), plus third-party
  `postgres:16-alpine`, `redis:7-alpine`.
- No scanner is installed on the host (no trivy/grype/docker scout). Run trivy **via docker**:
  `docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v <scratch>/trivy-cache:/root/.cache aquasec/trivy:latest image --severity CRITICAL,HIGH --format json <image>`
  (also a table run for readability). Use a scratch dir under `/tmp/claude-1000/...` for
  caches/output, not the repo.
- Python: `pip-audit` via a throwaway venv in scratch (`python3 -m venv`; system python is
  PEP-668) against `backend/requirements.txt`. Node: `npm audit --json` in `frontend/`
  (read-only; do NOT `npm audit fix`).
- Do NOT touch the dev stack containers or the test PG `pf3d-pg-v`. Pulling images is fine.

## Working tree check

Run `git status --porcelain`. You should not modify any tracked file except this prompt.

## What to do

1. **Scan the current published build.** `docker pull` `ghcr.io/crzykidd/partfolder3d:latest`,
   `-frontend:latest`, `-nginx:latest`, `postgres:16-alpine`, `redis:7-alpine`. Trivy each
   (CRITICAL+HIGH). Record counts by severity, and split **OS-package vs language-package**,
   and **fixed-version-available vs no-fix**. Note the frontend image only matters at build time
   (its runtime is a copy-to-volume step) — weight it accordingly.
2. **Attribute backend-image findings**: which come from the Debian base, which from openscad's
   Qt5/GUI dependency tree, which from pip packages (vtk-osmesa, lxml, Pillow, cryptography, etc.).
3. **Dependency audit**: pip-audit + npm audit. For each vuln: package, current pin, fixed
   version, whether it's reachable in our usage (brief), and upgrade risk (major bump? breaking?).
   Also flag generally stale pins (e.g. fastapi 0.115.x, cryptography 44.x, starlette transitive)
   even without a CVE, briefly.
4. **Base-image evaluation — "is it the best?"** For the backend compare at least:
   `python:3.12-slim` (bookworm vs trixie tag), `python:3.13-slim`, a distroless/Chainguard/
   wolfi python option, and an Ubuntu option — against our hard constraints: needs OSMesa for
   vtk-osmesa, openscad binary, glibc wheels (vtk-osmesa is manylinux → alpine/musl is out),
   runs as arbitrary UID. Where feasible, actually build a throwaway candidate image (in scratch,
   tagged `pf3d-audit-*`, deleted afterwards) and trivy it, so counts are measured not guessed.
   Also evaluate options to drop openscad's Qt5 weight (e.g. official OpenSCAD AppImage/
   nightly headless build, a multi-stage copy, or a separate optional image) and its CVE impact.
   For nginx/postgres/redis: are we on the right tags (e.g. postgres 16 vs 17, redis 7 vs 8 /
   valkey license note), anything pinned to an EOL line.
5. **Measured "now vs. fixable" table**: per image, current CRIT/HIGH → after recommended fixes
   CRIT/HIGH (measured where you built a candidate, else estimated and labeled as such).
6. Clean up: remove `pf3d-audit-*` images and any containers you started.

## Deliverable

Write `docs/security-audit-2026-11-25.md` containing: executive summary (the headline numbers),
the per-image table, per-finding notes for every CRITICAL (and HIGHs that have fixes), the
base-image recommendation with rationale, and a **prioritized remediation plan** broken into
discrete tasks sized for handoff prompts (each: files touched, risk, expected CVE reduction,
whether it needs a full `make verify` + a render/openscad smoke test). Keep raw scanner JSON in
scratch only — do not commit it.

## Conventions to honor

- Research only. No edits outside `docs/security-audit-2026-11-25.md` and this prompt file.
- Don't run `make verify` / pytest (shared test PG).
- Be explicit about which numbers are measured vs. estimated.

## When done

1. Update this file's frontmatter (`status`, `completed`, `result`).
2. `git mv` this file into `prompts/done/` (or `prompts/failed/`).
3. Do **not** commit. Report back: the headline numbers, the recommendation, the remediation
   task list, and the file list + proposed message (`docs: security audit of images and
   dependencies`).
