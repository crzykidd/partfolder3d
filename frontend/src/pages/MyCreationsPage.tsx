/**
 * MyCreationsPage — items whose Creator is linked to the current user.
 *
 * Route: /me/creations
 *
 * Uses GET /api/me/creations (Phase 3a).  Creator → User linkage is set via
 * the "this is my own design" toggle in the import wizard (Phase 5).
 *
 * Styling: Aurora — AdminPage + catalog-style aurora item cards + Pagination.
 */

import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Box, Pencil } from 'lucide-react'

import * as api from '@/lib/api'
import {
  AdminPage,
  PageHeader,
  EmptyState,
  Pagination,
} from '@/components/ui'

const PER_PAGE = 20

// ---------------------------------------------------------------------------
// Style constants
// ---------------------------------------------------------------------------

const ITEM_CARD_STYLE: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 12,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
  padding: '12px 14px',
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
  textDecoration: 'none',
  transition: 'border-color 0.15s, box-shadow 0.15s',
}

// ---------------------------------------------------------------------------
// Item card
// ---------------------------------------------------------------------------

function MiniItemCard({ item }: { item: api.ItemSummaryMini }) {
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
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        {item.default_image_path ? (
          <div
            style={{
              flexShrink: 0,
              width: 48,
              height: 48,
              borderRadius: 8,
              overflow: 'hidden',
              background: 'var(--aurora-glass)',
            }}
          >
            <img
              src={`/api/items/${item.key}/files/${item.default_image_path}`}
              alt={item.title}
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              loading="lazy"
            />
          </div>
        ) : (
          <div
            style={{
              flexShrink: 0,
              width: 48,
              height: 48,
              borderRadius: 8,
              background: 'var(--aurora-glass)',
              border: '1px solid var(--aurora-glass-border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Box size={18} style={{ color: 'var(--aurora-muted)' }} />
          </div>
        )}

        <div style={{ flex: 1, minWidth: 0 }}>
          <p
            style={{
              margin: 0,
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--aurora-text)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {item.title}
          </p>

          {item.tag_names.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px 5px', marginTop: 5 }}>
              {item.tag_names.slice(0, 3).map((t) => (
                <span
                  key={t}
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    background: 'var(--aurora-glass)',
                    border: '1px solid var(--aurora-glass-border)',
                    color: 'var(--aurora-muted)',
                    borderRadius: 20,
                    padding: '1px 7px',
                  }}
                >
                  {t}
                </span>
              ))}
            </div>
          )}

          <p style={{ margin: '5px 0 0', fontSize: 11, color: 'var(--aurora-muted)' }}>
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
    <AdminPage>
      <PageHeader
        title="My Creations"
        description="Items you designed yourself."
        meta={total > 0 ? `${total} item${total === 1 ? '' : 's'}` : undefined}
      />

      {isLoading && (
        <p style={{ fontSize: 13, color: 'var(--aurora-muted)' }} className="animate-pulse">Loading…</p>
      )}
      {isError && (
        <p style={{ fontSize: 13, color: 'var(--aurora-danger)' }}>Failed to load creations.</p>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <EmptyState
          icon={<Pencil size={32} />}
          title="No creations yet"
          description={
            'Mark an item as "this is my own design" when importing to see it here. ' +
            'Creator → User linking is set via the import wizard (Phase 5).'
          }
        />
      )}

      {items.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map((item) => (
              <MiniItemCard key={item.key} item={item} />
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
