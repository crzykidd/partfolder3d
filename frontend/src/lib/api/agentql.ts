import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Phase 18 — AgentQL fallback scraper (admin-only)
// ---------------------------------------------------------------------------

/** AgentQL settings as returned by GET /api/admin/agentql. Key is write-only. */
export interface AgentQLSettings {
  enabled: boolean
  /** True when an encrypted API key is stored. Plaintext never returned. */
  has_key: boolean
  free_allowance: number
  /** 'free_only' | 'cap' */
  budget_mode: string
  monthly_cap_usd: number | null
  per_call_usd: number
  reset_day: number
  /** Fallback priority (lower = tried first; default 2). */
  priority: number
  /** HTTP timeout for AgentQL calls in seconds (default 120). */
  timeout_s: number
}

/** Body for PUT /api/admin/agentql. All fields optional (partial update). */
export interface AgentQLSettingsUpdate {
  enabled?: boolean
  /** Plaintext key — encrypted before storage; write-only. */
  api_key?: string
  free_allowance?: number
  budget_mode?: string
  monthly_cap_usd?: number | null
  per_call_usd?: number
  priority?: number
  timeout_s?: number
}

/** Current-window scraper usage returned by GET /api/admin/scraper-usage. */
export interface ScraperUsageSummary {
  calls: number
  est_cost_usd: number
  allowance: number
  mode: string
  cap: number | null
  /** ISO date of the next window reset (first of next month). */
  resets_on: string
  per_call_usd: number
}

export const getAgentQLSettings = (): Promise<AgentQLSettings> =>
  apiFetch<AgentQLSettings>('/api/admin/agentql')

export const updateAgentQLSettings = (
  body: AgentQLSettingsUpdate,
): Promise<AgentQLSettings> =>
  apiFetch<AgentQLSettings>('/api/admin/agentql', {
    method: 'PUT',
    body: JSON.stringify(body),
  })

export const getScraperUsage = (): Promise<ScraperUsageSummary> =>
  apiFetch<ScraperUsageSummary>('/api/admin/scraper-usage')
