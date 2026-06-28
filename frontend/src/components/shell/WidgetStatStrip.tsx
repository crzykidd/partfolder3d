/**
 * WidgetStatStrip — customizable top stat strip driven by the widget registry.
 *
 * Features:
 *   - Renders the user's active stat tiles in order (from useDashboardLayout)
 *   - Density toggle: comfortable (larger) ↔ compact (smaller, tiles wrap to 2 rows)
 *   - Edit mode: move up/down + remove per tile; add-widget picker for all available tiles
 *   - All data fetched in one place; TanStack Query deduplicates shared queries
 *   - Graceful dash on any error; no hard failure states
 *
 * Data sources:
 *   totalAssets      → GET /api/items?per_page=1 → .total
 *   printStats       → GET /api/print-stats → (prints-done, filament, success-rate)
 *   jobsRunning      → GET /api/jobs?status=running&per_page=1 → .total
 *   openIssues       → GET /api/issues?status=open&per_page=1 → .total
 *   pendingReviews   → GET /api/reviews?status=pending&per_page=1 → .total
 *   allTagsCount     → GET /api/tags?active_only=false&per_page=1 → .total
 *   activeTagsCount  → GET /api/tags?active_only=true&per_page=1 → .total
 *   favoritesCount   → GET /api/me/favorites?per_page=1 → .total
 *   creatorsCount    → GET /api/creators?per_page=1 → .total
 */

import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Settings2, ChevronUp, ChevronDown, X, Plus, Check } from 'lucide-react'

import { useAuth } from '@/context/AuthContext'
import { useDashboardLayout } from '@/hooks/useDashboardLayout'
import { getWidgets, resolveWidgets } from '@/lib/widgets/registry'
import type { StatWidgetDef, StatDataCache } from '@/lib/widgets/types'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Shared tile base renderer
// ---------------------------------------------------------------------------

interface StatTileBaseProps {
  label: string
  value: string
  icon: React.ReactNode
  color: string
  compact: boolean
  /** In edit mode: show reorder/remove controls */
  editMode?: boolean
  isFirst?: boolean
  isLast?: boolean
  onMoveUp?: () => void
  onMoveDown?: () => void
  onRemove?: () => void
}

function StatTileBase({
  label,
  value,
  icon,
  color,
  compact,
  editMode,
  isFirst,
  isLast,
  onMoveUp,
  onMoveDown,
  onRemove,
}: StatTileBaseProps) {
  const pad = compact ? '6px 10px' : '10px 14px'
  const valueFontSize = compact ? 15 : 20

  return (
    <div
      style={{
        position: 'relative',
        background: 'var(--aurora-card)',
        border: editMode ? '1px dashed var(--aurora-pill-border)' : '1px solid var(--aurora-card-border)',
        borderRadius: 12,
        padding: pad,
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        flex: '1 1 120px',
        minWidth: compact ? 100 : 110,
        transition: 'border-color 0.15s, box-shadow 0.15s',
        cursor: editMode ? 'default' : 'default',
      } as React.CSSProperties}
      onMouseEnter={(e) => {
        if (!editMode) {
          ;(e.currentTarget as HTMLDivElement).style.borderColor = `${color}40`
          ;(e.currentTarget as HTMLDivElement).style.boxShadow = `0 0 20px ${color}20`
        }
      }}
      onMouseLeave={(e) => {
        if (!editMode) {
          ;(e.currentTarget as HTMLDivElement).style.borderColor = 'var(--aurora-card-border)'
          ;(e.currentTarget as HTMLDivElement).style.boxShadow = 'none'
        }
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          fontSize: compact ? 9 : 10,
          fontWeight: 700,
          color: 'var(--aurora-muted)',
          letterSpacing: '0.07em',
          textTransform: 'uppercase',
          marginBottom: compact ? 3 : 5,
        }}
      >
        <span style={{ color }}>{icon}</span>
        {label}
      </div>
      <div
        style={{
          fontSize: valueFontSize,
          fontWeight: 800,
          color: 'var(--aurora-text)',
          fontVariantNumeric: 'tabular-nums',
          letterSpacing: '-0.02em',
          textShadow: `0 0 30px ${color}30`,
        }}
      >
        {value}
      </div>

      {/* Edit-mode controls overlay */}
      {editMode && (
        <div
          style={{
            position: 'absolute',
            top: 4,
            right: 4,
            display: 'flex',
            gap: 2,
          }}
        >
          <EditBtn title="Move up" disabled={isFirst} onClick={onMoveUp}>
            <ChevronUp size={9} />
          </EditBtn>
          <EditBtn title="Move down" disabled={isLast} onClick={onMoveDown}>
            <ChevronDown size={9} />
          </EditBtn>
          <EditBtn title="Remove" danger onClick={onRemove}>
            <X size={9} />
          </EditBtn>
        </div>
      )}
    </div>
  )
}

interface EditBtnProps {
  title: string
  disabled?: boolean
  danger?: boolean
  onClick?: () => void
  children: React.ReactNode
}

function EditBtn({ title, disabled, danger, onClick, children }: EditBtnProps) {
  return (
    <button
      title={title}
      disabled={disabled}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 16,
        height: 16,
        borderRadius: 4,
        border: '1px solid var(--aurora-glass-border)',
        background: 'var(--aurora-glass)',
        cursor: disabled ? 'default' : 'pointer',
        color: danger ? 'var(--aurora-danger)' : 'var(--aurora-muted)',
        opacity: disabled ? 0.3 : 1,
        padding: 0,
      }}
    >
      {children}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Add-widget picker
// ---------------------------------------------------------------------------

interface AddTilePickerProps {
  availableTiles: StatWidgetDef[]
  activeTileIds: string[]
  onAdd: (id: string) => void
  onClose: () => void
}

function AddTilePicker({ availableTiles, activeTileIds, onAdd, onClose }: AddTilePickerProps) {
  const unaddedTiles = availableTiles.filter((w) => !activeTileIds.includes(w.id))

  return (
    <div
      style={{
        position: 'absolute',
        top: '100%',
        right: 0,
        zIndex: 200,
        background: 'var(--aurora-palette-bg)',
        border: '1px solid var(--aurora-palette-border)',
        borderRadius: 12,
        padding: '6px',
        minWidth: 200,
        boxShadow: '0 8px 30px rgba(0,0,0,0.25)',
        backdropFilter: 'blur(30px)',
        WebkitBackdropFilter: 'blur(30px)',
      } as React.CSSProperties}
    >
      <div style={{ padding: '4px 8px', marginBottom: 4 }}>
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: 'var(--aurora-muted)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          Add stat tile
        </span>
      </div>
      {unaddedTiles.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', padding: '4px 8px', margin: 0 }}>
          All tiles added
        </p>
      ) : (
        unaddedTiles.map((tile) => {
          const Icon = tile.icon
          return (
            <button
              key={tile.id}
              onClick={() => { onAdd(tile.id); onClose() }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                width: '100%',
                padding: '7px 10px',
                background: 'transparent',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 13,
                color: 'var(--aurora-text-dim)',
                textAlign: 'left',
              }}
              onMouseEnter={(e) => {
                ;(e.currentTarget as HTMLButtonElement).style.background =
                  'var(--aurora-palette-hover)'
              }}
              onMouseLeave={(e) => {
                ;(e.currentTarget as HTMLButtonElement).style.background = 'transparent'
              }}
            >
              <Icon size={13} style={{ color: tile.color }} />
              {tile.title}
            </button>
          )
        })
      )}
      <div style={{ borderTop: '1px solid var(--aurora-divider)', marginTop: 4, paddingTop: 4 }}>
        <button
          onClick={onClose}
          style={{
            width: '100%',
            padding: '6px 10px',
            background: 'transparent',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontSize: 12,
            color: 'var(--aurora-muted)',
            textAlign: 'left',
          }}
        >
          Done
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function WidgetStatStrip() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const { layout, updateStats } = useDashboardLayout()

  const [editMode, setEditMode] = useState(false)
  const [showPicker, setShowPicker] = useState(false)

  const density = layout.stats.density
  const tileIds = layout.stats.tiles
  const isCompact = density === 'compact'

  // ------ Data fetching (all tiles share these queries) ------

  const { data: itemsData } = useQuery({
    queryKey: ['stat-items-count'],
    queryFn: () => api.listItems({ per_page: 1 }),
    staleTime: 5 * 60_000,
    retry: false,
  })

  const { data: printStats } = useQuery({
    queryKey: ['stat-print-stats'],
    queryFn: () => api.getPrintStats(),
    staleTime: 5 * 60_000,
    retry: false,
  })

  const { data: jobsData } = useQuery({
    queryKey: ['stat-jobs-running'],
    queryFn: () => api.listJobs({ status: 'running', per_page: 1 }),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: false,
  })

  const { data: issuesData } = useQuery({
    queryKey: ['stat-issues-open'],
    queryFn: () => api.listIssues({ status: 'open', per_page: 1 }),
    staleTime: 60_000,
    retry: false,
    enabled: isAdmin && tileIds.includes('open-issues'),
  })

  const { data: reviewsData } = useQuery({
    queryKey: ['reviews-pending-count'],
    queryFn: () => api.listReviews({ status: 'pending', per_page: 1 }),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: false,
    enabled: isAdmin && tileIds.includes('pending-reviews'),
  })

  const { data: allTagsData } = useQuery({
    queryKey: ['stat-tags-all'],
    queryFn: () => api.listAllTags({ active_only: false, per_page: 1 }),
    staleTime: 5 * 60_000,
    retry: false,
    enabled: isAdmin && tileIds.includes('pending-tags'),
  })

  const { data: activeTagsData } = useQuery({
    queryKey: ['stat-tags-active'],
    queryFn: () => api.listTags({ per_page: 1 }),
    staleTime: 5 * 60_000,
    retry: false,
    enabled: isAdmin && tileIds.includes('pending-tags'),
  })

  const { data: favoritesData } = useQuery({
    queryKey: ['stat-favorites-count'],
    queryFn: () => api.listFavorites({ per_page: 1 }),
    staleTime: 5 * 60_000,
    retry: false,
    enabled: tileIds.includes('favorites'),
  })

  const { data: creatorsData } = useQuery({
    queryKey: ['stat-creators-count'],
    queryFn: () => api.listCreators({ per_page: 1 }),
    staleTime: 5 * 60_000,
    retry: false,
    enabled: tileIds.includes('creators'),
  })

  const cache: StatDataCache = {
    totalAssets: itemsData?.total,
    printStats: printStats,
    jobsRunning: jobsData?.total,
    openIssues: issuesData?.total,
    pendingReviews: reviewsData?.total,
    allTagsCount: allTagsData?.total,
    activeTagsCount: activeTagsData?.total,
    favoritesCount: favoritesData?.total,
    creatorsCount: creatorsData?.total,
  }

  // ------ Resolve active tiles ------

  const activeTiles = resolveWidgets(tileIds, 'stat', isAdmin) as StatWidgetDef[]
  const availableTiles = getWidgets('stat', isAdmin) as StatWidgetDef[]

  // ------ Handlers ------

  const moveUp = (idx: number) => {
    if (idx === 0) return
    const newTiles = [...tileIds]
    ;[newTiles[idx - 1], newTiles[idx]] = [newTiles[idx], newTiles[idx - 1]]
    updateStats({ ...layout.stats, tiles: newTiles })
  }

  const moveDown = (idx: number) => {
    if (idx >= tileIds.length - 1) return
    const newTiles = [...tileIds]
    ;[newTiles[idx], newTiles[idx + 1]] = [newTiles[idx + 1], newTiles[idx]]
    updateStats({ ...layout.stats, tiles: newTiles })
  }

  const removeTile = (id: string) => {
    updateStats({ ...layout.stats, tiles: tileIds.filter((t) => t !== id) })
  }

  const addTile = (id: string) => {
    if (!tileIds.includes(id)) {
      updateStats({ ...layout.stats, tiles: [...tileIds, id] })
    }
  }

  const toggleDensity = () => {
    updateStats({ ...layout.stats, density: isCompact ? 'comfortable' : 'compact' })
  }

  const gap = isCompact ? 6 : 8
  const py = isCompact ? '6px' : '8px'

  return (
    <div
      style={{
        position: 'relative',
        padding: `${py} 16px`,
        background: 'var(--aurora-glass)',
        borderBottom: '1px solid var(--aurora-divider)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        flexShrink: 0,
      } as React.CSSProperties}
    >
      {/* Tiles row */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap,
          paddingRight: 80, // space for the controls
        }}
      >
        {activeTiles.map((tile, idx) => {
          const Icon = tile.icon
          return (
            <StatTileBase
              key={tile.id}
              label={tile.title}
              value={tile.getValue(cache)}
              icon={<Icon size={isCompact ? 10 : 12} />}
              color={tile.color}
              compact={isCompact}
              editMode={editMode}
              isFirst={idx === 0}
              isLast={idx === activeTiles.length - 1}
              onMoveUp={() => moveUp(idx)}
              onMoveDown={() => moveDown(idx)}
              onRemove={() => removeTile(tile.id)}
            />
          )
        })}
      </div>

      {/* Controls (top-right) */}
      <div
        style={{
          position: 'absolute',
          top: '50%',
          right: 12,
          transform: 'translateY(-50%)',
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          zIndex: 10,
        }}
      >
        {editMode && (
          <>
            {/* Density toggle */}
            <button
              title={isCompact ? 'Switch to comfortable density' : 'Switch to compact density'}
              onClick={toggleDensity}
              style={controlBtnStyle}
              onMouseEnter={btnHoverOn}
              onMouseLeave={btnHoverOff}
            >
              <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.04em' }}>
                {isCompact ? 'COMFY' : 'CMPCT'}
              </span>
            </button>

            {/* Add tile */}
            <div style={{ position: 'relative' }}>
              <button
                title="Add stat tile"
                onClick={() => setShowPicker(!showPicker)}
                style={{ ...controlBtnStyle, color: 'var(--aurora-accent)' }}
                onMouseEnter={btnHoverOn}
                onMouseLeave={btnHoverOff}
              >
                <Plus size={11} />
              </button>
              {showPicker && (
                <AddTilePicker
                  availableTiles={availableTiles}
                  activeTileIds={tileIds}
                  onAdd={addTile}
                  onClose={() => setShowPicker(false)}
                />
              )}
            </div>

            {/* Done */}
            <button
              title="Done editing"
              onClick={() => { setEditMode(false); setShowPicker(false) }}
              style={{ ...controlBtnStyle, color: 'var(--aurora-accent)' }}
              onMouseEnter={btnHoverOn}
              onMouseLeave={btnHoverOff}
            >
              <Check size={11} />
            </button>
          </>
        )}

        {/* Customize toggle */}
        {!editMode && (
          <button
            title="Customize stat strip"
            onClick={() => setEditMode(true)}
            style={controlBtnStyle}
            onMouseEnter={btnHoverOn}
            onMouseLeave={btnHoverOff}
          >
            <Settings2 size={11} />
          </button>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shared control button style
// ---------------------------------------------------------------------------

const controlBtnStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 3,
  padding: '4px 6px',
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 7,
  cursor: 'pointer',
  color: 'var(--aurora-muted)',
  fontSize: 11,
  transition: 'all 0.15s',
}

function btnHoverOn(e: React.MouseEvent<HTMLButtonElement>) {
  const el = e.currentTarget as HTMLButtonElement
  el.style.borderColor = 'var(--aurora-pill-border)'
  el.style.color = 'var(--aurora-accent)'
}

function btnHoverOff(e: React.MouseEvent<HTMLButtonElement>) {
  const el = e.currentTarget as HTMLButtonElement
  el.style.borderColor = 'var(--aurora-glass-border)'
  el.style.color = el.style.color // preserve accent if set via props
}
