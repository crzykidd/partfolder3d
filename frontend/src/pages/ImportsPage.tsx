/**
 * ImportsPage — list of pending import sessions.
 *
 * Route: /imports
 *
 * Authenticated users see their own sessions.  Admin users see all sessions
 * (via the all_users=true query param toggle).
 *
 * Status badges: draft (grey), processing (animated teal), pending_wizard
 * (amber — ready for wizard), failed (red).
 *
 * Styling: Aurora aesthetic — glass cards, teal accent (#0FA4AB), --aurora-* CSS vars.
 */

import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Aurora style constants
// ---------------------------------------------------------------------------

const AURORA_CARD: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 14,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
}

const AURORA_INPUT: React.CSSProperties = {
  background: 'var(--aurora-input-bg)',
  border: '1px solid var(--aurora-input-border)',
  borderRadius: 8,
  color: 'var(--aurora-text)',
  padding: '7px 11px',
  fontSize: 13,
  outline: 'none',
  width: '100%',
  transition: 'border-color 0.15s, box-shadow 0.15s',
  boxSizing: 'border-box',
  display: 'block',
}

const AURORA_BTN_PRIMARY: React.CSSProperties = {
  background: 'var(--aurora-accent)',
  border: 'none',
  borderRadius: 20,
  color: 'var(--aurora-accent-fg)',
  fontSize: 12,
  fontWeight: 700,
  padding: '6px 16px',
  cursor: 'pointer',
  boxShadow: '0 4px 14px var(--aurora-accent-glow)',
  transition: 'opacity 0.15s',
  display: 'inline-flex',
  alignItems: 'center',
  textDecoration: 'none',
}

const AURORA_BTN_GHOST: React.CSSProperties = {
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 20,
  color: 'var(--aurora-text-dim)',
  fontSize: 13,
  padding: '7px 18px',
  cursor: 'pointer',
  transition: 'all 0.15s',
  display: 'inline-flex',
  alignItems: 'center',
}

// Focus handlers
function onAuroraFocus(e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) {
  e.currentTarget.style.borderColor = 'var(--aurora-pill-border)'
  e.currentTarget.style.boxShadow = '0 0 0 3px var(--aurora-pill)'
}
function onAuroraBlur(e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) {
  e.currentTarget.style.borderColor = 'var(--aurora-input-border)'
  e.currentTarget.style.boxShadow = 'none'
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

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

function SessionRow({ session }: { session: api.ImportSession }) {
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
            href={session.source_url}
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

// ---------------------------------------------------------------------------
// From-share-link import panel
// ---------------------------------------------------------------------------

function FromShareLinkPanel() {
  const navigate = useNavigate()
  const [shareUrl, setShareUrl] = useState('')
  const [libraryId, setLibraryId] = useState<number | null>(null)
  const [includePublicNotes, setIncludePublicNotes] = useState(true)
  const [includeGcode, setIncludeGcode] = useState(false)
  const [includePhotos, setIncludePhotos] = useState(true)
  const [includeSettings, setIncludeSettings] = useState(true)
  const [open, setOpen] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const { data: libraries = [] } = useQuery({
    queryKey: ['libraries'],
    queryFn: api.listLibraries,
    staleTime: 60_000,
  })

  const importMutation = useMutation({
    mutationFn: () =>
      api.importFromShareLink({
        share_url: shareUrl.trim(),
        library_id: libraryId,
        include_public_notes: includePublicNotes,
        include_gcode: includeGcode,
        include_photos: includePhotos,
        include_settings: includeSettings,
      }),
    onSuccess: (session) => {
      navigate(`/import/${session.id}`)
    },
    onError: (e) => {
      setSubmitError(e instanceof Error ? e.message : 'Import failed.')
    },
  })

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        style={AURORA_BTN_GHOST}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
      >
        Import from share link
      </button>
    )
  }

  return (
    <div
      style={{
        background: 'var(--aurora-glass)',
        border: '1px solid var(--aurora-glass-border)',
        borderRadius: 12,
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        minWidth: 320,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={{ fontSize: 14, fontWeight: 700, color: 'var(--aurora-text)', margin: 0 }}>
          Import from share link
        </h2>
        <button
          onClick={() => { setOpen(false); setSubmitError(null) }}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--aurora-muted)',
            fontSize: 16,
            lineHeight: 1,
            padding: 4,
            display: 'flex',
            transition: 'color 0.15s',
          }}
          aria-label="Close"
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-muted)' }}
        >
          ✕
        </button>
      </div>

      {/* Share URL */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label
          style={{ fontSize: 10, fontWeight: 700, color: 'var(--aurora-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}
        >
          Share URL
        </label>
        <input
          type="url"
          value={shareUrl}
          onChange={(e) => setShareUrl(e.target.value)}
          placeholder="https://otherinstance.example.com/share/<token>"
          style={AURORA_INPUT}
          onFocus={onAuroraFocus}
          onBlur={onAuroraBlur}
        />
        <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
          Paste a share link from another PartFolder 3D instance.
        </p>
      </div>

      {/* Destination library */}
      {libraries.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label
            style={{ fontSize: 10, fontWeight: 700, color: 'var(--aurora-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}
          >
            Destination library
            <span style={{ fontWeight: 400, marginLeft: 4 }}>(optional)</span>
          </label>
          <select
            value={libraryId ?? ''}
            onChange={(e) => setLibraryId(e.target.value === '' ? null : Number(e.target.value))}
            style={AURORA_INPUT}
            onFocus={onAuroraFocus}
            onBlur={onAuroraBlur}
          >
            <option value="">Auto-select (first enabled)</option>
            {libraries.map((lib) => (
              <option key={lib.id} value={lib.id}>
                {lib.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Include options */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <p style={{ fontSize: 10, fontWeight: 700, color: 'var(--aurora-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', margin: 0 }}>
          Include from public print history:
        </p>
        {(
          [
            [includePublicNotes, setIncludePublicNotes, 'Notes & ratings'] as const,
            [includeSettings, setIncludeSettings, 'Structured settings (printer, material, nozzle, etc.)'] as const,
            [includePhotos, setIncludePhotos, 'Print photos'] as const,
          ] as [boolean, React.Dispatch<React.SetStateAction<boolean>>, string][]
        ).map(([checked, setter, label]) => (
          <label
            key={label}
            style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer', userSelect: 'none', color: 'var(--aurora-text-dim)' }}
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setter(e.target.checked)}
              style={{ accentColor: 'var(--aurora-accent)', width: 14, height: 14, cursor: 'pointer' }}
            />
            {label}
          </label>
        ))}
        <label
          style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer', userSelect: 'none', color: 'var(--aurora-text-dim)' }}
        >
          <input
            type="checkbox"
            checked={includeGcode}
            onChange={(e) => setIncludeGcode(e.target.checked)}
            style={{ accentColor: 'var(--aurora-accent)', width: 14, height: 14, cursor: 'pointer' }}
          />
          Gcode files
          <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>(can be large)</span>
        </label>
      </div>

      {submitError && (
        <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{submitError}</p>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, paddingTop: 2 }}>
        <button
          onClick={() => importMutation.mutate()}
          disabled={!shareUrl.trim() || importMutation.isPending}
          style={{
            ...AURORA_BTN_PRIMARY,
            opacity: !shareUrl.trim() || importMutation.isPending ? 0.5 : 1,
            cursor: !shareUrl.trim() || importMutation.isPending ? 'not-allowed' : 'pointer',
          }}
          onMouseEnter={(e) => { if (shareUrl.trim() && !importMutation.isPending) (e.currentTarget as HTMLButtonElement).style.opacity = '0.85' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = !shareUrl.trim() || importMutation.isPending ? '0.5' : '1' }}
        >
          {importMutation.isPending ? 'Importing…' : 'Import'}
        </button>
        <button
          onClick={() => { setOpen(false); setSubmitError(null) }}
          style={AURORA_BTN_GHOST}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const PER_PAGE = 20

export function ImportsPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [allUsers, setAllUsers] = useState(false)
  const [page, setPage] = useState(1)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['import-sessions', allUsers, page],
    queryFn: () =>
      api.listImportSessions({
        all_users: isAdmin && allUsers,
        page,
        per_page: PER_PAGE,
      }),
    refetchInterval: (query) => {
      const sessions = query.state.data?.sessions ?? []
      const hasProcessing = sessions.some((s) => s.status === 'processing')
      return hasProcessing ? 5_000 : false
    },
  })

  const totalPages = data ? Math.ceil(data.total / PER_PAGE) : 1

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18, color: 'var(--aurora-text)' }}>
      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1
            style={{
              fontSize: 22,
              fontWeight: 800,
              color: 'var(--aurora-text)',
              letterSpacing: '-0.02em',
              margin: '0 0 4px',
            }}
          >
            Imports
          </h1>
          <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>
            {data ? `${data.total} session(s)` : 'Your pending import sessions.'}
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          {isAdmin && (
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontSize: 13,
                cursor: 'pointer',
                userSelect: 'none',
                color: 'var(--aurora-text-dim)',
              }}
            >
              <input
                type="checkbox"
                checked={allUsers}
                onChange={(e) => { setAllUsers(e.target.checked); setPage(1) }}
                style={{ accentColor: 'var(--aurora-accent)', width: 14, height: 14, cursor: 'pointer' }}
              />
              Show all users' sessions
            </label>
          )}
          <FromShareLinkPanel />
        </div>
      </div>

      {/* Loading */}
      {isLoading && (
        <div style={{ padding: '40px 0', textAlign: 'center', fontSize: 13, color: 'var(--aurora-muted)' }}>
          Loading…
        </div>
      )}

      {/* Error */}
      {isError && (
        <div
          style={{
            background: 'rgba(220,38,38,0.08)',
            border: '1px solid rgba(220,38,38,0.25)',
            borderRadius: 10,
            padding: '12px 16px',
          }}
        >
          <p style={{ fontSize: 13, color: 'var(--aurora-danger)', margin: 0 }}>
            {error instanceof Error ? error.message : 'Failed to load sessions.'}
          </p>
        </div>
      )}

      {/* Empty state */}
      {data && data.sessions.length === 0 && (
        <div
          style={{
            ...AURORA_CARD,
            padding: '56px 24px',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 12,
              background: 'var(--aurora-pill)',
              border: '1px solid var(--aurora-pill-border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 20,
            }}
          >
            📥
          </div>
          <div>
            <p style={{ fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)', margin: '0 0 6px' }}>
              No import sessions
            </p>
            <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0 }}>
              Use the <strong>Add Asset</strong> button in the navigation bar to start an import.
            </p>
          </div>
        </div>
      )}

      {/* Sessions table */}
      {data && data.sessions.length > 0 && (
        <>
          <div style={{ ...AURORA_CARD, overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    {(['Status', 'Source', 'Title', 'Created', 'Action'] as const).map((col) => (
                      <th
                        key={col}
                        style={{
                          padding: '10px 14px',
                          textAlign: 'left',
                          fontSize: 10,
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          letterSpacing: '0.08em',
                          color: 'var(--aurora-muted)',
                          background: 'var(--aurora-glass)',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.sessions.map((s) => (
                    <SessionRow key={s.id} session={s} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
              <button
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                style={{
                  ...AURORA_BTN_GHOST,
                  opacity: page === 1 ? 0.4 : 1,
                  cursor: page === 1 ? 'default' : 'pointer',
                }}
                onMouseEnter={(e) => { if (page > 1) (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
              >
                ← Prev
              </button>
              <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>
                Page {page} of {totalPages}
              </span>
              <button
                disabled={page === totalPages}
                onClick={() => setPage((p) => p + 1)}
                style={{
                  ...AURORA_BTN_GHOST,
                  opacity: page === totalPages ? 0.4 : 1,
                  cursor: page === totalPages ? 'default' : 'pointer',
                }}
                onMouseEnter={(e) => { if (page < totalPages) (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
