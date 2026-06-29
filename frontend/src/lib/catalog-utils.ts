/**
 * catalog-utils.ts — Pure helper functions for catalog UI logic.
 * Extracted for unit-testability (vitest).
 */

// ---------------------------------------------------------------------------
// Tag cloud weighting (PRD §5.2)
// ---------------------------------------------------------------------------

/** Font-size steps (rem) for the popularity tag cloud. */
const TAG_SIZE_SCALE = [0.75, 0.875, 1.0, 1.125, 1.25, 1.5, 1.75, 2.0]

/**
 * Map a tag's popularity count to a CSS font-size string.
 * Scales linearly between minCount and maxCount across the size buckets.
 * When minCount === maxCount all tags return 1rem.
 */
export function getTagFontSize(
  count: number,
  minCount: number,
  maxCount: number,
): string {
  if (maxCount <= minCount) return '1rem'
  const normalized = (count - minCount) / (maxCount - minCount)
  const idx = Math.round(normalized * (TAG_SIZE_SCALE.length - 1))
  return `${TAG_SIZE_SCALE[Math.min(idx, TAG_SIZE_SCALE.length - 1)]}rem`
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
