import { useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Maximize2, X } from 'lucide-react'

import * as api from '@/lib/api'
import { safeHref } from '@/lib/utils'

import { AURORA_CARD, formatDate } from './styles'

// ---------------------------------------------------------------------------
// Item metadata card (right column of hero grid)
// Includes: title, creator, tags, source/license, modified badge + override,
// description, and timestamps.
// ---------------------------------------------------------------------------

export interface ItemMetadataProps {
  item: api.ItemDetail
  itemKey: string
  isOwnerOrAdmin: boolean
}

export function ItemMetadata({ item, itemKey, isOwnerOrAdmin }: ItemMetadataProps) {
  const queryClient = useQueryClient()
  const [descExpanded, setDescExpanded] = useState(false)
  // A long description gets a capped, scrollable box + an "Expand" modal.
  const descLong = (item.description?.length ?? 0) > 280

  // Phase 15: manual modified-override mutation
  const overrideMutation = useMutation({
    mutationFn: (override: 'modified' | 'original' | null) =>
      api.patchModifiedOverride(itemKey, override),
    onSuccess: (updatedItem) => {
      queryClient.setQueryData(['item', itemKey], updatedItem)
    },
  })

  return (
    <div
      style={{
        ...AURORA_CARD,
        padding: '18px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
      }}
    >
      {/* Title + creator */}
      <div>
        <h1 style={{ fontSize: 20, fontWeight: 800, lineHeight: 1.2, color: 'var(--aurora-text)', letterSpacing: '-0.02em', margin: '0 0 6px' }}>
          {item.title}
        </h1>
        {item.creator && (
          <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>
            By{' '}
            <Link
              to={`/catalog?creator_id=${item.creator.id}`}
              style={{ color: 'var(--aurora-accent)', textDecoration: 'none' }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'underline' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'none' }}
            >
              {item.creator.name}
            </Link>
            {item.creator.source_site && (
              <span style={{ marginLeft: 4, fontSize: 11, color: 'var(--aurora-muted)' }}>
                ({item.creator.source_site})
              </span>
            )}
          </p>
        )}
      </div>

      {/* Tags */}
      {item.tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {item.tags.map((tag) => (
            <Link
              key={tag.id}
              to={`/catalog?tags=${encodeURIComponent(tag.name)}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '3px 9px',
                borderRadius: 20,
                fontSize: 11,
                fontWeight: 500,
                background: 'var(--aurora-glass)',
                border: '1px solid var(--aurora-glass-border)',
                color: 'var(--aurora-text-dim)',
                textDecoration: 'none',
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.background = 'var(--aurora-pill)'
                ;(e.currentTarget as HTMLElement).style.borderColor = 'var(--aurora-pill-border)'
                ;(e.currentTarget as HTMLElement).style.color = 'var(--aurora-accent)'
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.background = 'var(--aurora-glass)'
                ;(e.currentTarget as HTMLElement).style.borderColor = 'var(--aurora-glass-border)'
                ;(e.currentTarget as HTMLElement).style.color = 'var(--aurora-text-dim)'
              }}
            >
              #{tag.name}
            </Link>
          ))}
        </div>
      )}

      {/* Source + license */}
      {(item.source_url || item.license) && (
        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 10, rowGap: 6, alignItems: 'baseline', fontSize: 12 }}>
          {item.source_url && (
            <>
              <span style={{ color: 'var(--aurora-muted)', fontWeight: 600, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>Source</span>
              <a
                href={safeHref(item.source_url)}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'var(--aurora-accent)', textDecoration: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'underline' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = 'none' }}
              >
                {item.source_url}
              </a>
            </>
          )}
          {item.license && (
            <>
              <span style={{ color: 'var(--aurora-muted)', fontWeight: 600, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>License</span>
              <span style={{ color: 'var(--aurora-text-dim)' }}>{item.license}</span>
            </>
          )}
        </div>
      )}

      {/* Phase 15: Local-modification badge (only when source_url present) */}
      {item.source_url && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {/* Badge */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {item.is_modified ? (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  fontSize: 11,
                  fontWeight: 700,
                  background: 'rgba(220,38,38,0.10)',
                  color: 'var(--aurora-danger)',
                  border: '1px solid rgba(220,38,38,0.30)',
                  borderRadius: 20,
                  padding: '3px 10px',
                }}
              >
                ⚠ Modified from original
              </span>
            ) : (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  fontSize: 11,
                  fontWeight: 700,
                  background: 'rgba(22,163,74,0.10)',
                  color: '#16a34a',
                  border: '1px solid rgba(22,163,74,0.25)',
                  borderRadius: 20,
                  padding: '3px 10px',
                }}
                className="dark:text-green-300"
              >
                ✓ Matches original
              </span>
            )}
            {item.locally_modified_at && (
              <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
                Last changed {formatDate(item.locally_modified_at)}
              </span>
            )}
            {item.modified_override && (
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 600,
                  background: 'var(--aurora-glass)',
                  border: '1px solid var(--aurora-glass-border)',
                  borderRadius: 20,
                  padding: '2px 8px',
                  color: 'var(--aurora-muted)',
                }}
              >
                manual
              </span>
            )}
          </div>

          {/* Override control (owner/admin only) */}
          {isOwnerOrAdmin && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 10, color: 'var(--aurora-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Override:
              </span>
              {(['modified', 'original', null] as const).map((val) => {
                const label = val === null ? 'Auto' : val === 'modified' ? 'Modified' : 'Original'
                const isActive = item.modified_override === val
                return (
                  <button
                    key={String(val)}
                    onClick={() => overrideMutation.mutate(val)}
                    disabled={overrideMutation.isPending}
                    style={{
                      fontSize: 11,
                      fontWeight: isActive ? 700 : 500,
                      padding: '3px 10px',
                      borderRadius: 20,
                      border: isActive
                        ? '1px solid var(--aurora-accent)'
                        : '1px solid var(--aurora-glass-border)',
                      background: isActive ? 'rgba(15,164,171,0.12)' : 'var(--aurora-glass)',
                      color: isActive ? 'var(--aurora-accent)' : 'var(--aurora-text-dim)',
                      cursor: overrideMutation.isPending ? 'not-allowed' : 'pointer',
                      opacity: overrideMutation.isPending ? 0.6 : 1,
                      transition: 'all 0.15s',
                    }}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Description — capped + scrollable when long, with an Expand modal */}
      {item.description && (
        <div>
          <div
            style={{
              fontSize: 12,
              color: 'var(--aurora-text-dim)',
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
              maxHeight: descLong ? 220 : undefined,
              overflowY: descLong ? 'auto' : undefined,
              paddingRight: descLong ? 6 : undefined,
            }}
          >
            {item.description}
          </div>
          {descLong && (
            <button
              onClick={() => setDescExpanded(true)}
              style={{
                marginTop: 8,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--aurora-accent)',
                fontSize: 11,
                fontWeight: 600,
                padding: 0,
              }}
            >
              <Maximize2 size={11} />
              Expand
            </button>
          )}
        </div>
      )}

      {/* Timestamps */}
      <div style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 'auto' }}>
        Added {formatDate(item.created_at)}
        {item.updated_at !== item.created_at && (
          <> · Updated {formatDate(item.updated_at)}</>
        )}
      </div>

      {/* Expanded description modal — portaled so the card's backdrop-filter can't trap it */}
      {descExpanded && item.description &&
        createPortal(
          <div
            onClick={() => setDescExpanded(false)}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 9999,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(5,13,28,0.80)',
              backdropFilter: 'blur(10px)',
              WebkitBackdropFilter: 'blur(10px)',
              padding: 16,
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: 'var(--aurora-card)',
                border: '1px solid var(--aurora-card-border)',
                borderRadius: 14,
                width: '100%',
                maxWidth: 720,
                maxHeight: '85vh',
                display: 'flex',
                flexDirection: 'column',
                color: 'var(--aurora-text)',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 12,
                  padding: '16px 20px',
                  borderBottom: '1px solid var(--aurora-divider)',
                }}
              >
                <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>{item.title}</h2>
                <button
                  onClick={() => setDescExpanded(false)}
                  aria-label="Close description"
                  style={{
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--aurora-muted)',
                    padding: 4,
                    display: 'flex',
                    flexShrink: 0,
                  }}
                >
                  <X size={18} />
                </button>
              </div>
              <div
                style={{
                  padding: '16px 20px',
                  overflowY: 'auto',
                  fontSize: 13,
                  lineHeight: 1.65,
                  color: 'var(--aurora-text-dim)',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {item.description}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  )
}
