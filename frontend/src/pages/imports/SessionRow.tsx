/**
 * SessionRow — one row in the import-sessions table, plus its small
 * StatusBadge / SourceTypeBadge helpers (used only here).
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import * as api from '@/lib/api'
import { safeHref } from '@/lib/utils'
import { AURORA_BTN_PRIMARY, formatDate } from './styles'

// ---------------------------------------------------------------------------
// Status badge (aurora pill style)
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: string }) {
  let bg: string
  let border: string
  let color: string
  let label: string
  let animated = false

  switch (status) {
    case 'draft':
      bg = 'var(--aurora-glass)'; border = 'var(--aurora-glass-border)'; color = 'var(--aurora-muted)'; label = 'Draft'; break
    case 'processing':
      bg = 'rgba(15,164,171,0.12)'; border = 'rgba(15,164,171,0.35)'; color = 'var(--aurora-accent)'; label = 'Processing…'; animated = true; break
    case 'pending_wizard':
      bg = 'rgba(245,158,11,0.10)'; border = 'rgba(245,158,11,0.32)'; color = '#D97706'; label = 'Ready'; break
    case 'failed':
      bg = 'rgba(220,38,38,0.10)'; border = 'rgba(220,38,38,0.28)'; color = 'var(--aurora-danger)'; label = 'Failed'; break
    case 'committed':
      bg = 'rgba(22,163,74,0.10)'; border = 'rgba(22,163,74,0.28)'; color = '#16A34A'; label = 'Committed'; break
    case 'cancelled':
      bg = 'var(--aurora-glass)'; border = 'var(--aurora-glass-border)'; color = 'var(--aurora-muted)'; label = 'Cancelled'; break
    default:
      bg = 'var(--aurora-glass)'; border = 'var(--aurora-glass-border)'; color = 'var(--aurora-muted)'; label = status
  }

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        background: bg,
        border: `1px solid ${border}`,
        borderRadius: 20,
        color,
        fontSize: 10,
        fontWeight: 700,
        padding: '3px 9px',
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        whiteSpace: 'nowrap',
      }}
    >
      {animated && (
        <span
          className="animate-pulse"
          style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor', flexShrink: 0 }}
        />
      )}
      {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Source type badge
// ---------------------------------------------------------------------------

function SourceTypeBadge({ type }: { type: string }) {
  const label = type === 'url' ? 'URL' : type === 'upload' ? 'Upload' : type
  const isUrl = type === 'url'
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        background: isUrl ? 'var(--aurora-pill)' : 'var(--aurora-glass)',
        border: `1px solid ${isUrl ? 'var(--aurora-pill-border)' : 'var(--aurora-glass-border)'}`,
        borderRadius: 8,
        color: isUrl ? 'var(--aurora-accent)' : 'var(--aurora-muted)',
        fontSize: 10,
        fontWeight: 600,
        padding: '3px 8px',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Session row (aurora table row)
// ---------------------------------------------------------------------------

export function SessionRow({ session }: { session: api.ImportSession }) {
  const queryClient = useQueryClient()
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteImportSession(session.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['import-sessions'] })
    },
    onError: (err) => {
      setDeleteError(err instanceof Error ? err.message : 'Failed to delete session.')
    },
  })

  const handleDelete = () => {
    if (!window.confirm('Delete this import session? This cannot be undone.')) return
    setDeleteError(null)
    deleteMutation.mutate()
  }

  const displayTitle =
    session.confirmed_title ?? session.suggested_title ?? (
      <em style={{ color: 'var(--aurora-muted)' }}>Untitled</em>
    )

  const canOpenWizard = ['draft', 'processing', 'pending_wizard', 'failed'].includes(
    session.status,
  )

  return (
    <tr
      style={{ transition: 'background 0.1s' }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = 'var(--aurora-glass-hover)' }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = 'transparent' }}
    >
      <td style={{ padding: '10px 14px', borderTop: '1px solid var(--aurora-divider)' }}>
        <StatusBadge status={session.status} />
      </td>
      <td style={{ padding: '10px 14px', borderTop: '1px solid var(--aurora-divider)' }}>
        <SourceTypeBadge type={session.source_type} />
      </td>
      <td style={{ padding: '10px 14px', borderTop: '1px solid var(--aurora-divider)', maxWidth: 280, overflow: 'hidden' }}>
        <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--aurora-text)', margin: '0 0 2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {displayTitle}
        </p>
        {session.source_url && (
          <a
            href={safeHref(session.source_url)}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: 11,
              color: 'var(--aurora-muted)',
              textDecoration: 'none',
              display: 'block',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              transition: 'color 0.15s',
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = 'var(--aurora-accent)' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.color = 'var(--aurora-muted)' }}
          >
            {session.source_url}
          </a>
        )}
        {session.status === 'failed' && session.error && (
          <p
            style={{ fontSize: 11, color: 'var(--aurora-danger)', margin: '2px 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            title={session.error}
          >
            {session.error.slice(0, 80)}{session.error.length > 80 ? '…' : ''}
          </p>
        )}
        {deleteError && (
          <p style={{ fontSize: 11, color: 'var(--aurora-danger)', margin: '2px 0 0' }}>
            {deleteError}
          </p>
        )}
      </td>
      <td style={{ padding: '10px 14px', borderTop: '1px solid var(--aurora-divider)', fontSize: 11, color: 'var(--aurora-muted)', whiteSpace: 'nowrap' }}>
        {formatDate(session.created_at)}
      </td>
      <td style={{ padding: '10px 14px', borderTop: '1px solid var(--aurora-divider)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {canOpenWizard ? (
            <Link
              to={`/import/${session.id}`}
              style={AURORA_BTN_PRIMARY}
              onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.opacity = '0.85' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.opacity = '1' }}
            >
              Open Wizard →
            </Link>
          ) : session.status === 'committed' && session.item_id ? (
            <a
              href={`/items/${session.item_id}`}
              style={{ fontSize: 12, color: 'var(--aurora-accent)', textDecoration: 'none', transition: 'opacity 0.15s' }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.opacity = '0.8' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.opacity = '1' }}
            >
              View item →
            </a>
          ) : (
            <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>—</span>
          )}
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
            style={{
              background: 'transparent',
              border: '1px solid rgba(220,38,38,0.35)',
              borderRadius: 16,
              color: 'var(--aurora-danger)',
              fontSize: 11,
              fontWeight: 600,
              padding: '4px 11px',
              cursor: deleteMutation.isPending ? 'not-allowed' : 'pointer',
              opacity: deleteMutation.isPending ? 0.5 : 1,
              transition: 'all 0.15s',
              whiteSpace: 'nowrap',
            }}
            onMouseEnter={(e) => {
              if (!deleteMutation.isPending)
                (e.currentTarget as HTMLButtonElement).style.background = 'rgba(220,38,38,0.06)'
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = 'transparent'
            }}
          >
            {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </td>
    </tr>
  )
}
