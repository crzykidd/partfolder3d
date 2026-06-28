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
 * UI: Tailwind + CSS-variable theme + TanStack Query + apiFetch CSRF wrapper.
 * No Mantine, no toast library, no new deps.
 */

import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'

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
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-pending'] })
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Approve failed.'),
  })

  const rejectMutation = useMutation({
    mutationFn: () => api.adminRejectTag(tag.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin-tags-pending'] })
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Reject failed.'),
  })

  return (
    <tr className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
      <td className="px-4 py-3 font-medium">{tag.name}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {tag.category ?? '—'}
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {tag.popularity_count}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            disabled={approveMutation.isPending || rejectMutation.isPending}
            onClick={() => {
              setError(null)
              approveMutation.mutate()
            }}
            className="rounded-md bg-primary px-3 py-1 text-xs text-primary-foreground hover:opacity-90 disabled:opacity-50 transition-colors"
          >
            {approveMutation.isPending ? 'Approving…' : 'Approve'}
          </button>

          {confirmReject ? (
            <span className="flex items-center gap-1.5 text-xs">
              <span className="text-muted-foreground">Sure?</span>
              <button
                type="button"
                disabled={rejectMutation.isPending}
                onClick={() => {
                  setError(null)
                  rejectMutation.mutate()
                }}
                className="text-red-600 hover:text-red-700 font-medium disabled:opacity-50"
              >
                {rejectMutation.isPending ? 'Rejecting…' : 'Confirm reject'}
              </button>
              <button
                type="button"
                onClick={() => setConfirmReject(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                Cancel
              </button>
            </span>
          ) : (
            <button
              type="button"
              disabled={approveMutation.isPending}
              onClick={() => setConfirmReject(true)}
              className="text-xs text-red-500 hover:text-red-700 underline"
            >
              Reject
            </button>
          )}
        </div>
        {error && (
          <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>
        )}
      </td>
    </tr>
  )
}

function PendingTagsSection() {
  const { data: pending = [], isLoading, isError, error } = useQuery({
    queryKey: ['admin-tags-pending'],
    queryFn: api.listAdminPendingTags,
  })

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">Pending tags</h2>
        <p className="text-sm text-muted-foreground">
          Tags submitted by the import wizard that need approval before they
          appear in the catalog tag cloud.
        </p>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {isError && (
        <p className="text-sm text-red-600 dark:text-red-400">
          {error instanceof Error ? error.message : 'Failed to load pending tags.'}
        </p>
      )}

      {!isLoading && !isError && pending.length === 0 && (
        <div className="rounded-lg border border-dashed border-border py-8 text-center">
          <p className="text-sm text-muted-foreground">No pending tags.</p>
        </div>
      )}

      {pending.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                {['Tag name', 'Category', 'Uses', 'Actions'].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pending.map((tag) => (
                <PendingTagRow key={tag.id} tag={tag} />
              ))}
            </tbody>
          </table>
        </div>
      )}
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
    <tr className="border-b border-border bg-muted/10">
      <td colSpan={5} className="px-4 py-4">
        <div className="space-y-3 max-w-lg">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Aliases
            </h4>
            <button
              type="button"
              onClick={onClose}
              className="text-xs text-muted-foreground hover:text-foreground underline"
            >
              Close
            </button>
          </div>

          {isLoading ? (
            <p className="text-xs text-muted-foreground">Loading…</p>
          ) : aliases.length === 0 ? (
            <p className="text-xs text-muted-foreground">No aliases yet.</p>
          ) : (
            <ul className="space-y-1">
              {aliases.map((a) => (
                <li key={a.id} className="flex items-center justify-between text-sm">
                  <span className="font-mono text-xs">{a.alias}</span>
                  <button
                    type="button"
                    disabled={deleteMutation.isPending}
                    onClick={() => deleteMutation.mutate(a.id)}
                    className="text-xs text-red-500 hover:text-red-700 underline disabled:opacity-50"
                  >
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          )}

          {/* Add alias */}
          <div className="flex gap-2">
            <input
              type="text"
              value={newAlias}
              onChange={(e) => {
                setNewAlias(e.target.value)
                setAddError(null)
              }}
              placeholder="New alias…"
              className="input-base flex-1 text-sm"
            />
            <button
              type="button"
              disabled={addMutation.isPending || !newAlias.trim()}
              onClick={() => addMutation.mutate()}
              className="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:opacity-90 disabled:opacity-50 transition-colors"
            >
              {addMutation.isPending ? 'Adding…' : 'Add'}
            </button>
          </div>
          {addError && (
            <p className="text-xs text-red-600 dark:text-red-400">{addError}</p>
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

  // Filter out the current tag from options
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
      <tr className="border-b border-border bg-muted/10">
        <td colSpan={5} className="px-4 py-4">
          <p className="text-xs text-green-700 dark:text-green-400">{result}</p>
          <button
            type="button"
            onClick={onClose}
            className="mt-2 text-xs text-muted-foreground underline hover:text-foreground"
          >
            Close
          </button>
        </td>
      </tr>
    )
  }

  return (
    <tr className="border-b border-border bg-muted/10">
      <td colSpan={5} className="px-4 py-4">
        <div className="space-y-3 max-w-lg">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Merge "{tag.name}" into another tag
            </h4>
            <button
              type="button"
              onClick={onClose}
              className="text-xs text-muted-foreground hover:text-foreground underline"
            >
              Cancel
            </button>
          </div>

          <p className="text-xs text-muted-foreground">
            All items using "{tag.name}" will be re-tagged to the target.
            The source tag will be deleted and its name will become an alias of the target.
            This operation cannot be undone.
          </p>

          <div className="flex gap-2 items-center">
            <select
              value={targetId}
              onChange={(e) => {
                setTargetId(e.target.value === '' ? '' : Number(e.target.value))
                setConfirm(false)
                setMergeError(null)
              }}
              className="input-base flex-1 text-sm"
            >
              <option value="">— select target tag —</option>
              {options.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.popularity_count} uses)
                </option>
              ))}
            </select>
          </div>

          {targetId !== '' && !confirm && (
            <button
              type="button"
              onClick={() => setConfirm(true)}
              className="rounded-md border border-amber-400 bg-amber-50 dark:bg-amber-950/30 px-3 py-1.5 text-xs text-amber-800 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-950/50 transition-colors"
            >
              Merge — confirm required
            </button>
          )}

          {confirm && targetId !== '' && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">
                This will permanently delete "{tag.name}". Are you sure?
              </span>
              <button
                type="button"
                disabled={mergeMutation.isPending}
                onClick={() => mergeMutation.mutate()}
                className="rounded-md bg-red-600 px-3 py-1.5 text-xs text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                {mergeMutation.isPending ? 'Merging…' : 'Yes, merge'}
              </button>
              <button
                type="button"
                onClick={() => setConfirm(false)}
                className="text-xs text-muted-foreground underline hover:text-foreground"
              >
                Cancel
              </button>
            </div>
          )}

          {mergeError && (
            <p className="text-xs text-red-600 dark:text-red-400">{mergeError}</p>
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

  const handleCategorySave = () => {
    setCategoryError(null)
    const trimmed = categoryInput.trim() || null
    categoryMutation.mutate(trimmed)
  }

  return (
    <>
      <tr className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
        <td className="px-4 py-3 font-medium">{tag.name}</td>

        {/* Category cell */}
        <td className="px-4 py-3">
          {editingCategory ? (
            <div className="flex items-center gap-1.5">
              <input
                type="text"
                value={categoryInput}
                onChange={(e) => {
                  setCategoryInput(e.target.value)
                  setCategoryError(null)
                }}
                placeholder="e.g. material"
                className="input-base w-28 text-xs"
                autoFocus
              />
              <button
                type="button"
                disabled={categoryMutation.isPending}
                onClick={handleCategorySave}
                className="rounded-md bg-primary px-2 py-1 text-xs text-primary-foreground hover:opacity-90 disabled:opacity-50 transition-colors"
              >
                {categoryMutation.isPending ? '…' : 'Save'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditingCategory(false)
                  setCategoryInput(tag.category ?? '')
                  setCategoryError(null)
                }}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                ×
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => {
                setEditingCategory(true)
                setCategoryInput(tag.category ?? '')
              }}
              className="text-sm text-muted-foreground hover:text-foreground text-left"
              title="Click to edit category"
            >
              {tag.category ?? <span className="italic text-muted-foreground/60">none</span>}
            </button>
          )}
          {categoryError && (
            <p className="mt-0.5 text-xs text-red-600 dark:text-red-400">{categoryError}</p>
          )}
          {categorySaved && (
            <p className="mt-0.5 text-xs text-green-600 dark:text-green-400">Saved</p>
          )}
        </td>

        <td className="px-4 py-3 text-sm text-muted-foreground">
          {tag.popularity_count}
        </td>

        {/* Actions */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                setShowAliases((v) => !v)
                setShowMerge(false)
              }}
              className="text-xs text-muted-foreground hover:text-foreground underline"
            >
              {showAliases ? 'Hide aliases' : 'Aliases'}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowMerge((v) => !v)
                setShowAliases(false)
              }}
              className="text-xs text-muted-foreground hover:text-foreground underline"
            >
              {showMerge ? 'Cancel merge' : 'Merge into…'}
            </button>
          </div>
        </td>
      </tr>

      {showAliases && (
        <AliasesPanel tagId={tag.id} onClose={() => setShowAliases(false)} />
      )}
      {showMerge && (
        <MergePanel
          tag={tag}
          allTags={allTags}
          onClose={() => setShowMerge(false)}
        />
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
    <div className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">All tags</h2>
        <p className="text-sm text-muted-foreground">
          Search, set categories, manage aliases, or merge duplicate tags.
        </p>
      </div>

      {/* Search */}
      <input
        type="text"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value)
          setPage(1)
        }}
        placeholder="Search tags…"
        className="input-base w-full max-w-sm text-sm"
      />

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {isError && (
        <p className="text-sm text-red-600 dark:text-red-400">
          {error instanceof Error ? error.message : 'Failed to load tags.'}
        </p>
      )}

      {!isLoading && !isError && tags.length === 0 && (
        <div className="rounded-lg border border-dashed border-border py-8 text-center">
          <p className="text-sm text-muted-foreground">No tags found.</p>
        </div>
      )}

      {tags.length > 0 && (
        <>
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  {['Name', 'Category', 'Uses', 'Actions'].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tags.map((tag) => (
                  <AllTagRow key={tag.id} tag={tag} allTags={mergeList} />
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center gap-2 text-sm">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50 transition-colors"
              >
                Previous
              </button>
              <span className="text-muted-foreground text-xs">
                Page {page} of {totalPages} ({total} total)
              </span>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50 transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function TagAdminPage() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Tag Administration</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Approve or reject pending tags, manage categories and aliases, and
          merge duplicate tags into canonical forms.
        </p>
      </div>

      {/* Pending tags */}
      <PendingTagsSection />

      {/* Divider */}
      <hr className="border-border" />

      {/* All tags */}
      <AllTagsSection />
    </div>
  )
}
