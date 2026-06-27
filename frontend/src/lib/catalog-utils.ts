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
