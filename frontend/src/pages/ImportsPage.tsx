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
 *
 * Subcomponents live in ./imports/ (SessionRow, FromShareLinkPanel,
 * CommitReadyPanel, BulkResultSummary) with shared style consts in ./imports/styles.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { useAuth } from '@/context/AuthContext'
import * as api from '@/lib/api'

import { AURORA_BTN_GHOST, AURORA_CARD } from './imports/styles'
import { SessionRow } from './imports/SessionRow'
import { FromShareLinkPanel } from './imports/FromShareLinkPanel'
import { CommitReadyPanel } from './imports/CommitReadyPanel'

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

  // For "Commit ready" panel: count pending_wizard sessions on current page
  // (simple count from loaded data; server-side pagination means this may not be
  // exact for large datasets, but is the right data-range for the current view)
  const pendingCount = data?.sessions.filter((s) => s.status === 'pending_wizard').length ?? 0

  // Libraries + settings (for CommitReadyPanel — lib picker + default-lib detection)
  const { data: libraries = [] } = useQuery<api.LibraryOut[]>({
    queryKey: ['libraries'],
    queryFn: api.listLibraries,
    staleTime: 60_000,
  })

  const { data: settingsList = [] } = useQuery({
    queryKey: ['settings'],
    queryFn: api.listSettings,
    enabled: isAdmin,
    staleTime: 60_000,
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
          <CommitReadyPanel
            pendingCount={pendingCount}
            libraries={libraries}
            settings={settingsList}
          />
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
