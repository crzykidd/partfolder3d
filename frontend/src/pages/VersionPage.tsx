/**
 * VersionPage — fetches GET /api/version and displays the result.
 * Uses TanStack Query for data fetching + error/loading states.
 *
 * Styling: Aurora — AdminPage + Card (about/version card).
 */

import { useQuery } from '@tanstack/react-query'
import { Info, Server } from 'lucide-react'

import { AdminPage, PageHeader, Card, SectionHeader } from '@/components/ui'

type VersionResponse = {
  version: string
}

async function fetchVersion(): Promise<VersionResponse> {
  const res = await fetch('/api/version')
  if (!res.ok) throw new Error(`Failed to fetch version: ${res.statusText}`)
  return res.json() as Promise<VersionResponse>
}

export function VersionPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['version'],
    queryFn: fetchVersion,
    staleTime: 60_000,
  })

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

          {/* Backend version */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Server size={14} style={{ color: 'var(--aurora-muted)', flexShrink: 0 }} />
            <span style={{ fontSize: 13, color: 'var(--aurora-text-dim)' }}>Backend version:</span>
            {isLoading && (
              <span style={{ fontSize: 13, color: 'var(--aurora-muted)' }} className="animate-pulse">
                Loading…
              </span>
            )}
            {isError && (
              <span style={{ fontSize: 13, color: 'var(--aurora-danger)' }}>
                {error instanceof Error ? error.message : 'Unknown error'}
              </span>
            )}
            {data && (
              <span
                style={{
                  fontFamily: 'monospace',
                  fontSize: 13,
                  fontWeight: 700,
                  color: 'var(--aurora-accent)',
                  background: 'rgba(15,164,171,0.10)',
                  border: '1px solid rgba(15,164,171,0.25)',
                  borderRadius: 6,
                  padding: '2px 8px',
                }}
              >
                {data.version}
              </span>
            )}
          </div>
        </div>
      </Card>

      {/* Info card */}
      <Card accent padding="14px 18px">
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          <Info size={15} style={{ color: 'var(--aurora-accent)', flexShrink: 0, marginTop: 1 }} />
          <p style={{ margin: 0, fontSize: 13, color: 'var(--aurora-text-dim)', lineHeight: 1.6 }}>
            Configuration, library paths, and system settings are managed in{' '}
            <strong>Admin → Settings</strong>. For help or to report issues, see the
            project repository.
          </p>
        </div>
      </Card>
    </AdminPage>
  )
}
