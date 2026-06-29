/**
 * JobsPage — admin job/queue monitor (PRD §8.3).
 *
 * Live list of background jobs (queued/running/failed) with status, progress,
 * and error details.  Polls every 5 s so the view self-updates while work is
 * in progress.
 *
 * Route: /admin/jobs
 * Styling: Aurora aesthetic (B3a restyle — visual pass, all behavior preserved).
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RotateCw } from 'lucide-react'
import * as api from '@/lib/api'
import {
  AdminPage, PageHeader,
  Badge, jobStatusVariant,
  Button,
  FilterPill,
  DataTable, TableRow, Td, Pagination,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
// Progress bar
// ---------------------------------------------------------------------------

function ProgressBar({ value }: { value: number }) {
  return (
    <div
      style={{
        width: 80,
        height: 6,
        borderRadius: 3,
        background: 'var(--aurora-glass)',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          height: '100%',
          width: `${value}%`,
          background: 'var(--aurora-accent)',
          borderRadius: 3,
          transition: 'width 0.3s',
        }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Job row (expandable)
// ---------------------------------------------------------------------------

function JobRow({ job }: { job: api.JobOut }) {
  const [expanded, setExpanded] = useState(false)
  const queryClient = useQueryClient()

  const retryMutation = useMutation({
    mutationFn: () => api.retryJob(job.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  return (
    <>
      <TableRow onClick={() => setExpanded((v) => !v)}>
        <Td style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--aurora-muted)' }}>
          {job.id.slice(0, 8)}…
        </Td>
        <Td style={{ fontWeight: 600 }}>{job.type}</Td>
        <Td>
          <Badge variant={jobStatusVariant(job.status)}>{job.status}</Badge>
        </Td>
        <Td>
          <div className="flex items-center gap-2">
            <ProgressBar value={job.progress} />
            <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>{job.progress}%</span>
          </div>
        </Td>
        <Td style={{ fontSize: 11, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>
          {formatTs(job.created_at)}
        </Td>
        <Td style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
          {elapsed(job.started_at, job.finished_at)}
        </Td>
        <Td>
          {job.error ? (
            <span
              style={{
                fontSize: 11,
                color: 'var(--aurora-danger)',
                display: 'block',
                maxWidth: 200,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={job.error}
            >
              {job.error.slice(0, 60)}{job.error.length > 60 ? '…' : ''}
            </span>
          ) : (
            <span style={{ color: 'var(--aurora-muted)', fontSize: 11 }}>—</span>
          )}
        </Td>
        <Td onClick={(e) => e.stopPropagation()}>
          {job.status === 'failed' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => retryMutation.mutate()}
                disabled={retryMutation.isPending}
              >
                <RotateCw size={11} />
                {retryMutation.isPending ? 'Retrying…' : 'Retry'}
              </Button>
              {retryMutation.isError && (
                <span style={{ fontSize: 11, color: 'var(--aurora-danger)' }}>
                  {retryMutation.error instanceof Error ? retryMutation.error.message : 'Failed'}
                </span>
              )}
              {retryMutation.isSuccess && (
                <span style={{ fontSize: 11, color: '#16A34A' }}>Enqueued ✓</span>
              )}
            </div>
          )}
        </Td>
      </TableRow>

      {expanded && (job.log || job.error) && (
        <tr style={{ borderTop: '1px solid var(--aurora-divider)', background: 'rgba(15,164,171,0.02)' }}>
          <td colSpan={8} style={{ padding: '10px 14px' }}>
            {job.log && (
              <pre
                style={{
                  fontSize: 11,
                  color: 'var(--aurora-text-dim)',
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'monospace',
                  margin: '0 0 6px',
                  background: 'var(--aurora-glass)',
                  border: '1px solid var(--aurora-glass-border)',
                  borderRadius: 6,
                  padding: '8px 10px',
                  maxHeight: 200,
                  overflow: 'auto',
                }}
              >
                {job.log}
              </pre>
            )}
            {job.error && (
              <pre
                style={{
                  fontSize: 11,
                  color: 'var(--aurora-danger)',
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'monospace',
                  margin: 0,
                  background: 'rgba(239,68,68,0.06)',
                  border: '1px solid rgba(239,68,68,0.2)',
                  borderRadius: 6,
                  padding: '8px 10px',
                }}
              >
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
const STATUS_LABELS: Record<string, string> = {
  '': 'all',
  running: 'running',
  queued: 'queued',
  failed: 'failed',
  succeeded: 'succeeded',
}

const COLUMNS = ['ID', 'Type', 'Status', 'Progress', 'Created', 'Elapsed', 'Error', 'Actions']

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
    <AdminPage>
      <PageHeader
        title="Job Monitor"
        meta={
          data
            ? `${data.total} job${data.total === 1 ? '' : 's'} · auto-refreshes every 5 s`
            : undefined
        }
        actions={
          isError ? (
            <span style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
              {error instanceof Error ? error.message : 'Failed to load jobs'}
            </span>
          ) : undefined
        }
      />

      {/* Status filter pills */}
      <div className="flex flex-wrap items-center gap-2">
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Status
        </span>
        {STATUS_FILTERS.map((s) => (
          <FilterPill
            key={s || 'all'}
            active={statusFilter === s}
            onClick={() => { setStatusFilter(s); setPage(1) }}
          >
            {STATUS_LABELS[s]}
          </FilterPill>
        ))}
      </div>

      {/* Table */}
      <DataTable
        columns={COLUMNS}
        isLoading={isLoading}
        isEmpty={data ? data.jobs.length === 0 : false}
        emptyMessage="No jobs found."
      >
        {data?.jobs.map((job) => <JobRow key={job.id} job={job} />)}
      </DataTable>

      {/* Pagination */}
      <Pagination
        page={page}
        totalPages={totalPages}
        onPrev={() => setPage((p) => p - 1)}
        onNext={() => setPage((p) => p + 1)}
      />
    </AdminPage>
  )
}
