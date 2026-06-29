/**
 * PendingTagsPage — admin view for approving pending (not-yet-canonical) tags.
 *
 * Route: /admin/pending-tags
 *
 * Pending tags are created by the import wizard when an unknown tag string
 * is encountered during reconciliation.  Admins promote them to active/canonical
 * via POST /api/admin/tags/{id}/approve so they become visible in the tag cloud.
 *
 * Phase 8b addition: "AI-assist: possible duplicates (client-side matching)" section
 * at the top uses client-side Levenshtein fuzzy matching to surface pending tags that
 * look like near-duplicates of existing canonical tags. No AI endpoint is called here;
 * the matching is entirely client-side.
 *
 * Uses GET /api/admin/tags/pending for the approval table (pending-only, exact list),
 * and GET /api/tags?active_only=false for the DuplicateDetectSection comparison.
 *
 * Tip: /admin/tags (Tag Administration) is the single-stop shop for pending approval
 * + alias management + merge. This page is a focused approve/reject view.
 *
 * Styling: Aurora aesthetic (B3b restyle — visual pass, all behavior preserved).
 */

import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'
import { fuzzyMatchTags } from '@/lib/import-utils'
import {
  AdminPage, PageHeader,
  Card, SectionHeader,
  Button,
  DataTable, TableRow, Td,
  INPUT_STYLE,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// AI-assist: duplicate detection (client-side fuzzy matching)
// ---------------------------------------------------------------------------

interface DuplicateDetectSectionProps {
  allTags: api.TagSummary[]
}

function DuplicateDetectSection({ allTags }: DuplicateDetectSectionProps) {
  // Heuristic: tags with popularity_count === 0 are likely pending (not yet used in catalog).
  // Tags with popularity_count > 0 are canonical/active.
  const canonicalTags = useMemo(
    () => allTags.filter((t) => t.popularity_count > 0).map((t) => t.name),
    [allTags],
  )
  const pendingLikeTags = useMemo(
    () => allTags.filter((t) => t.popularity_count === 0).map((t) => t.name),
    [allTags],
  )

  const [tagInput, setTagInput] = useState(() => pendingLikeTags.join(', '))
  const [results, setResults] = useState<{ pending: string; closest: string }[] | null>(null)

  const runMatch = () => {
    const names = tagInput
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    const matches = names
      .map((name) => ({
        pending: name,
        closest: fuzzyMatchTags(name, canonicalTags) ?? '',
      }))
      .filter((r) => r.closest !== '')
    setResults(matches)
  }

  if (pendingLikeTags.length === 0 || canonicalTags.length === 0) return null

  return (
    <Card>
      <SectionHeader>AI-assist: possible duplicates (client-side matching)</SectionHeader>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0, lineHeight: 1.6 }}>
          Compares pending tag names against existing canonical tags using
          Levenshtein distance (≤ 3 edits). No AI endpoint is called — this is
          client-side only. Edit the list below and click{' '}
          <strong style={{ color: 'var(--aurora-text-dim)' }}>Find duplicates</strong> to re-run.
        </p>

        <textarea
          value={tagInput}
          onChange={(e) => {
            setTagInput(e.target.value)
            setResults(null)
          }}
          rows={3}
          placeholder="Comma-separated tag names to check…"
          style={{
            ...INPUT_STYLE,
            resize: 'vertical',
            fontFamily: 'inherit',
          }}
        />

        <Button
          variant="ghost"
          size="sm"
          onClick={runMatch}
          disabled={!tagInput.trim()}
          extraStyle={{ alignSelf: 'flex-start' }}
        >
          Find duplicates
        </Button>

        {results !== null && (
          results.length === 0 ? (
            <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>
              No near-duplicates found (all tags differ by more than 3 edits from
              existing canonical tags).
            </p>
          ) : (
            <DataTable
              columns={['Pending tag', 'Possible duplicate of']}
              isEmpty={false}
            >
              {results.map((r) => (
                <TableRow key={r.pending}>
                  <Td style={{ fontWeight: 600 }}>{r.pending}</Td>
                  <Td style={{ color: 'var(--aurora-muted)' }}>{r.closest}</Td>
                </TableRow>
              ))}
            </DataTable>
          )
        )}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Per-row approve + reject
// ---------------------------------------------------------------------------

function PendingTagRow({ tag }: { tag: api.TagAdminOut }) {
  const queryClient = useQueryClient()
  const [confirmReject, setConfirmReject] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const approveMutation = useMutation({
    mutationFn: () => api.adminApproveTag(tag.id),
    onSuccess: () => {
      setError(null)
      // Invalidate the exact pending-tags key used by this query, plus the
      // general tags key so other pages (tag cloud, all-tags table) update too.
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-pending'] })
      void queryClient.invalidateQueries({ queryKey: ['tags'] })
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Approve failed.'),
  })

  const rejectMutation = useMutation({
    mutationFn: () => api.adminRejectTag(tag.id),
    onSuccess: () => {
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-pending'] })
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Reject failed.'),
  })

  const busy = approveMutation.isPending || rejectMutation.isPending

  return (
    <TableRow>
      <Td style={{ fontWeight: 600 }}>{tag.name}</Td>
      <Td style={{ color: 'var(--aurora-muted)' }}>{tag.category ?? '—'}</Td>
      <Td style={{ color: 'var(--aurora-muted)' }}>{tag.popularity_count}</Td>
      <Td>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <Button
            size="sm"
            disabled={busy}
            onClick={() => {
              setError(null)
              approveMutation.mutate()
            }}
            extraStyle={{ background: 'rgba(22,163,74,0.1)', border: '1px solid rgba(22,163,74,0.3)', color: '#16A34A' }}
          >
            {approveMutation.isPending ? 'Approving…' : 'Approve'}
          </Button>

          {confirmReject ? (
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>Sure?</span>
              <Button
                variant="danger"
                size="sm"
                disabled={rejectMutation.isPending}
                onClick={() => {
                  setError(null)
                  rejectMutation.mutate()
                }}
              >
                {rejectMutation.isPending ? 'Rejecting…' : 'Confirm reject'}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmReject(false)}>
                Cancel
              </Button>
            </span>
          ) : (
            <Button
              variant="danger"
              size="sm"
              disabled={approveMutation.isPending}
              onClick={() => setConfirmReject(true)}
            >
              Reject
            </Button>
          )}
        </div>
        {error && (
          <p style={{ marginTop: 4, fontSize: 11, color: 'var(--aurora-danger)', margin: '4px 0 0' }}>{error}</p>
        )}
      </Td>
    </TableRow>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function PendingTagsPage() {
  // All-tags query: used only by DuplicateDetectSection for fuzzy comparison.
  // Key kept separate from the pending-only query to avoid cache confusion.
  const { data: allTagsData } = useQuery({
    queryKey: ['tags', 'all-for-dup-detect'],
    queryFn: () =>
      api.listAllTags({
        active_only: false,
        per_page: 500,
      }),
  })

  // Pending-only query: drives the approval table.
  // Uses the exact same key and endpoint as TagAdminPage's PendingTagsSection
  // so invalidation is consistent across both screens.
  const { data: pendingTags = [], isLoading, isError, error } = useQuery({
    queryKey: ['admin-tags-pending'],
    queryFn: api.listAdminPendingTags,
  })

  return (
    <AdminPage>
      <PageHeader
        title="Pending Tags"
        description="Tags added by the import wizard that haven't been approved yet. Approving a tag makes it canonical and visible in the tag cloud. For aliases, merges, and category edits, use Tag Administration (/admin/tags)."
        meta={isLoading ? undefined : `${pendingTags.length} tag${pendingTags.length === 1 ? '' : 's'}`}
      />

      {/* Phase 8b: AI-assist duplicate detection (client-side only) */}
      {allTagsData && <DuplicateDetectSection allTags={allTagsData.tags} />}

      {isError && (
        <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          {error instanceof Error ? error.message : 'Failed to load pending tags.'}
        </div>
      )}

      <DataTable
        columns={['Tag name', 'Category', 'Uses', 'Actions']}
        isLoading={isLoading}
        isEmpty={!isLoading && pendingTags.length === 0}
        emptyMessage="No pending tags."
      >
        {pendingTags.map((tag) => (
          <PendingTagRow key={tag.id} tag={tag} />
        ))}
      </DataTable>
    </AdminPage>
  )
}
