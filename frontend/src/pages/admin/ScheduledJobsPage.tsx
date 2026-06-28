/**
 * ScheduledJobsPage — recurring-job management (PRD §8.4).
 *
 * Shows every registered cron job with:
 *   - Last run time and outcome (succeeded / failed)
 *   - Next scheduled run time
 *   - Running-now indicator
 *   - Run Now button to enqueue immediately
 *
 * Route: /admin/scheduled-jobs
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusBadge(status: string | null) {
  if (!status) return <span className="text-muted-foreground text-xs">—</span>
  const cls =
    status === 'succeeded'
      ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
      : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  )
}

function formatTs(ts: string | null): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString()
}

// ---------------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------------

function JobRow({ job }: { job: api.ScheduledJobOut }) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => api.runScheduledJobNow(job.name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
    },
  })

  return (
    <tr className="border-b border-border">
      <td className="py-3 px-4">
        <div className="font-medium text-sm">{job.name}</div>
        <div className="text-xs text-muted-foreground mt-0.5">{job.description}</div>
      </td>
      <td className="py-3 px-4 text-xs text-muted-foreground">{job.schedule}</td>
      <td className="py-3 px-4">
        <div className="flex flex-col gap-1">
          {statusBadge(job.last_run_status)}
          <span className="text-xs text-muted-foreground">{formatTs(job.last_run_at)}</span>
          {job.last_run_error && (
            <span
              className="text-xs text-red-500 truncate max-w-[200px]"
              title={job.last_run_error}
            >
              {job.last_run_error.slice(0, 60)}{job.last_run_error.length > 60 ? '…' : ''}
            </span>
          )}
        </div>
      </td>
      <td className="py-3 px-4 text-xs text-muted-foreground">{formatTs(job.next_run_at)}</td>
      <td className="py-3 px-4">
        {job.is_running ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400 font-medium">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
            </span>
            Running
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">idle</span>
        )}
      </td>
      <td className="py-3 px-4">
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending || job.is_running}
          className="px-3 py-1 rounded-md text-xs font-medium bg-primary text-primary-foreground
                     hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {mutation.isPending ? 'Enqueueing…' : 'Run now'}
        </button>
        {mutation.isError && (
          <p className="text-xs text-red-500 mt-1">
            {mutation.error instanceof Error ? mutation.error.message : 'Failed'}
          </p>
        )}
        {mutation.isSuccess && (
          <p className="text-xs text-green-600 mt-1">Enqueued</p>
        )}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function ScheduledJobsPage() {
  const queryClient = useQueryClient()

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['scheduled-jobs'],
    queryFn: api.listScheduledJobs,
    refetchInterval: 10_000, // refresh every 10 s to pick up running state
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Scheduled Jobs</h1>
        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })}
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          Refresh
        </button>
      </div>

      <p className="text-sm text-muted-foreground">
        Recurring background jobs. Use <strong>Run now</strong> to trigger immediately
        outside of the normal schedule.
      </p>

      {isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}
      {isError && (
        <p className="text-red-600 text-sm">
          Error: {error instanceof Error ? error.message : 'Failed to load scheduled jobs'}
        </p>
      )}

      {data && (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="py-2 px-4 text-left font-medium text-muted-foreground text-xs">Job</th>
                <th className="py-2 px-4 text-left font-medium text-muted-foreground text-xs">Schedule</th>
                <th className="py-2 px-4 text-left font-medium text-muted-foreground text-xs">Last run</th>
                <th className="py-2 px-4 text-left font-medium text-muted-foreground text-xs">Next run</th>
                <th className="py-2 px-4 text-left font-medium text-muted-foreground text-xs">Status</th>
                <th className="py-2 px-4 text-left font-medium text-muted-foreground text-xs">Action</th>
              </tr>
            </thead>
            <tbody>
              {data.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-muted-foreground text-sm">
                    No scheduled jobs registered. The worker must start at least once to seed this list.
                  </td>
                </tr>
              ) : (
                data.map((job) => <JobRow key={job.name} job={job} />)
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
