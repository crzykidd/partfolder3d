/**
 * ChangesPage — read-only audit log of reconcile-engine changes (PRD §8.3).
 *
 * Newest-first paginated list of change log entries.  Filterable by behavior.
 * No actions — purely informational.
 *
 * Route: /admin/changes
 * Styling: Aurora aesthetic (B3a restyle — visual pass, all behavior preserved).
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as api from '@/lib/api'
import {
  AdminPage, PageHeader,
  Badge, behaviorVariant,
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
    <TableRow>
      <Td>
        <Badge variant={behaviorVariant(entry.behavior)}>{entry.behavior}</Badge>
      </Td>
      <Td style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--aurora-text-dim)' }}>
        {entry.change_type}
      </Td>
      <Td style={{ fontSize: 12 }}>
        {entry.item_id != null ? (
          <a
            href={`/items/${entry.item_id}`}
            style={{ color: 'var(--aurora-accent)', textDecoration: 'none' }}
            onMouseEnter={(e) => ((e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline')}
            onMouseLeave={(e) => ((e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none')}
          >
            #{entry.item_id}
          </a>
        ) : (
          <span style={{ color: 'var(--aurora-muted)' }}>—</span>
        )}
      </Td>
      <Td style={{ maxWidth: 320, color: 'var(--aurora-text-dim)' }} title={entry.summary}>
        <span
          style={{
            display: 'block',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            fontSize: 12,
          }}
        >
          {entry.summary.length > 100 ? `${entry.summary.slice(0, 100)}…` : entry.summary}
        </span>
      </Td>
      <Td style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>{entry.source}</Td>
      <Td style={{ fontSize: 11, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>
        {formatTs(entry.created_at)}
      </Td>
    </TableRow>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const PER_PAGE = 50
const COLUMNS = ['Behavior', 'Change type', 'Item', 'Summary', 'Source', 'Created']

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
    <AdminPage>
      <PageHeader
        title="Change Log"
        description="Audit log of every automated or approved change made by the reconcile engine. Read-only."
        meta={data ? `${data.total} entr${data.total === 1 ? 'y' : 'ies'}` : undefined}
      />

      {/* Behavior filter */}
      <div className="flex items-center gap-3">
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Behavior
        </span>
        <AuroraSelect
          value={behaviorFilter}
          onChange={(e) => { setBehaviorFilter(e.target.value); setPage(1) }}
          style={{ padding: '5px 10px', fontSize: 12, width: 'auto' }}
        >
          {BEHAVIOR_FILTERS.map((b) => (
            <option key={b.value || 'all'} value={b.value}>{b.label}</option>
          ))}
        </AuroraSelect>
      </div>

      {isError && (
        <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          Error: {error instanceof Error ? error.message : 'Failed to load change log'}
        </div>
      )}

      <DataTable
        columns={COLUMNS}
        isLoading={isLoading}
        isEmpty={data ? data.items.length === 0 : false}
        emptyMessage="No change log entries found."
      >
        {data?.items.map((entry) => <ChangeRow key={entry.id} entry={entry} />)}
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
