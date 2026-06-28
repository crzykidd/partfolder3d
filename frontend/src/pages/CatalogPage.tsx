/**
 * CatalogPage — browse / search / filter the item catalog.
 *
 * URL params (deep-linkable):
 *   q           full-text search
 *   tags        selected tag names (repeated for AND filter)
 *   creator_id  filter by creator
 *   favorited   "true" = show only my favorites
 *   sort        created_at_desc | created_at_asc | title_asc | title_desc | relevance
 *   view        grid | table
 *   page        current page (1-based)
 *
 * Tag browse: popularity-weighted tag cloud (NO hierarchy, NO depth control).
 * Grid view: virtualized with @tanstack/react-virtual (rows of 3 cards).
 * Table view: @tanstack/react-table with sortable headers.
 *
 * Styling: Aurora aesthetic — glass cards, teal accent (#0FA4AB), --aurora-* CSS vars.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Box, LayoutGrid, List, Search, Star, X } from 'lucide-react'

import * as api from '@/lib/api'
import { getTagFontSize, getTagFontWeight } from '@/lib/catalog-utils'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const GRID_COLS = 3
const ROW_HEIGHT_PX = 280
const PER_PAGE = 20
const DEBOUNCE_MS = 300
const TAG_CLOUD_PER_PAGE = 200
const VIRTUAL_CONTAINER_HEIGHT = 640 // px

const SORT_OPTIONS = [
  { value: 'created_at_desc', label: 'Newest first' },
  { value: 'created_at_asc', label: 'Oldest first' },
  { value: 'title_asc', label: 'Title A–Z' },
  { value: 'title_desc', label: 'Title Z–A' },
  { value: 'relevance', label: 'Relevance (search only)' },
]

// ---------------------------------------------------------------------------
// Aurora style helpers
// ---------------------------------------------------------------------------

const CARD_STYLE: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 12,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
}

const INPUT_STYLE: React.CSSProperties = {
  background: 'var(--aurora-input-bg)',
  border: '1px solid var(--aurora-input-border)',
  borderRadius: 10,
  color: 'var(--aurora-text)',
  padding: '7px 12px',
  fontSize: 13,
  outline: 'none',
  width: '100%',
  transition: 'border-color 0.15s, box-shadow 0.15s',
}

// ---------------------------------------------------------------------------
// Tag cloud
// ---------------------------------------------------------------------------

interface TagCloudProps {
  tags: api.TagSummary[]
  selectedTags: string[]
  onToggle: (name: string) => void
}

function TagCloud({ tags, selectedTags, onToggle }: TagCloudProps) {
  const counts = tags.map((t) => t.popularity_count)
  const minCount = counts.length ? Math.min(...counts) : 0
  const maxCount = counts.length ? Math.max(...counts) : 0

  if (!tags.length) {
    return (
      <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic' }}>No tags yet.</p>
    )
  }

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 8px' }}>
      {tags.map((tag) => {
        const selected = selectedTags.includes(tag.name)
        const fontSize = getTagFontSize(tag.popularity_count, minCount, maxCount)
        const weight = getTagFontWeight(tag.popularity_count, minCount, maxCount)
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
            title={`${tag.name} (${tag.popularity_count})`}
          >
            #{tag.name}
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Item card (grid view) — Aurora glass card
// ---------------------------------------------------------------------------

interface ItemCardProps {
  item: api.ItemSummary
  onToggleFavorite: (key: string, favorited: boolean) => void
  isFavoriting: boolean
}

function ItemCard({ item, onToggleFavorite, isFavoriting }: ItemCardProps) {
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
        style={{ display: 'block', height: 160, position: 'relative', textDecoration: 'none', flexShrink: 0 }}
      >
        {item.default_image_path ? (
          <img
            src={`/api/items/${item.key}/files/${item.default_image_path}`}
            alt={item.title}
            style={{ position: 'absolute', inset: 0, height: '100%', width: '100%', objectFit: 'cover' }}
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

// ---------------------------------------------------------------------------
// Virtualized grid view
// ---------------------------------------------------------------------------

interface VirtualGridProps {
  items: api.ItemSummary[]
  onToggleFavorite: (key: string, favorited: boolean) => void
  favoritingKey: string | null
}

function VirtualGrid({ items, onToggleFavorite, favoritingKey }: VirtualGridProps) {
  const parentRef = useRef<HTMLDivElement>(null)

  const rows = useMemo(() => {
    const result: api.ItemSummary[][] = []
    for (let i = 0; i < items.length; i += GRID_COLS) {
      result.push(items.slice(i, i + GRID_COLS))
    }
    return result
  }, [items])

  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT_PX + 16, // + gap
    overscan: 2,
  })

  return (
    <div
      ref={parentRef}
      style={{ height: VIRTUAL_CONTAINER_HEIGHT, overflowY: 'auto', width: '100%', scrollbarWidth: 'thin', scrollbarColor: 'var(--aurora-glass) transparent' }}
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
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, paddingBottom: 12 }}>
                {rowItems.map((item) => (
                  <ItemCard
                    key={item.key}
                    item={item}
                    onToggleFavorite={onToggleFavorite}
                    isFavoriting={favoritingKey === item.key}
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

// ---------------------------------------------------------------------------
// Table view — Aurora glass container
// ---------------------------------------------------------------------------

const colHelper = createColumnHelper<api.ItemSummary>()

interface TableViewProps {
  items: api.ItemSummary[]
  onToggleFavorite: (key: string, favorited: boolean) => void
  favoritingKey: string | null
}

function TableView({ items, onToggleFavorite, favoritingKey }: TableViewProps) {
  const navigate = useNavigate()
  const [sorting, setSorting] = useState<SortingState>([])

  const columns = useMemo(
    () => [
      colHelper.display({
        id: 'thumb',
        header: '',
        cell: (info) => {
          const item = info.row.original
          return (
            <div
              style={{
                height: 40,
                width: 40,
                borderRadius: 8,
                overflow: 'hidden',
                background: 'radial-gradient(ellipse at 50% 60%, rgba(15,164,171,0.2) 0%, rgba(15,164,171,0.06) 100%)',
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {item.default_image_path ? (
                <img
                  src={`/api/items/${item.key}/files/${item.default_image_path}`}
                  alt={item.title}
                  style={{ height: '100%', width: '100%', objectFit: 'cover' }}
                  loading="lazy"
                  onError={(e) => {
                    ;(e.currentTarget as HTMLImageElement).style.display = 'none'
                  }}
                />
              ) : (
                <Box size={16} style={{ color: 'var(--aurora-accent)' }} />
              )}
            </div>
          )
        },
      }),
      colHelper.accessor('title', {
        header: 'Title',
        cell: (info) => (
          <Link
            to={`/items/${info.row.original.key}`}
            style={{ fontWeight: 600, color: 'var(--aurora-text)', textDecoration: 'none', fontSize: 13 }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--aurora-accent)' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--aurora-text)' }}
          >
            {info.getValue()}
          </Link>
        ),
      }),
      colHelper.accessor('creator_name', {
        header: 'Creator',
        cell: (info) => (
          <span style={{ color: 'var(--aurora-muted)', fontSize: 12 }}>
            {info.getValue() ?? '—'}
          </span>
        ),
      }),
      colHelper.accessor('tag_names', {
        header: 'Tags',
        enableSorting: false,
        cell: (info) => (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {info.getValue().slice(0, 3).map((tag) => (
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
            {info.getValue().length > 3 && (
              <span style={{ fontSize: 10, color: 'var(--aurora-muted)', display: 'flex', alignItems: 'center' }}>
                +{info.getValue().length - 3}
              </span>
            )}
          </div>
        ),
      }),
      colHelper.accessor('created_at', {
        header: 'Added',
        cell: (info) => (
          <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
            {new Date(info.getValue()).toLocaleDateString()}
          </span>
        ),
      }),
      colHelper.display({
        id: 'star',
        header: '',
        cell: (info) => {
          const item = info.row.original
          return (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onToggleFavorite(item.key, item.favorited)
              }}
              disabled={favoritingKey === item.key}
              style={{
                opacity: favoritingKey === item.key ? 0.5 : 1,
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
                }}
              />
            </button>
          )
        },
      }),
    ],
    [onToggleFavorite, favoritingKey],
  )

  const table = useReactTable({
    data: items,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualSorting: false,
  })

  return (
    <div
      style={{
        ...CARD_STYLE,
        overflow: 'hidden',
      }}
    >
      <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} style={{ borderBottom: '1px solid var(--aurora-divider)' }}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  style={{
                    padding: '10px 14px',
                    textAlign: 'left',
                    fontSize: 10,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    color: 'var(--aurora-muted)',
                    cursor: header.column.getCanSort() ? 'pointer' : 'default',
                    userSelect: 'none',
                    background: 'var(--aurora-glass)',
                  }}
                  onClick={header.column.getToggleSortingHandler()}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === 'asc' && (
                      <span style={{ color: 'var(--aurora-accent)' }}>↑</span>
                    )}
                    {header.column.getIsSorted() === 'desc' && (
                      <span style={{ color: 'var(--aurora-accent)' }}>↓</span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              style={{ borderTop: '1px solid var(--aurora-divider)', cursor: 'pointer', transition: 'background 0.1s' }}
              onClick={() => navigate(`/items/${row.original.key}`)}
              onMouseEnter={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = 'var(--aurora-glass-hover)' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = 'transparent' }}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} style={{ padding: '10px 14px' }}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td
                colSpan={columns.length}
                style={{ padding: '48px 14px', textAlign: 'center', fontSize: 13, color: 'var(--aurora-muted)', fontStyle: 'italic' }}
              >
                No items found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pagination controls
// ---------------------------------------------------------------------------

interface PaginationProps {
  page: number
  totalPages: number
  onPage: (p: number) => void
}

function Pagination({ page, totalPages, onPage }: PaginationProps) {
  if (totalPages <= 1) return null
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, paddingTop: 8 }}>
      <button
        onClick={() => onPage(page - 1)}
        disabled={page <= 1}
        style={{
          background: 'var(--aurora-glass)',
          border: '1px solid var(--aurora-glass-border)',
          borderRadius: 20,
          color: page <= 1 ? 'var(--aurora-muted)' : 'var(--aurora-text-dim)',
          fontSize: 12,
          padding: '5px 14px',
          cursor: page <= 1 ? 'default' : 'pointer',
          opacity: page <= 1 ? 0.4 : 1,
          transition: 'all 0.15s',
        }}
        onMouseEnter={(e) => { if (page > 1) (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
      >
        ← Prev
      </button>
      <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>
        {page} / {totalPages}
      </span>
      <button
        onClick={() => onPage(page + 1)}
        disabled={page >= totalPages}
        style={{
          background: 'var(--aurora-glass)',
          border: '1px solid var(--aurora-glass-border)',
          borderRadius: 20,
          color: page >= totalPages ? 'var(--aurora-muted)' : 'var(--aurora-text-dim)',
          fontSize: 12,
          padding: '5px 14px',
          cursor: page >= totalPages ? 'default' : 'pointer',
          opacity: page >= totalPages ? 0.4 : 1,
          transition: 'all 0.15s',
        }}
        onMouseEnter={(e) => { if (page < totalPages) (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
      >
        Next →
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function CatalogPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()

  // --- Read URL params ---
  const urlQ = searchParams.get('q') ?? ''
  const urlTags = searchParams.getAll('tags')
  const urlCreatorId = searchParams.get('creator_id')
    ? Number(searchParams.get('creator_id'))
    : undefined
  const urlFavorited = searchParams.get('favorited') === 'true'
  const urlSort = searchParams.get('sort') ?? 'created_at_desc'
  const urlView = (searchParams.get('view') ?? localStorage.getItem('pf3d-catalog-view') ?? 'grid') as 'grid' | 'table'
  const urlPage = searchParams.get('page') ? Number(searchParams.get('page')) : 1

  // Local search input (debounced sync to URL)
  const [inputValue, setInputValue] = useState(urlQ)

  // Sync input value when URL changes externally
  useEffect(() => {
    setInputValue(urlQ)
  }, [urlQ])

  // Debounce: sync input → URL after DEBOUNCE_MS
  useEffect(() => {
    const t = setTimeout(() => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (inputValue) {
          next.set('q', inputValue)
        } else {
          next.delete('q')
        }
        next.delete('page')
        return next
      }, { replace: true })
    }, DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [inputValue, setSearchParams])

  // --- Helpers to update URL params ---
  const setPage = useCallback(
    (p: number) =>
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('page', String(p))
        return next
      }),
    [setSearchParams],
  )

  const setSort = useCallback(
    (s: string) =>
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('sort', s)
        next.delete('page')
        return next
      }),
    [setSearchParams],
  )

  const setView = useCallback(
    (v: 'grid' | 'table') => {
      localStorage.setItem('pf3d-catalog-view', v)
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('view', v)
        return next
      })
    },
    [setSearchParams],
  )

  const toggleFavorited = useCallback(
    () =>
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (next.get('favorited') === 'true') {
          next.delete('favorited')
        } else {
          next.set('favorited', 'true')
        }
        next.delete('page')
        return next
      }),
    [setSearchParams],
  )

  const toggleTag = useCallback(
    (name: string) =>
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        const current = next.getAll('tags')
        next.delete('tags')
        if (current.includes(name)) {
          current.filter((t) => t !== name).forEach((t) => next.append('tags', t))
        } else {
          ;[...current, name].forEach((t) => next.append('tags', t))
        }
        next.delete('page')
        return next
      }),
    [setSearchParams],
  )

  const clearTag = useCallback(
    (name: string) =>
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        const current = next.getAll('tags').filter((t) => t !== name)
        next.delete('tags')
        current.forEach((t) => next.append('tags', t))
        next.delete('page')
        return next
      }),
    [setSearchParams],
  )

  // --- Data fetching ---
  const { data: itemsData, isLoading: itemsLoading } = useQuery({
    queryKey: ['items', urlQ, urlTags, urlCreatorId, urlFavorited, urlSort, urlPage],
    queryFn: () =>
      api.listItems({
        q: urlQ || undefined,
        tags: urlTags.length ? urlTags : undefined,
        creator_id: urlCreatorId,
        favorited: urlFavorited || undefined,
        sort: urlSort,
        page: urlPage,
        per_page: PER_PAGE,
      }),
  })

  const { data: tagsData } = useQuery({
    queryKey: ['tags', 'cloud'],
    queryFn: () => api.listTags({ per_page: TAG_CLOUD_PER_PAGE }),
    staleTime: 5 * 60 * 1000,
  })

  // --- Favorite mutation ---
  const [favoritingKey, setFavoritingKey] = useState<string | null>(null)
  const favMutation = useMutation({
    mutationFn: ({ key, favorited }: { key: string; favorited: boolean }) =>
      favorited ? api.unfavoriteItem(key) : api.favoriteItem(key),
    onMutate: ({ key }) => setFavoritingKey(key),
    onSettled: (_data, _err, { key }) => {
      setFavoritingKey(null)
      void queryClient.invalidateQueries({ queryKey: ['items'] })
      void queryClient.invalidateQueries({ queryKey: ['item', key] })
    },
  })

  const handleToggleFavorite = useCallback(
    (key: string, favorited: boolean) => {
      favMutation.mutate({ key, favorited })
    },
    [favMutation],
  )

  const items = itemsData?.items ?? []
  const total = itemsData?.total ?? 0
  const totalPages = Math.ceil(total / PER_PAGE)
  const tags = tagsData?.tags ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18, color: 'var(--aurora-text)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: 'var(--aurora-text)', letterSpacing: '-0.02em', margin: 0 }}>
            Catalog
          </h1>
          <p style={{ marginTop: 4, fontSize: 12, color: 'var(--aurora-muted)', margin: '4px 0 0' }}>
            {total > 0
              ? `${total} item${total === 1 ? '' : 's'}`
              : 'Browse your 3D print library.'}
          </p>
        </div>
      </div>

      {/* Search bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          background: 'var(--aurora-input-bg)',
          border: '1px solid var(--aurora-input-border)',
          borderRadius: 10,
          padding: '7px 12px',
          transition: 'border-color 0.15s, box-shadow 0.15s',
        }}
        onFocusCapture={(e) => {
          (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--aurora-pill-border)'
          ;(e.currentTarget as HTMLDivElement).style.boxShadow = '0 0 0 3px var(--aurora-pill)'
        }}
        onBlurCapture={(e) => {
          // only reset if focus left the container entirely
          if (!e.currentTarget.contains(e.relatedTarget as Node)) {
            ;(e.currentTarget as HTMLDivElement).style.borderColor = 'var(--aurora-input-border)'
            ;(e.currentTarget as HTMLDivElement).style.boxShadow = 'none'
          }
        }}
      >
        <Search size={14} style={{ color: 'var(--aurora-muted)', flexShrink: 0 }} />
        <input
          type="search"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder="Search titles, descriptions, tags…"
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            color: 'var(--aurora-text)',
            fontSize: 13,
          }}
        />
      </div>

      {/* Active tag chips */}
      {urlTags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>Filtering by:</span>
          {urlTags.map((tag) => (
            <button
              key={tag}
              onClick={() => clearTag(tag)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                background: 'var(--aurora-pill)',
                border: '1px solid var(--aurora-pill-border)',
                borderRadius: 20,
                color: 'var(--aurora-accent)',
                fontSize: 11,
                fontWeight: 600,
                padding: '3px 8px 3px 10px',
                cursor: 'pointer',
                boxShadow: 'var(--aurora-glow)',
                transition: 'all 0.15s',
              }}
            >
              #{tag}
              <X size={11} />
            </button>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 16 }}>
        {/* Sidebar: tag cloud + filters */}
        <aside style={{ width: 200, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Favorites filter */}
          <div>
            <button
              onClick={toggleFavorited}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                background: urlFavorited ? 'var(--aurora-pill)' : 'var(--aurora-glass)',
                border: `1px solid ${urlFavorited ? 'var(--aurora-pill-border)' : 'var(--aurora-glass-border)'}`,
                borderRadius: 20,
                color: urlFavorited ? 'var(--aurora-accent)' : 'var(--aurora-text-dim)',
                fontSize: 12,
                fontWeight: urlFavorited ? 700 : 400,
                padding: '5px 12px',
                cursor: 'pointer',
                boxShadow: urlFavorited ? 'var(--aurora-glow)' : 'none',
                transition: 'all 0.15s',
              }}
            >
              <Star
                size={13}
                fill={urlFavorited ? '#FBBF24' : 'none'}
                style={{
                  color: urlFavorited ? '#FBBF24' : 'var(--aurora-muted)',
                  filter: urlFavorited ? 'drop-shadow(0 0 3px rgba(251,191,36,0.5))' : 'none',
                }}
              />
              Favorites only
            </button>
          </div>

          {/* Tag cloud */}
          <div
            style={{
              ...CARD_STYLE,
              padding: '12px 14px',
            }}
          >
            <div style={{
              fontSize: 10,
              fontWeight: 700,
              color: 'var(--aurora-muted)',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              marginBottom: 10,
            }}>
              Browse by tag
            </div>
            <TagCloud tags={tags} selectedTags={urlTags} onToggle={toggleTag} />
          </div>
        </aside>

        {/* Main content */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
          {/* Toolbar: sort + view toggle */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            {/* Sort select */}
            <select
              value={urlSort}
              onChange={(e) => setSort(e.target.value)}
              style={{
                ...INPUT_STYLE,
                width: 'auto',
                padding: '5px 10px',
                cursor: 'pointer',
              }}
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>

            {/* View toggle — icon buttons */}
            <div style={{ display: 'flex', background: 'var(--aurora-glass)', border: '1px solid var(--aurora-glass-border)', borderRadius: 10, overflow: 'hidden' }}>
              <button
                onClick={() => setView('grid')}
                title="Grid view"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '6px 12px',
                  fontSize: 12,
                  border: 'none',
                  cursor: 'pointer',
                  background: urlView === 'grid' ? 'var(--aurora-pill)' : 'transparent',
                  color: urlView === 'grid' ? 'var(--aurora-accent)' : 'var(--aurora-text-dim)',
                  fontWeight: urlView === 'grid' ? 700 : 400,
                  boxShadow: urlView === 'grid' ? 'var(--aurora-glow)' : 'none',
                  borderRight: '1px solid var(--aurora-glass-border)',
                  transition: 'all 0.15s',
                }}
              >
                <LayoutGrid size={13} />
                Grid
              </button>
              <button
                onClick={() => setView('table')}
                title="Table view"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '6px 12px',
                  fontSize: 12,
                  border: 'none',
                  cursor: 'pointer',
                  background: urlView === 'table' ? 'var(--aurora-pill)' : 'transparent',
                  color: urlView === 'table' ? 'var(--aurora-accent)' : 'var(--aurora-text-dim)',
                  fontWeight: urlView === 'table' ? 700 : 400,
                  boxShadow: urlView === 'table' ? 'var(--aurora-glow)' : 'none',
                  transition: 'all 0.15s',
                }}
              >
                <List size={13} />
                Table
              </button>
            </div>
          </div>

          {/* Loading state */}
          {itemsLoading && (
            <div style={{ padding: '48px 0', textAlign: 'center', fontSize: 13, color: 'var(--aurora-muted)' }}>
              Loading…
            </div>
          )}

          {/* Grid view */}
          {!itemsLoading && urlView === 'grid' && (
            <VirtualGrid
              items={items}
              onToggleFavorite={handleToggleFavorite}
              favoritingKey={favoritingKey}
            />
          )}

          {/* Table view */}
          {!itemsLoading && urlView === 'table' && (
            <TableView
              items={items}
              onToggleFavorite={handleToggleFavorite}
              favoritingKey={favoritingKey}
            />
          )}

          {/* Pagination */}
          <Pagination page={urlPage} totalPages={totalPages} onPage={setPage} />
        </div>
      </div>
    </div>
  )
}
