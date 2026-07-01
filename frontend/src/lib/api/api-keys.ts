import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// API keys
// ---------------------------------------------------------------------------

export interface ApiKeySummary {
  id: number
  label: string
  is_active: boolean
  last_used_at: string | null
}

export interface CreateApiKeyResponse {
  id: number
  label: string
  key: string
}

export const listApiKeys = (): Promise<ApiKeySummary[]> =>
  apiFetch<ApiKeySummary[]>('/api/api-keys')

export const createApiKey = (label: string): Promise<CreateApiKeyResponse> =>
  apiFetch<CreateApiKeyResponse>('/api/api-keys', {
    method: 'POST',
    body: JSON.stringify({ label }),
  })

export const revokeApiKey = (keyId: number): Promise<void> =>
  apiFetch<void>(`/api/api-keys/${keyId}`, { method: 'DELETE' })
