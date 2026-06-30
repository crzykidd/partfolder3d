/**
 * carousel-utils.ts — pure helpers for the image carousel pager.
 *
 * Extracted here so the paging math is unit-testable without a DOM.
 */

/**
 * Build the ordered list of page-index items for the jump nav.
 * Returns 0-based page indices and 'ellipsis' markers for overflow.
 *
 * Rules:
 * - totalPages <= 1  → empty (no pager needed)
 * - totalPages <= 7  → all page indices in order
 * - Otherwise        → first + last + two neighbours of currentPage + ellipsis
 *
 * @param currentPage  0-based active page
 * @param totalPages   total number of pages
 */
export function buildCarouselPagerItems(
  currentPage: number,
  totalPages: number,
): Array<number | 'ellipsis'> {
  if (totalPages <= 1) return []
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i)

  const items: Array<number | 'ellipsis'> = []
  const left = Math.max(1, currentPage - 1)
  const right = Math.min(totalPages - 2, currentPage + 1)

  items.push(0)
  if (left > 1) items.push('ellipsis')
  for (let i = left; i <= right; i++) items.push(i)
  if (right < totalPages - 2) items.push('ellipsis')
  items.push(totalPages - 1)

  return items
}
