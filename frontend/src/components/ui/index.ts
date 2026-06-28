/**
 * Aurora admin UI primitives — barrel export.
 *
 * B3b can import from '@/components/ui' to get all shared primitives.
 *
 * Primitives introduced in B3a:
 *  - AdminPage, PageHeader   — page wrapper + header
 *  - Card, SectionHeader     — glass card / panel
 *  - Badge + variant helpers — status/severity/behavior badges
 *  - Button, FilterPill      — aurora buttons + filter toggles
 *  - DataTable, TableRow, Td, Pagination — table scaffold + helpers
 *  - EmptyState              — icon + title + description empty state
 *  - Field, AuroraInput, AuroraSelect — form field with aurora focus ring
 */

export { AdminPage, PageHeader } from './AdminPage'
export type {} from './AdminPage'

export { Card, SectionHeader, CARD_STYLE, CARD_ACCENT_STYLE } from './Card'
export type {} from './Card'

export {
  Badge,
  jobStatusVariant,
  schedJobStatusVariant,
  severityVariant,
  issueStatusVariant,
  behaviorVariant,
} from './Badge'
export type { BadgeVariant } from './Badge'

export { Button, FilterPill, AuroraToggle } from './Button'
export type { ButtonProps } from './Button'

export {
  DataTable,
  TableRow,
  Td,
  Pagination,
  TABLE_CARD_STYLE,
  TH_STYLE,
  TD_STYLE,
  THEAD_STYLE,
} from './DataTable'

export { EmptyState } from './EmptyState'

export { Field, AuroraInput, AuroraSelect, INPUT_STYLE, LABEL_STYLE } from './Field'
export type { AuroraInputProps, AuroraSelectProps } from './Field'
