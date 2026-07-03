/**
 * CreatorPage — browse items by a specific creator.
 *
 * Route: /creators/:creatorId
 *
 * Shows creator name, profile link, source site, item count, and a paginated
 * list of their items (catalog card style matching CatalogPage / B1 aesthetic).
 *
 * Styling: Aurora — AdminPage + Card + aurora catalog cards + DataTable Pagination.
 */

import React, { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, User, Box } from 'lucide-react'

import * as api from '@/lib/api'
import { safeHref } from '@/lib/utils'
import {
  AdminPage,
  PageHeader,
  Card,
  EmptyState,
  Pagination,
} from '@/components/ui'

const PER_PAGE = 20

// ---------------------------------------------------------------------------
// Catalog-style item card (matches B1 aesthetic)
// ---------------------------------------------------------------------------

const ITEM_CARD_STYLE: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 12,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
  padding: '14px 16px',
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
  textDecoration: 'none',
  transition: 'border-color 0.15s, box-shadow 0.15s',
}

function CreatorItemCard({ item }: { item: api.CreatorItemSummary }) {
  const [hovered, setHovered] = useState(false)
  return (
    <Link
      to={`/items/${item.key}`}
      style={{
        ...ITEM_CARD_STYLE,
        borderColor: hovered ? 'var(--aurora-accent)' : 'var(--aurora-card-border)',
        boxShadow: hovered ? 'var(--aurora-glow)' : 'none',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 32,
            height: 32,
            borderRadius: 8,
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            flexShrink: 0,
          }}
        >
          <Box size={14} style={{ color: 'var(--aurora-muted)' }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p
            style={{
              margin: 0,
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--aurora-text)',
              overflow: 'hidden',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
            }}
          >
            {item.title}
          </p>
          <p style={{ margin: '3px 0 0', fontSize: 11, color: 'var(--aurora-muted)' }}>
            Added {new Date(item.created_at).toLocaleDateString()}
          </p>
        </div>
      </div>
    </Link>
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
      <AdminPage>
        <p style={{ fontSize: 13, color: 'var(--aurora-danger)' }}>Invalid creator ID.</p>
      </AdminPage>
    )
  }

  return (
    <AdminPage>
      {/* Breadcrumb */}
      <nav style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--aurora-muted)' }}>
        <Link
          to="/catalog"
          style={{ color: 'var(--aurora-accent)', textDecoration: 'none', fontWeight: 500 }}
        >
          Catalog
        </Link>
        <span style={{ color: 'var(--aurora-divider)' }}>›</span>
        <span style={{ color: 'var(--aurora-text)', fontWeight: 500 }}>
          {creator?.name ?? 'Creator'}
        </span>
      </nav>

      {/* Loading / error */}
      {isLoading && (
        <p style={{ fontSize: 13, color: 'var(--aurora-muted)' }} className="animate-pulse">Loading…</p>
      )}
      {isError && (
        <p style={{ fontSize: 13, color: 'var(--aurora-danger)' }}>Creator not found.</p>
      )}

      {/* Creator header */}
      {creator && (
        <>
          <PageHeader
            title={creator.name}
            meta={`${total} item${total === 1 ? '' : 's'}`}
            actions={
              creator.profile_url ? (
                <a
                  href={safeHref(creator.profile_url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 5,
                    fontSize: 12,
                    fontWeight: 600,
                    color: 'var(--aurora-accent)',
                    textDecoration: 'none',
                    background: 'rgba(15,164,171,0.08)',
                    border: '1px solid rgba(15,164,171,0.2)',
                    borderRadius: 8,
                    padding: '6px 12px',
                  }}
                >
                  <ExternalLink size={12} />
                  View profile
                </a>
              ) : undefined
            }
          />

          {/* Creator meta + catalog link */}
          <Card padding="14px 18px" style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <User size={14} style={{ color: 'var(--aurora-muted)' }} />
              <span style={{ fontSize: 13, color: 'var(--aurora-text-dim)' }}>
                {creator.source_site ?? 'Unknown source'}
              </span>
            </div>
            <Link
              to={`/catalog?creator_id=${creator.id}`}
              style={{ fontSize: 13, color: 'var(--aurora-accent)', textDecoration: 'none', fontWeight: 500 }}
            >
              Browse in catalog →
            </Link>
          </Card>
        </>
      )}

      {/* Items grid */}
      {!isLoading && !isError && items.length === 0 && (
        <EmptyState
          icon={<Box size={32} />}
          title="No items found"
          description="This creator has no items in the catalog yet."
        />
      )}

      {items.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map((item) => (
              <CreatorItemCard key={item.key} item={item} />
            ))}
          </div>

          <Pagination
            page={page}
            totalPages={totalPages}
            onPrev={() => setPage((p) => p - 1)}
            onNext={() => setPage((p) => p + 1)}
          />
        </>
      )}
    </AdminPage>
  )
}
