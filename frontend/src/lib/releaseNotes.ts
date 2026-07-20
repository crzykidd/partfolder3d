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
  '0.6.1': {
    title: "What's New in v0.6.1",
    bullets: [
      'Fixes a worker crash-loop — analyzing a very large model could out-of-memory–kill the whole background worker and retry forever, stalling all jobs',
      'Mesh analysis now runs in an isolated, memory- and time-bounded subprocess, so one bad file can never take the worker down',
      'Very large models — including huge multi-object 3MFs — are flagged "too large to analyze" and cached instead of failing on every rescan',
      'A repeatedly-failing job is now retried a bounded number of times, then marked failed instead of looping',
      'A model is no longer analyzed twice at once after a restart or double-enqueue',
    ],
    githubReleaseUrl: 'https://github.com/crzykidd/partfolder3d/releases/tag/v0.6.1',
  },
  '0.6.0': {
    title: "What's New in v0.6.0",
    bullets: [
      'Manyfold import — connect self-hosted Manyfold instances with OAuth credentials, then import a model straight from its URL',
      'Pasting a Manyfold model URL pulls the title, description, license, creator, tags, images, and 3D files directly from Manyfold’s API — no page scraping',
      'New wizard Assets step — review the pulled 3D files (checked by default) and deselect any you don’t want before committing',
      'Configure instances under Admin → AI & Scraping → Manyfold; the OAuth secret is stored encrypted and verified with a Test connection button',
      'Fix — the post-upgrade "What’s New" popup was empty for v0.5.0 and v0.5.1',
    ],
    githubReleaseUrl: 'https://github.com/crzykidd/partfolder3d/releases/tag/v0.6.0',
  },
  '0.5.1': {
    title: "What's New in v0.5.1",
    bullets: [
      'Scraped-image previews in the import wizard now display in production — the nginx Content-Security-Policy blocked images hotlinked from source sites (dev was unaffected)',
      'Custom nginx config? Reconcile your copy against the updated nginx/nginx.conf before upgrading',
      'Side-nav layout — the user menu no longer opens underneath the stat strip and right widget rail',
    ],
    githubReleaseUrl: 'https://github.com/crzykidd/partfolder3d/releases/tag/v0.5.1',
  },
  '0.5.0': {
    title: "What's New in v0.5.0",
    bullets: [
      'Pluggable fallback scrapers — FlareSolverr (free, self-hosted) and AgentQL run in a configurable priority order, each with enable/disable, timeout, Test connection, and usage tracking',
      'Scrapers admin UI — collapsible per-scraper sections, reorder priority by drag or up/down arrows',
      'URL imports can now attach model files — an "Attach Model Files" section on Review & Commit, plus a popup for zero-file imports',
      'MakerWorld imports pre-fill the Designer, a clean title, category tags, and the official full-res gallery',
      'Catalog — filter items by with/without print files, with a file icon on cards that have them',
      'Fix — the CSRF cookie now survives browser restarts; if a save fails with a CSRF error after upgrading, log out and back in once',
    ],
    githubReleaseUrl: 'https://github.com/crzykidd/partfolder3d/releases/tag/v0.5.0',
  },
  '0.4.0': {
    title: "What's New in v0.4.0",
    bullets: [
      'Security hardening — SSRF-guarded scraping, javascript:-link XSS blocked, Redis now requires a password, nginx security headers, and a fail-fast on the default DB password',
      'Jobs monitor now shows queued and analyze jobs (previously invisible)',
      'Libraries — move items between libraries, filter the catalog by library, and mount multiple library roots',
      'Import wizard — full-resolution scraped images, cleaned title/description, creator pre-fill, and a "Try to render file" viewport capture',
      'Tags — auto-approve setting + bulk "Approve all"',
      'Fixes — catalog pagination, scraped images now appear in the file list, and imported items are analyzed automatically',
      'Upgrading — set POSTGRES_PASSWORD and REDIS_PASSWORD (now required) and drain the worker queue',
    ],
    githubReleaseUrl: 'https://github.com/crzykidd/partfolder3d/releases/tag/v0.4.0',
  },
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
    // Defensive: never throw if handed a non-string (e.g. a corrupted cache or
    // localStorage value) — treat it as 0.0.0.
    const s = typeof v === 'string' ? v : ''
    // Strip any pre-release suffix (e.g. "1.2.3-alpha" → "1.2.3")
    const clean = s.split('-')[0] ?? s
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
