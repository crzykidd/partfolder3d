/**
 * JobsPage — admin job/queue monitor (PRD §8.3).
 *
 * Live list of background jobs (queued/running/failed) with status, progress,
 * and error details.  Polls every 5 s so the view self-updates while work is
 * in progress.
 *
 * Route: /admin/jobs
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusBadge(status: string) {
  const cls =
    status === 'running'
      ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
      : status === 'succeeded'
        ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
        : status === 'failed'
          ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
          : 'bg-muted text-muted-foreground'
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  )
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="w-20 h-2 bg-muted rounded-full overflow-hidden">
      <div
        className="h-full bg-primary transition-all"
        style={{ width: `${value}%` }}
      />
    </div>
  )
}

function formatTs(ts: string | null): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString()
}

function elapsed(start: string | null, end: string | null): string {
  if (!start) return '—'
  const s = new Date(start).getTime()
  const e = end ? new Date(end).getTime() : Date.now()
  const secs = Math.round((e - s) / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  return `${mins}m ${secs % 60}s`
}

// ---------------------------------------------------------------------------
// Job row detail (expandable)
// ---------------------------------------------------------------------------

function JobRow({ job }: { job: api.JobOut }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <>
      <tr
        className="border-b border-border hover:bg-muted/40 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="py-2 px-3 font-mono text-xs text-muted-foreground">{job.id.slice(0, 8)}…</td>
        <td className="py-2 px-3 text-sm font-medium">{job.type}</td>
        <td className="py-2 px-3">{statusBadge(job.status)}</td>
        <td className="py-2 px-3">
          <div className="flex items-center gap-2">
            <ProgressBar value={job.progress} />
            <span className="text-xs text-muted-foreground">{job.progress}%</span>
          </div>
        </td>
        <td className="py-2 px-3 text-xs text-muted-foreground">{formatTs(job.created_at)}</td>
        <td className="py-2 px-3 text-xs text-muted-foreground">{elapsed(job.started_at, job.finished_at)}</td>
        <td className="py-2 px-3 text-xs">
          {job.error ? (
            <span className="text-red-600 dark:text-red-400 truncate max-w-[200px] block" title={job.error}>
              {job.error.slice(0, 60)}{job.error.length > 60 ? '…' : ''}
            </span>
          ) : '—'}
        </td>
      </tr>
      {expanded && (job.log || job.error) && (
        <tr className="border-b border-border bg-muted/20">
          <td colSpan={7} className="px-3 py-2">
            {job.log && (
              <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono mb-1">
                {job.log}
              </pre>
            )}
            {job.error && (
              <pre className="text-xs text-red-600 dark:text-red-400 whitespace-pre-wrap font-mono">
                Error: {job.error}
              </pre>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const STATUS_FILTERS = ['', 'running', 'queued', 'failed', 'succeeded']

export function JobsPage() {
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const perPage = 50

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['jobs', statusFilter, page],
    queryFn: () =>
      api.listJobs({
        status: statusFilter || undefined,
        page,
        per_page: perPage,
      }),
    refetchInterval: 5000, // poll every 5 s
  })

  const totalPages = data ? Math.ceil(data.total / perPage) : 1

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Job Monitor</h1>
        <span className="text-sm text-muted-foreground">
          {data ? `${data.total} job(s)` : ''}
          {' · '}
          <span className="text-primary">auto-refreshes every 5 s</span>
        </span>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium">Status:</label>
        <div className="flex gap-1">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s || 'all'}
              onClick={() => { setStatusFilter(s); setPage(1) }}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                statusFilter === s
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
              }`}
            >
              {s || 'all'}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}
      {isError && (
        <p className="text-red-600 text-sm">
          Error: {error instanceof Error ? error.message : 'Failed to load jobs'}
        </p>
      )}

      {data && (
        <>
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">ID</th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">Type</th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">Status</th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">Progress</th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">Created</th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">Elapsed</th>
                  <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">Error</th>
                </tr>
              </thead>
              <tbody>
                {data.jobs.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-muted-foreground text-sm">
                      No jobs found.
                    </td>
                  </tr>
                ) : (
                  data.jobs.map((job) => <JobRow key={job.id} job={job} />)
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
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
