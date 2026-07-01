import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Phase 8 — AI Providers (admin)
// ---------------------------------------------------------------------------

export interface AiProviderOut {
  id: number
  provider: 'claude' | 'openai' | 'ollama'
  endpoint: string | null
  model: string | null
  has_key: boolean // true when a key is set — key itself is NEVER returned
  enabled: boolean
}

export interface CreateAiProviderRequest {
  provider: string
  endpoint?: string | null
  model?: string | null
  api_key?: string | null // plaintext — encrypted before storage; write-only
  enabled?: boolean
}

export interface PatchAiProviderRequest {
  endpoint?: string | null
  model?: string | null
  api_key?: string | null // if provided, rotates the stored key
  enabled?: boolean | null
}

export interface EnableAiProviderRequest {
  enabled: boolean
}

export interface TestAiConnectionRequest {
  provider: string
  endpoint?: string | null
  model?: string | null
  api_key?: string | null // plaintext — NOT persisted; used for the test call only
  provider_id?: number | null // test a saved provider with its stored key (no re-entry)
}

export interface TestAiConnectionResponse {
  ok: boolean
  error: string | null
}

export const listAiProviders = (): Promise<AiProviderOut[]> =>
  apiFetch<AiProviderOut[]>('/api/ai-providers')

export const createAiProvider = (
  body: CreateAiProviderRequest,
): Promise<AiProviderOut> =>
  apiFetch<AiProviderOut>('/api/ai-providers', {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const getAiProvider = (id: number): Promise<AiProviderOut> =>
  apiFetch<AiProviderOut>(`/api/ai-providers/${id}`)

export const patchAiProvider = (
  id: number,
  body: PatchAiProviderRequest,
): Promise<AiProviderOut> =>
  apiFetch<AiProviderOut>(`/api/ai-providers/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })

export const deleteAiProvider = (id: number): Promise<void> =>
  apiFetch<void>(`/api/ai-providers/${id}`, { method: 'DELETE' })

export const enableAiProvider = (
  id: number,
  body: EnableAiProviderRequest,
): Promise<AiProviderOut> =>
  apiFetch<AiProviderOut>(`/api/ai-providers/${id}/enable`, {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const testAiConnection = (
  body: TestAiConnectionRequest,
): Promise<TestAiConnectionResponse> =>
  apiFetch<TestAiConnectionResponse>('/api/ai-providers/test', {
    method: 'POST',
    body: JSON.stringify(body),
  })

// ---------------------------------------------------------------------------
// Phase 8 — AI Actions for import sessions
// ---------------------------------------------------------------------------

export interface AiTagSuggestionOut {
  canonical: string[]
  new_suggestions: string[]
  provider_available: boolean
  error: string | null
}

export interface AiTextOut {
  text: string | null
  provider_available: boolean
  error: string | null
}

export const aiSuggestTags = (sessionId: string): Promise<AiTagSuggestionOut> =>
  apiFetch<AiTagSuggestionOut>(
    `/api/import-sessions/${sessionId}/ai/suggest-tags`,
    { method: 'POST' },
  )

export const aiCleanupDescription = (sessionId: string): Promise<AiTextOut> =>
  apiFetch<AiTextOut>(
    `/api/import-sessions/${sessionId}/ai/cleanup-description`,
    { method: 'POST' },
  )

export const aiSummarize = (sessionId: string): Promise<AiTextOut> =>
  apiFetch<AiTextOut>(
    `/api/import-sessions/${sessionId}/ai/summarize`,
    { method: 'POST' },
  )

export interface AiStatusOut {
  provider_available: boolean
}

/** Cheap provider-availability probe — no AI call, no token spend, no usage row. */
export const getAiStatus = (): Promise<AiStatusOut> =>
  apiFetch<AiStatusOut>('/api/ai/status')

// ---------------------------------------------------------------------------
// Phase 13 — AI usage summary (admin-only)
// ---------------------------------------------------------------------------

export interface AiUsageWindow {
  calls: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  /**
   * Estimated cost in USD (derived from local pricing table).
   * null when any contributing model has an unknown rate — show '—' in the UI.
   * Labelled as an estimate; rates may drift from actual billing.
   */
  estimated_cost_usd: number | null
}

export interface AiUsageBreakdownRow {
  provider: string
  model: string | null
  calls: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  estimated_cost_usd: number | null
}

export interface AiUsageSummary {
  last_24h: AiUsageWindow
  last_7d: AiUsageWindow
  last_30d: AiUsageWindow
  /** Provider/model breakdown for the 30-day window, descending by call count. */
  breakdown: AiUsageBreakdownRow[]
}

export const getAiUsageSummary = (): Promise<AiUsageSummary> =>
  apiFetch<AiUsageSummary>('/api/ai-usage/summary')
