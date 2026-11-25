/**
 * VersionPage — fetches GET /api/version and displays the result.
 * Uses TanStack Query for data fetching + error/loading states.
 *
 * Styling: Aurora — AdminPage + Card (about/version card).
 */

import { useQuery } from '@tanstack/react-query'
import { Info, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router-dom'

import { AdminPage, PageHeader, Card, SectionHeader } from '@/components/ui'
import { BUILD_INFO, type BuildInfo } from '@/lib/buildInfo'

const REPO_COMMIT_URL = 'https://github.com/crzykidd/partfolder3d/commit/'

/** A component's build info; fields other than commit/channel may be absent (nginx has no version). */
type ComponentBuild = Partial<BuildInfo> & { started_at?: string; host?: string }

type DetailsResponse = {
  backend: ComponentBuild
  worker: ComponentBuild | null
  error?: string | null
}

/** Fetch a JSON build-info file; null when missing/404/non-JSON (e.g. SPA fallback HTML). */
async function fetchBuildFile(url: string): Promise<ComponentBuild | null> {
  try {
    const res = await fetch(url, { cache: 'no-store' })
    if (!res.ok) return null
    const data = (await res.json()) as ComponentBuild
    return data && typeof data === 'object' && 'commit' in data ? data : null
  } catch {
    return null
  }
}

async function fetchDetails(): Promise<DetailsResponse | null> {
  try {
    const res = await fetch('/api/version/details')
    if (!res.ok) return null
    return (await res.json()) as DetailsResponse
  } catch {
    return null
  }
}

function isKnown(v: string | undefined): v is string {
  return !!v && v !== 'unknown'
}

function formatBuilt(date: string | undefined): string {
  if (!isKnown(date)) return '—'
  const d = new Date(date)
  if (Number.isNaN(d.getTime())) return date
  const mins = Math.round((Date.now() - d.getTime()) / 60000)
  let rel: string
  if (mins < 1) rel = 'just now'
  else if (mins < 60) rel = `${mins}m ago`
  else if (mins < 60 * 48) rel = `${Math.round(mins / 60)}h ago`
  else rel = `${Math.round(mins / 1440)}d ago`
  return `${d.toLocaleString()} (${rel})`
}

type Row = { key: string; label: string; info: ComponentBuild | null | undefined; loading: boolean }

const cellStyle = { padding: '6px 10px', fontSize: 12, color: 'var(--aurora-text-dim)', textAlign: 'left' as const }
const monoStyle = { fontFamily: 'monospace', color: 'var(--aurora-text)' }

export function VersionPage() {
  const served = useQuery({ queryKey: ['build-served'], queryFn: () => fetchBuildFile('/build-info.json'), staleTime: 60_000 })
  const nginx = useQuery({ queryKey: ['build-nginx'], queryFn: () => fetchBuildFile('/build-info/nginx.json'), staleTime: 60_000 })
  const details = useQuery({ queryKey: ['version-details'], queryFn: fetchDetails, staleTime: 60_000 })

  const rows: Row[] = [
    { key: 'bundle', label: "Frontend (this browser's bundle)", info: BUILD_INFO, loading: false },
    { key: 'served', label: 'Frontend (served by nginx — /build-info.json)', info: served.data, loading: served.isLoading },
    { key: 'nginx', label: 'nginx', info: nginx.data, loading: nginx.isLoading },
    { key: 'backend', label: 'Backend', info: details.data?.backend, loading: details.isLoading },
    { key: 'worker', label: 'Worker', info: details.data?.worker, loading: details.isLoading },
  ]

  const commits = new Map<string, string[]>()
  for (const r of rows) {
    const c = r.info?.commit
    if (isKnown(c)) commits.set(c, [...(commits.get(c) ?? []), r.key])
  }
  const mismatch = commits.size > 1
  const bundleCommit = BUILD_INFO.commit
  const servedCommit = served.data?.commit
  const bundleVsServed = isKnown(bundleCommit) && isKnown(servedCommit) && bundleCommit !== servedCommit

  return (
    <AdminPage>
      <PageHeader
        title="PartFolder 3D"
        description="Self-hosted 3D-printing asset manager"
      />

      <Card padding="20px 24px">
        <SectionHeader>About</SectionHeader>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* App identity row */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 36,
                height: 36,
                borderRadius: 10,
                background: 'var(--aurora-accent)',
                boxShadow: 'var(--aurora-glow)',
                flexShrink: 0,
              }}
            >
              <span style={{ color: '#fff', fontWeight: 900, fontSize: 13, letterSpacing: '-0.03em' }}>PF</span>
            </div>
            <div>
              <p style={{ margin: 0, fontSize: 14, fontWeight: 700, color: 'var(--aurora-text)' }}>
                PartFolder 3D
              </p>
              <p style={{ margin: '2px 0 0', fontSize: 11, color: 'var(--aurora-muted)' }}>
                Open-source, self-hosted 3D print library manager
              </p>
            </div>
          </div>

          <div style={{ height: 1, background: 'var(--aurora-divider)' }} />

          {/* Components */}
          <SectionHeader>Components</SectionHeader>
          {mismatch && (
            <div
              role="alert"
              style={{
                display: 'flex',
                gap: 8,
                alignItems: 'flex-start',
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid var(--aurora-warn, #d97706)',
                fontSize: 12,
                color: 'var(--aurora-text)',
              }}
            >
              <TriangleAlert size={14} style={{ flexShrink: 0, marginTop: 1, color: 'var(--aurora-warn, #d97706)' }} />
              <span>
                Components are on different builds — stale frontend volume or a container wasn&apos;t restarted?
                {bundleVsServed && ' This browser is running a different bundle than nginx is serving — try a hard refresh.'}
              </span>
            </div>
          )}
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--aurora-divider)' }}>
                  <th style={cellStyle}>Component</th>
                  <th style={cellStyle}>Version</th>
                  <th style={cellStyle}>Channel</th>
                  <th style={cellStyle}>Commit</th>
                  <th style={cellStyle}>Built</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.key} data-testid={`build-row-${r.key}`} style={{ borderBottom: '1px solid var(--aurora-divider)' }}>
                    <td style={{ ...cellStyle, color: 'var(--aurora-text)', fontWeight: 600 }}>{r.label}</td>
                    {r.loading ? (
                      <td style={cellStyle} colSpan={4} className="animate-pulse">Loading…</td>
                    ) : !r.info ? (
                      <td style={{ ...cellStyle, color: 'var(--aurora-muted)' }} colSpan={4}>
                        {r.key === 'worker' && details.data ? 'unavailable (worker not reporting)' : 'unavailable'}
                      </td>
                    ) : (
                      <>
                        <td style={{ ...cellStyle, ...monoStyle }}>{r.info.version ?? '—'}</td>
                        <td style={cellStyle}>{r.info.channel ?? '—'}</td>
                        <td style={{ ...cellStyle, ...monoStyle }}>
                          {isKnown(r.info.commit) ? (
                            <a
                              href={`${REPO_COMMIT_URL}${r.info.commit}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ color: 'var(--aurora-accent)', textDecoration: 'none' }}
                            >
                              {r.info.commit.slice(0, 7)}
                            </a>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td style={cellStyle}>{formatBuilt(r.info.build_date)}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Card>

      {/* Info card */}
      <Card accent padding="14px 18px">
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          <Info size={15} style={{ color: 'var(--aurora-accent)', flexShrink: 0, marginTop: 1 }} />
          <p style={{ margin: 0, fontSize: 13, color: 'var(--aurora-text-dim)', lineHeight: 1.6 }}>
            Configuration, library paths, and system settings are managed in{' '}
            <Link
              to="/admin/content/libraries"
              style={{ color: 'var(--aurora-accent)', textDecoration: 'none', fontWeight: 600 }}
            >
              Admin → Content
            </Link>. For help or to report issues, see the
            project repository.
          </p>
        </div>
      </Card>
    </AdminPage>
  )
}
