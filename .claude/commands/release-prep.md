---
description: Prepare a release — bump version, roll changelog, sync docs, validate, commit, push to dev, open PR
argument-hint: <version>   (e.g. 0.3.6)
---

# Release Prep

You are preparing release **v$ARGUMENTS**. This command does ONLY the prep + PR
steps. It does **not** merge and does **not** create the GitHub release — the
human merges, and `/release-cut` (run after `main` CI is green) creates the
release.

## Project-specific values

| Key | Value |
|-----|-------|
| Version source-of-truth | `backend/app/version.py` — literal `__version__ = "<current>"`. Also sync `frontend/package.json` `"version": "<current>"` (same bare semver). |
| README badge pattern | `version-<current>-0FA4AB` (teal badge) |
| README What's New heading | `## What's New` |
| Docs to sync | `CLAUDE.md` — refresh the **whole** top `> **Status:**` line (version number **and** any surrounding prose, e.g. "first tagged release pending") so no stale phrase survives. |
| Changelog archiving | **None** — single living `CHANGELOG.md`; never split to `docs/CHANGELOG-<minor>.x.md` (see Step 3). |

## Local validation checks (same commands CI runs)

Run in order; stop on first failure:

```
# 1. Backend lint
ruff check backend/

# 2. Frontend build (tsc -b + vite build). MUST be `npm run build`, NOT
#    `npx tsc --noEmit`: the latter uses the root tsconfig.json (references-only)
#    and skips the project-reference strict settings (noUnusedLocals, full type
#    checks) that the prod image build enforces — it misses real build errors.
cd frontend && npm run build

# 3. Frontend tests
cd frontend && npx vitest run

# 4. Backend tests (requires live Postgres — set DATABASE_URL or skip with a note)
#    DATABASE_URL=postgresql+asyncpg://... cd backend && pytest -v

# 5. Migration check (requires live Postgres)
#    cd backend && alembic upgrade head && alembic current

# 6. Compose validation (both configs must pass)
docker compose config --quiet
docker compose -f docker-compose.dev.yml config --quiet
```

> Note: steps 4 and 5 require a live Postgres instance. If one is not available in
> the current environment, run 1–3 and 6, note the skipped steps in the commit body,
> and flag them in the PR description so CI covers them.

## Execution rules

- Work on the `dev` branch. Never push directly to `main`.
- Do NOT add `Co-authored-by` lines to the commit.
- Do NOT create the GitHub release or tag in this command.
- If any validation step fails, STOP and report — do not commit broken state.
- Make exactly ONE commit covering version + changelog + all doc updates.
- `$ARGUMENTS` is the target version. It SHOULD be bare semver, no `v` prefix
  (e.g. `0.3.6`). If a leading `v` was typed (`v0.3.6`), strip it silently and
  proceed with the bare number. After stripping, if the value is empty or does
  not match `MAJOR.MINOR.PATCH` exactly (three integers, dot-separated, no
  pre-release/build suffix), STOP and ask for a valid version.
- Reminder on the `v` convention: the version is stored and used BARE
  everywhere (`backend/app/version.py`, `frontend/package.json`, changelog header,
  README badge, in-code image tags). The `v` prefix is added in exactly one place —
  the git tag / GitHub release — and that happens in `/release-cut`, not here.

## Step 0 — Preflight

1. Confirm the current branch is `dev`. If not, STOP and report.
2. Confirm the working tree is clean (`git status --porcelain` empty). If
   there are uncommitted changes, STOP and show them — the user must decide.
3. Read the current version from `backend/app/version.py`. Parse both the current
   version and `$ARGUMENTS` into `(MAJOR, MINOR, PATCH)` integer triples for
   comparison.

### 0a — Hard stops (never proceed past these)

- **Not newer.** If `$ARGUMENTS` is not strictly greater than the current
  version (compared as integer triples, not string compare), STOP and report.
  This blocks re-running an already-shipped version, going backward, or a typo
  that lands on an old number. Equal-to-current also stops.
- **Tag already exists.** Run `git fetch --tags` then check both
  `git tag -l "v$ARGUMENTS"` and `gh release view "v$ARGUMENTS"`. If either
  exists, STOP and report — the release already exists and must not be
  clobbered.

### 0b — Bump-tier classification (warn + confirm)

Classify the jump from current → target. Only a clean single-patch bump
proceeds silently; everything else pauses for explicit confirmation.

- **Patch bump** = MAJOR and MINOR unchanged, PATCH increased.
  - If PATCH increased by exactly 1 (e.g. `0.3.3` → `0.3.4`): proceed, no
    prompt.
  - If PATCH skipped ahead (e.g. `0.3.3` → `0.3.7`): WARN that N patch
    versions were skipped, show the expected next patch (current with
    PATCH+1), and require explicit confirmation before proceeding.

- **Minor bump** = MINOR increased (MAJOR unchanged), e.g. `0.3.3` → `0.4.0`.
  ALWAYS warn and require confirmation, even for the clean `.0` case. Message:
  this is a **new minor release**, which is infrequent — confirm it's
  intended. If the target is a minor bump but PATCH is not `0` (e.g.
  `0.3.3` → `0.4.2`), additionally flag that new minors normally start at
  `.0`.

- **Major bump** = MAJOR increased, e.g. `0.3.3` → `1.0.0`. ALWAYS warn with
  strong language and require explicit confirmation: this is a **major
  release**, the rarest and most consequential bump, and it produces a new
  `:<major>` image tag. If MINOR or PATCH is not `0` (e.g. `1.2.0`),
  additionally flag that major releases normally start at `X.0.0`.

When warning, always show the three "expected next" successors from the
current version so the user can see what they may have meant:
next patch (`MAJOR.MINOR.PATCH+1`), next minor (`MAJOR.MINOR+1.0`),
next major (`MAJOR+1.0.0`).

Do not proceed on any warned tier without a clear affirmative ("yes",
"confirmed", etc.) in the chat. If the user declines, STOP.

### 0c — Remaining setup

4. Capture today's date as `YYYY-MM-DD` for the changelog header. (There is no
   archive trigger — Step 3 never archives, regardless of bump tier.)

## Step 1 — Bump the version

Update `backend/app/version.py` so `__version__ = "<current>"` reflects
`$ARGUMENTS`. Also update `frontend/package.json` `"version": "<current>"` to
match. These two are the only version source-of-truth files — CI and the in-app
version display both read from `backend/app/version.py` (via `GET /api/version`).
Do not touch helper functions or surrounding code.

## Step 2 — Roll the changelog

In `CHANGELOG.md`:

1. Change the `## [Unreleased]` header to `## [$ARGUMENTS] — <today>`.
2. Insert a fresh empty `## [Unreleased]` block (matching whatever HTML-comment
   skeleton the file already uses) directly above the new version header.
3. Leave the rolled section's entries exactly as written by the dev work — do
   not rewrite them, but DO sanity-check that every entry is user-facing prose
   and sits under a correct category heading (Added / Changed / Fixed /
   Security / Deprecated / Removed). Fix obvious miscategorisation only.
4. If the `[Unreleased]` section is empty (no entries to ship), STOP and
   report — there is nothing to release.

## Step 3 — Changelog archiving: NONE (single living changelog)

**Do not archive anything, on any bump tier.** This project keeps a **single living
`CHANGELOG.md`** — every release, oldest to newest, stays in full Keep-a-Changelog
detail in that one file. There is **no** per-minor archive, no summarize-on-archive
step, and no `docs/CHANGELOG-<minor>.x.md` files. (An earlier archive-on-minor policy
was dropped — see `docs/decisions.md`.)

The only maintenance here is the reference-link block at the bottom of `CHANGELOG.md`:

1. Under the "Release history policy" footer, update the comparison reference links so
   they cover the new release. Add a `[$ARGUMENTS]:
   https://github.com/crzykidd/partfolder3d/compare/v<previous-tag>...v$ARGUMENTS` line,
   and repoint the `[Unreleased]:` link to `...compare/v$ARGUMENTS...HEAD`.
2. Confirm the active `CHANGELOG.md` still holds `[Unreleased]` + **every** prior
   release in **full detail** (nothing moved out, nothing summarized).

## Step 4 — Sync the README

In `README.md`:

1. Update the version badge: replace `version-<old>-0FA4AB` with
   `version-$ARGUMENTS-0FA4AB` in the badge `src` URL.
2. Add a `### v$ARGUMENTS (<today>)` entry at the top of the `## What's New`
   section, summarising this release in user-facing language drawn from the
   changelog entries you just rolled. Keep it consistent with the voice of the
   existing entries.
3. Update any top-of-file new-in banner / one-line status blurb to reference
   `$ARGUMENTS` if it currently names a specific version.

## Step 5 — Sync long-form docs

For `CLAUDE.md`:
- Find the top `> **Status:**` block and refresh the **entire Status line**, not just
  the version number. Update the version reference **and** re-read the surrounding
  prose for anything now false: stale lifecycle phrases like "first tagged release
  pending", "pre-release", "unreleased", "N migrations", etc. must be corrected or
  removed so no obsolete claim survives the bump. (This phrase-sync gap is exactly why
  "first tagged release pending" outlived seven releases — don't reintroduce it.)
- Do not invent new sections — only adjust content in that Status block.

## Step 6 — Validate locally BEFORE committing

Run the local validation checks listed in the "Local validation checks" section
above. If ANY check fails, STOP, report exactly what failed, and do not commit.

Also grep for version-string drift: confirm no stale `<old-version>`
references remain in `README.md`, `backend/app/version.py`,
`frontend/package.json`, or `CLAUDE.md`. Report any other occurrences you find
rather than blindly editing.

## Step 6b — Check for nginx config changes

Run:

```bash
git diff v<previous-tag>..HEAD -- nginx/nginx.conf
```

(Replace `<previous-tag>` with the most recent release tag, e.g. `v0.2.2`.)

If `nginx/nginx.conf` has changed since the previous release tag, prepend a
prominent callout to the changelog section you are about to roll:

```
> ⚠️ **nginx config changed** — if you are running a custom nginx config
> (the `./nginx/nginx.conf` bind-mount in `docker-compose.yml`), compare your
> copy against the updated `nginx/nginx.conf` in this release and reconcile any
> differences before upgrading.
```

Place the callout at the very top of the `## [$ARGUMENTS] — <today>` block,
before the `### Added` / `### Changed` / etc. entries.

If `nginx/nginx.conf` has NOT changed, skip this step with no action.

## Step 7 — Commit

Stage everything and make ONE commit. Use a conventional-commit subject and a
body that lists what changed. Template:

```
chore(release): prepare v$ARGUMENTS

- backend/app/version.py bumped to $ARGUMENTS
- frontend/package.json bumped to $ARGUMENTS
- CHANGELOG: rolled [Unreleased] → [$ARGUMENTS] — <today>; compare-link refs updated
- README: version badge + What's New entry
- CLAUDE.md: Status line refreshed (version + surrounding prose)
```

No `Co-authored-by` lines.

## Step 8 — Push and open the PR

1. `git push origin dev`.
2. Open a PR `dev` → `main` with `gh pr create`:
   - Title: `Release v$ARGUMENTS`
   - Body: this release's CHANGELOG section (the `[$ARGUMENTS]` block you just
     rolled), so the PR description is the release notes. This is the same
     text `/release-cut` will use as the GitHub release body — single source
     of truth.
3. Capture the PR URL.

## Step 9 — Report and STOP

Print a short summary:

- The PR URL.
- Confirmation that local validation passed.
- The exact next steps for the human, verbatim:
  1. Review the PR on GitHub and wait for CI to go green.
  2. Merge the PR into `main`.
  3. Wait for the push-to-`main` build to publish `:latest` to the registry.
  4. Run `/release-cut $ARGUMENTS` to tag and publish the GitHub release.

Do NOT proceed past this point. Do not merge. Do not tag.
