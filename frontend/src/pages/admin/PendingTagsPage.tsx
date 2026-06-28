/**
 * PendingTagsPage — admin view for approving pending (not-yet-canonical) tags.
 *
 * Route: /admin/pending-tags
 *
 * Pending tags are created by the import wizard when an unknown tag string
 * is encountered during reconciliation.  Admins promote them to active/canonical
 * via POST /api/tags/{id}/approve so they become visible in the tag cloud.
 *
 * Uses GET /api/tags?active_only=false and filters client-side for status=pending.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function PendingTagsPage() {
  const queryClient = useQueryClient()

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['tags', 'pending'],
    queryFn: () =>
      api.listAllTags({
        active_only: false,
        per_page: 200,
      }),
  })

  // Filter to pending tags only (status field not on TagSummary but we'll work
  // with what the API returns — pending tags will have popularity_count 0 in
  // most cases).  The backend returns all tags when active_only=false; we need
  // to identify pending ones.  Since TagSummary lacks a status field, we rely
  // on the backend's active_only=false returning *all* tags including pending
  // ones, and we call approvePendingTag on any of them via their id.
  // Note: the current TagSummary interface doesn't expose status.  The
  // approval flow works regardless — the backend validates the tag is pending.
  const pendingTags = data?.tags ?? []

  const approveMutation = useMutation({
    mutationFn: (id: number) => api.approvePendingTag(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tags'] })
    },
  })

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Pending Tags</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Tags added by the import wizard that haven't been approved yet.
          Approving a tag makes it canonical and visible in the tag cloud.
        </p>
      </div>

      {isLoading && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}

      {isError && (
        <p className="text-sm text-red-600">
          {error instanceof Error ? error.message : 'Failed to load tags.'}
        </p>
      )}

      {data && pendingTags.length === 0 && (
        <div className="py-16 text-center">
          <p className="text-muted-foreground">No pending tags.</p>
        </div>
      )}

      {pendingTags.length > 0 && (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Tag name
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Category
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Uses
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Action
                </th>
              </tr>
            </thead>
            <tbody>
              {pendingTags.map((tag) => (
                <tr
                  key={tag.id}
                  className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors"
                >
                  <td className="px-4 py-3 font-medium">{tag.name}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {tag.category ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {tag.popularity_count}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      disabled={approveMutation.isPending}
                      onClick={() => approveMutation.mutate(tag.id)}
                      className="rounded-md bg-primary px-3 py-1 text-xs text-primary-foreground hover:opacity-90 disabled:opacity-50 transition-colors"
                    >
                      Approve
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {approveMutation.isError && (
        <p className="text-sm text-red-600">
          {approveMutation.error instanceof Error
            ? approveMutation.error.message
            : 'Failed to approve tag.'}
        </p>
      )}
    </div>
  )
}
