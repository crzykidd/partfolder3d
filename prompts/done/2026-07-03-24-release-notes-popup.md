---
name: 2026-07-03-24-release-notes-popup
status: completed
created: 2026-07-03
model: sonnet
completed: 2026-07-03
result: Implemented release-notes popup (issue #24) — localStorage-based show-once modal in AuroraShell; vitest suite passes
---

# Task: Show a release-notes popup after upgrading to a new version (issue #24)

On authenticated app load, compare the current version to the last version the user
has seen. If current is strictly newer, show a dismissible "What's New" modal once;
on dismiss, persist the current version as seen so it does not reappear until the next
upgrade.  Do not show on first-ever use.

## What was done

### New files
- `frontend/src/lib/releaseNotes.ts` — `RELEASE_NOTES` map (version → blurb), `compareSemver`, `getReleaseNote`
- `frontend/src/hooks/useReleaseNotesPopup.ts` — hook: fetches `/api/version`, reads/writes `partfolder3d-seen-version` from localStorage, computes `shouldShow`, exposes `dismiss()`
- `frontend/src/components/ReleaseNotesModal.tsx` — Aurora-palette modal with header icon, bullet list, GitHub release link, "Got it" button
- `frontend/src/test/release-notes.test.ts` — vitest suite covering compareSemver, show-once, not-on-first-use, dismiss()

### Modified files
- `frontend/src/components/shell/AuroraShell.tsx` — imports hook + modal; renders `<ReleaseNotesModal>` when `shouldShow && currentVersion`
- `CHANGELOG.md` — added entry under [Unreleased] ### Added
- `docs/decisions.md` — recorded storage choice (localStorage) and notes-source choice (frontend module)
