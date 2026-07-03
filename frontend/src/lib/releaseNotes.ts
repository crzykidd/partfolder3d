/**
 * Release notes blurbs — curated "What's New" summaries, one per version.
 *
 * Keys are bare version strings (no "v" prefix), matching backend/app/version.py.
 *
 * The release-prep process should add a new entry here when bumping the version.
 * Each entry is shown in the "What's New" modal the first time a user loads the
 * app after upgrading to that version.
 */

export interface ReleaseNote {
  /** Modal headline, e.g. "What's New in v0.3.0" */
  title: string
  /** Short bullet-point items describing new features and fixes */
  bullets: string[]
  /** Full release page on GitHub */
  githubReleaseUrl: string
}

export const RELEASE_NOTES: Record<string, ReleaseNote> = {
  '0.3.0': {
    title: "What's New in v0.3.0",
    bullets: [
      'Release notes popup — see what changed after each upgrade (this dialog)',
      '3D viewer capture — save a snapshot from the viewer as a permanent item image',
      'Item file management — upload, rename, and delete files directly from the item page',
      'Extraction progress — the file list refreshes automatically when archives finish extracting',
      'AI fix — "Clean up" / "Summarize" now reads your in-progress description before it is saved',
      'AI fix — provider calls no longer block the server during slow or stuck responses',
    ],
    githubReleaseUrl: 'https://github.com/crzykidd/partfolder3d/releases/tag/v0.3.0',
  },
}

// ---------------------------------------------------------------------------
// Semver comparison
// ---------------------------------------------------------------------------

/**
 * Compare two bare semver strings as numeric triples (major.minor.patch).
 *
 * Returns:
 *  < 0  when a is older than b
 *    0  when equal
 *  > 0  when a is newer than b
 *
 * Non-numeric segments default to 0.  Pre-release suffixes are ignored.
 */
export function compareSemver(a: string, b: string): number {
  const parse = (v: string): [number, number, number] => {
    // Strip any pre-release suffix (e.g. "1.2.3-alpha" → "1.2.3")
    const clean = v.split('-')[0] ?? v
    const parts = clean.split('.').map((s) => parseInt(s, 10))
    return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0]
  }
  const [aMaj, aMin, aPat] = parse(a)
  const [bMaj, bMin, bPat] = parse(b)
  if (aMaj !== bMaj) return aMaj - bMaj
  if (aMin !== bMin) return aMin - bMin
  return aPat - bPat
}

/**
 * Return the curated notes for `version`, or null if none exist.
 */
export function getReleaseNote(version: string): ReleaseNote | null {
  return RELEASE_NOTES[version] ?? null
}
