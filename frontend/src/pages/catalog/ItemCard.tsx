/**
 * ItemCard — a single catalog item rendered as an Aurora glass card (grid view).
 */

import React from 'react'
import { Link } from 'react-router-dom'
import { Box, Star } from 'lucide-react'

import type * as api from '@/lib/api'
import { CARD_STYLE } from './styles'

interface ItemCardProps {
  item: api.ItemSummary
  onToggleFavorite: (key: string, favorited: boolean) => void
  isFavoriting: boolean
  gridMode: 'compact' | 'full'
}

export function ItemCard({ item, onToggleFavorite, isFavoriting, gridMode }: ItemCardProps) {
  const imgHeight = gridMode === 'compact' ? 160 : 260
  return (
    <div
      style={{
        ...CARD_STYLE,
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        transition: 'all 0.15s cubic-bezier(0.4,0,0.2,1)',
        cursor: 'default',
      }}
      onMouseEnter={(e) => {
        const el = e.currentTarget as HTMLDivElement
        el.style.borderColor = 'rgba(15,164,171,0.5)'
        el.style.boxShadow = '0 0 20px rgba(15,164,171,0.18)'
        el.style.transform = 'translateY(-2px)'
      }}
      onMouseLeave={(e) => {
        const el = e.currentTarget as HTMLDivElement
        el.style.borderColor = 'var(--aurora-card-border)'
        el.style.boxShadow = 'none'
        el.style.transform = 'none'
      }}
    >
      {/* Cover image */}
      <Link
        to={`/items/${item.key}`}
        style={{ display: 'block', height: imgHeight, position: 'relative', textDecoration: 'none', flexShrink: 0 }}
      >
        {item.default_image_path ? (
          <img
            src={`/api/items/${item.key}/files/${item.default_image_path}`}
            alt={item.title}
            style={{
              position: 'absolute',
              inset: 0,
              height: '100%',
              width: '100%',
              objectFit: gridMode === 'compact' ? 'cover' : 'contain',
              // Full mode: subtle letterbox backdrop so empty space looks intentional
              background: gridMode === 'full'
                ? 'radial-gradient(ellipse at 50% 50%, rgba(15,164,171,0.08) 0%, rgba(0,0,0,0.18) 100%)'
                : undefined,
            }}
            loading="lazy"
            onError={(e) => {
              ;(e.currentTarget as HTMLImageElement).style.display = 'none'
            }}
          />
        ) : (
          <div
            style={{
              height: '100%',
              background:
                'radial-gradient(ellipse at 50% 65%, rgba(15,164,171,0.22) 0%, rgba(15,164,171,0.06) 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Box
              size={30}
              style={{ color: 'var(--aurora-accent)', filter: 'drop-shadow(0 0 8px rgba(15,164,171,0.55))' }}
            />
            <span className="sr-only">{item.title}</span>
          </div>
        )}
      </Link>

      {/* Body */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '10px 12px', flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
          <Link
            to={`/items/${item.key}`}
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--aurora-text)',
              textDecoration: 'none',
              lineHeight: 1.3,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            } as React.CSSProperties}
          >
            {item.title}
          </Link>
          <button
            onClick={() => onToggleFavorite(item.key, item.favorited)}
            disabled={isFavoriting}
            style={{
              flexShrink: 0,
              marginTop: 1,
              opacity: isFavoriting ? 0.5 : 1,
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 2,
              display: 'flex',
            }}
            title={item.favorited ? 'Remove from favorites' : 'Add to favorites'}
          >
            <Star
              size={15}
              fill={item.favorited ? '#FBBF24' : 'none'}
              style={{
                color: item.favorited ? '#FBBF24' : 'var(--aurora-muted)',
                filter: item.favorited ? 'drop-shadow(0 0 4px rgba(251,191,36,0.5))' : 'none',
                transition: 'all 0.15s',
              }}
            />
          </button>
        </div>

        {item.creator_name && (
          <p style={{ fontSize: 11, color: 'var(--aurora-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', margin: 0 }}>
            {item.creator_name}
          </p>
        )}

        {/* Tag chips */}
        {item.tag_names.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 'auto', paddingTop: 6 }}>
            {item.tag_names.slice(0, 3).map((tag) => (
              <span
                key={tag}
                style={{
                  fontSize: 10,
                  padding: '2px 7px',
                  background: 'var(--aurora-glass)',
                  color: 'var(--aurora-text-dim)',
                  borderRadius: 10,
                  border: '1px solid var(--aurora-glass-border)',
                }}
              >
                #{tag}
              </span>
            ))}
            {item.tag_names.length > 3 && (
              <span style={{ fontSize: 10, color: 'var(--aurora-muted)', display: 'flex', alignItems: 'center' }}>
                +{item.tag_names.length - 3}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
