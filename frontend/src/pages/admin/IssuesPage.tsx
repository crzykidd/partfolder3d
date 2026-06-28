/**
 * IssuesPage — admin view of reconcile-engine issues (PRD §8.3).
 *
 * Paginated table of issues (open/resolved/ignored) with severity and type
 * filters.  Resolve / Ignore actions on open issues.  Clicking a row expands
 * to show detail, suggested action, and resolution timestamp.
 *
 * Route: /admin/issues
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function severityBadge(severity: string) {
  const cls =
    severity === 'critical'
      ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
      : severity === 'warning'
        ? 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200'
        : 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {severity}
    </span>
  )
}

function statusBadge(status: string) {
  const cls =
    status === 'open'
      ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
      : status === 'resolved'
        ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
        : 'bg-muted text-muted-foreground'
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {status}
    </span>
  )
}

function formatTs(ts: string | null): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString()
}

// ---------------------------------------------------------------------------
// Issue row (expandable)
// ---------------------------------------------------------------------------

function IssueRow({ issue }: { issue: api.IssueOut }) {
  const [expanded, setExpanded] = useState(false)
  const queryClient = useQueryClient()

  const resolveMutation = useMutation({
    mutationFn: () => api.resolveIssue(issue.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['issues'] })
    },
  })

  const ignoreMutation = useMutation({
    mutationFn: () => api.ignoreIssue(issue.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['issues'] })
    },
  })

  const busy = resolveMutation.isPending || ignoreMutation.isPending

  return (
    <>
      <tr
        className="border-b border-border hover:bg-muted/40 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="py-2 px-3">{severityBadge(issue.severity)}</td>
        <td className="py-2 px-3 font-mono text-xs">{issue.issue_type}</td>
        <td className="py-2 px-3">{statusBadge(issue.status)}</td>
        <td className="py-2 px-3 text-xs">
          {issue.item_id != null ? (
            <a
              href={`/items/${issue.item_id}`}
              className="text-primary hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              #{issue.item_id}
            </a>
          ) : (
            '—'
          )}
        </td>
        <td className="py-2 px-3 text-xs text-muted-foreground max-w-xs">
          <span
            className="truncate block"
            title={issue.detail}
          >
            {issue.detail.length > 80
              ? `${issue.detail.slice(0, 80)}…`
              : issue.detail}
          </span>
        </td>
        <td className="py-2 px-3 text-xs text-muted-foreground whitespace-nowrap">
          {formatTs(issue.created_at)}
        </td>
        <td className="py-2 px-3" onClick={(e) => e.stopPropagation()}>
          {issue.status === 'open' && (
            <div className="flex gap-1">
              <button
                onClick={() => resolveMutation.mutate()}
                disabled={busy}
                className="px-2 py-1 rounded text-xs font-medium bg-green-600 text-white
                           hover:bg-green-700 disabled:opacity-50 transition-colors"
              >
                {resolveMutation.isPending ? '…' : 'Resolve'}
              </button>
              <button
                onClick={() => ignoreMutation.mutate()}
                disabled={busy}
                className="px-2 py-1 rounded text-xs font-medium bg-muted text-muted-foreground
                           hover:bg-muted/70 disabled:opacity-50 transition-colors"
              >
                {ignoreMutation.isPending ? '…' : 'Ignore'}
              </button>
            </div>
          )}
          {(resolveMutation.isError || ignoreMutation.isError) && (
            <p className="text-xs text-red-500 mt-1">Action failed</p>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border bg-muted/20">
          <td colSpan={7} className="px-3 py-2 text-xs space-y-1">
            <div>
              <span className="font-medium">Detail: </span>
              <span className="text-muted-foreground">{issue.detail}</span>
            </div>
            {issue.suggested_action && (
              <div>
                <span className="font-medium">Suggested action: </span>
                <span className="text-muted-foreground">{issue.suggested_action}</span>
              </div>
            )}
            {issue.resolved_at && (
              <div>
                <span className="font-medium">Resolved at: </span>
                <span className="text-muted-foreground">{formatTs(issue.resolved_at)}</span>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Filter constants
// ---------------------------------------------------------------------------

const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'open', label: 'Open' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'ignored', label: 'Ignored' },
]

// Values from IssueType enum in backend/app/models/issue.py
const ISSUE_TYPES = [
  { value: '', label: 'all types' },
  { value: 'conflict', label: 'conflict' },
  { value: 'dead_link', label: 'dead_link' },
  { value: 'corruption', label: 'corruption' },
  { value: 'orphan', label: 'orphan' },
  { value: 'missing_file', label: 'missing_file' },
  { value: 'extra_file', label: 'extra_file' },
  { value: 'sidecar_error', label: 'sidecar_error' },
  { value: 'other', label: 'other' },
]

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const PER_PAGE = 50

export function IssuesPage() {
  const [statusFilter, setStatusFilter] = useState('open')
  const [typeFilter, setTypeFilter] = useState('')
  const [page, setPage] = useState(1)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['issues', statusFilter, typeFilter, page],
    queryFn: () =>
      api.listIssues({
        status: statusFilter || undefined,
        issue_type: typeFilter || undefined,
        page,
        per_page: PER_PAGE,
      }),
  })

  const totalPages = data ? Math.ceil(data.total / PER_PAGE) : 1

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Issues</h1>
        <span className="text-sm text-muted-foreground">
          {data ? `${data.total} issue(s)` : ''}
        </span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium">Status:</label>
          <div className="flex gap-1">
            {STATUS_FILTERS.map((s) => (
              <button
                key={s.value || 'all'}
                onClick={() => {
                  setStatusFilter(s.value)
                  setPage(1)
                }}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  statusFilter === s.value
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-sm font-medium">Type:</label>
          <select
            value={typeFilter}
            onChange={(e) => {
              setTypeFilter(e.target.value)
              setPage(1)
            }}
            className="input-base py-1 text-xs"
          >
            {ISSUE_TYPES.map((t) => (
              <option key={t.value || 'all'} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}
      {isError && (
        <p className="text-red-600 text-sm">
          Error: {error instanceof Error ? error.message : 'Failed to load issues'}
        </p>
      )}

      {data && (
        <>
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                    Severity
                  </th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                    Type
                  </th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                    Status
                  </th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                    Item
                  </th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                    Detail
                  </th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                    Created
                  </th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="py-8 text-center text-muted-foreground text-sm"
                    >
                      No issues found.
                    </td>
                  </tr>
                ) : (
                  data.items.map((issue) => (
                    <IssueRow key={issue.id} issue={issue} />
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
