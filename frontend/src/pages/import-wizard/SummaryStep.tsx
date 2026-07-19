/**
 * SummaryStep — Step 5 of the import wizard.
 *
 * Read-only review of all session data plus a mid-wizard file-attach affordance
 * for URL and upload sessions (#27).  Commit (→ item page) or Cancel import.
 *
 * For URL imports with zero staged files, shows an explicit attach-or-create-without-
 * objects modal on mount (once per wizard visit, keyed by session id in sessionStorage).
 * Modal portals to <body> to escape the Aurora card's backdrop-filter stacking context.
 */

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
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
// AttachOrCommitModal — portals to <body> to escape backdrop-filter contexts.
// Shown once per wizard visit for url+0-file sessions.
// ---------------------------------------------------------------------------

interface AttachOrCommitModalProps {
  domain: string | null
  commitDisabled: boolean
  commitPending: boolean
  onAttach: () => void
  onCommit: () => void
  onDismiss: () => void
}

function AttachOrCommitModal({
  domain,
  commitDisabled,
  commitPending,
  onAttach,
  onCommit,
  onDismiss,
}: AttachOrCommitModalProps) {
  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onDismiss()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onDismiss])

  const bodyText = domain
    ? `Site "${domain}" needs auth to download print assets. Please attach.`
    : 'This import has no model files attached.'

  return createPortal(
    /* Backdrop — aurora dark blur */
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(5,13,28,0.82)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        padding: 16,
      } as React.CSSProperties}
      onClick={onDismiss}
    >
      {/* Dialog panel — aurora palette card */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="No model files attached"
        style={{
          background: 'var(--aurora-palette-bg)',
          border: '1px solid var(--aurora-palette-border)',
          borderRadius: 16,
          boxShadow: '0 24px 60px rgba(0,0,0,0.5)',
          backdropFilter: 'blur(40px)',
          WebkitBackdropFilter: 'blur(40px)',
          width: '100%',
          maxWidth: 440,
          color: 'var(--aurora-text)',
          padding: '24px 24px 20px',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        } as React.CSSProperties}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)', margin: 0 }}>
          No model files attached
        </h2>
        <p style={{ fontSize: 13, color: 'var(--aurora-text-dim)', margin: 0, lineHeight: 1.55 }}>
          {bodyText}
        </p>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', paddingTop: 8 }}>
          {/* Secondary: create without objects — same commit handler, same disabled state */}
          <button
            type="button"
            disabled={commitDisabled}
            onClick={onCommit}
            style={{
              background: 'var(--aurora-glass)',
              border: '1px solid var(--aurora-glass-border)',
              borderRadius: 20,
              color: commitDisabled ? 'var(--aurora-muted)' : 'var(--aurora-text-dim)',
              fontSize: 13,
              padding: '7px 16px',
              cursor: commitDisabled ? 'not-allowed' : 'pointer',
              opacity: commitDisabled ? 0.5 : 1,
              transition: 'all 0.15s',
              display: 'inline-flex',
              alignItems: 'center',
            }}
          >
            {commitPending ? 'Committing…' : 'Create without objects'}
          </button>
          {/* Primary: attach files */}
          <button
            type="button"
            onClick={onAttach}
            style={{
              background: 'var(--aurora-accent)',
              border: 'none',
              borderRadius: 20,
              color: 'var(--aurora-accent-fg)',
              fontSize: 13,
              fontWeight: 700,
              padding: '8px 20px',
              cursor: 'pointer',
              boxShadow: '0 4px 14px var(--aurora-accent-glow)',
              transition: 'opacity 0.15s',
              display: 'inline-flex',
              alignItems: 'center',
            }}
          >
            Attach files
          </button>
        </div>
      </div>
    </div>,
    document.body,
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

/** sessionStorage key used to track that the modal was already dismissed for a given session. */
function modalDismissedKey(sessionId: string) {
  return `pf3d-attach-modal-dismissed-${sessionId}`
}

/** Extract hostname from a URL string, stripping a leading "www.". Returns null on failure. */
function extractDomain(url: string | null | undefined): string | null {
  if (!url) return null
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return null
  }
}

export function SummaryStep({ session, onPrev, onCancelled }: SummaryStepProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [commitError, setCommitError] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [attachError, setAttachError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const attachSectionRef = useRef<HTMLDivElement>(null)

  // Modal: show once per wizard visit for url+0-file sessions.
  // Session-keyed dismissal state lives in sessionStorage so it survives
  // step-back → step-forward navigation (component unmount/remount).
  const [modalOpen, setModalOpen] = useState<boolean>(
    () =>
      session.source_type === 'url' &&
      session.files.length === 0 &&
      !sessionStorage.getItem(modalDismissedKey(session.id)),
  )

  const dismissModal = () => {
    sessionStorage.setItem(modalDismissedKey(session.id), '1')
    setModalOpen(false)
  }

  const domain = extractDomain(session.source_url)

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

  // Commit is disabled when no library is set or when a commit is already in-flight.
  const commitDisabled = commitMutation.isPending || !session.library_id

  const handleCommit = () => {
    setCommitError(null)
    commitMutation.mutate()
  }

  // Modal action: open the file picker and scroll to the attach section.
  const handleModalAttach = () => {
    dismissModal()
    // Guard: scrollIntoView is not available in all environments (e.g. jsdom).
    if (typeof attachSectionRef.current?.scrollIntoView === 'function') {
      attachSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    fileInputRef.current?.click()
  }

  // Modal action: commit without objects (same handler + disabled logic as the main button).
  const handleModalCommit = () => {
    dismissModal()
    handleCommit()
  }

  const confirmed = session.tag_state?.confirmed ?? []
  const title = session.confirmed_title ?? session.suggested_title ?? '—'

  // Files row reflects the selected-file count (Manyfold Part 3 — a session can
  // stage several file variants and let the user deselect some before commit).
  // When every staged file is still selected (the default), keep the original
  // "N file(s)" text unchanged.
  const totalFiles = session.files.length
  const selectedFiles = session.files.filter((f) => f.selected).length
  const filesValue =
    totalFiles === 0
      ? '0 file(s)'
      : selectedFiles === totalFiles
        ? `${totalFiles} file(s)`
        : `${selectedFiles} of ${totalFiles} file(s) selected`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Attach-or-create modal — portals to <body> to escape backdrop-filter stacking */}
      {modalOpen && (
        <AttachOrCommitModal
          domain={domain}
          commitDisabled={commitDisabled}
          commitPending={commitMutation.isPending}
          onAttach={handleModalAttach}
          onCommit={handleModalCommit}
          onDismiss={dismissModal}
        />
      )}

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
              value={filesValue}
              warn={totalFiles === 0 || selectedFiles === 0}
              note={
                totalFiles === 0
                  ? session.source_type === 'url'
                    ? 'No model files attached — attach the file you downloaded from the source site, or commit metadata-only.'
                    : 'No model file attached — this will be a metadata-only entry.'
                  : selectedFiles === 0
                    ? 'All staged files are deselected — this will commit as metadata-only.'
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
        <div
          ref={attachSectionRef}
          style={{ ...AURORA_CARD, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}
        >
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
            disabled={commitDisabled}
            onClick={handleCommit}
            style={{
              background: '#16A34A',
              border: 'none',
              borderRadius: 20,
              color: '#FFFFFF',
              fontSize: 13,
              fontWeight: 700,
              padding: '8px 24px',
              cursor: commitDisabled ? 'not-allowed' : 'pointer',
              boxShadow: '0 4px 14px rgba(22,163,74,0.28)',
              transition: 'opacity 0.15s',
              opacity: commitDisabled ? 0.5 : 1,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
            }}
            onMouseEnter={(e) => {
              if (!commitDisabled)
                (e.currentTarget as HTMLButtonElement).style.opacity = '0.85'
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.opacity =
                commitDisabled ? '0.5' : '1'
            }}
          >
            {commitMutation.isPending ? 'Committing…' : 'Commit to Library →'}
          </button>
        </div>
      </div>
    </div>
  )
}
