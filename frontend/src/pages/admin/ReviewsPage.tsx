/**
 * ReviewsPage — admin review queue for reconcile-engine proposed changes (PRD §8.2).
 *
 * Two tabs: Pending (default) and All.  Approve / Reject actions on pending items.
 * Expanding a row shows the proposed_action JSON payload.
 *
 * Also contains the "Reconcile Modes" card (Deliverable 5 / PRD §8.2):
 * three per-behavior Auto/Review toggles backed by the generic settings API.
 *
 * Route: /admin/reviews
 * Styling: Aurora aesthetic (B3a restyle — visual pass, all behavior preserved).
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'
import {
  getReconcileMode,
  reconcileSettingKey,
  RECONCILE_DEFAULTS,
} from '@/lib/reconcile-utils'
import {
  AdminPage, PageHeader,
  Card,
  Badge, behaviorVariant, issueStatusVariant,
  Button, FilterPill,
  DataTable, TableRow, Td, Pagination,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTs(ts: string | null): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString()
}

// ---------------------------------------------------------------------------
// Review row (expandable)
// ---------------------------------------------------------------------------

function ReviewRow({ item }: { item: api.ReviewItemOut }) {
  const [expanded, setExpanded] = useState(false)
  const queryClient = useQueryClient()

  const approveMutation = useMutation({
    mutationFn: () => api.approveReview(item.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['reviews'] }),
  })

  const rejectMutation = useMutation({
    mutationFn: () => api.rejectReview(item.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['reviews'] }),
  })

  const busy = approveMutation.isPending || rejectMutation.isPending

  return (
    <>
      <TableRow onClick={() => setExpanded((v) => !v)}>
        <Td>
          <Badge variant={behaviorVariant(item.behavior)}>{item.behavior}</Badge>
        </Td>
        <Td style={{ fontFamily: 'monospace', fontSize: 11 }}>{item.change_type}</Td>
        <Td style={{ fontSize: 12 }}>
          {item.item_id != null ? (
            <a
              href={`/items/${item.item_id}`}
              style={{ color: 'var(--aurora-accent)', textDecoration: 'none' }}
              onClick={(e) => e.stopPropagation()}
              onMouseEnter={(e) => ((e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline')}
              onMouseLeave={(e) => ((e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none')}
            >
              #{item.item_id}
            </a>
          ) : (
            <span style={{ color: 'var(--aurora-muted)' }}>—</span>
          )}
        </Td>
        <Td style={{ maxWidth: 300, color: 'var(--aurora-text-dim)' }} title={item.summary}>
          <span
            style={{
              display: 'block',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              fontSize: 12,
            }}
          >
            {item.summary.length > 100 ? `${item.summary.slice(0, 100)}…` : item.summary}
          </span>
        </Td>
        <Td style={{ fontSize: 11, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>
          {formatTs(item.created_at)}
        </Td>
        <Td>
          <Badge variant={issueStatusVariant(item.status)}>{item.status}</Badge>
        </Td>
        <Td onClick={(e) => e.stopPropagation()}>
          {item.status === 'pending' && (
            <div style={{ display: 'flex', gap: 6 }}>
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => approveMutation.mutate()}
                extraStyle={{ background: 'rgba(22,163,74,0.1)', border: '1px solid rgba(22,163,74,0.3)', color: '#16A34A' }}
              >
                {approveMutation.isPending ? '…' : 'Approve'}
              </Button>
              <Button
                variant="danger"
                size="sm"
                disabled={busy}
                onClick={() => rejectMutation.mutate()}
              >
                {rejectMutation.isPending ? '…' : 'Reject'}
              </Button>
            </div>
          )}
          {(approveMutation.isError || rejectMutation.isError) && (
            <span style={{ fontSize: 11, color: 'var(--aurora-danger)', display: 'block', marginTop: 4 }}>
              Action failed
            </span>
          )}
        </Td>
      </TableRow>

      {expanded && (
        <tr style={{ borderTop: '1px solid var(--aurora-divider)', background: 'rgba(15,164,171,0.02)' }}>
          <td colSpan={7} style={{ padding: '10px 14px' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--aurora-text-dim)', marginBottom: 6 }}>
              Proposed action:
            </div>
            <pre
              style={{
                fontSize: 11,
                color: 'var(--aurora-muted)',
                whiteSpace: 'pre-wrap',
                fontFamily: 'monospace',
                margin: 0,
                background: 'var(--aurora-glass)',
                border: '1px solid var(--aurora-glass-border)',
                borderRadius: 6,
                padding: '8px 10px',
                maxHeight: 200,
                overflow: 'auto',
              }}
            >
              {JSON.stringify(item.proposed_action, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Reconcile Modes card (Deliverable 5)
// ---------------------------------------------------------------------------

const RECONCILE_BEHAVIORS: { key: string; label: string; description: string }[] = [
  {
    key: 'sidecar_sync',
    label: 'Sidecar sync',
    description:
      'When the on-disk sidecar YAML and the DB diverge, auto-apply the change or queue for review.',
  },
  {
    key: 're_render',
    label: 'Re-render',
    description:
      'When a mesh file changes and a thumbnail refresh is needed, enqueue render automatically or queue for review.',
  },
  {
    key: 'file_changes',
    label: 'File changes',
    description:
      'When new or deleted files are detected in an item directory, apply automatically or queue for review.',
  },
]

function ReconcileModesCard() {
  const queryClient = useQueryClient()

  const { data: settings = [], isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: api.listSettings,
  })

  const mutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) =>
      api.upsertSetting(key, value),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['settings'] }),
  })

  return (
    <section>
      <div
        style={{
          fontSize: 16,
          fontWeight: 700,
          color: 'var(--aurora-text)',
          marginBottom: 12,
        }}
      >
        Reconcile Modes
      </div>
      <Card>
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: '0 0 16px', lineHeight: 1.6 }}>
          Controls whether the nightly library scan applies changes automatically
          ("auto") or queues them here for review ("review"). Per-item rescans
          always use auto mode regardless of these settings.
        </p>

        {isLoading ? (
          <p style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>Loading…</p>
        ) : (
          <div>
            {RECONCILE_BEHAVIORS.map((b, idx) => {
              const currentMode = getReconcileMode(settings, b.key)
              const defaultMode = RECONCILE_DEFAULTS[b.key]
              const settingKey = reconcileSettingKey(b.key)
              const isPending = mutation.isPending && mutation.variables?.key === settingKey

              return (
                <div
                  key={b.key}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: 16,
                    paddingTop: idx > 0 ? 14 : 0,
                    paddingBottom: 14,
                    borderTop: idx > 0 ? '1px solid var(--aurora-divider)' : 'none',
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--aurora-text)' }}>
                      {b.label}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 2, lineHeight: 1.5 }}>
                      {b.description}
                    </div>
                    {currentMode === defaultMode && (
                      <div style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 2 }}>
                        (engine default)
                      </div>
                    )}
                  </div>

                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    {(['auto', 'review'] as const).map((mode) => (
                      <FilterPill
                        key={mode}
                        active={currentMode === mode}
                        disabled={isPending}
                        onClick={() => mutation.mutate({ key: settingKey, value: mode })}
                      >
                        {mode === 'auto' ? 'Auto' : 'Review'}
                      </FilterPill>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {mutation.isError && (
          <p style={{ fontSize: 12, color: 'var(--aurora-danger)', marginTop: 8 }}>
            Failed to save:{' '}
            {mutation.error instanceof Error ? mutation.error.message : 'unknown error'}
          </p>
        )}
      </Card>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const PER_PAGE = 50

const STATUS_TABS = [
  { value: 'pending', label: 'Pending' },
  { value: '', label: 'All' },
]

const COLUMNS = ['Behavior', 'Change type', 'Item', 'Summary', 'Created', 'Status', 'Actions']

// ---------------------------------------------------------------------------
// Bulk actions (Approve all / Reject all) — Pending tab only
// ---------------------------------------------------------------------------

function BulkActions({ pendingTotal }: { pendingTotal: number }) {
  const queryClient = useQueryClient()
  const [confirmApprove, setConfirmApprove] = useState(false)
  const [confirmReject, setConfirmReject] = useState(false)
  const [lastResult, setLastResult] = useState<string | null>(null)

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['reviews'] })
    // Pending-review badges/widgets elsewhere in the shell + dashboard.
    void queryClient.invalidateQueries({ queryKey: ['reviews-pending-count'] })
    void queryClient.invalidateQueries({ queryKey: ['widget-pending-reviews-panel'] })
  }

  const approveAllMutation = useMutation({
    mutationFn: api.approveAllReviews,
    onSuccess: (data) => {
      setLastResult(`Approved ${data.approved} pending item${data.approved === 1 ? '' : 's'}.`)
      setConfirmApprove(false)
      invalidate()
    },
  })

  const rejectAllMutation = useMutation({
    mutationFn: api.rejectAllReviews,
    onSuccess: (data) => {
      setLastResult(`Rejected ${data.rejected} pending item${data.rejected === 1 ? '' : 's'}.`)
      setConfirmReject(false)
      invalidate()
    },
  })

  const busy = approveAllMutation.isPending || rejectAllMutation.isPending
  const disabled = pendingTotal === 0 || busy

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {confirmApprove ? (
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>
              Approve all {pendingTotal} pending? This applies each change to your library.
            </span>
            <Button
              size="sm"
              disabled={approveAllMutation.isPending}
              onClick={() => approveAllMutation.mutate()}
              extraStyle={{ background: 'rgba(22,163,74,0.1)', border: '1px solid rgba(22,163,74,0.3)', color: '#16A34A' }}
            >
              {approveAllMutation.isPending ? 'Approving…' : 'Confirm approve all'}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirmApprove(false)}>
              Cancel
            </Button>
          </span>
        ) : (
          <Button
            size="sm"
            disabled={disabled}
            onClick={() => { setConfirmReject(false); setLastResult(null); setConfirmApprove(true) }}
            extraStyle={{ background: 'rgba(22,163,74,0.1)', border: '1px solid rgba(22,163,74,0.3)', color: '#16A34A' }}
          >
            Approve all{pendingTotal > 0 ? ` (${pendingTotal})` : ''}
          </Button>
        )}

        {confirmReject ? (
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>
              Reject all {pendingTotal} pending?
            </span>
            <Button
              variant="danger"
              size="sm"
              disabled={rejectAllMutation.isPending}
              onClick={() => rejectAllMutation.mutate()}
            >
              {rejectAllMutation.isPending ? 'Rejecting…' : 'Confirm reject all'}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirmReject(false)}>
              Cancel
            </Button>
          </span>
        ) : (
          <Button
            variant="danger"
            size="sm"
            disabled={disabled}
            onClick={() => { setConfirmApprove(false); setLastResult(null); setConfirmReject(true) }}
          >
            Reject all{pendingTotal > 0 ? ` (${pendingTotal})` : ''}
          </Button>
        )}
      </div>

      {(approveAllMutation.isError || rejectAllMutation.isError) && (
        <span style={{ fontSize: 11, color: 'var(--aurora-danger)' }}>
          Bulk action failed.
        </span>
      )}
      {lastResult && !approveAllMutation.isError && !rejectAllMutation.isError && (
        <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>{lastResult}</span>
      )}
    </div>
  )
}

export function ReviewsPage() {
  const [statusFilter, setStatusFilter] = useState('pending')
  const [page, setPage] = useState(1)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['reviews', statusFilter, page],
    queryFn: () =>
      api.listReviews({
        status: statusFilter || undefined,
        page,
        per_page: PER_PAGE,
      }),
  })

  const totalPages = data ? Math.ceil(data.total / PER_PAGE) : 1

  return (
    <AdminPage>
      <PageHeader
        title="Review Queue"
        meta={data ? `${data.total} item${data.total === 1 ? '' : 's'}` : undefined}
      />

      {/* Reconcile Modes card */}
      <ReconcileModesCard />

      {/* Queue section */}
      <section style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* View tabs + bulk actions */}
        <div className="flex items-center justify-between" style={{ flexWrap: 'wrap', gap: 12 }}>
          <div className="flex items-center gap-2">
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              View
            </span>
            <div className="flex gap-1.5">
              {STATUS_TABS.map((t) => (
                <FilterPill
                  key={t.value || 'all'}
                  active={statusFilter === t.value}
                  onClick={() => { setStatusFilter(t.value); setPage(1) }}
                >
                  {t.label}
                </FilterPill>
              ))}
            </div>
          </div>

          {statusFilter === 'pending' && (
            <BulkActions pendingTotal={data?.total ?? 0} />
          )}
        </div>

        {isError && (
          <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
            Error: {error instanceof Error ? error.message : 'Failed to load review queue'}
          </div>
        )}

        <DataTable
          columns={COLUMNS}
          isLoading={isLoading}
          isEmpty={data ? data.items.length === 0 : false}
          emptyMessage={
            statusFilter === 'pending'
              ? 'No pending review items. The queue is clear.'
              : 'No review items found.'
          }
        >
          {data?.items.map((item) => <ReviewRow key={item.id} item={item} />)}
        </DataTable>

        <Pagination
          page={page}
          totalPages={totalPages}
          onPrev={() => setPage((p) => p - 1)}
          onNext={() => setPage((p) => p + 1)}
        />
      </section>
    </AdminPage>
  )
}
