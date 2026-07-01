import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Invites
// ---------------------------------------------------------------------------

export interface InviteResponse {
  id: number
  email: string
  status: string
  expires_at: string
  token?: string | null
  created_at: string
}

export interface AcceptInviteRequest {
  name: string
  password: string
}

export interface AcceptInviteResponse {
  ok: boolean
  user_id: number
}

export const createInvite = (email: string): Promise<InviteResponse> =>
  apiFetch<InviteResponse>('/api/invites', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })

export const listInvites = (): Promise<InviteResponse[]> =>
  apiFetch<InviteResponse[]>('/api/invites')

export const revokeInvite = (inviteId: number): Promise<void> =>
  apiFetch<void>(`/api/invites/${inviteId}`, { method: 'DELETE' })

export const acceptInvite = (
  token: string,
  body: AcceptInviteRequest,
): Promise<AcceptInviteResponse> =>
  apiFetch<AcceptInviteResponse>(`/api/invites/${token}/accept`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
