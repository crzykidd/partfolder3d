import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

export interface SetupStatus {
  initialized: boolean
}

export interface SetupRequest {
  admin_email: string
  admin_name: string
  admin_password: string
  instance_name?: string
  external_url?: string
  timezone?: string
}

export interface SetupResponse {
  ok: boolean
  user_id: number
}

export const getSetupStatus = (): Promise<SetupStatus> =>
  apiFetch<SetupStatus>('/api/setup/status')

export const runSetup = (body: SetupRequest): Promise<SetupResponse> =>
  apiFetch<SetupResponse>('/api/setup', {
    method: 'POST',
    body: JSON.stringify(body),
  })
