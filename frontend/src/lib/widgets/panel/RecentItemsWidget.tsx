/**
 * RecentItemsWidget — panel widget showing the 5 most recently added items.
 *
 * Data: GET /api/items?sort=-created_at&per_page=5
 * Graceful dash if endpoint errors.
 */

import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { LayoutGrid } from 'lucide-react'

import * as api from '@/lib/api'

export function RecentItemsWidget() {
  const navigate = useNavigate()

  const { data, isLoading } = useQuery({
    queryKey: ['widget-recent-items'],
    queryFn: () => api.listItems({ per_page: 5 }),
    staleTime: 2 * 60_000,
    retry: false,
  })

  if (isLoading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            style={{
              height: 36,
              borderRadius: 8,
              background: 'var(--aurora-glass)',
              opacity: 0.4,
              animation: 'pulse 2s infinite',
            }}
          />
        ))}
      </div>
    )
  }

  const items = data?.items ?? []

  if (items.length === 0) {
    return (
      <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>
        No items yet. Add your first asset!
      </p>
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
          <LayoutGrid size={12} style={{ color: 'var(--aurora-accent)', flexShrink: 0 }} />
          <span
            style={{
              fontSize: 12,
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
    </div>
  )
}
