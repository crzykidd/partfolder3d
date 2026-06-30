/**
 * catalog-utils.ts — Pure helper functions for catalog UI logic.
 * Extracted for unit-testability (vitest).
 */

// ---------------------------------------------------------------------------
// Tag cloud weighting (PRD §5.2)
// ---------------------------------------------------------------------------

/** Minimum tag font size (rem ≈ 12 px at 16 px base). */
const MIN_TAG_FONT_REM = 0.75
/** Maximum tag font size (rem ≈ 16 px at 16 px base) — keeps the cloud balanced. */
const MAX_TAG_FONT_REM = 1

/**
 * Map a tag's item count to a CSS font-size string.
 *
 * Uses a log scale so high-count outliers do not balloon disproportionately.
 * Clamps between MIN_TAG_FONT_REM and MAX_TAG_FONT_REM.
 * When minCount === maxCount all tags return 1rem.
 */
export function getTagFontSize(
  count: number,
  minCount: number,
  maxCount: number,
): string {
  if (maxCount <= minCount) return '1rem'
  const range = maxCount - minCount
  // Log-normalise: gentle curve, count=minCount → 0, count=maxCount → 1
  const logNorm = Math.log(count - minCount + 1) / Math.log(range + 1)
  const size = MIN_TAG_FONT_REM + logNorm * (MAX_TAG_FONT_REM - MIN_TAG_FONT_REM)
  // Strip trailing zeros (e.g. 0.750 → 0.75)
  return `${parseFloat(size.toFixed(3))}rem`
}

/**
 * Map a tag's popularity count to a Tailwind font-weight class.
 */
export function getTagFontWeight(
  count: number,
  minCount: number,
  maxCount: number,
): 'font-normal' | 'font-medium' | 'font-semibold' | 'font-bold' {
  if (maxCount <= minCount) return 'font-normal'
  const normalized = (count - minCount) / (maxCount - minCount)
  if (normalized >= 0.7) return 'font-bold'
  if (normalized >= 0.4) return 'font-semibold'
  if (normalized >= 0.15) return 'font-medium'
  return 'font-normal'
}

// ---------------------------------------------------------------------------
// Tag cloud sort (PRD §5.2)
// ---------------------------------------------------------------------------

/** Sort mode for the tag cloud: A→Z by name or by item_count descending. */
export type TagSortMode = 'alpha' | 'number'

/** Minimal duck type accepted by sortTags — compatible with api.TagSummary. */
export interface TagForSort {
  name: string
  item_count: number
}

/**
 * Return a new sorted copy of `tags`.
 *   alpha  — A→Z by name (locale, case-insensitive)
 *   number — item_count descending; ties → name A→Z
 */
export function sortTags<T extends TagForSort>(tags: T[], mode: TagSortMode): T[] {
  if (mode === 'alpha') {
    return [...tags].sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }),
    )
  }
  return [...tags].sort(
    (a, b) =>
      b.item_count - a.item_count ||
      a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }),
  )
}

// ---------------------------------------------------------------------------
// Path prefix rewrite (PRD §3.3)
// ---------------------------------------------------------------------------

/**
 * Normalise every path separator in `path` to the chosen style.
 *
 * - 'windows': convert all `/` → `\`
 * - 'posix':   convert all `\` → `/`
 *
 * Use this to keep the saved path-prefix string consistent with the user's
 * chosen path style before persisting it.  `rewritePath`'s separator
 * inference (checks whether the prefix contains `\`) remains unchanged.
 */
export function toPathStyle(path: string, style: 'windows' | 'posix'): string {
  if (style === 'windows') return path.replace(/\//g, '\\')
  return path.replace(/\\/g, '/')
}

/**
 * Rewrite a stored dir_path using the user's local path prefix.
 *
 * Rules:
 * - If no prefix is set, return the raw path unchanged.
 * - Detect Windows-style prefix (contains backslash); convert internal
 *   slashes accordingly.
 * - Ensure the prefix ends with the appropriate separator before joining.
 */
export function rewritePath(
  dirPath: string,
  prefix: string | null | undefined,
): string {
  if (!prefix) return dirPath

  const usesWin = prefix.includes('\\')
  const sep = usesWin ? '\\' : '/'

  // Normalise internal separators to match the prefix style.
  const normalised = usesWin ? dirPath.replace(/\//g, '\\') : dirPath

  // Strip leading separator so join works correctly.
  const stripped = normalised.startsWith(sep) ? normalised.slice(sep.length) : normalised

  // Ensure prefix ends with the right separator.
  const normalPrefix = prefix.endsWith(sep) ? prefix : prefix + sep

  return normalPrefix + stripped
}

// ---------------------------------------------------------------------------
// OS detection (for per-library path rewrite)
// ---------------------------------------------------------------------------

/**
 * Detect whether the current browser is running on Windows or a posix OS
 * (Mac / Linux / iOS / Android).
 *
 * Pass a `platformHint` string to override navigator in tests.
 * Otherwise reads `navigator.userAgentData?.platform` (modern) or falls back
 * to `navigator.platform` / `navigator.userAgent`.
 *
 * Returns `'windows'` only for genuine Windows environments; everything else
 * is `'posix'`.
 */
export function detectOS(platformHint?: string): 'windows' | 'posix' {
  const src =
    platformHint ??
    (typeof navigator !== 'undefined'
      ? ((navigator as Navigator & { userAgentData?: { platform?: string } })
          .userAgentData?.platform ??
          navigator.platform ??
          navigator.userAgent)
      : '')
  return /win/i.test(src) ? 'windows' : 'posix'
}

/**
 * Rewrite a container-relative `containerPath` (e.g. the item's `dir_path`)
 * into the user's local machine path for a specific library.
 *
 * Steps:
 * 1. Strip `libraryMountPath` from the front of `containerPath`.
 * 2. Prepend `localPrefix` (the user's configured prefix for this library + OS).
 * 3. Normalise all separators to `os` style via `toPathStyle`.
 *
 * Falls back to the raw `containerPath` when `localPrefix` is absent.
 *
 * Example:
 *   containerPath    = '/library/main/Creator/Cool-Thing'
 *   libraryMountPath = '/library/main'
 *   localPrefix      = 'C:\\prints\\'
 *   os               = 'windows'
 *   → 'C:\\prints\\Creator\\Cool-Thing'
 */
export function rewriteLocalPath(
  containerPath: string,
  libraryMountPath: string,
  localPrefix: string | null | undefined,
  os: 'windows' | 'posix',
): string {
  if (!localPrefix) return containerPath

  // Strip the library mount path from the front of the container path.
  let relative = containerPath
  if (libraryMountPath && containerPath.startsWith(libraryMountPath)) {
    relative = containerPath.slice(libraryMountPath.length)
  }

  // Remove any leading separator that was left behind.
  if (relative.startsWith('/') || relative.startsWith('\\')) {
    relative = relative.slice(1)
  }

  // Normalise relative segment separators to the target OS.
  const normalizedRelative = toPathStyle(relative, os)

  // Ensure the prefix ends with the right separator then normalise it too.
  const sep = os === 'windows' ? '\\' : '/'
  const prefixWithSep =
    localPrefix.endsWith('/') || localPrefix.endsWith('\\')
      ? localPrefix
      : localPrefix + sep
  const normalizedPrefix = toPathStyle(prefixWithSep, os)

  return normalizedPrefix + normalizedRelative
}

// ---------------------------------------------------------------------------
// ZIP poll state machine (PRD §11)
// ---------------------------------------------------------------------------

export type ZipPollStatus = 'idle' | 'queued' | 'building' | 'ready' | 'failed' | 'expired'

/**
 * Map a raw backend bundle status string to the UI state.
 * Backend values: pending | ready | failed | expired
 */
export function mapBundleStatus(backendStatus: string): ZipPollStatus {
  switch (backendStatus) {
    case 'pending':
      return 'building'
    case 'ready':
      return 'ready'
    case 'failed':
      return 'failed'
    case 'expired':
      return 'expired'
    default:
      return 'queued'
  }
}

/** Whether the ZIP poll loop should continue for the given UI state. */
export function shouldContinuePolling(status: ZipPollStatus): boolean {
  return status === 'queued' || status === 'building'
}
