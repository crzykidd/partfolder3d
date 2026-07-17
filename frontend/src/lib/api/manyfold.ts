import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Manyfold connector — Part 3: admin API client
//
// Mirrors backend/app/routers/manyfold.py. Multiple self-hosted Manyfold
// instances can be registered by an admin; each has an OAuth2
// (client_credentials) client_id/client_secret pair. The secret is
// write-only — POST/PATCH accept it, but no response ever echoes it back.
// `has_secret` tells the UI whether one is stored.
// ---------------------------------------------------------------------------

export interface ManyfoldInstance {
  id: number
  base_url: string
  domain: string
  display_name: string | null
  client_id: string
  /** Whether a client_secret is stored server-side — the secret itself is never returned. */
  has_secret: boolean
  scopes: string
  enabled: boolean
  last_connected_at: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface CreateManyfoldInstanceRequest {
  base_url: string
  display_name?: string | null
  client_id: string
  /** Plaintext; encrypted server-side before storage. Write-only. */
  client_secret: string
  scopes?: string
  enabled?: boolean
  notes?: string | null
}

export interface PatchManyfoldInstanceRequest {
  base_url?: string | null
  display_name?: string | null
  client_id?: string | null
  /** If provided, rotates the stored secret. Write-only — omit to keep the existing one. */
  client_secret?: string | null
  scopes?: string | null
  enabled?: boolean | null
  notes?: string | null
}

export interface ManyfoldTestConnectionResult {
  ok: boolean
  scope?: string | null
  message?: string | null
}

export const listManyfoldInstances = (): Promise<ManyfoldInstance[]> =>
  apiFetch<ManyfoldInstance[]>('/api/admin/manyfold')

export const getManyfoldInstance = (id: number): Promise<ManyfoldInstance> =>
  apiFetch<ManyfoldInstance>(`/api/admin/manyfold/${id}`)

export const createManyfoldInstance = (
  body: CreateManyfoldInstanceRequest,
): Promise<ManyfoldInstance> =>
  apiFetch<ManyfoldInstance>('/api/admin/manyfold', {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const patchManyfoldInstance = (
  id: number,
  body: PatchManyfoldInstanceRequest,
): Promise<ManyfoldInstance> =>
  apiFetch<ManyfoldInstance>(`/api/admin/manyfold/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })

export const deleteManyfoldInstance = (id: number): Promise<void> =>
  apiFetch<void>(`/api/admin/manyfold/${id}`, { method: 'DELETE' })

export const testManyfoldConnection = (
  id: number,
): Promise<ManyfoldTestConnectionResult> =>
  apiFetch<ManyfoldTestConnectionResult>(
    `/api/admin/manyfold/${id}/test-connection`,
    { method: 'POST', body: '{}' },
  )
