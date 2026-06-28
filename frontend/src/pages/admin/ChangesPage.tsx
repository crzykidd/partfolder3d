/**
 * ChangesPage — read-only audit log of reconcile-engine changes (PRD §8.3).
 *
 * Newest-first paginated list of change log entries.  Filterable by behavior.
 * No actions — purely informational.
 *
 * Route: /admin/changes
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Behavior values match backend ChangeLog.behavior field.
// Colors chosen to be consistent with ReviewsPage behavior badges.
function behaviorBadge(behavior: string) {
  const cls =
    behavior === 'sidecar_sync'
      ? 'bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-200'
      : behavior === 'file_changes'
        ? 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200'
        : behavior === 're_render'
          ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
          : behavior === 'integrity'
            ? 'bg-muted text-muted-foreground'
            : behavior === 'orphan'
              ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
              : 'bg-muted text-muted-foreground'
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {behavior}
    </span>
  )
}

function formatTs(ts: string | null): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString()
}

// ---------------------------------------------------------------------------
// Filter constants
// ---------------------------------------------------------------------------

const BEHAVIOR_FILTERS = [
  { value: '', label: 'all' },
  { value: 'sidecar_sync', label: 'sidecar_sync' },
  { value: 'file_changes', label: 'file_changes' },
  { value: 're_render', label: 're_render' },
  { value: 'integrity', label: 'integrity' },
  { value: 'orphan', label: 'orphan' },
]

// ---------------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------------

function ChangeRow({ entry }: { entry: api.ChangeLogOut }) {
  return (
    <tr className="border-b border-border hover:bg-muted/40">
      <td className="py-2 px-3">{behaviorBadge(entry.behavior)}</td>
      <td className="py-2 px-3 font-mono text-xs">{entry.change_type}</td>
      <td className="py-2 px-3 text-xs">
        {entry.item_id != null ? (
          <a
            href={`/items/${entry.item_id}`}
            className="text-primary hover:underline"
          >
            #{entry.item_id}
          </a>
        ) : (
          '—'
        )}
      </td>
      <td className="py-2 px-3 text-xs text-muted-foreground max-w-sm">
        <span className="truncate block" title={entry.summary}>
          {entry.summary.length > 100
            ? `${entry.summary.slice(0, 100)}…`
            : entry.summary}
        </span>
      </td>
      <td className="py-2 px-3 text-xs text-muted-foreground">{entry.source}</td>
      <td className="py-2 px-3 text-xs text-muted-foreground whitespace-nowrap">
        {formatTs(entry.created_at)}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const PER_PAGE = 50

export function ChangesPage() {
  const [behaviorFilter, setBehaviorFilter] = useState('')
  const [page, setPage] = useState(1)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['changes', behaviorFilter, page],
    queryFn: () =>
      api.listChanges({
        behavior: behaviorFilter || undefined,
        page,
        per_page: PER_PAGE,
      }),
  })

  const totalPages = data ? Math.ceil(data.total / PER_PAGE) : 1

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Change Log</h1>
        <span className="text-sm text-muted-foreground">
          {data ? `${data.total} entry(s)` : ''}
        </span>
      </div>

      <p className="text-sm text-muted-foreground">
        Audit log of every automated or approved change made by the reconcile
        engine. Read-only.
      </p>

      {/* Behavior filter */}
      <div className="flex items-center gap-2">
        <label className="text-sm font-medium">Behavior:</label>
        <select
          value={behaviorFilter}
          onChange={(e) => {
            setBehaviorFilter(e.target.value)
            setPage(1)
          }}
          className="input-base py-1 text-xs"
        >
          {BEHAVIOR_FILTERS.map((b) => (
            <option key={b.value || 'all'} value={b.value}>
              {b.label}
            </option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}
      {isError && (
        <p className="text-red-600 text-sm">
          Error:{' '}
          {error instanceof Error ? error.message : 'Failed to load change log'}
        </p>
      )}

      {data && (
        <>
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                    Behavior
                  </th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                    Change type
                  </th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                    Item
                  </th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                    Summary
                  </th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                    Source
                  </th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                    Created
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="py-8 text-center text-muted-foreground text-sm"
                    >
                      No change log entries found.
                    </td>
                  </tr>
                ) : (
                  data.items.map((entry) => (
                    <ChangeRow key={entry.id} entry={entry} />
                  ))
                )}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm">
              <button
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                className="px-3 py-1 rounded-md bg-muted disabled:opacity-50"
              >
                Previous
              </button>
              <span className="text-muted-foreground">
                Page {page} of {totalPages}
              </span>
              <button
                disabled={page === totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1 rounded-md bg-muted disabled:opacity-50"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
