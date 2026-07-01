---
name: 2026-07-01-codeql-triage-fix
status: done
created: 2026-07-01
model: sonnet            # security triage + fixes
completed: 2026-07-01
result: >
  Fixed 4 alert categories in code (#1 XSS, #2-5/#17-20 path injection, #21 SSRF hardening,
  #22/#32/#33 log injection). Dismissed 25 false positives via API (journal/sidecar path
  injection, UUID-gated/repr-logged log injection). All 36 alerts addressed.
---

# Task: Triage + clear the 36 CodeQL alerts on release PR #1 (security)

The first-ever CodeQL run (on the `dev → main` release PR #1) raised **36 alerts** (1 critical,
20 high, 15 medium). CodeQL is a **required release gate**, so all must be cleared — **fixed in
code** (preferred, durable) or **dismissed with a written justification** (only for true false
positives). Be conservative: when in doubt, add a real guard rather than dismiss.

## Before you start
- Read `prompts/startnewsession.md` and `CLAUDE.md`. Spawned agent on `dev`. Do NOT push, do NOT
  merge, do NOT tag. Prepare the working tree; report back. Today is 2026-07-01.
- **Per the changelog rule: every code fix here adds a `### Security` entry under
  `## [Unreleased]` in `CHANGELOG.md` in the same change.**
- The full alert inventory (number | severity | rule | path:line) is at
  `/tmp/claude-1000/-home-manderse-projects-partfolder3d/0148983d-ad1b-40a7-863f-8a68fab2264f/scratchpad/codeql_alerts.txt`.
  Re-fetch live details as needed:
  `gh api "repos/crzykidd/partfolder3d/code-scanning/alerts?ref=refs/pull/1/merge&state=open&per_page=100"`.

## The alerts (grouped)

**Critical — `py/partial-ssrf` (#21)** `backend/app/routers/import_sessions/__init__.py:52`
- `_fetch_share_link` does `client.get(url)`. The caller (line ~141-145) already calls
  `assert_safe_url(api_url)` (the Phase-10a SSRF guard blocking internal/link-local/metadata IPs),
  and the client does NOT follow redirects. **Verify** the guard truly covers the exact URL
  fetched (same value, no mutation between guard and fetch; no redirect following). If verified
  safe, this is a false positive CodeQL can't see (custom guard) → **dismiss with justification**.
  If there's any gap (e.g. guard applied to a different URL than fetched, or redirects enabled),
  **fix it** (guard the fetched URL; keep redirects off).

**High — `js/xss-through-dom` (#1)** `frontend/src/pages/import-wizard/CreatorStep.tsx:129`
- `<a href={profileUrl}>` with raw user input → a `javascript:`/`data:` URL executes on click.
  **REAL — fix.** Only render the link (or only set href) when `profileUrl` passes an
  http(s)-scheme check; otherwise don't make it a live link. Use a small helper like
  `isSafeHttpUrl(u)` (try `new URL(u)`, allow only `http:`/`https:`). This is CodeQL-recognized.

**High — `py/path-injection` (#2–#20)** in `downloads.py` (118,129,133), `shares.py`
(364,374,381), `journal.py` (123,289,325,435,437), `sidecar.py` (259,271,273,275,277,283)
- For each: determine if the path is built from **user-controlled** input (e.g. a request-supplied
  relative path/filename) or **app-controlled** (e.g. `item.dir_path` from the DB, a sanitized
  slug). 
  - **User-controlled → fix** with a CodeQL-recognized containment barrier at the sink:
    ```python
    base = Path(item_dir).resolve()
    target = (base / user_part).resolve()
    if not target.is_relative_to(base):   # py3.12 ok
        raise HTTPException(400, "Invalid path")
    ```
    (downloads/shares already have some guards — strengthen/relocate so the check is on the exact
    path that reaches the filesystem sink. Reuse existing guards; don't duplicate.)
  - **App-controlled / already-contained → dismiss** with a justification naming why the input
    can't be attacker-influenced (e.g. "path derived from DB `item.dir_path`, not request input"
    or "filename is a sanitized base32 key / slug"). journal.py + sidecar.py are largely internal
    (operate on `item.dir_path` + sanitized names) — verify before dismissing.

**Medium — `py/log-injection` (#22–#36)** across `jobs.py`, `tag_admin.py`, `journal.py`,
`import_sessions/*`, `print_records.py`, `scheduled_jobs.py`, `ssrf_guard.py`
- User input logged unsanitized (newline/CRLF forging). Low risk. Preferred: a tiny helper that
  strips CR/LF from interpolated user values at these log sites (CodeQL-recognized sanitizer),
  applied where the value is genuinely request-derived. Where the logged value is app-controlled
  (ids, counts), dismiss as false positive. Judgment call — keep it tidy, don't over-engineer.

## How to dismiss (only for verified false positives)
```
gh api -X PATCH repos/crzykidd/partfolder3d/code-scanning/alerts/<NUMBER> \
  -f state=dismissed -f dismissed_reason="false positive" \
  -f dismissed_comment="<specific justification>"
```
(`dismissed_reason` ∈ `false positive` | `won't fix` | `used in tests`.) If the token lacks the
`security_events` scope (403), STOP dismissing and instead produce a table of `#number → reason →
justification` for the owner to dismiss in the Security tab. Report which path you took.

## Verification — CPU-CAPPED (a prior run buried the host CPU)
- `backend/.venv/bin/ruff check backend/` (repo root).
- `cd frontend && npx tsc --noEmit && npx vitest run && npx vite build`.
- If you touched request-handling routers, a capped ephemeral-PG pytest of the affected test
  files is welcome but NOT the full suite (CI covers it): ephemeral PG on :5433, `alembic upgrade
  head` first, `nice -n 19 OMP_NUM_THREADS=2 backend/.venv/bin/pytest <files> -q`, tear down after.
- Add a focused frontend test for `isSafeHttpUrl` (rejects `javascript:`/`data:`, accepts http/https).

## When done
1. Update frontmatter (`status`, `completed: 2026-07-01`, `result`).
2. `git mv` into `prompts/done/`.
3. Do NOT edit `docs/decisions.md` — report the note back.
4. Do NOT commit/push. Report: (a) per-alert disposition table (fixed-in-code vs dismissed, with
   the justification for each dismissal), (b) files changed + the `### Security` CHANGELOG entry
   added, (c) whether you could dismiss via API or the owner must, (d) validation results, (e) a
   one-line `fix:`-prefixed (security) commit message.
