import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Password reset
// ---------------------------------------------------------------------------

export interface ResetTokenResponse {
  id: number
  user_id: number
  expires_at: string
  token?: string | null
}

export const createPasswordReset = (email: string): Promise<ResetTokenResponse> =>
  apiFetch<ResetTokenResponse>('/api/password-reset', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })

export const revokePasswordReset = (resetId: number): Promise<void> =>
  apiFetch<void>(`/api/password-reset/${resetId}`, { method: 'DELETE' })

export const useResetToken = (
  token: string,
  newPassword: string,
): Promise<{ ok: boolean }> =>
  apiFetch<{ ok: boolean }>(`/api/password-reset/${token}`, {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword }),
  })
