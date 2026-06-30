/**
 * TagAdminPage — full tag administration (Phase 9 — PRD §13).
 *
 * Route: /admin/tags
 *
 * Two sections:
 *
 * 1. Pending tags: list of tags awaiting approval, with Approve/Reject per row.
 *    Uses admin endpoints:
 *      GET  /api/admin/tags/pending
 *      POST /api/admin/tags/{id}/approve
 *      POST /api/admin/tags/{id}/reject
 *
 * 2. All tags table: searchable, paginated. Per-row actions:
 *    - Set Category (inline input → PATCH /api/admin/tags/{id}/category).
 *    - View Aliases (expand row → GET + POST/DELETE for aliases).
 *    - Merge Into (inline select → POST /api/admin/tags/{id}/merge-into/{target_id}).
 *
 * Styling: Aurora aesthetic (B3b restyle — visual pass, all behavior preserved).
 */

import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'
import {
  AdminPage, PageHeader,
  Button,
  DataTable, TableRow, Td, Pagination,
  AuroraInput, AuroraSelect,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// Starter tags seeding
// ---------------------------------------------------------------------------

function StarterTagsSection() {
  const queryClient = useQueryClient()
  const [result, setResult] = useState<api.LoadDefaultTagsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: api.loadDefaultTags,
    onSuccess: (data) => {
      setResult(data)
      setError(null)
      // Refresh both the all-tags table and the pending tags list
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-all'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-pending'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-merge-list'] })
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : 'Failed to load starter tags.')
      setResult(null)
    },
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)', marginBottom: 4 }}>
          Starter tags
        </div>
        <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0 }}>
          Seed the catalog with a curated default vocabulary organized by category
          (type, function, feature, theme, process, audience, mechanical).
          Existing tags are skipped — safe to run on a fresh instance or re-run at any time.
        </p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <Button
          disabled={mutation.isPending}
          onClick={() => {
            setResult(null)
            setError(null)
            mutation.mutate()
          }}
        >
          {mutation.isPending ? 'Loading…' : 'Load starter tags'}
        </Button>

        {result && (
          <span style={{ fontSize: 13, color: '#16A34A' }}>
            Added {result.added}, skipped {result.skipped}
          </span>
        )}

        {error && (
          <span style={{ fontSize: 13, color: 'var(--aurora-danger)' }}>{error}</span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pending tags section
// ---------------------------------------------------------------------------

function PendingTagRow({ tag }: { tag: api.TagAdminOut }) {
  const queryClient = useQueryClient()
  const [confirmReject, setConfirmReject] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const approveMutation = useMutation({
    mutationFn: () => api.adminApproveTag(tag.id),
    onSuccess: () => {
      // Invalidate the pending list (removes the row), the all-tags table
      // (approved tag now appears there), and the general tags key so the
      // tag cloud and other consumers pick up the change.
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-pending'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-all'] })
      void queryClient.invalidateQueries({ queryKey: ['tags'] })
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Approve failed.'),
  })

  const rejectMutation = useMutation({
    mutationFn: () => api.adminRejectTag(tag.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-pending'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-all'] })
      void queryClient.invalidateQueries({ queryKey: ['tags'] })
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Reject failed.'),
  })

  const busy = approveMutation.isPending || rejectMutation.isPending

  return (
    <TableRow>
      <Td style={{ fontWeight: 600 }}>{tag.name}</Td>
      <Td style={{ color: 'var(--aurora-muted)' }}>{tag.category ?? '—'}</Td>
      <Td style={{ color: 'var(--aurora-muted)' }}>{tag.item_count}</Td>
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

function PendingTagsSection() {
  const { data: pending = [], isLoading, isError, error } = useQuery({
    queryKey: ['admin-tags-pending'],
    queryFn: api.listAdminPendingTags,
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)', marginBottom: 4 }}>
          Pending tags
        </div>
        <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0 }}>
          Tags submitted by the import wizard that need approval before they
          appear in the catalog tag cloud.{' '}
          <a
            href="/admin/pending-tags"
            style={{ color: 'var(--aurora-accent)', textDecoration: 'none', fontSize: 12 }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none' }}
          >
            Focused pending-tags view →
          </a>
        </p>
      </div>

      {isError && (
        <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          {error instanceof Error ? error.message : 'Failed to load pending tags.'}
        </div>
      )}

      <DataTable
        columns={['Tag name', 'Category', 'Uses', 'Actions']}
        isLoading={isLoading}
        isEmpty={!isLoading && pending.length === 0}
        emptyMessage="No pending tags."
      >
        {pending.map((tag) => (
          <PendingTagRow key={tag.id} tag={tag} />
        ))}
      </DataTable>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Aliases expand panel (rendered inside a colspan row)
// ---------------------------------------------------------------------------

function AliasesPanel({ tagId, onClose }: { tagId: number; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [newAlias, setNewAlias] = useState('')
  const [addError, setAddError] = useState<string | null>(null)

  const { data: aliases = [], isLoading } = useQuery({
    queryKey: ['tag-aliases', tagId],
    queryFn: () => api.listTagAliases(tagId),
  })

  const addMutation = useMutation({
    mutationFn: () => api.addTagAlias(tagId, newAlias.trim()),
    onSuccess: () => {
      setNewAlias('')
      setAddError(null)
      void queryClient.invalidateQueries({ queryKey: ['tag-aliases', tagId] })
    },
    onError: (err) =>
      setAddError(err instanceof Error ? err.message : 'Failed to add alias.'),
  })

  const deleteMutation = useMutation({
    mutationFn: (aliasId: number) => api.deleteTagAlias(aliasId),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['tag-aliases', tagId] }),
  })

  return (
    <tr style={{ borderTop: '1px solid var(--aurora-divider)', background: 'rgba(15,164,171,0.02)' }}>
      <td colSpan={5} style={{ padding: '16px 18px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 480 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              Aliases
            </span>
            <button
              type="button"
              onClick={onClose}
              style={{ fontSize: 12, color: 'var(--aurora-muted)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
            >
              Close
            </button>
          </div>

          {isLoading ? (
            <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>Loading…</p>
          ) : aliases.length === 0 ? (
            <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>No aliases yet.</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {aliases.map((a) => (
                <li key={a.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--aurora-text)' }}>{a.alias}</span>
                  <Button
                    variant="danger"
                    size="sm"
                    disabled={deleteMutation.isPending}
                    onClick={() => deleteMutation.mutate(a.id)}
                  >
                    Delete
                  </Button>
                </li>
              ))}
            </ul>
          )}

          {/* Add alias */}
          <div style={{ display: 'flex', gap: 8 }}>
            <AuroraInput
              type="text"
              value={newAlias}
              onChange={(e) => {
                setNewAlias(e.target.value)
                setAddError(null)
              }}
              placeholder="New alias…"
              style={{ flex: 1 }}
            />
            <Button
              size="sm"
              disabled={addMutation.isPending || !newAlias.trim()}
              onClick={() => addMutation.mutate()}
            >
              {addMutation.isPending ? 'Adding…' : 'Add'}
            </Button>
          </div>
          {addError && (
            <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{addError}</p>
          )}
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Merge panel (rendered inside a colspan row)
// ---------------------------------------------------------------------------

interface MergePanelProps {
  tag: api.TagSummary
  allTags: api.TagSummary[]
  onClose: () => void
}

function MergePanel({ tag, allTags, onClose }: MergePanelProps) {
  const queryClient = useQueryClient()
  const [targetId, setTargetId] = useState<number | ''>('')
  const [confirm, setConfirm] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [mergeError, setMergeError] = useState<string | null>(null)

  const options = allTags.filter((t) => t.id !== tag.id)

  const mergeMutation = useMutation({
    mutationFn: () => api.mergeTag(tag.id, targetId as number),
    onSuccess: (data) => {
      setResult(
        `Merged "${data.source_name}" into target (id=${data.target_id}). ` +
          `Items repointed: ${data.items_repointed}, aliases repointed: ${data.aliases_repointed}.`,
      )
      setMergeError(null)
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-all'] })
    },
    onError: (err) => {
      setMergeError(err instanceof Error ? err.message : 'Merge failed.')
      setConfirm(false)
    },
  })

  if (result) {
    return (
      <tr style={{ borderTop: '1px solid var(--aurora-divider)', background: 'rgba(15,164,171,0.02)' }}>
        <td colSpan={5} style={{ padding: '16px 18px' }}>
          <p style={{ fontSize: 12, color: '#16A34A', margin: '0 0 8px' }}>{result}</p>
          <button
            type="button"
            onClick={onClose}
            style={{ fontSize: 12, color: 'var(--aurora-muted)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
          >
            Close
          </button>
        </td>
      </tr>
    )
  }

  return (
    <tr style={{ borderTop: '1px solid var(--aurora-divider)', background: 'rgba(15,164,171,0.02)' }}>
      <td colSpan={5} style={{ padding: '16px 18px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 480 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              Merge "{tag.name}" into another tag
            </span>
            <button
              type="button"
              onClick={onClose}
              style={{ fontSize: 12, color: 'var(--aurora-muted)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
            >
              Cancel
            </button>
          </div>

          <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0, lineHeight: 1.5 }}>
            All items using "{tag.name}" will be re-tagged to the target.
            The source tag will be deleted and its name will become an alias of the target.
            This operation cannot be undone.
          </p>

          <AuroraSelect
            value={targetId}
            onChange={(e) => {
              setTargetId(e.target.value === '' ? '' : Number(e.target.value))
              setConfirm(false)
              setMergeError(null)
            }}
          >
            <option value="">— select target tag —</option>
            {options.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} ({t.item_count} uses)
              </option>
            ))}
          </AuroraSelect>

          {targetId !== '' && !confirm && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirm(true)}
              extraStyle={{ color: '#D97706', borderColor: 'rgba(245,158,11,0.4)', background: 'rgba(245,158,11,0.07)', alignSelf: 'flex-start' }}
            >
              Merge — confirm required
            </Button>
          )}

          {confirm && targetId !== '' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>
                This will permanently delete "{tag.name}". Are you sure?
              </span>
              <Button
                variant="danger"
                size="sm"
                disabled={mergeMutation.isPending}
                onClick={() => mergeMutation.mutate()}
              >
                {mergeMutation.isPending ? 'Merging…' : 'Yes, merge'}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirm(false)}>
                Cancel
              </Button>
            </div>
          )}

          {mergeError && (
            <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{mergeError}</p>
          )}
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// All-tags row
// ---------------------------------------------------------------------------

interface AllTagRowProps {
  tag: api.TagSummary
  allTags: api.TagSummary[]
}

function AllTagRow({ tag, allTags }: AllTagRowProps) {
  const queryClient = useQueryClient()
  const [showAliases, setShowAliases] = useState(false)
  const [showMerge, setShowMerge] = useState(false)
  const [editingCategory, setEditingCategory] = useState(false)
  const [categoryInput, setCategoryInput] = useState(tag.category ?? '')
  const [categoryError, setCategoryError] = useState<string | null>(null)
  const [categorySaved, setCategorySaved] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const categoryMutation = useMutation({
    mutationFn: (cat: string | null) => api.adminSetTagCategory(tag.id, cat),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-all'] })
      setEditingCategory(false)
      setCategorySaved(true)
      setTimeout(() => setCategorySaved(false), 2000)
    },
    onError: (err) =>
      setCategoryError(err instanceof Error ? err.message : 'Failed to set category.'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteTag(tag.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-all'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-pending'] })
      void queryClient.invalidateQueries({ queryKey: ['tags'] })
    },
    onError: (err) => {
      setDeleteError(err instanceof Error ? err.message : 'Delete failed.')
      setConfirmDelete(false)
    },
  })

  const handleCategorySave = () => {
    setCategoryError(null)
    const trimmed = categoryInput.trim() || null
    categoryMutation.mutate(trimmed)
  }

  return (
    <>
      <TableRow>
        <Td style={{ fontWeight: 600 }}>{tag.name}</Td>

        {/* Category cell */}
        <Td>
          {editingCategory ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <AuroraInput
                type="text"
                value={categoryInput}
                onChange={(e) => {
                  setCategoryInput(e.target.value)
                  setCategoryError(null)
                }}
                placeholder="e.g. material"
                style={{ width: 110, fontSize: 12 }}
                autoFocus
              />
              <Button
                size="sm"
                disabled={categoryMutation.isPending}
                onClick={handleCategorySave}
              >
                {categoryMutation.isPending ? '…' : 'Save'}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEditingCategory(false)
                  setCategoryInput(tag.category ?? '')
                  setCategoryError(null)
                }}
              >
                ×
              </Button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => {
                setEditingCategory(true)
                setCategoryInput(tag.category ?? '')
              }}
              style={{
                fontSize: 13,
                color: 'var(--aurora-muted)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                textAlign: 'left',
              }}
              title="Click to edit category"
            >
              {tag.category ?? <span style={{ fontStyle: 'italic', opacity: 0.5 }}>none</span>}
            </button>
          )}
          {categoryError && (
            <p style={{ marginTop: 2, fontSize: 11, color: 'var(--aurora-danger)', margin: '2px 0 0' }}>{categoryError}</p>
          )}
          {categorySaved && (
            <p style={{ marginTop: 2, fontSize: 11, color: '#16A34A', margin: '2px 0 0' }}>Saved</p>
          )}
        </Td>

        <Td style={{ color: 'var(--aurora-muted)' }}>{tag.item_count}</Td>

        {/* Actions */}
        <Td>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setShowAliases((v) => !v)
                setShowMerge(false)
              }}
            >
              {showAliases ? 'Hide aliases' : 'Aliases'}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setShowMerge((v) => !v)
                setShowAliases(false)
              }}
            >
              {showMerge ? 'Cancel merge' : 'Merge into…'}
            </Button>

            {confirmDelete ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 11, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>
                  Delete &ldquo;{tag.name}&rdquo;? Removes it from {tag.item_count} item{tag.item_count === 1 ? '' : 's'}.
                </span>
                <Button
                  variant="danger"
                  size="sm"
                  disabled={deleteMutation.isPending}
                  onClick={() => {
                    setDeleteError(null)
                    deleteMutation.mutate()
                  }}
                >
                  {deleteMutation.isPending ? 'Deleting…' : 'Confirm delete'}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
                  Cancel
                </Button>
              </span>
            ) : (
              <Button
                variant="danger"
                size="sm"
                onClick={() => {
                  setConfirmDelete(true)
                  setDeleteError(null)
                }}
              >
                Delete
              </Button>
            )}
          </div>
          {deleteError && (
            <p style={{ marginTop: 4, fontSize: 11, color: 'var(--aurora-danger)', margin: '4px 0 0' }}>{deleteError}</p>
          )}
        </Td>
      </TableRow>

      {showAliases && (
        <AliasesPanel tagId={tag.id} onClose={() => setShowAliases(false)} />
      )}
      {showMerge && (
        <MergePanel tag={tag} allTags={allTags} onClose={() => setShowMerge(false)} />
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// All tags section
// ---------------------------------------------------------------------------

function AllTagsSection() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const PER_PAGE = 50

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['admin-tags-all', search, page],
    queryFn: () =>
      api.listAllTags({
        q: search || undefined,
        active_only: false,
        page,
        per_page: PER_PAGE,
      }),
    placeholderData: (prev) => prev,
  })

  // Load all tags (up to 500) for the merge dropdown — only when needed
  const { data: allTagsForMerge } = useQuery({
    queryKey: ['admin-tags-merge-list'],
    queryFn: () => api.listAllTags({ active_only: false, per_page: 500 }),
    staleTime: 30_000,
  })

  const tags = data?.tags ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / PER_PAGE)
  const mergeList = allTagsForMerge?.tags ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)', marginBottom: 4 }}>
          All tags
        </div>
        <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0 }}>
          Search, set categories, manage aliases, or merge duplicate tags.
        </p>
      </div>

      {/* Search */}
      <AuroraInput
        type="text"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value)
          setPage(1)
        }}
        placeholder="Search tags…"
        style={{ maxWidth: 320 }}
      />

      {isError && (
        <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          {error instanceof Error ? error.message : 'Failed to load tags.'}
        </div>
      )}

      <DataTable
        columns={['Name', 'Category', 'Uses', 'Actions']}
        isLoading={isLoading}
        isEmpty={!isLoading && tags.length === 0}
        emptyMessage="No tags found."
      >
        {tags.map((tag) => (
          <AllTagRow key={tag.id} tag={tag} allTags={mergeList} />
        ))}
      </DataTable>

      {total > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>{total} total</span>
          <Pagination
            page={page}
            totalPages={totalPages}
            onPrev={() => setPage((p) => p - 1)}
            onNext={() => setPage((p) => p + 1)}
          />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function TagAdminPage() {
  return (
    <AdminPage>
      <PageHeader
        title="Tag Administration"
        description="Approve or reject pending tags, manage categories and aliases, and merge duplicate tags into canonical forms."
      />

      <StarterTagsSection />

      <div style={{ borderTop: '1px solid var(--aurora-divider)', margin: '4px 0' }} />

      <PendingTagsSection />

      <div style={{ borderTop: '1px solid var(--aurora-divider)', margin: '4px 0' }} />

      <AllTagsSection />
    </AdminPage>
  )
}
