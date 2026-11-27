---
name: 2026-11-26-fastapi-starlette-bump
status: done             # pending | in-progress | done | failed
created: 2026-11-26
model: sonnet
completed: 2026-11-26
result: fastapi 0.165.0, starlette 1.10.0, uvicorn 0.54.0; gate 1027 passed; pip-audit clean
---

# Task: Security audit task 2b — bump fastapi (→ starlette ≥1.3.1) and uvicorn

Clear the 14 remaining starlette advisories (pip-audit on `backend/requirements.txt` today:
starlette 0.41.3, fixes up to 1.3.1 — Range-header DoS on our `FileResponse` downloads/shares and
`request.form()` limits ignored on uploads are reachable). starlette is pulled by fastapi
0.115.6, so bump fastapi to a current release that requires starlette ≥1.3.1, and uvicorn to
current. This is a **major** starlette jump (0.x → 1.x); deprecated APIs were removed.

## Before you start

- Read `docs/security-audit-2026-11-25.md` §3.2/§3.3 and Task 2 (the 2b split), `CLAUDE.md`,
  `docs/architecture.md` gotchas.
- Use `backend/.venv` (Python 3.12). If its interpreter is broken, recreate:
  `uv venv --python 3.12 backend/.venv && uv pip install --python backend/.venv/bin/python -r backend/requirements-dev.txt`.
- **You are the only agent running — you MAY run the full gate**, but only in the foreground:
  `docker rm -f pf3d-pg-v 2>/dev/null; make verify-backend > <scratch log> 2>&1; echo EXIT=$?` then
  read the log (never pipe `make verify` through `tail`/`head`; that masks the exit code). Never
  run it in the background, never run two at once, and `docker rm -f pf3d-pg-v` when done.
  Frontend is untouched; skip the frontend gate.

## Working tree check

`git status --porcelain`; if a file you'll touch is dirty, stop and report. This prompt is exempt.

## What to do

1. **Pick versions.** Check PyPI for the latest `fastapi` and its starlette requirement; choose the
   newest fastapi whose allowed starlette range includes ≥1.3.1 (prefer the latest stable), and
   latest `uvicorn[standard]`. Pin fastapi + uvicorn in `backend/requirements.txt`; add an explicit
   floor `starlette>=1.3.1` with a CVE comment (match the style of the existing `anyio>=` floor
   line). Check whether `pydantic` / `pydantic-settings` / `httpx` (dev) need bumps to satisfy the
   new fastapi; bump only what's required. Install into `backend/.venv`.
2. **Audit the code for removed/changed APIs** (grep the whole `backend/`):
   `on_event`, `on_startup`/`on_shutdown`, `add_event_handler`, `TemplateResponse` arg order,
   `starlette.` direct imports (e.g. `starlette.middleware`, `starlette.responses`,
   `BaseHTTPMiddleware`), `request.form(` (new `max_files`/`max_fields`/`max_part_size` defaults —
   make sure our upload routes — Add Asset multipart, import wizard, backup restore, print-record
   photo/gcode uploads — still accept our real file sizes; set explicit limits if the new defaults
   would reject legitimate uploads), `UploadFile` behaviour, `FileResponse`/`StreamingResponse`
   (Range handling, `stat_result`, headers), `TestClient`/`httpx.ASGITransport` usage in tests,
   `Mount`/`Router` signatures, exception handlers, CORS/session middleware args, and anything
   FastAPI deprecated (e.g. `regex=` → `pattern=` on Query, `example=` → `examples=`). Fix what
   breaks; fix deprecation warnings introduced by the bump where cheap.
3. **Run the backend gate** (above). Iterate until `EXIT=0`. Compare the warning count with before
   (≈30 warnings) and note any new ones.
4. **Re-run** `uvx pip-audit -r backend/requirements.txt --progress-spinner off` and record the result
   (target: 0 starlette findings; vtk-osmesa "not on PyPI" skip is expected).
5. **Container sanity (best effort):** `docker build -f backend/Dockerfile backend -t pf3d-backend-bump:test`
   (check the real Dockerfile path/context in `docker-compose.dev.yml` / CI workflow) to make sure
   the image still resolves deps. If the build is too slow or blocked, say so — the orchestrator will
   do the image smoke test. Don't push images.
6. **Docs:** `CHANGELOG.md` `[Unreleased]` → `### Security` (create the subsection if absent, following
   the format used in `[0.9.0]`): one bullet naming fastapi/starlette/uvicorn old→new versions and
   the reachable CVEs fixed. In `docs/security-audit-2026-11-25.md`, mark Task 2b as done (short note
   + date + versions). Update any `docs/architecture.md` gotcha this changes. Record non-obvious
   choices (e.g. explicit form limits) in `docs/decisions.md`.

## When done

1. Frontmatter: `status`, `completed`, `result`.
2. `mv` this file to `prompts/done/` (or `prompts/failed/`).
3. Ensure `pf3d-pg-v` is removed and no pytest processes remain.
4. **Do not commit or push.** Report: chosen versions, every code change and why, gate result
   (pass count + warning delta), pip-audit result, image-build result, and a proposed one-line
   `chore:` commit message.
