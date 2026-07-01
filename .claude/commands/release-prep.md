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
| Docs to sync | `CLAUDE.md` — update the top `> **Status:**` line to reference the new version if it names a specific version. |
| Changelog archive dir | `docs/` (archive files: `docs/CHANGELOG-<minor>.x.md`) |

## Local validation checks (same commands CI runs)

Run in order; stop on first failure:

```
# 1. Backend lint
ruff check backend/

# 2. Frontend type-check
cd frontend && npx tsc --noEmit

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
  intended. Note that a new minor also fires the changelog archive trigger
  (Step 3). If the target is a minor bump but PATCH is not `0` (e.g.
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

4. Determine whether this is a **new minor/major** (MINOR or MAJOR differs from
   current) or a **patch within the current minor**. This decides whether the
   archive trigger fires (Step 3): minor and major bumps archive **every closed
   minor series** still in the active file; patch bumps archive nothing.
5. Capture today's date as `YYYY-MM-DD` for the changelog header.

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

## Step 3 — Per-minor archive trigger (MINOR/MAJOR ONLY — summarize-on-archive)

Run this step only when Step 0 determined this is a **new minor (`0.x.0`) or
major (`x.0.0`) bump**. For a **patch release** (e.g. `0.3.6`), do NOT archive
anything — skip this step entirely.

Archive **every closed minor series** still living in the active `CHANGELOG.md`
(every series whose MINOR is below the new current minor), not just the
immediately-prior one — this clears any deferred backlog in one pass. For each
such closed series `<minor>.x`:

1. **Move the full detail to the archive.** Move the entire series (all its
   `## [<minor>.PATCH] — <date>` blocks, full content) out of `CHANGELOG.md` into
   `docs/CHANGELOG-<minor>.x.md`, newest-first, matching the format of any
   existing archive file. Full Keep-a-Changelog detail is preserved here.
2. **Leave a summary in the active file.** In place of each moved version, write a
   condensed summary block:
   - Heading: `## [<version>] — <date> (summary)`.
   - Body: **one bullet per major feature or fix.** Use judgment to **drop
     small/trivial entries** (typo fixes, copy tweaks, minor internal cleanups);
     keep user-visible features and significant fixes. Phrase each as a tight
     one-liner.
   - End the block with a deep link to the full archived section, e.g.
     `[Full notes →](docs/CHANGELOG-<minor>.x.md#<anchor>)`
     (anchor = the GitHub-style slug of the full header, e.g. `031--2026-06-21`).
3. Prepend a link to each new archive file in the "Archived releases" index at the
   bottom of `CHANGELOG.md` (create the index if absent).
4. Confirm the active `CHANGELOG.md` now holds `[Unreleased]` + the **current**
   minor series in **full detail** + each older minor as a **summary block** (with
   archive deep links).

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
- Find the top `> **Status:**` block and update it to reflect the new release
  if it currently names a specific version (e.g. change "alpha" + a specific
  version reference). Do not invent new sections — only adjust content that
  already references a version.

## Step 6 — Validate locally BEFORE committing

Run the local validation checks listed in the "Local validation checks" section
above. If ANY check fails, STOP, report exactly what failed, and do not commit.

Also grep for version-string drift: confirm no stale `<old-version>`
references remain in `README.md`, `backend/app/version.py`,
`frontend/package.json`, or `CLAUDE.md`. Report any other occurrences you find
rather than blindly editing.

## Step 7 — Commit

Stage everything and make ONE commit. Use a conventional-commit subject and a
body that lists what changed. Template:

```
chore(release): prepare v$ARGUMENTS

- backend/app/version.py bumped to $ARGUMENTS
- frontend/package.json bumped to $ARGUMENTS
- CHANGELOG: rolled [Unreleased] → [$ARGUMENTS] — <today>
- README: version badge + What's New entry
- CLAUDE.md: Status line updated
<- archive line ONLY if a new-minor archive was performed>
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
