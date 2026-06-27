/**
 * MyCreationsPage — items whose Creator is linked to the current user.
 *
 * Route: /me/creations
 *
 * Uses GET /api/me/creations (Phase 3a).  Creator → User linkage is set via
 * the "this is my own design" toggle in the import wizard (Phase 5).
 */

import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import * as api from '@/lib/api'

const PER_PAGE = 20

// ---------------------------------------------------------------------------
// Item card
// ---------------------------------------------------------------------------

function MiniItemCard({ item }: { item: api.ItemSummaryMini }) {
  return (
    <Link
      to={`/items/${item.key}`}
      className="flex flex-col rounded-lg border border-border bg-card p-3 hover:border-primary/50 transition-colors"
    >
      <div className="flex items-start gap-3">
        {item.default_image_path && (
          <div className="shrink-0 h-12 w-12 rounded overflow-hidden bg-muted">
            <img
              src={`/api/items/${item.key}/files/${item.default_image_path}`}
              alt={item.title}
              className="h-full w-full object-cover"
              loading="lazy"
            />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <span className="text-sm font-medium line-clamp-1">{item.title}</span>
          {item.tag_names.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {item.tag_names.slice(0, 3).map((t) => (
                <span
                  key={t}
                  className="inline-flex rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
          <span className="text-xs text-muted-foreground mt-1 block">
            Added {new Date(item.created_at).toLocaleDateString()}
          </span>
        </div>
      </div>
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

interface PaginationProps {
  page: number
  totalPages: number
  onPage: (p: number) => void
}

function Pagination({ page, totalPages, onPage }: PaginationProps) {
  if (totalPages <= 1) return null
  return (
    <div className="flex items-center justify-center gap-2 pt-4">
      <button
        onClick={() => onPage(page - 1)}
        disabled={page <= 1}
        className="rounded border border-border px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-40 transition-colors"
      >
        Previous
      </button>
      <span className="text-sm text-muted-foreground">
        {page} / {totalPages}
      </span>
      <button
        onClick={() => onPage(page + 1)}
        disabled={page >= totalPages}
        className="rounded border border-border px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-40 transition-colors"
      >
        Next
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function MyCreationsPage() {
  const [page, setPage] = useState(1)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['my-creations', page],
    queryFn: () => api.listCreations({ page, per_page: PER_PAGE }),
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / PER_PAGE)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">My Creations</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Items you designed yourself.{' '}
          {total > 0 && (
            <span>{total} item{total === 1 ? '' : 's'}</span>
          )}
        </p>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {isError && <p className="text-sm text-destructive">Failed to load creations.</p>}

      {!isLoading && !isError && items.length === 0 && (
        <div className="rounded-lg border border-dashed border-border p-8 text-center">
          <p className="text-sm text-muted-foreground">
            No creations yet. Mark an item as{' '}
            <em>&quot;this is my own design&quot;</em> when importing to see it here.
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            Creator → User linking is set via the import wizard (Phase 5).
          </p>
        </div>
      )}

      {items.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((item) => (
            <MiniItemCard key={item.key} item={item} />
          ))}
        </div>
      )}

      <Pagination page={page} totalPages={totalPages} onPage={setPage} />
    </div>
  )
}
