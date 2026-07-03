/**
 * TagCloud — popularity-weighted tag cloud for the catalog sidebar.
 * NO hierarchy, NO depth control; Alpha / Number sort toggle.
 */

import { useMemo } from 'react'

import type * as api from '@/lib/api'
import { getTagFontSize, getTagFontWeight, sortTags, type TagSortMode } from '@/lib/catalog-utils'

interface TagCloudProps {
  tags: api.TagSummary[]
  selectedTags: string[]
  onToggle: (name: string) => void
  sortMode: TagSortMode
  onSortModeChange: (mode: TagSortMode) => void
}

export function TagCloud({ tags, selectedTags, onToggle, sortMode, onSortModeChange }: TagCloudProps) {
  // Use real item_count for sizing — accurate even if popularity_count drifted.
  const counts = tags.map((t) => t.item_count)
  const minCount = counts.length ? Math.min(...counts) : 0
  const maxCount = counts.length ? Math.max(...counts) : 0

  // Client-side re-sort; min/max are invariant to sort order.
  const sorted = useMemo(() => sortTags(tags, sortMode), [tags, sortMode])

  return (
    <>
      {/* Header row: "Browse by tag" label + Alpha / Number sort toggle */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{
          fontSize: 10,
          fontWeight: 700,
          color: 'var(--aurora-muted)',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
        }}>
          Browse by tag
        </div>
        <div
          style={{
            display: 'flex',
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 6,
            overflow: 'hidden',
          }}
        >
          {(['alpha', 'number'] as TagSortMode[]).map((mode, i) => (
            <button
              key={mode}
              onClick={() => onSortModeChange(mode)}
              style={{
                padding: '2px 8px',
                fontSize: 10,
                border: 'none',
                borderRight: i === 0 ? '1px solid var(--aurora-glass-border)' : 'none',
                background: sortMode === mode ? 'var(--aurora-pill)' : 'transparent',
                color: sortMode === mode ? 'var(--aurora-accent)' : 'var(--aurora-muted)',
                cursor: 'pointer',
                fontWeight: sortMode === mode ? 700 : 400,
                transition: 'all 0.15s',
              }}
            >
              {mode === 'alpha' ? 'A–Z' : '#'}
            </button>
          ))}
        </div>
      </div>

      {!sorted.length ? (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic' }}>
          No tags in use yet — tags appear here once items use them.
        </p>
      ) : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 8px' }}>
          {sorted.map((tag) => {
            const selected = selectedTags.includes(tag.name)
            const fontSize = getTagFontSize(tag.item_count, minCount, maxCount)
            const weight = getTagFontWeight(tag.item_count, minCount, maxCount)
            return (
              <button
                key={tag.id}
                onClick={() => onToggle(tag.name)}
                className={weight}
                style={{
                  fontSize,
                  lineHeight: 1.2,
                  padding: '3px 10px',
                  borderRadius: 20,
                  border: `1px solid ${selected ? 'var(--aurora-pill-border)' : 'var(--aurora-glass-border)'}`,
                  background: selected ? 'var(--aurora-pill)' : 'var(--aurora-glass)',
                  color: selected ? 'var(--aurora-accent)' : 'var(--aurora-text-dim)',
                  boxShadow: selected ? 'var(--aurora-glow)' : 'none',
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
                title={`${tag.name} (${tag.item_count} items)`}
              >
                #{tag.name} ({tag.item_count})
              </button>
            )
          })}
        </div>
      )}
    </>
  )
}
