/**
 * Pagination — prev / page-count / next controls for the catalog.
 */

interface PaginationProps {
  page: number
  totalPages: number
  onPage: (p: number) => void
}

export function Pagination({ page, totalPages, onPage }: PaginationProps) {
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
