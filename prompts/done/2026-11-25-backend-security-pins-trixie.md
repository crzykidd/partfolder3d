---
name: 2026-11-25-backend-security-pins-trixie
status: done             # pending | in-progress | done | failed
created: 2026-11-25
model: sonnet
completed: 2026-11-25
result: 2a pins + dev split + trixie pin done; image smoke tests pass; not committed
---

# Task: Backend security pin bumps (low-risk set) + dev/runtime requirements split + pin base to trixie

Implements audit Tasks **2a + 3** from `docs/security-audit-2026-11-25.md` (read §3.1–3.3, §4.1,
§5 Tasks 2–3 first). Goal: clear the backend image's language-package CRITICALs (incl. the reachable
python-multipart path-traversal file write), stop shipping dev/test tools in the prod image, and pin
the base image's Debian codename so a future floating-tag change can't silently break OSMesa rendering.

**Explicitly OUT of scope (that's 2b, later): fastapi / starlette / uvicorn bumps.** Keep
`fastapi==0.115.6` and its starlette. If a 2a bump forces a fastapi/starlette change, stop and report.

## Before you start

- Read `CLAUDE.md`, the audit doc sections above, `Dockerfile`, `backend/requirements.txt`,
  `.github/workflows/ci.yml`, `.github/workflows/dev-checks.yml`, `scripts/verify-backend.sh`,
  `docker-compose.dev.yml`, `Makefile`.
- `backend/.venv` was just rebuilt on Python 3.12.13 via uv (system python is 3.14 / PEP-668). Use
  `uv pip install --python backend/.venv/bin/python ...` to sync it to the new files.
- **Do NOT run `make verify` / pytest** (the orchestrator runs the single authoritative gate). You MAY
  run pinned ruff and an import check (`backend/.venv/bin/python -c "import app.main"` from `backend/`).
- **Do NOT touch the dev stack containers** (`partfolder3d-*-1`), `pf3d-pg-v`, or `frontend/`.
  A concurrent agent edits `frontend/` — ignore its files.
- **Do NOT edit `CHANGELOG.md`** (orchestrator adds it). Docs edits listed below are allowed.

## Working tree check

`git status --porcelain`; stop and report if any file you need is dirty. Unrelated dirty files: note once.

## What to do

1. **`backend/requirements.txt` → runtime only.** Bump: Pillow → 13.0.0 (or latest 13.x),
   python-multipart → 0.0.34 (latest that the pinned fastapi 0.115.6 / its starlette accept — verify
   starlette's multipart import works with it; python-multipart renamed its module to
   `python_multipart`), cryptography → latest 50.x, lxml → 6.1.3. Add security floors:
   `PyJWT>=2.15.1`, `certifi>=2026.11.20`, `dnspython>=2.9.2`, `anyio>=4.14.2` (only those that are
   actually in the resolved tree — check; keep comments explaining they are CVE floors). Check
   whatever else the audit lists as fixable in §3.2 that is NOT fastapi/starlette/uvicorn and bump it
   if low-risk. Move ruff, pytest*, httpx-for-tests, anyio[trio] etc. out.
2. **New `backend/requirements-dev.txt`**: `-r requirements.txt` + ruff==0.8.4 (keep the pin) +
   pytest/pytest-asyncio/pytest-xdist at current pins + anything tests need that isn't runtime. Make sure
   nothing in `app/` imports a dev-only package (grep).
3. **CI**: `ci.yml` and `dev-checks.yml` install `requirements-dev.txt` for test/lint jobs; the
   `grep '^ruff=='` lines point at the dev file; `cache-dependency-path` covers both files. Don't change
   the image build/publish jobs except where needed.
4. **Dev compose / scripts**: if the dev backend container or `scripts/verify-backend.sh` relies on test
   deps being in the image, adjust (e.g. dev compose installs the dev file, or the scripts use the venv —
   check what actually runs pytest). Document how to (re)create the local venv in one line in the
   relevant doc (README dev section or `docs/architecture.md`): `uv venv --python 3.12 backend/.venv &&
   uv pip install --python backend/.venv/bin/python -r backend/requirements-dev.txt`.
5. **`Dockerfile`**: `FROM python:3.12-slim-trixie AS base`, with a comment: pinned codename because
   Debian forky drops `libosmesa6` which `vtk-osmesa` needs (see audit §4.2). Image keeps installing
   only `requirements.txt`.
6. **Sync the local venv** to `requirements-dev.txt` (uv) and run ruff + the import check.
7. **Built-image smoke test** (this is the important part — pytest doesn't cover the image):
   - `docker build -t pf3d-smoke-backend:2a .` (target runtime).
   - `docker run --rm pf3d-smoke-backend:2a python -c ...` checks: `import PIL, multipart/python_multipart,
     cryptography, lxml, vtk, trimesh, fastapi, starlette`; print versions; confirm `pytest`/`ruff` are
     NOT importable/installed.
   - **Render smoke**: inside the container, generate a small STL (trimesh box) in /tmp and render a
     thumbnail via the app's own render entrypoint (find it in `app/worker/` render code / the render
     subprocess module) — assert a non-empty PNG. Do the same for a 3MF if there's a test fixture or
     trimesh can export one.
   - **OpenSCAD smoke**: `openscad -o /tmp/c.stl` on a one-line `cube(10);` `.scad` → non-empty STL.
   - **Upload/multipart smoke**: run the app's FastAPI app with Starlette's `TestClient` (or httpx
     ASGITransport) inside the container if feasible without a DB; otherwise in the local venv post a
     multipart form to a tiny throwaway FastAPI app using the same fastapi/multipart versions to prove
     form parsing + `UploadFile` works. Don't commit throwaway scripts.
   - Trivy the image (`docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest
     image --severity CRITICAL,HIGH pf3d-smoke-backend:2a`) and report CRIT/HIGH (unique) vs the audit's
     14/135 baseline. Then `docker rmi pf3d-smoke-backend:2a`.
8. Record the decision (2a/2b split, trixie pin, dev split) in `docs/decisions.md` (newest at top).

## When done

1. Frontmatter (`status`, `completed`, `result`); move this file to `prompts/done/` (plain `mv` —
   it's untracked) or `prompts/failed/`.
2. Do **not** commit. Report: files changed, exact old→new versions, smoke-test results, trivy
   before/after, and anything the orchestrator must know for the gate (e.g. venv resync done).
