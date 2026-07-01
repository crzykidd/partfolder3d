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
import { RotateCw, RefreshCw, X, Archive, Trash2 } from 'lucide-react'
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

function JobRow({ job, archived }: { job: api.JobOut; archived: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['jobs'] })
  const onError = (err: unknown) => {
    setActionError(err instanceof Error ? err.message : 'Action failed')
  }

  const retryMutation = useMutation({
    mutationFn: () => api.retryJob(job.id),
    onSuccess: invalidate,
    onError,
  })

  const cancelMutation = useMutation({
    mutationFn: () => api.cancelJob(job.id),
    onSuccess: invalidate,
    onError,
  })

  const restartMutation = useMutation({
    mutationFn: () => api.restartJob(job.id),
    onSuccess: invalidate,
    onError,
  })

  const archiveMutation = useMutation({
    mutationFn: () => api.archiveJob(job.id),
    onSuccess: invalidate,
    onError,
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteJob(job.id),
    onSuccess: invalidate,
    onError,
  })

  const anyPending =
    retryMutation.isPending ||
    cancelMutation.isPending ||
    restartMutation.isPending ||
    archiveMutation.isPending ||
    deleteMutation.isPending

  const clearError = () => setActionError(null)

  const handleDelete = () => {
    if (!window.confirm('Permanently delete this job? This cannot be undone.')) return
    clearError()
    deleteMutation.mutate()
  }

  const isRunning = job.status === 'running'
  const isFailed = job.status === 'failed'
  // terminal = can be archived/deleted in live view
  const isTerminal = job.status === 'succeeded' || job.status === 'cancelled' || job.status === 'failed'

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
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {archived ? (
              /* Archive view: Restart + Delete */
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => { clearError(); restartMutation.mutate() }}
                  disabled={anyPending}
                >
                  <RefreshCw size={11} />
                  {restartMutation.isPending ? 'Restarting…' : 'Restart'}
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={handleDelete}
                  disabled={anyPending}
                >
                  <Trash2 size={11} />
                  {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
                </Button>
              </>
            ) : (
              /* Live view: status-gated actions */
              <>
                {isRunning && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => { clearError(); cancelMutation.mutate() }}
                      disabled={anyPending}
                    >
                      <X size={11} />
                      {cancelMutation.isPending ? 'Cancelling…' : 'Cancel'}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => { clearError(); restartMutation.mutate() }}
                      disabled={anyPending}
                    >
                      <RefreshCw size={11} />
                      {restartMutation.isPending ? 'Restarting…' : 'Restart'}
                    </Button>
                  </>
                )}
                {isFailed && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => { clearError(); retryMutation.mutate() }}
                      disabled={anyPending}
                    >
                      <RotateCw size={11} />
                      {retryMutation.isPending ? 'Retrying…' : 'Retry'}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => { clearError(); restartMutation.mutate() }}
                      disabled={anyPending}
                    >
                      <RefreshCw size={11} />
                      {restartMutation.isPending ? 'Restarting…' : 'Restart'}
                    </Button>
                  </>
                )}
                {isTerminal && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => { clearError(); archiveMutation.mutate() }}
                      disabled={anyPending}
                    >
                      <Archive size={11} />
                      {archiveMutation.isPending ? 'Archiving…' : 'Archive'}
                    </Button>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={handleDelete}
                      disabled={anyPending}
                    >
                      <Trash2 size={11} />
                      {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
                    </Button>
                  </>
                )}
              </>
            )}

            {actionError && (
              <span style={{ fontSize: 11, color: 'var(--aurora-danger)' }}>{actionError}</span>
            )}
            {retryMutation.isSuccess && !actionError && (
              <span style={{ fontSize: 11, color: '#16A34A' }}>Enqueued ✓</span>
            )}
            {restartMutation.isSuccess && !actionError && (
              <span style={{ fontSize: 11, color: '#16A34A' }}>Restarted ✓</span>
            )}
          </div>
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

const STATUS_FILTERS = ['', 'running', 'queued', 'failed', 'succeeded', 'cancelled']
const STATUS_LABELS: Record<string, string> = {
  '': 'all',
  running: 'running',
  queued: 'queued',
  failed: 'failed',
  succeeded: 'succeeded',
  cancelled: 'cancelled',
}

const COLUMNS = ['ID', 'Type', 'Status', 'Progress', 'Created', 'Elapsed', 'Error', 'Actions']

export function JobsPage() {
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const [archived, setArchived] = useState(false)
  const [clearCount, setClearCount] = useState<number | null>(null)
  const perPage = 50
  const queryClient = useQueryClient()

  const clearMutation = useMutation({
    mutationFn: (status: 'succeeded' | 'failed' | 'cancelled') => api.clearJobsByStatus(status),
    onSuccess: (data) => {
      setClearCount(data.archived)
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['jobs', statusFilter, page, archived],
    queryFn: () =>
      api.listJobs({
        status: statusFilter || undefined,
        page,
        per_page: perPage,
        ...(archived ? { archived: true } : {}),
      }),
    refetchInterval: 5000, // poll every 5 s
  })

  const totalPages = data ? Math.ceil(data.total / perPage) : 1

  const handleToggleArchived = () => {
    setArchived((v) => !v)
    setStatusFilter('')
    setPage(1)
    setClearCount(null)
  }

  // Contextual clear button, keyed to the active status filter:
  //   all / succeeded → Clear succeeded · failed → Clear all failed ·
  //   cancelled → Clear cancelled · running / queued → no button.
  const clearConfig: { status: 'succeeded' | 'failed' | 'cancelled'; label: string } | null =
    statusFilter === '' || statusFilter === 'succeeded'
      ? { status: 'succeeded', label: 'Clear succeeded' }
      : statusFilter === 'failed'
        ? { status: 'failed', label: 'Clear all failed' }
        : statusFilter === 'cancelled'
          ? { status: 'cancelled', label: 'Clear cancelled' }
          : null

  const handleClear = () => {
    if (!clearConfig) return
    if (!window.confirm(`Archive all ${clearConfig.status} jobs? They will be moved to the archive and hidden from the live view.`)) return
    setClearCount(null)
    clearMutation.mutate(clearConfig.status)
  }

  return (
    <AdminPage>
      <PageHeader
        title={archived ? 'Job Archive' : 'Job Monitor'}
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

      {/* Top controls */}
      <div className="flex flex-wrap items-center gap-3">
        {!archived && clearConfig && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClear}
            disabled={clearMutation.isPending}
          >
            <Archive size={12} />
            {clearMutation.isPending ? 'Clearing…' : clearConfig.label}
          </Button>
        )}
        {clearCount != null && (
          <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>
            Archived {clearCount} job{clearCount === 1 ? '' : 's'}
          </span>
        )}
        {clearMutation.isError && (
          <span style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
            {clearMutation.error instanceof Error ? clearMutation.error.message : 'Clear failed'}
          </span>
        )}
        <Button
          variant={archived ? 'primary' : 'ghost'}
          size="sm"
          onClick={handleToggleArchived}
        >
          <Archive size={12} />
          {archived ? '← Live view' : 'View archive'}
        </Button>
      </div>

      {/* Status filter pills (live view only) */}
      {!archived && (
        <div className="flex flex-wrap items-center gap-2">
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Status
          </span>
          {STATUS_FILTERS.map((s) => (
            <FilterPill
              key={s || 'all'}
              active={statusFilter === s}
              onClick={() => { setStatusFilter(s); setPage(1); setClearCount(null) }}
            >
              {STATUS_LABELS[s]}
            </FilterPill>
          ))}
        </div>
      )}

      {/* Table */}
      <DataTable
        columns={COLUMNS}
        isLoading={isLoading}
        isEmpty={data ? data.jobs.length === 0 : false}
        emptyMessage={archived ? 'No archived jobs.' : 'No jobs found.'}
      >
        {data?.jobs.map((job) => <JobRow key={job.id} job={job} archived={archived} />)}
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
