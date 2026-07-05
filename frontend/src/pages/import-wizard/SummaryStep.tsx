/**
 * SummaryStep — Step 5 of the import wizard.
 *
 * Read-only review of all session data plus a mid-wizard file-attach affordance
 * for URL and upload sessions (#27).  Commit (→ item page) or Cancel import.
 */

import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'
import { safeHref } from '@/lib/utils'
import { AURORA_CARD, AURORA_BTN_GHOST, AURORA_BTN_GHOST_SM } from './styles'

// ---------------------------------------------------------------------------
// SummaryRow helper
// ---------------------------------------------------------------------------

function SummaryRow({
  label,
  value,
  isLink,
  href,
  warn,
  note,
}: {
  label: string
  value: string
  isLink?: boolean
  href?: string
  /** Amber-highlight the value to flag a state the user should notice (e.g. zero files). */
  warn?: boolean
  /** Optional muted sub-line rendered under the value. */
  note?: string
}) {
  return (
    <tr style={{ borderBottom: '1px solid var(--aurora-divider)' }}>
      <td
        style={{
          width: 100,
          padding: '10px 16px',
          fontSize: 10,
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          color: 'var(--aurora-muted)',
          verticalAlign: 'top',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </td>
      <td style={{ padding: '10px 16px', color: 'var(--aurora-text)', wordBreak: 'break-word', fontSize: 13 }}>
        {isLink && safeHref(href) ? (
          <a
            href={safeHref(href)}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: 'var(--aurora-accent)', textDecoration: 'none' }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none' }}
          >
            {value}
          </a>
        ) : (
          <span style={warn ? { color: '#D97706', fontWeight: 600 } : undefined}>{value}</span>
        )}
        {note && (
          <div style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 3 }}>{note}</div>
        )}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// SummaryStep
// ---------------------------------------------------------------------------

export interface SummaryStepProps {
  session: api.ImportSession
  onPrev: () => void
  onCancelled: () => void
}

export function SummaryStep({ session, onPrev, onCancelled }: SummaryStepProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [commitError, setCommitError] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [attachError, setAttachError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Fetch libraries to display name instead of raw ID in the summary.
  // Uses the shared ['libraries'] key so the result is served from cache if
  // another page (CatalogPage, SettingsPage, etc.) already fetched it.
  const librariesQ = useQuery({
    queryKey: ['libraries'],
    queryFn: api.listLibraries,
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  const libraryDisplay =
    session.library_id == null
      ? '—'
      : (librariesQ.data?.find((l) => l.id === session.library_id)?.name ??
         `ID ${session.library_id}`)

  const commitMutation = useMutation({
    mutationFn: () => api.commitImportSession(session.id),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['import-session', session.id] })
      navigate(`/items/${result.item_key}`)
    },
    onError: (err) =>
      setCommitError(err instanceof Error ? err.message : 'Commit failed.'),
  })

  const cancelMutation = useMutation({
    mutationFn: () => api.cancelImportSession(session.id),
    onSuccess: () => {
      onCancelled()
      navigate('/catalog')
    },
  })

  const attachMutation = useMutation({
    mutationFn: (files: File[]) => api.uploadSessionFiles(session.id, files),
    onSuccess: (updated) => {
      queryClient.setQueryData(['import-session', session.id], updated)
      void queryClient.invalidateQueries({ queryKey: ['import-session', session.id] })
      setAttachError(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    },
    onError: (err) =>
      setAttachError(err instanceof Error ? err.message : 'Upload failed.'),
  })

  const deleteFileMutation = useMutation({
    mutationFn: (fileId: number) => api.deleteSessionFile(session.id, fileId),
    onSuccess: (updated) => {
      queryClient.setQueryData(['import-session', session.id], updated)
      void queryClient.invalidateQueries({ queryKey: ['import-session', session.id] })
    },
    onError: (err) =>
      setAttachError(err instanceof Error ? err.message : 'Remove failed.'),
  })

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? [])
    if (selected.length === 0) return
    setAttachError(null)
    attachMutation.mutate(selected)
  }

  // File attach affordance is available for url and upload sessions.
  const canAttach = session.source_type === 'url' || session.source_type === 'upload'

  const handleCancel = () => {
    if (!window.confirm('Discard this import session?')) return
    setCancelling(true)
    cancelMutation.mutate()
  }

  const confirmed = session.tag_state?.confirmed ?? []
  const title = session.confirmed_title ?? session.suggested_title ?? '—'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Summary table */}
      <div style={{ ...AURORA_CARD, overflow: 'hidden' }}>
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <tbody>
            <SummaryRow label="Title" value={title} />
            <SummaryRow
              label="Creator"
              value={
                session.creator_is_own_design
                  ? 'My own design'
                  : session.creator_name ?? '—'
              }
            />
            <SummaryRow
              label="Tags"
              value={confirmed.length ? confirmed.join(', ') : '—'}
            />
            <SummaryRow
              label="Library"
              value={libraryDisplay}
            />
            <SummaryRow
              label="Source"
              value={session.source_url ?? '—'}
              isLink={!!session.source_url}
              href={session.source_url ?? undefined}
            />
            <SummaryRow
              label="Files"
              value={`${session.files.length} file(s)`}
              warn={session.files.length === 0}
              note={
                session.files.length === 0
                  ? session.source_type === 'url'
                    ? 'No model files attached — attach the file you downloaded from the source site, or commit metadata-only.'
                    : 'No model file attached — this will be a metadata-only entry.'
                  : undefined
              }
            />
            <SummaryRow
              label="Images"
              value={`${session.images.length} image(s)`}
            />
          </tbody>
        </table>
      </div>

      {/* Attach files section (url + upload sessions) */}
      {canAttach && (
        <div style={{ ...AURORA_CARD, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--aurora-muted)' }}>
            Attach Model Files
          </div>

          {/* Staged file list */}
          {session.files.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {session.files.map((f) => (
                <div
                  key={f.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 8,
                    padding: '5px 8px',
                    background: 'var(--aurora-glass)',
                    border: '1px solid var(--aurora-glass-border)',
                    borderRadius: 6,
                  }}
                >
                  <span style={{ fontSize: 12, color: 'var(--aurora-text)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flexShrink: 1 }}>
                    {f.original_name}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--aurora-muted)', flexShrink: 0 }}>
                    {f.role}
                  </span>
                  <button
                    type="button"
                    aria-label="Remove file"
                    disabled={deleteFileMutation.isPending}
                    onClick={() => deleteFileMutation.mutate(f.id)}
                    style={{
                      ...AURORA_BTN_GHOST_SM,
                      padding: '2px 8px',
                      color: 'var(--aurora-danger)',
                      border: '1px solid rgba(220,38,38,0.25)',
                      flexShrink: 0,
                    }}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Attach affordance */}
          <div>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              style={{ display: 'none' }}
              onChange={handleFileSelect}
            />
            <button
              type="button"
              disabled={attachMutation.isPending}
              onClick={() => fileInputRef.current?.click()}
              style={{ ...AURORA_BTN_GHOST, fontSize: 12, padding: '6px 14px', opacity: attachMutation.isPending ? 0.5 : 1 }}
            >
              {attachMutation.isPending ? 'Uploading…' : '+ Attach files'}
            </button>
          </div>

          {/* Attach error */}
          {attachError && (
            <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>{attachError}</div>
          )}
        </div>
      )}

      {/* No library warning */}
      {!session.library_id && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            background: 'rgba(245,158,11,0.08)',
            border: '1px solid rgba(245,158,11,0.25)',
            borderRadius: 8,
            padding: '10px 14px',
          }}
        >
          <span style={{ fontSize: 13, color: '#D97706' }}>
            ⚠ No library selected. Go back to the Title step to set one.
          </span>
        </div>
      )}

      {/* Commit error */}
      {commitError && (
        <div
          style={{
            background: 'rgba(220,38,38,0.08)',
            border: '1px solid rgba(220,38,38,0.25)',
            borderRadius: 10,
            padding: '12px 16px',
          }}
        >
          <p style={{ fontSize: 13, fontWeight: 700, color: 'var(--aurora-danger)', margin: '0 0 4px' }}>
            Commit failed: {commitError}
          </p>
          <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
            Your session data is preserved — fix the issue and try again.
          </p>
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <button
          type="button"
          disabled={cancelling}
          onClick={handleCancel}
          style={{
            background: 'transparent',
            border: '1px solid rgba(220,38,38,0.35)',
            borderRadius: 20,
            color: 'var(--aurora-danger)',
            fontSize: 13,
            padding: '7px 18px',
            cursor: 'pointer',
            opacity: cancelling ? 0.5 : 1,
            transition: 'all 0.15s',
          }}
          onMouseEnter={(e) => { if (!cancelling) (e.currentTarget as HTMLButtonElement).style.background = 'rgba(220,38,38,0.06)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
        >
          {cancelling ? 'Cancelling…' : 'Cancel Import'}
        </button>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button
            type="button"
            onClick={onPrev}
            style={AURORA_BTN_GHOST}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
          >
            ← Back
          </button>
          <button
            type="button"
            disabled={commitMutation.isPending || !session.library_id}
            onClick={() => { setCommitError(null); commitMutation.mutate() }}
            style={{
              background: '#16A34A',
              border: 'none',
              borderRadius: 20,
              color: '#FFFFFF',
              fontSize: 13,
              fontWeight: 700,
              padding: '8px 24px',
              cursor: commitMutation.isPending || !session.library_id ? 'not-allowed' : 'pointer',
              boxShadow: '0 4px 14px rgba(22,163,74,0.28)',
              transition: 'opacity 0.15s',
              opacity: commitMutation.isPending || !session.library_id ? 0.5 : 1,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
            }}
            onMouseEnter={(e) => {
              if (!commitMutation.isPending && session.library_id)
                (e.currentTarget as HTMLButtonElement).style.opacity = '0.85'
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.opacity =
                commitMutation.isPending || !session.library_id ? '0.5' : '1'
            }}
          >
            {commitMutation.isPending ? 'Committing…' : 'Commit to Library →'}
          </button>
        </div>
      </div>
    </div>
  )
}
