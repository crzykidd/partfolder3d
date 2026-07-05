/**
 * TableView — @tanstack/react-table sortable list view for the catalog.
 * Aurora glass container.
 */

import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table'
import { Box, Star } from 'lucide-react'

import type * as api from '@/lib/api'
import { CARD_STYLE } from './styles'

const colHelper = createColumnHelper<api.ItemSummary>()

interface TableViewProps {
  items: api.ItemSummary[]
  onToggleFavorite: (key: string, favorited: boolean) => void
  favoritingKey: string | null
}

export function TableView({ items, onToggleFavorite, favoritingKey }: TableViewProps) {
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
