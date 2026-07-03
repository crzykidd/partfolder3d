/**
 * VirtualGrid — virtualized (rows-of-N) grid view for the catalog.
 * Responsive column count via ResizeObserver; @tanstack/react-virtual rows.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'

import type * as api from '@/lib/api'
import { computeCols, GRID_GAP_PX } from '@/lib/catalog-utils'
import { ItemCard } from './ItemCard'

/** Minimum card width (px) for compact grid mode — dense layout. */
const MIN_CARD_WIDTH_COMPACT = 220
/** Minimum card width (px) for full grid mode — uncropped images, fewer columns. */
const MIN_CARD_WIDTH_FULL = 340
/** Estimated row height for compact mode (image 160 + body + padding). */
const ROW_HEIGHT_COMPACT = 300
/** Estimated row height for full mode (image 260 + body + padding). */
const ROW_HEIGHT_FULL = 400

/**
 * Height of the virtual scroll container.
 * Using viewport-relative height so large page sizes (60–100 items) show
 * more rows without a fixed cut-off; clamped to a sensible range.
 * See docs/decisions.md for rationale.
 */
const VIRTUAL_CONTAINER_HEIGHT = 'calc(100vh - 320px)'
const VIRTUAL_CONTAINER_MIN_HEIGHT = 480  // px
const VIRTUAL_CONTAINER_MAX_HEIGHT = 900  // px

interface VirtualGridProps {
  items: api.ItemSummary[]
  onToggleFavorite: (key: string, favorited: boolean) => void
  favoritingKey: string | null
  gridMode: 'compact' | 'full'
}

export function VirtualGrid({ items, onToggleFavorite, favoritingKey, gridMode }: VirtualGridProps) {
  const parentRef = useRef<HTMLDivElement>(null)

  // --- Responsive column count via ResizeObserver ---
  const [containerWidth, setContainerWidth] = useState(0)

  useEffect(() => {
    const el = parentRef.current
    if (!el) return
    // Measure immediately so first render uses the real width.
    setContainerWidth(el.clientWidth)
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width)
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, []) // parentRef.current is stable after mount

  const minCardWidth = gridMode === 'compact' ? MIN_CARD_WIDTH_COMPACT : MIN_CARD_WIDTH_FULL
  const cols = useMemo(
    () => computeCols(containerWidth, minCardWidth, GRID_GAP_PX),
    [containerWidth, minCardWidth],
  )

  const rows = useMemo(() => {
    const result: api.ItemSummary[][] = []
    for (let i = 0; i < items.length; i += cols) {
      result.push(items.slice(i, i + cols))
    }
    return result
  }, [items, cols])

  const estimatedRowHeight = gridMode === 'compact' ? ROW_HEIGHT_COMPACT : ROW_HEIGHT_FULL

  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimatedRowHeight + GRID_GAP_PX,
    overscan: 2,
  })

  return (
    <div
      ref={parentRef}
      style={{
        height: VIRTUAL_CONTAINER_HEIGHT,
        minHeight: VIRTUAL_CONTAINER_MIN_HEIGHT,
        maxHeight: VIRTUAL_CONTAINER_MAX_HEIGHT,
        overflowY: 'auto',
        width: '100%',
        scrollbarWidth: 'thin',
        scrollbarColor: 'var(--aurora-glass) transparent',
      }}
    >
      <div style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
        {rowVirtualizer.getVirtualItems().map((virtualRow) => {
          const rowItems = rows[virtualRow.index]
          return (
            <div
              key={virtualRow.key}
              data-index={virtualRow.index}
              ref={rowVirtualizer.measureElement}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: `repeat(${cols}, 1fr)`,
                  gap: GRID_GAP_PX,
                  paddingBottom: GRID_GAP_PX,
                }}
              >
                {rowItems.map((item) => (
                  <ItemCard
                    key={item.key}
                    item={item}
                    onToggleFavorite={onToggleFavorite}
                    isFavoriting={favoritingKey === item.key}
                    gridMode={gridMode}
                  />
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
