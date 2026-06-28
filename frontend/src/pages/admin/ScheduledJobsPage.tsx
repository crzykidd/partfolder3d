/**
 * ScheduledJobsPage — recurring-job management (PRD §8.4).
 *
 * Shows every registered cron job with:
 *   - Last run time and outcome (succeeded / failed)
 *   - Next scheduled run time
 *   - Running-now indicator
 *   - Run Now button to enqueue immediately (incl. library_reconcile_scan reindex)
 *
 * Route: /admin/scheduled-jobs
 * Styling: Aurora aesthetic (B3a restyle — visual pass, all behavior preserved).
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Play } from 'lucide-react'
import * as api from '@/lib/api'
import {
  AdminPage, PageHeader,
  Badge, schedJobStatusVariant,
  Button,
  DataTable, TableRow, Td,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTs(ts: string | null): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString()
}

// ---------------------------------------------------------------------------
// Running indicator
// ---------------------------------------------------------------------------

function RunningIndicator() {
  return (
    <span className="inline-flex items-center gap-1.5" style={{ fontSize: 12, color: 'var(--aurora-accent)', fontWeight: 600 }}>
      {/* Pulsing dot */}
      <span className="relative flex h-2 w-2">
        <span
          className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
          style={{ background: 'var(--aurora-accent)' }}
        />
        <span
          className="relative inline-flex rounded-full h-2 w-2"
          style={{ background: 'var(--aurora-accent)' }}
        />
      </span>
      Running
    </span>
  )
}

// ---------------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------------

function JobRow({ job }: { job: api.ScheduledJobOut }) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => api.runScheduledJobNow(job.name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
    },
  })

  return (
    <TableRow>
      {/* Job name + description */}
      <Td>
        <div style={{ fontWeight: 600, fontSize: 13 }}>{job.name}</div>
        <div style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 2 }}>{job.description}</div>
      </Td>

      {/* Schedule */}
      <Td style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--aurora-text-dim)' }}>
        {job.schedule}
      </Td>

      {/* Last run */}
      <Td>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          {job.last_run_status ? (
            <Badge variant={schedJobStatusVariant(job.last_run_status)}>
              {job.last_run_status}
            </Badge>
          ) : (
            <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>—</span>
          )}
          <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>{formatTs(job.last_run_at)}</span>
          {job.last_run_error && (
            <span
              style={{
                fontSize: 11,
                color: 'var(--aurora-danger)',
                maxWidth: 200,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={job.last_run_error}
            >
              {job.last_run_error.slice(0, 60)}{job.last_run_error.length > 60 ? '…' : ''}
            </span>
          )}
        </div>
      </Td>

      {/* Next run */}
      <Td style={{ fontSize: 11, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>
        {formatTs(job.next_run_at)}
      </Td>

      {/* Running status */}
      <Td>
        {job.is_running ? (
          <RunningIndicator />
        ) : (
          <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>idle</span>
        )}
      </Td>

      {/* Run now action */}
      <Td onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <Button
            variant="primary"
            size="sm"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || job.is_running}
          >
            <Play size={11} />
            {mutation.isPending ? 'Enqueueing…' : 'Run now'}
          </Button>
          {mutation.isError && (
            <span style={{ fontSize: 11, color: 'var(--aurora-danger)' }}>
              {mutation.error instanceof Error ? mutation.error.message : 'Failed'}
            </span>
          )}
          {mutation.isSuccess && (
            <span style={{ fontSize: 11, color: '#16A34A' }}>Enqueued ✓</span>
          )}
        </div>
      </Td>
    </TableRow>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const COLUMNS = ['Job', 'Schedule', 'Last run', 'Next run', 'Status', 'Action']

export function ScheduledJobsPage() {
  const queryClient = useQueryClient()

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['scheduled-jobs'],
    queryFn: api.listScheduledJobs,
    refetchInterval: 10_000, // refresh every 10 s to pick up running state
  })

  return (
    <AdminPage>
      <PageHeader
        title="Scheduled Jobs"
        description="Recurring background jobs. Use Run now to trigger immediately outside of the normal schedule."
        actions={
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })}
          >
            <RefreshCw size={13} />
            Refresh
          </Button>
        }
      />

      {isError && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 7,
            background: 'rgba(239,68,68,0.08)',
            border: '1px solid rgba(239,68,68,0.2)',
            borderRadius: 8,
            padding: '10px 14px',
            fontSize: 12,
            color: 'var(--aurora-danger)',
          }}
        >
          {error instanceof Error ? error.message : 'Failed to load scheduled jobs'}
        </div>
      )}

      <DataTable
        columns={COLUMNS}
        isLoading={isLoading}
        isEmpty={data ? data.length === 0 : false}
        emptyMessage="No scheduled jobs registered. The worker must start at least once to seed this list."
      >
        {data?.map((job) => <JobRow key={job.name} job={job} />)}
      </DataTable>
    </AdminPage>
  )
}
