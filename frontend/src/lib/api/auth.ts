import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface LoginRequest {
  email: string
  password: string
}

export interface LoginResponse {
  ok: boolean
  user_id: number
  email: string
  name: string
  role: string
}

export interface MeResponse {
  user_id: number
  email: string
  name: string
  role: string
  theme_pref: string
  is_active: boolean
}

export const login = (body: LoginRequest): Promise<LoginResponse> =>
  apiFetch<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const logout = (): Promise<{ ok: boolean }> =>
  apiFetch<{ ok: boolean }>('/api/auth/logout', { method: 'POST' })

export const getMe = (): Promise<MeResponse> =>
  apiFetch<MeResponse>('/api/auth/me')
