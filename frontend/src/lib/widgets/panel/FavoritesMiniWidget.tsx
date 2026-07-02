/**
 * FavoritesMiniWidget — panel widget showing the user's starred items.
 *
 * Data: GET /api/me/favorites?per_page=5
 * Graceful empty state if no favorites.
 */

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Heart } from 'lucide-react'

import * as api from '@/lib/api'

export function FavoritesMiniWidget() {
  const navigate = useNavigate()

  const { data } = useQuery({
    queryKey: ['widget-favorites-mini'],
    queryFn: () => api.listFavorites({ per_page: 5 }),
    staleTime: 2 * 60_000,
    retry: false,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0

  if (items.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '8px 10px',
          borderRadius: 8,
          background: 'var(--aurora-card)',
          border: '1px solid var(--aurora-card-border)',
        }}
      >
        <Heart size={12} style={{ color: 'var(--aurora-muted)' }} />
        <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>No favorites yet</span>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {items.map((item) => (
        <button
          key={item.key}
          onClick={() => navigate(`/catalog/${item.key}`)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            width: '100%',
            padding: '6px 8px',
            background: 'var(--aurora-card)',
            border: '1px solid var(--aurora-card-border)',
            borderRadius: 8,
            cursor: 'pointer',
            textAlign: 'left',
            transition: 'all 0.15s',
          }}
          onMouseEnter={(e) => {
            const el = e.currentTarget as HTMLButtonElement
            el.style.background = 'var(--aurora-glass-hover)'
            el.style.borderColor = 'var(--aurora-pill-border)'
          }}
          onMouseLeave={(e) => {
            const el = e.currentTarget as HTMLButtonElement
            el.style.background = 'var(--aurora-card)'
            el.style.borderColor = 'var(--aurora-card-border)'
          }}
        >
          <Heart size={11} style={{ color: 'var(--aurora-accent)', flexShrink: 0 }} />
          <span
            style={{
              fontSize: 11,
              color: 'var(--aurora-text)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              flex: 1,
            }}
          >
            {item.title}
          </span>
        </button>
      ))}
      {total > items.length && (
        <button
          onClick={() => navigate('/catalog?favorited=true')}
          style={{
            fontSize: 11,
            color: 'var(--aurora-accent)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            textAlign: 'left',
            padding: '2px 8px',
          }}
        >
          +{total - items.length} more →
        </button>
      )}
    </div>
  )
}
