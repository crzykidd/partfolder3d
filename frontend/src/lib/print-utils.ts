/**
 * print-utils.ts — Pure helpers for print history display.
 * Extracted for unit-testability (vitest).
 */

/**
 * Format seconds into a human-readable duration.
 * e.g. 7380 → "2h 3m"
 */
export function formatPrintTime(seconds: number): string {
  if (seconds <= 0) return '0m'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h === 0) return `${m}m`
  if (m === 0) return `${h}h`
  return `${h}h ${m}m`
}

/**
 * Format filament length in mm into metres with 2 decimal places.
 * e.g. 1234.56 → "1.23 m"
 */
export function formatFilamentLength(mm: number): string {
  return `${(mm / 1000).toFixed(2)} m`
}

/**
 * Format filament weight in grams.
 * e.g. 4.5 → "4.5 g"
 */
export function formatFilamentWeight(g: number): string {
  return `${g.toFixed(1)} g`
}

/**
 * Render a rating as star characters (1–5).
 * e.g. 4 → "★★★★☆"
 */
export function renderStars(rating: number): string {
  const clamped = Math.max(1, Math.min(5, Math.round(rating)))
  return '★'.repeat(clamped) + '☆'.repeat(5 - clamped)
}
