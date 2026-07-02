/**
 * PendingReviewsWidget — panel widget showing pending review items (admin only).
 *
 * Data: GET /api/reviews?status=pending&per_page=5
 * Graceful empty state if no pending reviews.
 */

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Eye } from 'lucide-react'

import * as api from '@/lib/api'

export function PendingReviewsWidget() {
  const navigate = useNavigate()

  const { data } = useQuery({
    queryKey: ['widget-pending-reviews-panel'],
    queryFn: () => api.listReviews({ status: 'pending', per_page: 5 }),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: false,
  })

  const reviews = data?.items ?? []
  const total = data?.total ?? 0

  if (reviews.length === 0) {
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
        <Eye size={12} style={{ color: 'var(--aurora-muted)' }} />
        <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>No pending reviews</span>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {reviews.map((review) => (
        <button
          key={review.id}
          onClick={() => navigate('/admin/reviews')}
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
          <Eye size={11} style={{ color: 'var(--aurora-accent)', flexShrink: 0 }} />
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
            {review.summary}
          </span>
        </button>
      ))}
      {total > reviews.length && (
        <button
          onClick={() => navigate('/admin/reviews')}
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
          +{total - reviews.length} more →
        </button>
      )}
    </div>
  )
}
