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
 *
 * Subcomponents live in ./catalog/ (TagCloud, ItemCard, VirtualGrid, TableView,
 * Pagination) with shared style consts in ./catalog/styles.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { HardDrive, LayoutGrid, List, Maximize, Search, Star, X } from 'lucide-react'

import * as api from '@/lib/api'
import { type TagSortMode } from '@/lib/catalog-utils'
import { useAuth } from '@/context/AuthContext'
import { useTheme } from '@/components/ThemeProvider'

import { CARD_STYLE, INPUT_STYLE } from './catalog/styles'
import { TagCloud } from './catalog/TagCloud'
import { VirtualGrid } from './catalog/VirtualGrid'
import { TableView } from './catalog/TableView'
import { Pagination } from './catalog/Pagination'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_PER_PAGE = 20
const PER_PAGE_OPTIONS = [20, 40, 60, 100]
const DEBOUNCE_MS = 300
const TAG_CLOUD_PER_PAGE = 200

const SORT_OPTIONS = [
  { value: 'created_at_desc', label: 'Newest first' },
  { value: 'created_at_asc', label: 'Oldest first' },
  { value: 'title_asc', label: 'Title A–Z' },
  { value: 'title_desc', label: 'Title Z–A' },
  { value: 'relevance', label: 'Relevance (search only)' },
]

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function CatalogPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const { theme } = useTheme()

  // Effective dark-mode flag — used to set color-scheme on native <select>.
  const isDark =
    theme === 'dark' ||
    (theme === 'system' &&
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches)

  // Tag cloud sort mode — persisted in localStorage, default Number.
  const [tagSortMode, setTagSortMode] = useState<TagSortMode>(
    () => (localStorage.getItem('pf3d-tag-sort') as TagSortMode | null) ?? 'number',
  )

  // Grid display mode — persisted in localStorage, default compact.
  const [gridMode, setGridMode] = useState<'compact' | 'full'>(
    () => (localStorage.getItem('pf3d-catalog-grid-mode') as 'compact' | 'full' | null) ?? 'compact',
  )

  const handleGridModeChange = useCallback((mode: 'compact' | 'full') => {
    localStorage.setItem('pf3d-catalog-grid-mode', mode)
    setGridMode(mode)
  }, [])

  // Items per page — persisted in localStorage, default 20.
  const [perPage, setPerPage] = useState<number>(
    () => {
      const stored = localStorage.getItem('pf3d-catalog-per-page')
      const parsed = stored ? Number(stored) : NaN
      return PER_PAGE_OPTIONS.includes(parsed) ? parsed : DEFAULT_PER_PAGE
    },
  )

  const handlePerPageChange = useCallback(
    (value: number) => {
      localStorage.setItem('pf3d-catalog-per-page', String(value))
      setPerPage(value)
      // Reset to page 1 when page size changes.
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.delete('page')
        return next
      })
    },
    [setSearchParams],
  )

  const handleTagSortChange = useCallback((mode: TagSortMode) => {
    localStorage.setItem('pf3d-tag-sort', mode)
    setTagSortMode(mode)
  }, [])

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

  // Debounce: sync input → URL after DEBOUNCE_MS.
  // Guard on an actual change: without this, the debounced writer runs on mount
  // and on every render and unconditionally deletes the `page` param, bouncing the
  // user back to page 1 moments after they paginate. Only rewrite the URL (and reset
  // to page 1) when the search text genuinely differs from what's in the URL.
  useEffect(() => {
    if (inputValue === urlQ) return
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
  }, [inputValue, urlQ, setSearchParams])

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
    queryKey: ['items', urlQ, urlTags, urlCreatorId, urlFavorited, urlSort, urlPage, perPage],
    queryFn: () =>
      api.listItems({
        q: urlQ || undefined,
        tags: urlTags.length ? urlTags : undefined,
        creator_id: urlCreatorId,
        favorited: urlFavorited || undefined,
        sort: urlSort,
        page: urlPage,
        per_page: perPage,
      }),
  })

  const { data: tagsData } = useQuery({
    queryKey: ['tags', 'cloud'],
    queryFn: () => api.listTags({ per_page: TAG_CLOUD_PER_PAGE, in_use_only: true }),
    staleTime: 5 * 60 * 1000,
  })

  const { data: libraries } = useQuery({
    queryKey: ['libraries'],
    queryFn: api.listLibraries,
    staleTime: 5 * 60 * 1000,
  })

  // --- Favorite mutation ---
  const [favoritingKey, setFavoritingKey] = useState<string | null>(null)
  const favMutation = useMutation<api.FavoriteOut | void, Error, { key: string; favorited: boolean }>({
    mutationFn: ({ key, favorited }) =>
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
  const totalPages = Math.ceil(total / perPage)
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
            <TagCloud
              tags={tags}
              selectedTags={urlTags}
              onToggle={toggleTag}
              sortMode={tagSortMode}
              onSortModeChange={handleTagSortChange}
            />
          </div>
        </aside>

        {/* Main content */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
          {/* Toolbar: sort + per-page + grid-mode (grid only) + view toggle */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
            {/* Left cluster: sort + per-page */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {/* Sort select — color-scheme matches active theme so native dropdown
                  is readable in both light and dark mode. */}
              <select
                value={urlSort}
                onChange={(e) => setSort(e.target.value)}
                style={{
                  ...INPUT_STYLE,
                  width: 'auto',
                  padding: '5px 10px',
                  cursor: 'pointer',
                  colorScheme: isDark ? 'dark' : 'light',
                }}
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>

              {/* Per-page selector — both views */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ fontSize: 11, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>Per page:</span>
                <select
                  value={perPage}
                  onChange={(e) => handlePerPageChange(Number(e.target.value))}
                  style={{
                    ...INPUT_STYLE,
                    width: 'auto',
                    padding: '5px 8px',
                    cursor: 'pointer',
                    colorScheme: isDark ? 'dark' : 'light',
                  }}
                >
                  {PER_PAGE_OPTIONS.map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Right cluster: compact/full toggle (grid only) + view toggle */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {/* Compact / Full grid-mode toggle — shown only in grid view */}
              {urlView === 'grid' && (
                <div
                  style={{
                    display: 'flex',
                    background: 'var(--aurora-glass)',
                    border: '1px solid var(--aurora-glass-border)',
                    borderRadius: 10,
                    overflow: 'hidden',
                  }}
                  title="Grid density"
                >
                  <button
                    onClick={() => handleGridModeChange('compact')}
                    title="Compact — dense grid, cropped images"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 5,
                      padding: '6px 12px',
                      fontSize: 12,
                      border: 'none',
                      cursor: 'pointer',
                      background: gridMode === 'compact' ? 'var(--aurora-pill)' : 'transparent',
                      color: gridMode === 'compact' ? 'var(--aurora-accent)' : 'var(--aurora-text-dim)',
                      fontWeight: gridMode === 'compact' ? 700 : 400,
                      boxShadow: gridMode === 'compact' ? 'var(--aurora-glow)' : 'none',
                      borderRight: '1px solid var(--aurora-glass-border)',
                      transition: 'all 0.15s',
                    }}
                  >
                    <LayoutGrid size={13} />
                    Compact
                  </button>
                  <button
                    onClick={() => handleGridModeChange('full')}
                    title="Full — uncropped images, fewer columns"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 5,
                      padding: '6px 12px',
                      fontSize: 12,
                      border: 'none',
                      cursor: 'pointer',
                      background: gridMode === 'full' ? 'var(--aurora-pill)' : 'transparent',
                      color: gridMode === 'full' ? 'var(--aurora-accent)' : 'var(--aurora-text-dim)',
                      fontWeight: gridMode === 'full' ? 700 : 400,
                      boxShadow: gridMode === 'full' ? 'var(--aurora-glow)' : 'none',
                      transition: 'all 0.15s',
                    }}
                  >
                    <Maximize size={13} />
                    Full
                  </button>
                </div>
              )}

              {/* View toggle — Grid / Table */}
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
          </div>

          {/* Loading state */}
          {itemsLoading && (
            <div style={{ padding: '48px 0', textAlign: 'center', fontSize: 13, color: 'var(--aurora-muted)' }}>
              Loading…
            </div>
          )}

          {/* Empty-state CTA — only when not loading, no filters active, and no items */}
          {!itemsLoading && total === 0 && !urlQ && !urlTags.length && !urlFavorited && !urlCreatorId && (
            <div
              style={{
                ...CARD_STYLE,
                padding: '48px 24px',
                textAlign: 'center',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 12,
              }}
            >
              <div
                style={{
                  width: 56,
                  height: 56,
                  borderRadius: 14,
                  background: 'rgba(15,164,171,0.10)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <HardDrive size={26} style={{ color: 'var(--aurora-accent)' }} />
              </div>
              <div>
                <p style={{ fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)', margin: '0 0 6px' }}>
                  {libraries && libraries.length === 0 ? 'No libraries configured yet' : 'No items yet'}
                </p>
                {user?.role === 'admin' ? (
                  <>
                    <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: '0 0 16px' }}>
                      {libraries && libraries.length === 0
                        ? 'Add a library so PartFolder 3D knows where to store your models.'
                        : 'Start importing models through the import wizard.'}
                    </p>
                    {libraries && libraries.length === 0 && (
                      <Link
                        to="/admin/libraries"
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                          background: 'var(--aurora-accent)',
                          color: '#fff',
                          textDecoration: 'none',
                          borderRadius: 8,
                          padding: '8px 18px',
                          fontSize: 13,
                          fontWeight: 600,
                          transition: 'opacity 0.15s',
                        }}
                        onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.opacity = '0.85' }}
                        onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.opacity = '1' }}
                      >
                        <HardDrive size={14} />
                        Add a library
                      </Link>
                    )}
                  </>
                ) : (
                  <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0 }}>
                    No items have been added yet. Ask an admin to configure a library and import some models.
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Grid view — skip when showing empty-state CTA */}
          {!itemsLoading && urlView === 'grid' && (total > 0 || urlQ || urlTags.length > 0 || urlFavorited || urlCreatorId) && (
            <VirtualGrid
              items={items}
              onToggleFavorite={handleToggleFavorite}
              favoritingKey={favoritingKey}
              gridMode={gridMode}
            />
          )}

          {/* Table view — skip when showing empty-state CTA */}
          {!itemsLoading && urlView === 'table' && (total > 0 || urlQ || urlTags.length > 0 || urlFavorited || urlCreatorId) && (
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
