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
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'
import {
  getReconcileMode,
  reconcileSettingKey,
  RECONCILE_DEFAULTS,
} from '@/lib/reconcile-utils'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function behaviorBadge(behavior: string) {
  const cls =
    behavior === 'sidecar_sync'
      ? 'bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-200'
      : behavior === 'file_changes'
        ? 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200'
        : behavior === 're_render'
          ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
          : 'bg-muted text-muted-foreground'
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {behavior}
    </span>
  )
}

function statusBadge(status: string) {
  const cls =
    status === 'pending'
      ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
      : status === 'approved'
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
// Review row (expandable)
// ---------------------------------------------------------------------------

function ReviewRow({ item }: { item: api.ReviewItemOut }) {
  const [expanded, setExpanded] = useState(false)
  const queryClient = useQueryClient()

  const approveMutation = useMutation({
    mutationFn: () => api.approveReview(item.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['reviews'] })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: () => api.rejectReview(item.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['reviews'] })
    },
  })

  const busy = approveMutation.isPending || rejectMutation.isPending

  return (
    <>
      <tr
        className="border-b border-border hover:bg-muted/40 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="py-2 px-3">{behaviorBadge(item.behavior)}</td>
        <td className="py-2 px-3 font-mono text-xs">{item.change_type}</td>
        <td className="py-2 px-3 text-xs">
          {item.item_id != null ? (
            <a
              href={`/items/${item.item_id}`}
              className="text-primary hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              #{item.item_id}
            </a>
          ) : (
            '—'
          )}
        </td>
        <td className="py-2 px-3 text-xs text-muted-foreground max-w-sm">
          <span className="truncate block" title={item.summary}>
            {item.summary.length > 100
              ? `${item.summary.slice(0, 100)}…`
              : item.summary}
          </span>
        </td>
        <td className="py-2 px-3 text-xs text-muted-foreground whitespace-nowrap">
          {formatTs(item.created_at)}
        </td>
        <td className="py-2 px-3">{statusBadge(item.status)}</td>
        <td className="py-2 px-3" onClick={(e) => e.stopPropagation()}>
          {item.status === 'pending' && (
            <div className="flex gap-1">
              <button
                onClick={() => approveMutation.mutate()}
                disabled={busy}
                className="px-2 py-1 rounded text-xs font-medium bg-green-600 text-white
                           hover:bg-green-700 disabled:opacity-50 transition-colors"
              >
                {approveMutation.isPending ? '…' : 'Approve'}
              </button>
              <button
                onClick={() => rejectMutation.mutate()}
                disabled={busy}
                className="px-2 py-1 rounded text-xs font-medium bg-red-600 text-white
                           hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                {rejectMutation.isPending ? '…' : 'Reject'}
              </button>
            </div>
          )}
          {(approveMutation.isError || rejectMutation.isError) && (
            <p className="text-xs text-red-500 mt-1">Action failed</p>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border bg-muted/20">
          <td colSpan={7} className="px-3 py-2 text-xs">
            <div className="font-medium mb-1">Proposed action:</div>
            <pre className="text-muted-foreground whitespace-pre-wrap font-mono text-xs bg-muted rounded p-2 overflow-auto max-h-48">
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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  return (
    <section>
      <h2 className="text-lg font-semibold mb-3">Reconcile Modes</h2>
      <div className="rounded-lg border border-border bg-card p-4">
        <p className="text-xs text-muted-foreground mb-4">
          Controls whether the nightly library scan applies changes automatically
          ("auto") or queues them here for review ("review"). Per-item rescans
          always use auto mode regardless of these settings.
        </p>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
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
                  className={`flex items-start justify-between gap-4 py-3 ${
                    idx > 0 ? 'border-t border-border' : ''
                  }`}
                >
                  <div className="flex-1">
                    <div className="text-sm font-medium">{b.label}</div>
                    <div className="text-xs text-muted-foreground">{b.description}</div>
                    {currentMode === defaultMode && (
                      <div className="text-xs text-muted-foreground mt-0.5">
                        (engine default)
                      </div>
                    )}
                  </div>
                  <div className="flex gap-1 shrink-0">
                    {(['auto', 'review'] as const).map((mode) => (
                      <button
                        key={mode}
                        disabled={isPending}
                        onClick={() =>
                          mutation.mutate({ key: settingKey, value: mode })
                        }
                        className={`px-3 py-1 rounded-md text-xs font-medium transition-colors disabled:opacity-50 ${
                          currentMode === mode
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted text-muted-foreground hover:bg-muted/80'
                        }`}
                      >
                        {mode === 'auto' ? 'Auto' : 'Review'}
                      </button>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
        {mutation.isError && (
          <p className="text-xs text-red-500 mt-2">
            Failed to save:{' '}
            {mutation.error instanceof Error ? mutation.error.message : 'unknown error'}
          </p>
        )}
      </div>
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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Review Queue</h1>
        <span className="text-sm text-muted-foreground">
          {data ? `${data.total} item(s)` : ''}
        </span>
      </div>

      {/* Reconcile Modes card */}
      <ReconcileModesCard />

      {/* Queue table */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium">View:</label>
          <div className="flex gap-1">
            {STATUS_TABS.map((t) => (
              <button
                key={t.value || 'all'}
                onClick={() => {
                  setStatusFilter(t.value)
                  setPage(1)
                }}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  statusFilter === t.value
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}
        {isError && (
          <p className="text-red-600 text-sm">
            Error:{' '}
            {error instanceof Error ? error.message : 'Failed to load review queue'}
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
                      Created
                    </th>
                    <th className="py-2 px-3 text-left font-medium text-muted-foreground text-xs">
                      Status
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
                        {statusFilter === 'pending'
                          ? 'No pending review items. The queue is clear.'
                          : 'No review items found.'}
                      </td>
                    </tr>
                  ) : (
                    data.items.map((item) => (
                      <ReviewRow key={item.id} item={item} />
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
      </section>
    </div>
  )
}
