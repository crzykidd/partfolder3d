/**
 * api.ts — Typed fetch wrapper for the PartFolder 3D backend.
 *
 * - Reads the CSRF token from the `pf3d_csrf` cookie (set by the backend).
 * - Attaches `X-CSRF-Token` on all state-changing methods (POST/PUT/PATCH/DELETE).
 * - Bearer-authenticated calls are exempt from CSRF (API keys; the server handles that).
 * - Throws `ApiError` on non-2xx responses.
 * - All server state goes through TanStack Query; callers import these functions as
 *   `queryFn` / `mutationFn` values. No manual `fetch` outside this file.
 */

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

// ---------------------------------------------------------------------------
// CSRF helpers
// ---------------------------------------------------------------------------

const CSRF_COOKIE = 'pf3d_csrf'
const CSRF_HEADER = 'X-CSRF-Token'
const CSRF_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

function getCsrfToken(): string | null {
  const entry = document.cookie
    .split(';')
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${CSRF_COOKIE}=`))
  return entry ? decodeURIComponent(entry.slice(CSRF_COOKIE.length + 1)) : null
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)

  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json')
  }

  if (CSRF_METHODS.has(method)) {
    const csrf = getCsrfToken()
    if (csrf) {
      headers.set(CSRF_HEADER, csrf)
    }
  }

  const res = await fetch(path, { ...options, headers })

  if (!res.ok) {
    let detail: unknown
    try {
      detail = await res.json()
    } catch {
      detail = res.statusText
    }
    const message =
      typeof detail === 'object' && detail !== null && 'detail' in detail
        ? String((detail as Record<string, unknown>)['detail'])
        : res.statusText
    throw new ApiError(res.status, message, detail)
  }

  // 204 No Content — return undefined cast to T
  if (res.status === 204) {
    return undefined as T
  }

  return res.json() as Promise<T>
}

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

// ---------------------------------------------------------------------------
// Users (admin)
// ---------------------------------------------------------------------------

export interface UserSummary {
  id: number
  email: string
  name: string
  role: string
  is_active: boolean
}

export interface UpdateUserRequest {
  name?: string
  role?: string
  is_active?: boolean
}

export const listUsers = (): Promise<UserSummary[]> =>
  apiFetch<UserSummary[]>('/api/users')

export const updateUser = (
  userId: number,
  body: UpdateUserRequest,
): Promise<UserSummary> =>
  apiFetch<UserSummary>(`/api/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })

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

// ---------------------------------------------------------------------------
// Settings (admin)
// ---------------------------------------------------------------------------

export interface SettingOut {
  key: string
  value: unknown
}

export const listSettings = (): Promise<SettingOut[]> =>
  apiFetch<SettingOut[]>('/api/settings')

export const upsertSetting = (key: string, value: unknown): Promise<SettingOut> =>
  apiFetch<SettingOut>(`/api/settings/${encodeURIComponent(key)}`, {
    method: 'PUT',
    body: JSON.stringify({ value }),
  })

// ---------------------------------------------------------------------------
// Per-user theme
// ---------------------------------------------------------------------------

export const updateTheme = (theme_pref: string): Promise<{ theme_pref: string }> =>
  apiFetch<{ theme_pref: string }>('/api/me/theme', {
    method: 'PUT',
    body: JSON.stringify({ theme_pref }),
  })

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
