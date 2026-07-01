/**
 * DataTable — Aurora-styled table wrapper with loading/empty states and pagination.
 *
 * Composable: pass columns as string array (or Column objects for sortable headers),
 * children as tbody rows. The outer container uses the aurora glass-card style.
 *
 * Usage (plain):
 *   <DataTable columns={['ID','Type','Status']} isEmpty={!rows.length} emptyMessage="No jobs.">
 *     {rows.map(r => <tr key={r.id}>…</tr>)}
 *   </DataTable>
 *
 * Usage (with sortable column):
 *   <DataTable columns={['Name', { label: 'Date', sortable: true, sortDir: dir, onSort: fn }]}>
 *     …
 *   </DataTable>
 *
 * Reusable by B3b.
 */

import React from 'react'
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'

// ---------------------------------------------------------------------------
// Column type — plain string OR sortable column descriptor
// ---------------------------------------------------------------------------

export interface SortableColumnDef {
  label: string
  sortable?: boolean
  sortDir?: 'asc' | 'desc' | null
  onSort?: () => void
}

export type Column = string | SortableColumnDef

// ---------------------------------------------------------------------------
// Style constants
// ---------------------------------------------------------------------------

export const TABLE_CARD_STYLE: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 12,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
  overflow: 'hidden',
}

export const TH_STYLE: React.CSSProperties = {
  padding: '10px 14px',
  textAlign: 'left',
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--aurora-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  whiteSpace: 'nowrap',
}

export const TD_STYLE: React.CSSProperties = {
  padding: '10px 14px',
  fontSize: 13,
  color: 'var(--aurora-text)',
  verticalAlign: 'middle',
}

export const THEAD_STYLE: React.CSSProperties = {
  background: 'rgba(0,0,0,0.03)',
  borderBottom: '1px solid var(--aurora-divider)',
}

export const TR_HOVER_CLASS = 'hover:bg-white/5 dark:hover:bg-white/5 cursor-pointer'

// ---------------------------------------------------------------------------
// DataTable
// ---------------------------------------------------------------------------

interface DataTableProps {
  columns: Column[]
  /** tbody content (rows). When isLoading or isEmpty, this is ignored. */
  children?: React.ReactNode
  isLoading?: boolean
  isEmpty?: boolean
  emptyMessage?: string
  /** Style overrides on the outer card div */
  style?: React.CSSProperties
  className?: string
}

export function DataTable({
  columns,
  children,
  isLoading,
  isEmpty,
  emptyMessage = 'No records found.',
  style,
  className,
}: DataTableProps) {
  const colCount = columns.length

  return (
    <div style={{ ...TABLE_CARD_STYLE, ...style }} className={className}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead style={THEAD_STYLE}>
          <tr>
            {columns.map((col) => {
              if (typeof col === 'string') {
                return (
                  <th key={col} style={TH_STYLE}>
                    {col}
                  </th>
                )
              }
              const { label, sortable, sortDir, onSort } = col
              if (!sortable) {
                return (
                  <th key={label} style={TH_STYLE}>
                    {label}
                  </th>
                )
              }
              return (
                <th key={label} style={TH_STYLE}>
                  <button
                    type="button"
                    onClick={onSort}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: 0,
                      color: 'inherit',
                      font: 'inherit',
                      fontSize: 'inherit',
                      textTransform: 'inherit',
                      letterSpacing: 'inherit',
                      fontWeight: 'inherit',
                      transition: 'opacity 0.15s',
                    }}
                    onMouseEnter={(e) => {
                      ;(e.currentTarget as HTMLButtonElement).style.opacity = '0.7'
                    }}
                    onMouseLeave={(e) => {
                      ;(e.currentTarget as HTMLButtonElement).style.opacity = '1'
                    }}
                  >
                    {label}
                    {sortDir === 'asc' ? (
                      <ChevronUp size={12} />
                    ) : sortDir === 'desc' ? (
                      <ChevronDown size={12} />
                    ) : (
                      <ChevronsUpDown size={12} style={{ opacity: 0.4 }} />
                    )}
                  </button>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <tr>
              <td
                colSpan={colCount}
                style={{ ...TD_STYLE, textAlign: 'center', color: 'var(--aurora-muted)', padding: '36px 14px' }}
              >
                Loading…
              </td>
            </tr>
          ) : isEmpty ? (
            <tr>
              <td
                colSpan={colCount}
                style={{ ...TD_STYLE, textAlign: 'center', color: 'var(--aurora-muted)', padding: '48px 14px' }}
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            children
          )}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TableRow — styled tbody row with hover + divider
// ---------------------------------------------------------------------------

interface TableRowProps {
  children: React.ReactNode
  onClick?: () => void
  /** Expanded detail row — slightly different background */
  isDetail?: boolean
  style?: React.CSSProperties
}

export function TableRow({ children, onClick, isDetail, style }: TableRowProps) {
  return (
    <tr
      onClick={onClick}
      style={{
        borderTop: '1px solid var(--aurora-divider)',
        background: isDetail ? 'rgba(15,164,171,0.02)' : 'transparent',
        cursor: onClick ? 'pointer' : 'default',
        ...style,
      }}
      onMouseEnter={(e) => {
        if (!isDetail && onClick) {
          (e.currentTarget as HTMLTableRowElement).style.background =
            'var(--aurora-glass-hover)'
        }
      }}
      onMouseLeave={(e) => {
        if (!isDetail) {
          (e.currentTarget as HTMLTableRowElement).style.background =
            isDetail ? 'rgba(15,164,171,0.02)' : 'transparent'
        }
      }}
    >
      {children}
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Td — styled table cell
// ---------------------------------------------------------------------------

interface TdProps {
  children: React.ReactNode
  style?: React.CSSProperties
  colSpan?: number
  onClick?: React.MouseEventHandler<HTMLTableCellElement>
  title?: string
  className?: string
}

export function Td({ children, style, colSpan, onClick, title, className }: TdProps) {
  return (
    <td
      colSpan={colSpan}
      onClick={onClick}
      title={title}
      className={className}
      style={{ ...TD_STYLE, ...style }}
    >
      {children}
    </td>
  )
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

interface PaginationProps {
  page: number
  totalPages: number
  onPrev: () => void
  onNext: () => void
}

const PAGER_BTN: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '6px 14px',
  borderRadius: 8,
  fontSize: 12,
  fontWeight: 500,
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  color: 'var(--aurora-text-dim)',
  cursor: 'pointer',
  transition: 'opacity 0.15s',
}

export function Pagination({ page, totalPages, onPrev, onNext }: PaginationProps) {
  if (totalPages <= 1) return null

  return (
    <div className="flex items-center justify-between">
      <button
        onClick={onPrev}
        disabled={page === 1}
        style={{ ...PAGER_BTN, opacity: page === 1 ? 0.4 : 1, cursor: page === 1 ? 'not-allowed' : 'pointer' }}
      >
        ← Previous
      </button>
      <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>
        Page {page} of {totalPages}
      </span>
      <button
        onClick={onNext}
        disabled={page === totalPages}
        style={{
          ...PAGER_BTN,
          opacity: page === totalPages ? 0.4 : 1,
          cursor: page === totalPages ? 'not-allowed' : 'pointer',
        }}
      >
        Next →
      </button>
    </div>
  )
}
