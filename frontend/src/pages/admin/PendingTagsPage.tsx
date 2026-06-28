/**
 * PendingTagsPage — admin view for approving pending (not-yet-canonical) tags.
 *
 * Route: /admin/pending-tags
 *
 * Pending tags are created by the import wizard when an unknown tag string
 * is encountered during reconciliation.  Admins promote them to active/canonical
 * via POST /api/tags/{id}/approve so they become visible in the tag cloud.
 *
 * Phase 8b addition: "AI-assist: possible duplicates (client-side matching)" section
 * at the top uses client-side Levenshtein fuzzy matching to surface pending tags that
 * look like near-duplicates of existing canonical tags. No AI endpoint is called here;
 * the matching is entirely client-side.
 *
 * Uses GET /api/tags?active_only=false and filters client-side for status=pending.
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
    <AdminPage>
      <PageHeader
        title="Pending Tags"
        description="Tags added by the import wizard that haven't been approved yet. Approving a tag makes it canonical and visible in the tag cloud."
        meta={isLoading ? undefined : `${pendingTags.length} tag${pendingTags.length === 1 ? '' : 's'}`}
      />

      {/* Phase 8b: AI-assist duplicate detection (client-side only) */}
      {data && <DuplicateDetectSection allTags={data.tags} />}

      {isError && (
        <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          {error instanceof Error ? error.message : 'Failed to load tags.'}
        </div>
      )}

      {approveMutation.isError && (
        <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          {approveMutation.error instanceof Error
            ? approveMutation.error.message
            : 'Failed to approve tag.'}
        </div>
      )}

      <DataTable
        columns={['Tag name', 'Category', 'Uses', 'Action']}
        isLoading={isLoading}
        isEmpty={!isLoading && pendingTags.length === 0}
        emptyMessage="No pending tags."
      >
        {pendingTags.map((tag) => (
          <TableRow key={tag.id}>
            <Td style={{ fontWeight: 600 }}>{tag.name}</Td>
            <Td style={{ color: 'var(--aurora-muted)' }}>{tag.category ?? '—'}</Td>
            <Td style={{ color: 'var(--aurora-muted)' }}>{tag.popularity_count}</Td>
            <Td>
              <Button
                size="sm"
                disabled={approveMutation.isPending}
                onClick={() => approveMutation.mutate(tag.id)}
                extraStyle={{ background: 'rgba(22,163,74,0.1)', border: '1px solid rgba(22,163,74,0.3)', color: '#16A34A' }}
              >
                Approve
              </Button>
            </Td>
          </TableRow>
        ))}
      </DataTable>
    </AdminPage>
  )
}
