/**
 * ImportsPage — list of pending import sessions.
 *
 * Route: /imports
 *
 * Authenticated users see their own sessions.  Admin users see all sessions
 * (via the all_users=true query param toggle).
 *
 * Status badges: draft (grey), processing (animated blue), pending_wizard
 * (yellow — ready for wizard), failed (red).
 *
 * Each row links to the wizard at /import/:sessionId.
 */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import * as api from '@/lib/api'

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

function StatusBadge({ status }: { status: string }) {
  let cls: string
  let label: string

  switch (status) {
    case 'draft':
      cls = 'bg-muted text-muted-foreground'
      label = 'Draft'
      break
    case 'processing':
      cls = 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 animate-pulse'
      label = 'Processing…'
      break
    case 'pending_wizard':
      cls = 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
      label = 'Ready'
      break
    case 'failed':
      cls = 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
      label = 'Failed'
      break
    case 'committed':
      cls = 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
      label = 'Committed'
      break
    case 'cancelled':
      cls = 'bg-muted text-muted-foreground line-through'
      label = 'Cancelled'
      break
    default:
      cls = 'bg-muted text-muted-foreground'
      label = status
  }

  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  )
}

function SourceTypeBadge({ type }: { type: string }) {
  const label = type === 'url' ? 'URL' : type === 'upload' ? 'Upload' : type
  const cls = type === 'url'
    ? 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-200'
    : 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900 dark:text-cyan-200'
  return (
    <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Session row
// ---------------------------------------------------------------------------

function SessionRow({ session }: { session: api.ImportSession }) {
  const displayTitle =
    session.confirmed_title ?? session.suggested_title ?? (
      <em className="text-muted-foreground">Untitled</em>
    )

  const canOpenWizard = ['draft', 'processing', 'pending_wizard', 'failed'].includes(
    session.status,
  )

  return (
    <tr className="border-b border-border hover:bg-muted/30 transition-colors">
      <td className="px-4 py-3">
        <StatusBadge status={session.status} />
      </td>
      <td className="px-4 py-3">
        <SourceTypeBadge type={session.source_type} />
      </td>
      <td className="px-4 py-3 max-w-xs">
        <p className="font-medium text-sm truncate">{displayTitle}</p>
        {session.source_url && (
          <a
            href={session.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-0.5 block truncate text-xs text-muted-foreground hover:text-primary"
          >
            {session.source_url}
          </a>
        )}
        {session.status === 'failed' && session.error && (
          <p
            className="mt-0.5 truncate text-xs text-red-600 dark:text-red-400"
            title={session.error}
          >
            {session.error.slice(0, 80)}
            {session.error.length > 80 ? '…' : ''}
          </p>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
        {formatDate(session.created_at)}
      </td>
      <td className="px-4 py-3">
        {canOpenWizard ? (
          <Link
            to={`/import/${session.id}`}
            className="rounded-md bg-primary px-3 py-1 text-xs text-primary-foreground hover:opacity-90 transition-colors"
          >
            Open Wizard →
          </Link>
        ) : session.status === 'committed' && session.item_id ? (
          <a
            href={`/items/${session.item_id}`}
            className="text-xs text-primary hover:underline"
          >
            View item →
          </a>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// From-share-link import panel (Phase 7b)
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
        className="rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent transition-colors"
      >
        Import from share link
      </button>
    )
  }

  return (
    <div className="rounded-lg border border-border bg-muted/20 p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Import from share link</h2>
        <button
          onClick={() => { setOpen(false); setSubmitError(null) }}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ✕
        </button>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-muted-foreground">Share URL</label>
        <input
          type="url"
          value={shareUrl}
          onChange={(e) => setShareUrl(e.target.value)}
          placeholder="https://otherinstance.example.com/share/<token>"
          className="input-base py-2 text-sm"
        />
        <p className="text-xs text-muted-foreground">
          Paste a share link from another PartFolder 3D instance.
        </p>
      </div>

      {libraries.length > 0 && (
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">
            Destination library (optional)
          </label>
          <select
            value={libraryId ?? ''}
            onChange={(e) => setLibraryId(e.target.value === '' ? null : Number(e.target.value))}
            className="input-base py-1.5 text-sm"
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

      <div className="flex flex-col gap-2">
        <p className="text-xs font-medium text-muted-foreground">Include from public print history:</p>
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            checked={includePublicNotes}
            onChange={(e) => setIncludePublicNotes(e.target.checked)}
            className="h-4 w-4 rounded border-border accent-primary"
          />
          Notes &amp; ratings
        </label>
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            checked={includeSettings}
            onChange={(e) => setIncludeSettings(e.target.checked)}
            className="h-4 w-4 rounded border-border accent-primary"
          />
          Structured settings (printer, material, nozzle, etc.)
        </label>
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            checked={includePhotos}
            onChange={(e) => setIncludePhotos(e.target.checked)}
            className="h-4 w-4 rounded border-border accent-primary"
          />
          Print photos
        </label>
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            checked={includeGcode}
            onChange={(e) => setIncludeGcode(e.target.checked)}
            className="h-4 w-4 rounded border-border accent-primary"
          />
          Gcode files{' '}
          <span className="text-xs text-muted-foreground">(can be large)</span>
        </label>
      </div>

      {submitError && (
        <p className="text-sm text-destructive">{submitError}</p>
      )}

      <div className="flex gap-2">
        <button
          onClick={() => importMutation.mutate()}
          disabled={!shareUrl.trim() || importMutation.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {importMutation.isPending ? 'Importing…' : 'Import'}
        </button>
        <button
          onClick={() => { setOpen(false); setSubmitError(null) }}
          className="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent transition-colors"
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
    // Refresh automatically while any session is processing
    refetchInterval: (query) => {
      const sessions = query.state.data?.sessions ?? []
      const hasProcessing = sessions.some((s) => s.status === 'processing')
      return hasProcessing ? 5_000 : false
    },
  })

  const totalPages = data ? Math.ceil(data.total / PER_PAGE) : 1

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Imports</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {data ? `${data.total} session(s)` : 'Your pending import sessions.'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {isAdmin && (
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input
                type="checkbox"
                checked={allUsers}
                onChange={(e) => { setAllUsers(e.target.checked); setPage(1) }}
                className="h-4 w-4 rounded border-border accent-primary"
              />
              Show all users' sessions
            </label>
          )}
          <FromShareLinkPanel />
        </div>
      </div>

      {isLoading && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}

      {isError && (
        <p className="text-sm text-red-600">
          {error instanceof Error ? error.message : 'Failed to load sessions.'}
        </p>
      )}

      {data && data.sessions.length === 0 && (
        <div className="py-16 text-center">
          <p className="text-muted-foreground">No import sessions found.</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Use the <strong>Add Asset</strong> button in the navigation bar to start an import.
          </p>
        </div>
      )}

      {data && data.sessions.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Source
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Title
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Created
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.sessions.map((s) => (
                  <SessionRow key={s.id} session={s} />
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm">
              <button
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                className="rounded-md border border-border px-3 py-1 hover:bg-accent disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-muted-foreground">
                Page {page} of {totalPages}
              </span>
              <button
                disabled={page === totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="rounded-md border border-border px-3 py-1 hover:bg-accent disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
