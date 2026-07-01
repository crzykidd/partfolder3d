/**
 * IssuesPage — admin view of reconcile-engine issues (PRD §8.3).
 *
 * Paginated table of issues (open/resolved/ignored) with severity and type
 * filters.  Action buttons driven by issue.available_actions (ignore, delete,
 * import); Import opens the import wizard prefilled from the folder's sidecar.
 *
 * Route: /admin/issues
 * Styling: Aurora aesthetic (B3a restyle — visual pass, all behavior preserved).
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Trash2, EyeOff, FolderInput } from 'lucide-react'
import * as api from '@/lib/api'
import {
  AdminPage, PageHeader,
  Badge, severityVariant, issueStatusVariant,
  Button, FilterPill,
  DataTable, TableRow, Td, Pagination,
  AuroraSelect,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTs(ts: string | null): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString()
}

// ---------------------------------------------------------------------------
// Action button config
// ---------------------------------------------------------------------------

const ACTION_LABEL: Record<string, string> = {
  ignore: 'Ignore',
  delete: 'Delete folder',
  import: 'Import',
}

function ActionIcon({ action }: { action: string }) {
  if (action === 'delete') return <Trash2 size={12} />
  if (action === 'ignore') return <EyeOff size={12} />
  if (action === 'import') return <FolderInput size={12} />
  return null
}

function actionExtraStyle(action: string): React.CSSProperties | undefined {
  if (action === 'delete') {
    return {
      background: 'rgba(220,38,38,0.10)',
      border: '1px solid rgba(220,38,38,0.30)',
      color: '#DC2626',
    }
  }
  if (action === 'import') {
    return {
      background: 'rgba(22,163,74,0.10)',
      border: '1px solid rgba(22,163,74,0.30)',
      color: '#16A34A',
    }
  }
  return undefined
}

// ---------------------------------------------------------------------------
// Issue row (expandable)
// ---------------------------------------------------------------------------

function IssueRow({ issue }: { issue: api.IssueOut }) {
  const [expanded, setExpanded] = useState(false)
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const actionMutation = useMutation({
    mutationFn: (action: string) => api.issueAction(issue.id, action),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ['issues'] })
      if (data.import_session_id) {
        navigate(`/import/${data.import_session_id}?prefill=sidecar`)
      }
    },
  })

  const busy = actionMutation.isPending

  function handleAction(action: string) {
    if (action === 'delete') {
      const path = issue.target_path ? `\n\n${issue.target_path}` : ''
      const ok = window.confirm(`Move this directory to trash? This cannot be easily undone.${path}`)
      if (!ok) return
    }
    actionMutation.mutate(action)
  }

  const availableActions = issue.available_actions ?? []

  return (
    <>
      <TableRow onClick={() => setExpanded((v) => !v)}>
        <Td><Badge variant={severityVariant(issue.severity)}>{issue.severity}</Badge></Td>
        <Td style={{ fontFamily: 'monospace', fontSize: 11 }}>{issue.issue_type}</Td>
        <Td><Badge variant={issueStatusVariant(issue.status)}>{issue.status}</Badge></Td>
        <Td style={{ fontSize: 12 }}>
          {issue.item_id != null ? (
            <a
              href={`/items/${issue.item_id}`}
              style={{ color: 'var(--aurora-accent)', textDecoration: 'none' }}
              onClick={(e) => e.stopPropagation()}
              onMouseEnter={(e) => ((e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline')}
              onMouseLeave={(e) => ((e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none')}
            >
              #{issue.item_id}
            </a>
          ) : (
            <span style={{ color: 'var(--aurora-muted)' }}>—</span>
          )}
        </Td>
        <Td style={{ maxWidth: 280, color: 'var(--aurora-text-dim)' }} title={issue.detail}>
          <span
            style={{
              display: 'block',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              fontSize: 12,
            }}
          >
            {issue.detail.length > 80 ? `${issue.detail.slice(0, 80)}…` : issue.detail}
          </span>
        </Td>
        <Td style={{ fontSize: 11, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>
          {formatTs(issue.created_at)}
        </Td>
        <Td onClick={(e) => e.stopPropagation()}>
          {issue.status === 'open' && availableActions.length > 0 && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {availableActions.map((action) => (
                <Button
                  key={action}
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  onClick={() => handleAction(action)}
                  extraStyle={actionExtraStyle(action)}
                >
                  <ActionIcon action={action} />
                  {busy && actionMutation.variables === action
                    ? '…'
                    : (ACTION_LABEL[action] ?? action)}
                </Button>
              ))}
            </div>
          )}
          {actionMutation.isError && (
            <span style={{ fontSize: 11, color: 'var(--aurora-danger)', display: 'block', marginTop: 4 }}>
              {actionMutation.error instanceof Error
                ? actionMutation.error.message
                : 'Action failed'}
            </span>
          )}
        </Td>
      </TableRow>

      {expanded && (
        <tr style={{ borderTop: '1px solid var(--aurora-divider)', background: 'rgba(15,164,171,0.02)' }}>
          <td colSpan={7} style={{ padding: '10px 14px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
              <div>
                <span style={{ fontWeight: 600, color: 'var(--aurora-text-dim)' }}>Detail: </span>
                <span style={{ color: 'var(--aurora-muted)' }}>{issue.detail}</span>
              </div>
              {issue.target_path && (
                <div>
                  <span style={{ fontWeight: 600, color: 'var(--aurora-text-dim)' }}>Path: </span>
                  <span style={{ color: 'var(--aurora-muted)', fontFamily: 'monospace' }}>{issue.target_path}</span>
                </div>
              )}
              {issue.suggested_action && (
                <div>
                  <span style={{ fontWeight: 600, color: 'var(--aurora-text-dim)' }}>Suggested action: </span>
                  <span style={{ color: 'var(--aurora-muted)' }}>{issue.suggested_action}</span>
                </div>
              )}
              {issue.resolved_at && (
                <div>
                  <span style={{ fontWeight: 600, color: 'var(--aurora-text-dim)' }}>Resolved at: </span>
                  <span style={{ color: 'var(--aurora-muted)' }}>{formatTs(issue.resolved_at)}</span>
                </div>
              )}
            </div>
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
const COLUMNS = ['Severity', 'Type', 'Status', 'Item', 'Detail', 'Created', 'Actions']

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
    <AdminPage>
      <PageHeader
        title="Issues"
        meta={data ? `${data.total} issue${data.total === 1 ? '' : 's'}` : undefined}
      />

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Status
          </span>
          <div className="flex gap-1.5">
            {STATUS_FILTERS.map((s) => (
              <FilterPill
                key={s.value || 'all'}
                active={statusFilter === s.value}
                onClick={() => { setStatusFilter(s.value); setPage(1) }}
              >
                {s.label}
              </FilterPill>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Type
          </span>
          <AuroraSelect
            value={typeFilter}
            onChange={(e) => { setTypeFilter(e.target.value); setPage(1) }}
            style={{ padding: '5px 10px', fontSize: 12, width: 'auto' }}
          >
            {ISSUE_TYPES.map((t) => (
              <option key={t.value || 'all'} value={t.value}>{t.label}</option>
            ))}
          </AuroraSelect>
        </div>
      </div>

      {isError && (
        <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          Error: {error instanceof Error ? error.message : 'Failed to load issues'}
        </div>
      )}

      <DataTable
        columns={COLUMNS}
        isLoading={isLoading}
        isEmpty={data ? data.items.length === 0 : false}
        emptyMessage="No issues found."
      >
        {data?.items.map((issue) => <IssueRow key={issue.id} issue={issue} />)}
      </DataTable>

      <Pagination
        page={page}
        totalPages={totalPages}
        onPrev={() => setPage((p) => p - 1)}
        onNext={() => setPage((p) => p + 1)}
      />
    </AdminPage>
  )
}
