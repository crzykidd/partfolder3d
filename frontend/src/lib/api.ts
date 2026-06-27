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

// ---------------------------------------------------------------------------
// Phase 3 — Catalog types
// ---------------------------------------------------------------------------

export interface ItemSummary {
  id: number
  key: string
  title: string
  slug: string
  library_id: number
  dir_path: string
  created_at: string
  updated_at: string
  default_image_path: string | null
  creator_name: string | null
  tag_names: string[]
  favorited: boolean
}

export interface TagOut {
  id: number
  name: string
  category: string | null
}

export interface FileOut {
  id: number
  path: string
  role: string
  size: number
  sha256: string | null
}

export interface ImageOut {
  id: number
  path: string
  source: string
  is_default: boolean
  order: number
}

export interface CreatorOut {
  id: number
  name: string
  profile_url: string | null
  source_site: string | null
}

export interface ItemDetail {
  id: number
  key: string
  title: string
  slug: string
  library_id: number
  dir_path: string
  created_at: string
  updated_at: string
  description: string | null
  source_url: string | null
  source_site: string | null
  license: string | null
  schema_version: number
  creator: CreatorOut | null
  tags: TagOut[]
  files: FileOut[]
  images: ImageOut[]
}

export interface PaginatedItems {
  total: number
  page: number
  per_page: number
  items: ItemSummary[]
}

export interface ItemListParams {
  q?: string
  tags?: string[]
  creator_id?: number
  favorited?: boolean
  sort?: string
  page?: number
  per_page?: number
  library_id?: number
}

export interface TagSummary {
  id: number
  name: string
  category: string | null
  popularity_count: number
}

export interface PaginatedTags {
  total: number
  page: number
  per_page: number
  tags: TagSummary[]
}

export interface CreatorDetail {
  id: number
  name: string
  profile_url: string | null
  source_site: string | null
  item_count: number
}

export interface PaginatedCreators {
  total: number
  page: number
  per_page: number
  creators: CreatorDetail[]
}

export interface CreatorItemSummary {
  id: number
  key: string
  title: string
  slug: string
  library_id: number
  dir_path: string
  created_at: string
  updated_at: string
}

export interface PaginatedCreatorItems {
  total: number
  page: number
  per_page: number
  creator: CreatorDetail
  items: CreatorItemSummary[]
}

export interface ItemSummaryMini {
  id: number
  key: string
  title: string
  slug: string
  library_id: number
  dir_path: string
  created_at: string
  updated_at: string
  default_image_path: string | null
  creator_name: string | null
  tag_names: string[]
}

export interface PaginatedMiniItems {
  total: number
  page: number
  per_page: number
  items: ItemSummaryMini[]
}

export interface FavoriteOut {
  item_id: number
  favorited: boolean
}

export interface BundleOut {
  id: string
  status: string
  expires_at: string | null
  error_message: string | null
}

export interface PathPrefixResponse {
  path_prefix: string | null
}

// ---------------------------------------------------------------------------
// Phase 3 — Catalog API functions
// ---------------------------------------------------------------------------

export const listItems = (params: ItemListParams = {}): Promise<PaginatedItems> => {
  const sp = new URLSearchParams()
  if (params.q) sp.set('q', params.q)
  if (params.tags) params.tags.forEach((t) => sp.append('tags', t))
  if (params.creator_id != null) sp.set('creator_id', String(params.creator_id))
  if (params.favorited === true) sp.set('favorited', 'true')
  if (params.sort) sp.set('sort', params.sort)
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  if (params.library_id != null) sp.set('library_id', String(params.library_id))
  const qs = sp.toString()
  return apiFetch<PaginatedItems>(`/api/items${qs ? `?${qs}` : ''}`)
}

export const getItem = (key: string): Promise<ItemDetail> =>
  apiFetch<ItemDetail>(`/api/items/${key}`)

export const favoriteItem = (key: string): Promise<FavoriteOut> =>
  apiFetch<FavoriteOut>(`/api/items/${key}/favorite`, { method: 'POST' })

export const unfavoriteItem = (key: string): Promise<void> =>
  apiFetch<void>(`/api/items/${key}/favorite`, { method: 'DELETE' })

export const setDefaultImage = (key: string, imageId: number): Promise<ItemDetail> =>
  apiFetch<ItemDetail>(`/api/items/${key}/default-image`, {
    method: 'PATCH',
    body: JSON.stringify({ image_id: imageId }),
  })

export const listTags = (params: {
  q?: string
  category?: string
  page?: number
  per_page?: number
} = {}): Promise<PaginatedTags> => {
  const sp = new URLSearchParams()
  if (params.q) sp.set('q', params.q)
  if (params.category) sp.set('category', params.category)
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  const qs = sp.toString()
  return apiFetch<PaginatedTags>(`/api/tags${qs ? `?${qs}` : ''}`)
}

export const listCreators = (params: {
  q?: string
  page?: number
  per_page?: number
} = {}): Promise<PaginatedCreators> => {
  const sp = new URLSearchParams()
  if (params.q) sp.set('q', params.q)
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  const qs = sp.toString()
  return apiFetch<PaginatedCreators>(`/api/creators${qs ? `?${qs}` : ''}`)
}

export const getCreator = (creatorId: number): Promise<CreatorDetail> =>
  apiFetch<CreatorDetail>(`/api/creators/${creatorId}`)

export const listCreatorItems = (
  creatorId: number,
  params: { page?: number; per_page?: number } = {},
): Promise<PaginatedCreatorItems> => {
  const sp = new URLSearchParams()
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  const qs = sp.toString()
  return apiFetch<PaginatedCreatorItems>(
    `/api/creators/${creatorId}/items${qs ? `?${qs}` : ''}`,
  )
}

export const listFavorites = (params: {
  page?: number
  per_page?: number
} = {}): Promise<PaginatedMiniItems> => {
  const sp = new URLSearchParams()
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  const qs = sp.toString()
  return apiFetch<PaginatedMiniItems>(`/api/me/favorites${qs ? `?${qs}` : ''}`)
}

export const listCreations = (params: {
  page?: number
  per_page?: number
} = {}): Promise<PaginatedMiniItems> => {
  const sp = new URLSearchParams()
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  const qs = sp.toString()
  return apiFetch<PaginatedMiniItems>(`/api/me/creations${qs ? `?${qs}` : ''}`)
}

export const getPathPrefix = (): Promise<PathPrefixResponse> =>
  apiFetch<PathPrefixResponse>('/api/me/path-prefix')

export const setPathPrefix = (pathPrefix: string | null): Promise<PathPrefixResponse> =>
  apiFetch<PathPrefixResponse>('/api/me/path-prefix', {
    method: 'PUT',
    body: JSON.stringify({ path_prefix: pathPrefix }),
  })

export const queueZip = (key: string): Promise<BundleOut> =>
  apiFetch<BundleOut>(`/api/items/${key}/zip`, { method: 'POST' })

export const pollZip = (key: string, bundleId: string): Promise<BundleOut> =>
  apiFetch<BundleOut>(`/api/items/${key}/zip/${bundleId}`)

/** URL for directly streaming a single file (use as href or window.open). */
export const fileDownloadUrl = (key: string, filePath: string): string =>
  `/api/items/${key}/files/${filePath}`

/** URL for streaming the ready ZIP bundle (use as href or window.open). */
export const zipDownloadUrl = (key: string, bundleId: string): string =>
  `/api/items/${key}/zip/${bundleId}?download=true`
