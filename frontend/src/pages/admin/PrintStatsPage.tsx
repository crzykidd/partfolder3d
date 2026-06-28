/**
 * PrintStatsPage — aggregate print statistics (PRD §9.2).
 *
 * Shows: total prints, success rate, total filament used, average print time,
 * and a "most printed" items table linking back to ItemPage.
 *
 * Route: /admin/print-stats  (admin only)
 */

import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import * as api from '@/lib/api'
import { formatPrintTime, formatFilamentLength, formatFilamentWeight } from '@/lib/print-utils'

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-5 flex flex-col gap-1">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-3xl font-bold">{value}</p>
      {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function PrintStatsPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['print-stats'],
    queryFn: api.getPrintStats,
    staleTime: 60_000,
  })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Print Statistics</h1>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {isError && (
        <p className="text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load print stats.'}
        </p>
      )}

      {data && (
        <>
          {/* Stat cards */}
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
              sub={data.success_rate != null ? `${data.success_count + data.fail_count} with outcome recorded` : 'No outcome data'}
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
              value={data.avg_print_time_s != null ? formatPrintTime(Math.round(data.avg_print_time_s)) : '—'}
              sub={
                data.total_print_time_s > 0
                  ? `Total: ${formatPrintTime(data.total_print_time_s)}`
                  : undefined
              }
            />
          </div>

          {/* Most printed table */}
          {data.most_printed_items.length > 0 && (
            <section>
              <h2 className="text-lg font-semibold mb-3">Most Printed</h2>
              <div className="rounded-lg border border-border overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="py-2 px-4 text-left font-medium text-muted-foreground text-xs">
                        #
                      </th>
                      <th className="py-2 px-4 text-left font-medium text-muted-foreground text-xs">
                        Title
                      </th>
                      <th className="py-2 px-4 text-left font-medium text-muted-foreground text-xs">
                        Key
                      </th>
                      <th className="py-2 px-4 text-right font-medium text-muted-foreground text-xs">
                        Prints
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.most_printed_items.map((item, idx) => (
                      <tr key={item.item_id} className="border-t border-border hover:bg-muted/30">
                        <td className="py-2 px-4 text-xs text-muted-foreground">{idx + 1}</td>
                        <td className="py-2 px-4">
                          {item.item_key ? (
                            <Link
                              to={`/items/${item.item_key}`}
                              className="text-primary hover:underline text-sm font-medium"
                            >
                              {item.title ?? item.item_key}
                            </Link>
                          ) : (
                            <span className="text-sm text-muted-foreground italic">
                              {item.title ?? '(deleted item)'}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-4 font-mono text-xs text-muted-foreground">
                          {item.item_key ?? '—'}
                        </td>
                        <td className="py-2 px-4 text-right font-medium text-sm">
                          {item.count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {data.most_printed_items.length === 0 && data.total_prints === 0 && (
            <p className="text-sm text-muted-foreground italic">
              No print records yet.
            </p>
          )}
        </>
      )}
    </div>
  )
}
