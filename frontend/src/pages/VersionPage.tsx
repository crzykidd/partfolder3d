/**
 * VersionPage — fetches GET /api/version and displays the result.
 * Uses TanStack Query for data fetching + error/loading states.
 */

import { useQuery } from '@tanstack/react-query'

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
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">PartFolder 3D</h1>
        <p className="mt-1 text-muted-foreground">
          Self-hosted 3D-printing asset manager
        </p>
      </div>

      <div className="rounded-lg border border-border bg-card p-4 text-card-foreground">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          API Status
        </h2>
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {isError && (
          <p className="text-sm text-destructive">
            Error: {error instanceof Error ? error.message : 'Unknown error'}
          </p>
        )}
        {data && (
          <p className="text-sm">
            Backend version:{' '}
            <span className="font-mono font-semibold text-primary">{data.version}</span>
          </p>
        )}
      </div>
    </div>
  )
}
