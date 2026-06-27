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
// Helpers
// ---------------------------------------------------------------------------

function StarIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={1.5}
      className={`h-5 w-5 ${filled ? 'text-yellow-400' : 'text-muted-foreground'}`}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.562.562 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z"
      />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Placeholder image
// ---------------------------------------------------------------------------

function PlaceholderImage({ title }: { title: string }) {
  return (
    <div className="flex h-full w-full items-center justify-center bg-muted/50 rounded">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1}
        className="h-12 w-12 text-muted-foreground/40"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M21 7.5l-2.25-1.313M21 7.5v2.25m0-2.25l-2.25 1.313M3 7.5l2.25-1.313M3 7.5l2.25 1.313M3 7.5v2.25m9 3l2.25-1.313M12 12.75l-2.25-1.313M12 12.75V15m0 6.75l2.25-1.313M12 21.75V19.5m0 2.25l-2.25-1.313m0-16.875L12 2.25l2.25 1.313M21 14.25v2.25l-9 5.25-9-5.25v-2.25"
        />
      </svg>
      <span className="sr-only">{title}</span>
    </div>
  )
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
      <p className="text-sm text-muted-foreground italic">No tags yet.</p>
    )
  }

  return (
    <div className="flex flex-wrap gap-x-3 gap-y-2">
      {tags.map((tag) => {
        const selected = selectedTags.includes(tag.name)
        const fontSize = getTagFontSize(tag.popularity_count, minCount, maxCount)
        const weight = getTagFontWeight(tag.popularity_count, minCount, maxCount)
        return (
          <button
            key={tag.id}
            onClick={() => onToggle(tag.name)}
            style={{ fontSize }}
            className={`${weight} transition-colors leading-tight rounded px-1 py-0.5 ${
              selected
                ? 'bg-primary text-primary-foreground'
                : 'text-foreground hover:text-primary'
            }`}
            title={`${tag.name} (${tag.popularity_count})`}
          >
            {tag.name}
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Item card (grid view)
// ---------------------------------------------------------------------------

interface ItemCardProps {
  item: api.ItemSummary
  onToggleFavorite: (key: string, favorited: boolean) => void
  isFavoriting: boolean
}

function ItemCard({ item, onToggleFavorite, isFavoriting }: ItemCardProps) {
  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden flex flex-col hover:border-primary/50 transition-colors">
      {/* Cover image */}
      <Link to={`/items/${item.key}`} className="block h-40 bg-muted relative">
        {item.default_image_path ? (
          <img
            src={`/api/items/${item.key}/files/${item.default_image_path}`}
            alt={item.title}
            className="absolute inset-0 h-full w-full object-cover"
            loading="lazy"
            onError={(e) => {
              ;(e.currentTarget as HTMLImageElement).style.display = 'none'
            }}
          />
        ) : (
          <PlaceholderImage title={item.title} />
        )}
      </Link>

      {/* Body */}
      <div className="flex flex-col gap-1 p-3 flex-1">
        <div className="flex items-start justify-between gap-2">
          <Link
            to={`/items/${item.key}`}
            className="text-sm font-medium leading-snug hover:text-primary line-clamp-2"
          >
            {item.title}
          </Link>
          <button
            onClick={() => onToggleFavorite(item.key, item.favorited)}
            disabled={isFavoriting}
            className="shrink-0 mt-0.5 disabled:opacity-50"
            title={item.favorited ? 'Remove from favorites' : 'Add to favorites'}
          >
            <StarIcon filled={item.favorited} />
          </button>
        </div>

        {item.creator_name && (
          <p className="text-xs text-muted-foreground truncate">{item.creator_name}</p>
        )}

        {/* Tag chips (first 3 + overflow) */}
        {item.tag_names.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-auto pt-2">
            {item.tag_names.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
              >
                {tag}
              </span>
            ))}
            {item.tag_names.length > 3 && (
              <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
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
      style={{ height: VIRTUAL_CONTAINER_HEIGHT, overflowY: 'auto' }}
      className="w-full"
    >
      <div
        style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}
      >
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
              <div className="grid grid-cols-3 gap-4 pb-4">
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
// Table view
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
            <div className="h-10 w-10 rounded overflow-hidden bg-muted shrink-0">
              {item.default_image_path ? (
                <img
                  src={`/api/items/${item.key}/files/${item.default_image_path}`}
                  alt={item.title}
                  className="h-full w-full object-cover"
                  loading="lazy"
                  onError={(e) => {
                    ;(e.currentTarget as HTMLImageElement).style.display = 'none'
                  }}
                />
              ) : (
                <PlaceholderImage title={item.title} />
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
            className="font-medium hover:text-primary"
          >
            {info.getValue()}
          </Link>
        ),
      }),
      colHelper.accessor('creator_name', {
        header: 'Creator',
        cell: (info) => (
          <span className="text-muted-foreground text-sm">
            {info.getValue() ?? '—'}
          </span>
        ),
      }),
      colHelper.accessor('tag_names', {
        header: 'Tags',
        enableSorting: false,
        cell: (info) => (
          <div className="flex flex-wrap gap-1">
            {info.getValue().slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="inline-flex rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
              >
                {tag}
              </span>
            ))}
            {info.getValue().length > 3 && (
              <span className="inline-flex rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                +{info.getValue().length - 3}
              </span>
            )}
          </div>
        ),
      }),
      colHelper.accessor('created_at', {
        header: 'Added',
        cell: (info) => (
          <span className="text-xs text-muted-foreground">
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
              className="disabled:opacity-50"
              title={item.favorited ? 'Remove from favorites' : 'Add to favorites'}
            >
              <StarIcon filled={item.favorited} />
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
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className={`px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground ${
                    header.column.getCanSort() ? 'cursor-pointer select-none' : ''
                  }`}
                  onClick={header.column.getToggleSortingHandler()}
                >
                  <span className="flex items-center gap-1">
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === 'asc' && ' ↑'}
                    {header.column.getIsSorted() === 'desc' && ' ↓'}
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
              className="border-t border-border hover:bg-muted/30 transition-colors cursor-pointer"
              onClick={() => navigate(`/items/${row.original.key}`)}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-4 py-3">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-12 text-center text-sm text-muted-foreground"
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
    <div className="flex items-center justify-center gap-2 pt-2">
      <button
        onClick={() => onPage(page - 1)}
        disabled={page <= 1}
        className="rounded border border-border px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-40 transition-colors"
      >
        Previous
      </button>
      <span className="text-sm text-muted-foreground">
        {page} / {totalPages}
      </span>
      <button
        onClick={() => onPage(page + 1)}
        disabled={page >= totalPages}
        className="rounded border border-border px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-40 transition-colors"
      >
        Next
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
      // Optimistic update is implicitly handled by re-fetch
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
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Catalog</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {total > 0 ? `${total} item${total === 1 ? '' : 's'}` : 'Browse your 3D print library.'}
          </p>
        </div>
      </div>

      {/* Search bar */}
      <div className="flex items-center gap-3">
        <input
          type="search"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder="Search titles, descriptions, tags…"
          className="input-base flex-1 text-sm"
        />
      </div>

      {/* Active tag chips */}
      {urlTags.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Filtering by:</span>
          {urlTags.map((tag) => (
            <button
              key={tag}
              onClick={() => clearTag(tag)}
              className="inline-flex items-center gap-1 rounded-full bg-primary/10 text-primary px-2.5 py-0.5 text-xs font-medium hover:bg-primary/20 transition-colors"
            >
              {tag}
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="h-3 w-3">
                <path d="M5.28 4.22a.75.75 0 0 0-1.06 1.06L6.94 8l-2.72 2.72a.75.75 0 1 0 1.06 1.06L8 9.06l2.72 2.72a.75.75 0 1 0 1.06-1.06L9.06 8l2.72-2.72a.75.75 0 0 0-1.06-1.06L8 6.94 5.28 4.22Z" />
              </svg>
            </button>
          ))}
        </div>
      )}

      <div className="flex gap-6">
        {/* Sidebar: tag cloud + filters */}
        <aside className="w-56 shrink-0 flex flex-col gap-4">
          {/* Favorites filter */}
          <div>
            <button
              onClick={toggleFavorited}
              className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition-colors ${
                urlFavorited
                  ? 'border-primary bg-primary/10 text-primary font-medium'
                  : 'border-border hover:bg-accent'
              }`}
            >
              <StarIcon filled={urlFavorited} />
              Favorites only
            </button>
          </div>

          {/* Tag cloud */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Browse by tag
            </h3>
            <TagCloud tags={tags} selectedTags={urlTags} onToggle={toggleTag} />
          </div>
        </aside>

        {/* Main content */}
        <div className="flex-1 flex flex-col gap-4">
          {/* Toolbar: sort + view toggle */}
          <div className="flex items-center justify-between gap-3">
            <select
              value={urlSort}
              onChange={(e) => setSort(e.target.value)}
              className="input-base text-sm py-1.5 w-auto"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>

            <div className="flex items-center rounded-md border border-border overflow-hidden">
              <button
                onClick={() => setView('grid')}
                className={`px-3 py-1.5 text-sm transition-colors ${
                  urlView === 'grid'
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-accent'
                }`}
                title="Grid view"
              >
                Grid
              </button>
              <button
                onClick={() => setView('table')}
                className={`px-3 py-1.5 text-sm transition-colors border-l border-border ${
                  urlView === 'table'
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-accent'
                }`}
                title="Table view"
              >
                Table
              </button>
            </div>
          </div>

          {/* Loading state */}
          {itemsLoading && (
            <div className="py-12 text-center text-sm text-muted-foreground">
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
