import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Issue #23 — Pluggable fallback scrapers admin API
// ---------------------------------------------------------------------------

// ── FlareSolverr ────────────────────────────────────────────────────────────

/** FlareSolverr settings (GET/PUT /api/admin/scrapers/flaresolverr). */
export interface FlareSolverrSettings {
  enabled: boolean
  /** Container URL, e.g. http://flaresolverr:8191 */
  base_url: string
  /** Solve timeout forwarded to FlareSolverr as maxTimeout (seconds). */
  timeout_s: number
  /** Fallback priority (lower = tried first; default 1). */
  priority: number
}

export interface FlareSolverrSettingsUpdate {
  enabled?: boolean
  base_url?: string
  timeout_s?: number
  priority?: number
}

export const getFlareSolverrSettings = (): Promise<FlareSolverrSettings> =>
  apiFetch<FlareSolverrSettings>('/api/admin/scrapers/flaresolverr')

export const updateFlareSolverrSettings = (
  body: FlareSolverrSettingsUpdate,
): Promise<FlareSolverrSettings> =>
  apiFetch<FlareSolverrSettings>('/api/admin/scrapers/flaresolverr', {
    method: 'PUT',
    body: JSON.stringify(body),
  })

// ── Test-connection ──────────────────────────────────────────────────────────

export interface TestConnectionResult {
  ok: boolean
  message: string
}

export const testFlareSolverrConnection = (): Promise<TestConnectionResult> =>
  apiFetch<TestConnectionResult>(
    '/api/admin/scrapers/flaresolverr/test-connection',
    { method: 'POST', body: '{}' },
  )

export const testAgentQLConnection = (): Promise<TestConnectionResult> =>
  apiFetch<TestConnectionResult>(
    '/api/admin/scrapers/agentql/test-connection',
    { method: 'POST', body: '{}' },
  )

// ── All-provider usage ───────────────────────────────────────────────────────

export interface ProviderUsageSummary {
  provider: string
  calls: number
  est_cost_usd: number
}

export const getAllScraperUsage = (
  provider?: string,
): Promise<ProviderUsageSummary[]> => {
  const qs = provider ? `?provider=${encodeURIComponent(provider)}` : ''
  return apiFetch<ProviderUsageSummary[]>(`/api/admin/scrapers/usage${qs}`)
}

export const clearScraperUsage = (provider?: string): Promise<void> => {
  const qs = provider ? `?provider=${encodeURIComponent(provider)}` : ''
  return apiFetch<void>(`/api/admin/scrapers/usage${qs}`, { method: 'DELETE' })
}
