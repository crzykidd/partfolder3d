/**
 * import-utils.ts — Pure helper functions for the import wizard UI.
 *
 * All functions here are stateless and testable with vitest (no React deps).
 */

// ---------------------------------------------------------------------------
// Wizard step definitions
// ---------------------------------------------------------------------------

export type WizardStep = 'title' | 'images' | 'tags' | 'creator' | 'summary'

export const WIZARD_STEPS: WizardStep[] = [
  'title',
  'images',
  'tags',
  'creator',
  'summary',
]

export const STEP_LABELS: Record<WizardStep, string> = {
  title: 'Title',
  images: 'Images',
  tags: 'Tags',
  creator: 'Creator',
  summary: 'Review & Commit',
}

/** Navigate to the next step, clamping at the last step. */
export function nextStep(current: WizardStep): WizardStep {
  const idx = WIZARD_STEPS.indexOf(current)
  if (idx < 0 || idx >= WIZARD_STEPS.length - 1) return current
  return WIZARD_STEPS[idx + 1]
}

/** Navigate to the previous step, clamping at the first step. */
export function prevStep(current: WizardStep): WizardStep {
  const idx = WIZARD_STEPS.indexOf(current)
  if (idx <= 0) return current
  return WIZARD_STEPS[idx - 1]
}

/** Index (0-based) of the step in the wizard. */
export function stepIndex(step: WizardStep): number {
  return WIZARD_STEPS.indexOf(step)
}

/** Whether the step is the first in the wizard. */
export function isFirstStep(step: WizardStep): boolean {
  return step === WIZARD_STEPS[0]
}

/** Whether the step is the last in the wizard. */
export function isLastStep(step: WizardStep): boolean {
  return step === WIZARD_STEPS[WIZARD_STEPS.length - 1]
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
