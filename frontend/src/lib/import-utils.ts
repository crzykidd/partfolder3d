/**
 * import-utils.ts — Pure helper functions for the import wizard UI.
 *
 * All functions here are stateless and testable with vitest (no React deps).
 */

// ---------------------------------------------------------------------------
// Wizard step definitions
// ---------------------------------------------------------------------------

export type WizardStep = 'title' | 'images' | 'tags' | 'creator' | 'assets' | 'summary'

export const WIZARD_STEPS: WizardStep[] = [
  'title',
  'images',
  'tags',
  'creator',
  'assets',
  'summary',
]

export const STEP_LABELS: Record<WizardStep, string> = {
  title: 'Title',
  images: 'Images',
  tags: 'Tags',
  creator: 'Creator',
  assets: 'Assets',
  summary: 'Review & Commit',
}

/**
 * Steps visible for this wizard run. The 'assets' (file-selection) step only
 * appears when the session has staged files — a metadata-only session (e.g.
 * a URL import with nothing downloadable) skips straight from Creator to
 * Summary. `hasFiles` defaults to false so callers that don't pass it get
 * the original 5-step sequence unchanged.
 */
export function visibleSteps(hasFiles = false): WizardStep[] {
  return hasFiles ? WIZARD_STEPS : WIZARD_STEPS.filter((s) => s !== 'assets')
}

/** Navigate to the next step, clamping at the last step. */
export function nextStep(current: WizardStep, hasFiles = false): WizardStep {
  const steps = visibleSteps(hasFiles)
  const idx = steps.indexOf(current)
  if (idx < 0 || idx >= steps.length - 1) return current
  return steps[idx + 1]
}

/** Navigate to the previous step, clamping at the first step. */
export function prevStep(current: WizardStep, hasFiles = false): WizardStep {
  const steps = visibleSteps(hasFiles)
  const idx = steps.indexOf(current)
  if (idx <= 0) return current
  return steps[idx - 1]
}

/** Index (0-based) of the step in the wizard's visible sequence. */
export function stepIndex(step: WizardStep, hasFiles = false): number {
  return visibleSteps(hasFiles).indexOf(step)
}

/** Whether the step is the first in the wizard. */
export function isFirstStep(step: WizardStep, hasFiles = false): boolean {
  const steps = visibleSteps(hasFiles)
  return step === steps[0]
}

/** Whether the step is the last in the wizard. */
export function isLastStep(step: WizardStep, hasFiles = false): boolean {
  const steps = visibleSteps(hasFiles)
  return step === steps[steps.length - 1]
}

// ---------------------------------------------------------------------------
// Tag state helpers
// ---------------------------------------------------------------------------

/**
 * Accept a pending tag — move it to confirmed.
 * Returns updated [confirmed, pending] arrays.
 */
export function acceptPendingTag(
  confirmed: string[],
  pending: string[],
  tag: string,
): [string[], string[]] {
  if (confirmed.includes(tag)) {
    // Already confirmed; just remove from pending
    return [confirmed, pending.filter((t) => t !== tag)]
  }
  return [[...confirmed, tag], pending.filter((t) => t !== tag)]
}

/**
 * Reject a pending tag — remove it from pending.
 */
export function rejectPendingTag(
  confirmed: string[],
  pending: string[],
  tag: string,
): [string[], string[]] {
  return [confirmed, pending.filter((t) => t !== tag)]
}

/**
 * Remove a confirmed tag.
 */
export function removeConfirmedTag(
  confirmed: string[],
  tag: string,
): string[] {
  return confirmed.filter((t) => t !== tag)
}

/**
 * Add a tag to confirmed (if not already present and non-empty).
 */
export function addConfirmedTag(confirmed: string[], tag: string): string[] {
  const trimmed = tag.trim()
  if (!trimmed || confirmed.includes(trimmed)) return confirmed
  return [...confirmed, trimmed]
}

// ---------------------------------------------------------------------------
// Session status helpers
// ---------------------------------------------------------------------------

export type ImportStatus =
  | 'draft'
  | 'processing'
  | 'pending_wizard'
  | 'committed'
  | 'cancelled'
  | 'failed'

/** Whether the session is still being processed (poll needed). */
export function isProcessing(status: string): boolean {
  return status === 'processing'
}

/** Whether the wizard should be editable. */
export function isEditable(status: string): boolean {
  return status === 'pending_wizard' || status === 'draft' || status === 'failed'
}

// ---------------------------------------------------------------------------
// Domain extraction
// ---------------------------------------------------------------------------

/** Extract the domain from a URL string, returning null on failure. */
export function extractDomain(url: string): string | null {
  try {
    return new URL(url).hostname
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// Fuzzy tag matching (Phase 8b — PendingTagsPage duplicate detection)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Pending-tag-on-next decision
// ---------------------------------------------------------------------------

/**
 * Determine what action to take when the user advances from the Tags step
 * while there is text in the tag input that has not yet been added.
 *
 * - 'advance' — input is empty or is already a confirmed tag (duplicate);
 *               the caller should clear the input silently and advance.
 * - 'prompt'  — input is non-empty and not a duplicate; show the
 *               "Add & continue / Discard & continue / Cancel" confirmation.
 */
export function pendingTagNextAction(
  input: string,
  confirmed: string[],
): 'advance' | 'prompt' {
  const trimmed = input.trim()
  if (!trimmed || confirmed.includes(trimmed)) return 'advance'
  return 'prompt'
}

// ---------------------------------------------------------------------------
// Fuzzy tag matching (Phase 8b — PendingTagsPage duplicate detection)
// ---------------------------------------------------------------------------

/**
 * Compute the Levenshtein edit distance between two strings.
 * Case-sensitive — normalise to lower-case before calling if needed.
 */
export function levenshtein(a: string, b: string): number {
  const m = a.length
  const n = b.length
  // Row-only DP to save memory
  let prev = Array.from({ length: n + 1 }, (_, j) => j)
  for (let i = 1; i <= m; i++) {
    const curr = new Array<number>(n + 1)
    curr[0] = i
    for (let j = 1; j <= n; j++) {
      if (a[i - 1] === b[j - 1]) {
        curr[j] = prev[j - 1]
      } else {
        curr[j] = 1 + Math.min(prev[j], curr[j - 1], prev[j - 1])
      }
    }
    prev = curr
  }
  return prev[n]
}

/**
 * Find the closest canonical tag to `pendingTag` within `maxDistance` edits
 * (case-insensitive). Returns the closest tag name, or null if none is within
 * the threshold.
 */
export function fuzzyMatchTags(
  pendingTag: string,
  canonicalTags: string[],
  maxDistance = 3,
): string | null {
  const lower = pendingTag.toLowerCase()
  let bestMatch: string | null = null
  let bestDist = maxDistance + 1
  for (const tag of canonicalTags) {
    const dist = levenshtein(lower, tag.toLowerCase())
    if (dist < bestDist) {
      bestDist = dist
      bestMatch = tag
    }
  }
  return bestDist <= maxDistance ? bestMatch : null
}
