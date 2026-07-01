/**
 * PrintStatsPage — aggregate print statistics (PRD §9.2).
 *
 * Shows: total prints, success rate, total filament used, average print time,
 * and a "most printed" items table linking back to ItemPage.
 *
 * Route: /admin/print-stats  (admin only)
 * Styling: Aurora aesthetic (B3a restyle — visual pass, all behavior preserved).
 */

import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import * as api from '@/lib/api'
import { formatPrintTime, formatFilamentLength, formatFilamentWeight } from '@/lib/print-utils'
import {
  AdminPage, PageHeader,
  DataTable, TableRow, Td,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// Stat card — Aurora glass style
// ---------------------------------------------------------------------------

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div
      style={{
        background: 'var(--aurora-card)',
        border: '1px solid var(--aurora-card-border)',
        borderRadius: 12,
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        padding: '18px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      <p
        style={{
          fontSize: 10,
          fontWeight: 700,
          color: 'var(--aurora-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          margin: 0,
        }}
      >
        {label}
      </p>
      <p
        style={{
          fontSize: 28,
          fontWeight: 800,
          color: 'var(--aurora-text)',
          letterSpacing: '-0.02em',
          margin: 0,
        }}
      >
        {value}
      </p>
      {sub && (
        <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>{sub}</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const MOST_PRINTED_COLS = ['#', 'Title', 'Key', 'Prints']

export function PrintStatsPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['print-stats'],
    queryFn: api.getPrintStats,
    staleTime: 60_000,
  })

  return (
    <AdminPage>
      <PageHeader title="Print Statistics" />

      {isLoading && (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>Loading…</p>
      )}

      {isError && (
        <p style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          {error instanceof Error ? error.message : 'Failed to load print stats.'}
        </p>
      )}

      {data && (
        <>
          {/* Stat cards grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              label="Total Prints"
              value={String(data.total_prints)}
              sub={`${data.success_count} succeeded · ${data.fail_count} failed`}
            />
            <StatCard
              label="Success Rate"
              value={
                data.success_rate != null
                  ? `${(data.success_rate * 100).toFixed(1)}%`
                  : '—'
              }
              sub={
                data.success_rate != null
                  ? `${data.success_count + data.fail_count} with outcome recorded`
                  : 'No outcome data'
              }
            />
            <StatCard
              label="Total Filament"
              value={
                data.total_filament_length_mm > 0
                  ? formatFilamentLength(data.total_filament_length_mm)
                  : '—'
              }
              sub={
                data.total_filament_weight_g > 0
                  ? formatFilamentWeight(data.total_filament_weight_g)
                  : undefined
              }
            />
            <StatCard
              label="Avg Print Time"
              value={
                data.avg_print_time_s != null
                  ? formatPrintTime(Math.round(data.avg_print_time_s))
                  : '—'
              }
              sub={
                data.total_print_time_s > 0
                  ? `Total: ${formatPrintTime(data.total_print_time_s)}`
                  : undefined
              }
            />
          </div>

          {/* Most Printed table */}
          {data.most_printed_items.length > 0 && (
            <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div
                style={{
                  fontSize: 16,
                  fontWeight: 700,
                  color: 'var(--aurora-text)',
                }}
              >
                Most Printed
              </div>
              <DataTable columns={MOST_PRINTED_COLS}>
                {data.most_printed_items.map((item, idx) => (
                  <TableRow key={item.item_id}>
                    <Td style={{ fontSize: 11, color: 'var(--aurora-muted)', width: 36 }}>
                      {idx + 1}
                    </Td>
                    <Td>
                      {item.item_key ? (
                        <Link
                          to={`/items/${item.item_key}`}
                          style={{
                            color: 'var(--aurora-accent)',
                            textDecoration: 'none',
                            fontWeight: 600,
                            fontSize: 13,
                          }}
                          onMouseEnter={(e) => ((e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline')}
                          onMouseLeave={(e) => ((e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none')}
                        >
                          {item.title ?? item.item_key}
                        </Link>
                      ) : (
                        <span style={{ fontSize: 13, color: 'var(--aurora-muted)', fontStyle: 'italic' }}>
                          {item.title ?? '(deleted item)'}
                        </span>
                      )}
                    </Td>
                    <Td style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--aurora-muted)' }}>
                      {item.item_key ?? '—'}
                    </Td>
                    <Td style={{ textAlign: 'right', fontWeight: 700, fontSize: 14 }}>
                      {item.count}
                    </Td>
                  </TableRow>
                ))}
              </DataTable>
            </section>
          )}

          {data.most_printed_items.length === 0 && data.total_prints === 0 && (
            <p style={{ fontSize: 13, color: 'var(--aurora-muted)', fontStyle: 'italic' }}>
              No print records yet.
            </p>
          )}
        </>
      )}
    </AdminPage>
  )
}
