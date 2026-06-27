/**
 * CreatorPage — browse items by a specific creator.
 *
 * Route: /creators/:creatorId
 *
 * Shows creator name, profile link, source site, item count, and a paginated
 * list of their items (reuses the same card/list component style as CatalogPage).
 */

import React, { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import * as api from '@/lib/api'

const PER_PAGE = 20

// ---------------------------------------------------------------------------
// Item mini-card (reused from creator items list)
// ---------------------------------------------------------------------------

function CreatorItemCard({ item }: { item: api.CreatorItemSummary }) {
  return (
    <Link
      to={`/items/${item.key}`}
      className="flex flex-col rounded-lg border border-border bg-card p-3 hover:border-primary/50 transition-colors"
    >
      <span className="text-sm font-medium hover:text-primary line-clamp-2">{item.title}</span>
      <span className="mt-1 text-xs text-muted-foreground">
        Added {new Date(item.created_at).toLocaleDateString()}
      </span>
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

export function CreatorPage() {
  const { creatorId } = useParams<{ creatorId: string }>()
  const [page, setPage] = useState(1)

  const creatorIdNum = creatorId ? Number(creatorId) : NaN

  const { data: itemsData, isLoading, isError } = useQuery({
    queryKey: ['creator-items', creatorIdNum, page],
    queryFn: () => api.listCreatorItems(creatorIdNum, { page, per_page: PER_PAGE }),
    enabled: !isNaN(creatorIdNum),
  })

  const creator = itemsData?.creator
  const items = itemsData?.items ?? []
  const total = itemsData?.total ?? 0
  const totalPages = Math.ceil(total / PER_PAGE)

  if (isNaN(creatorIdNum)) {
    return (
      <div className="py-24 text-center text-sm text-destructive">Invalid creator ID.</div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/catalog" className="hover:text-primary">Catalog</Link>
        <span>›</span>
        <span className="text-foreground font-medium">
          {creator?.name ?? 'Creator'}
        </span>
      </nav>

      {/* Creator header */}
      {isLoading && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}

      {isError && (
        <p className="text-sm text-destructive">Creator not found.</p>
      )}

      {creator && (
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold">{creator.name}</h1>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            {creator.source_site && (
              <span>{creator.source_site}</span>
            )}
            {creator.profile_url && (
              <a
                href={creator.profile_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                View profile
              </a>
            )}
            <span>{total} item{total === 1 ? '' : 's'}</span>
          </div>
          <div className="mt-1">
            <Link
              to={`/catalog?creator_id=${creator.id}`}
              className="text-sm text-primary hover:underline"
            >
              Browse in catalog →
            </Link>
          </div>
        </div>
      )}

      {/* Items grid */}
      {!isLoading && !isError && items.length === 0 && (
        <p className="text-sm text-muted-foreground italic">No items found.</p>
      )}

      {items.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((item) => (
            <CreatorItemCard key={item.key} item={item} />
          ))}
        </div>
      )}

      <Pagination page={page} totalPages={totalPages} onPage={setPage} />
    </div>
  )
}
