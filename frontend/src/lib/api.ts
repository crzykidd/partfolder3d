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
// Per-user nav layout (Phase 11)
// ---------------------------------------------------------------------------

export const getNavLayout = (): Promise<{ nav_layout: string }> =>
  apiFetch<{ nav_layout: string }>('/api/me/nav-layout')

export const updateNavLayout = (nav_layout: string | null): Promise<{ nav_layout: string }> =>
  apiFetch<{ nav_layout: string }>('/api/me/nav-layout', {
    method: 'PUT',
    body: JSON.stringify({ nav_layout }),
  })

// ---------------------------------------------------------------------------
// Per-user dashboard layout (Phase 12)
// ---------------------------------------------------------------------------

export interface DashboardStatsLayout {
  density: 'comfortable' | 'compact'
  tiles: string[]
}

export interface DashboardRailLayout {
  collapsed: boolean
  widgets: string[]
}

export interface DashboardLayout {
  stats: DashboardStatsLayout
  rail: DashboardRailLayout
}

export const getDashboardLayout = (): Promise<{ dashboard_layout: DashboardLayout }> =>
  apiFetch<{ dashboard_layout: DashboardLayout }>('/api/me/dashboard')

export const updateDashboardLayout = (
  dashboard_layout: DashboardLayout,
): Promise<{ dashboard_layout: DashboardLayout }> =>
  apiFetch<{ dashboard_layout: DashboardLayout }>('/api/me/dashboard', {
    method: 'PUT',
    body: JSON.stringify({ dashboard_layout }),
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

export const queueZip = (
  key: string,
  opts: { includeHistory?: boolean } = {},
): Promise<BundleOut> => {
  const qs = opts.includeHistory ? '?include_history=true' : ''
  return apiFetch<BundleOut>(`/api/items/${key}/zip${qs}`, { method: 'POST' })
}

export const pollZip = (key: string, bundleId: string): Promise<BundleOut> =>
  apiFetch<BundleOut>(`/api/items/${key}/zip/${bundleId}`)

/** URL for directly streaming a single file (use as href or window.open). */
export const fileDownloadUrl = (key: string, filePath: string): string =>
  `/api/items/${key}/files/${filePath}`

/** URL for streaming the ready ZIP bundle (use as href or window.open). */
export const zipDownloadUrl = (key: string, bundleId: string): string =>
  `/api/items/${key}/zip/${bundleId}?download=true`

// ---------------------------------------------------------------------------
// Phase 5 — Libraries (needed for import session library selector)
// ---------------------------------------------------------------------------

export interface LibraryOut {
  id: number
  name: string
  mount_path: string
  enabled: boolean
}

export const listLibraries = (): Promise<LibraryOut[]> =>
  apiFetch<LibraryOut[]>('/api/libraries')

// ---------------------------------------------------------------------------
// Phase 5 — Import Sessions
// ---------------------------------------------------------------------------

export interface ImportSessionFile {
  id: number
  staged_path: string
  original_name: string
  role: string
  size: number
}

export interface ImportSessionImage {
  id: number
  path: string
  is_url: boolean
  source: string
  order: number
  is_default: boolean
}

export interface TagStateOut {
  confirmed: string[]
  pending: string[]
}

export interface ImportSession {
  id: string
  status: string
  source_type: string
  source_url: string | null
  inbox_folder: string | null
  staging_dir: string | null
  suggested_title: string | null
  confirmed_title: string | null
  description: string | null
  license: string | null
  source_site: string | null
  creator_name: string | null
  creator_profile_url: string | null
  creator_source_site: string | null
  creator_is_own_design: boolean
  creator_id: number | null
  tag_state: TagStateOut | null
  default_image_path: string | null
  library_id: number | null
  job_id: string | null
  item_id: number | null
  created_by_id: number
  created_at: string
  updated_at: string
  error: string | null
  files: ImportSessionFile[]
  images: ImportSessionImage[]
}

export interface PaginatedSessions {
  total: number
  page: number
  per_page: number
  sessions: ImportSession[]
}

export interface SiteCapability {
  domain: string
  can_scrape_metadata: boolean
  can_scrape_images: boolean
  requires_token: boolean
  is_manual_only: boolean
  last_probed_at: string | null
  notes: string | null
  has_token: boolean
}

export interface CommitResponse {
  item_key: string
  item_id: number
  session_id: string
}

export interface TagApproveOut {
  id: number
  name: string
  status: string
  category: string | null
  popularity_count: number
}

export interface CreateImportSessionRequest {
  source_type: string
  source_url?: string | null
  library_id?: number | null
  title?: string | null
  description?: string | null
  license?: string | null
}

export interface PatchImportSessionRequest {
  confirmed_title?: string | null
  description?: string | null
  license?: string | null
  source_url?: string | null
  creator_name?: string | null
  creator_profile_url?: string | null
  creator_source_site?: string | null
  creator_is_own_design?: boolean | null
  confirmed_tags?: string[] | null
  default_image_path?: string | null
  library_id?: number | null
}

export interface PatchSiteCapabilityRequest {
  can_scrape_metadata?: boolean | null
  can_scrape_images?: boolean | null
  requires_token?: boolean | null
  is_manual_only?: boolean | null
  notes?: string | null
  token?: string | null
}

// ---------------------------------------------------------------------------
// Internal helper: multipart/form-data fetch (for file uploads)
// ---------------------------------------------------------------------------

async function apiFetchForm<T>(path: string, body: FormData): Promise<T> {
  // Do NOT set Content-Type — browser sets it (with boundary) for FormData
  const headers = new Headers()
  const csrf = getCsrfToken()
  if (csrf) {
    headers.set(CSRF_HEADER, csrf)
  }

  const res = await fetch(path, { method: 'POST', headers, body })

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

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Phase 5 — Import Session API functions
// ---------------------------------------------------------------------------

export const createImportSession = (
  body: CreateImportSessionRequest,
): Promise<ImportSession> =>
  apiFetch<ImportSession>('/api/import-sessions', {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const listImportSessions = (
  params: {
    page?: number
    per_page?: number
    status?: string
    all_users?: boolean
  } = {},
): Promise<PaginatedSessions> => {
  const sp = new URLSearchParams()
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  if (params.status) sp.set('status', params.status)
  if (params.all_users) sp.set('all_users', 'true')
  const qs = sp.toString()
  return apiFetch<PaginatedSessions>(`/api/import-sessions${qs ? `?${qs}` : ''}`)
}

export const getImportSession = (id: string): Promise<ImportSession> =>
  apiFetch<ImportSession>(`/api/import-sessions/${id}`)

export const patchImportSession = (
  id: string,
  body: PatchImportSessionRequest,
): Promise<ImportSession> =>
  apiFetch<ImportSession>(`/api/import-sessions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })

export const processImportSession = (id: string): Promise<ImportSession> =>
  apiFetch<ImportSession>(`/api/import-sessions/${id}/process`, {
    method: 'POST',
  })

export const uploadSessionFiles = (
  id: string,
  files: File[],
): Promise<ImportSession> => {
  const form = new FormData()
  for (const file of files) {
    form.append('files', file)
  }
  return apiFetchForm<ImportSession>(`/api/import-sessions/${id}/files`, form)
}

export const commitImportSession = (id: string): Promise<CommitResponse> =>
  apiFetch<CommitResponse>(`/api/import-sessions/${id}/commit`, {
    method: 'POST',
  })

export const cancelImportSession = (id: string): Promise<void> =>
  apiFetch<void>(`/api/import-sessions/${id}/cancel`, {
    method: 'POST',
  })

export const listSiteCapabilities = (): Promise<SiteCapability[]> =>
  apiFetch<SiteCapability[]>('/api/site-capabilities')

export const getSiteCapability = (domain: string): Promise<SiteCapability> =>
  apiFetch<SiteCapability>(
    `/api/site-capabilities/${encodeURIComponent(domain)}`,
  )

export const patchSiteCapability = (
  domain: string,
  body: PatchSiteCapabilityRequest,
): Promise<SiteCapability> =>
  apiFetch<SiteCapability>(
    `/api/site-capabilities/${encodeURIComponent(domain)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(body),
    },
  )

// ---------------------------------------------------------------------------
// Phase 7 — Print Records
// ---------------------------------------------------------------------------

export interface PrintRecord {
  id: number
  item_key: string
  note: string | null
  visibility: string  // 'private' | 'public'
  date: string | null
  printer: string | null
  material: string | null
  filament_color: string | null
  nozzle_diameter: number | null
  layer_height: number | null
  supports: boolean | null
  success: boolean | null
  rating: number | null
  filament_length_mm: number | null
  filament_weight_g: number | null
  estimated_print_time_s: number | null
  gcode_file_path: string | null
  print_photo_path: string | null
  logged_by_id: number | null
  created_at: string
  updated_at: string
}

export interface PrintRecordIn {
  note?: string | null
  visibility?: string
  date?: string | null
  printer?: string | null
  material?: string | null
  filament_color?: string | null
  nozzle_diameter?: number | null
  layer_height?: number | null
  supports?: boolean | null
  success?: boolean | null
  rating?: number | null
}

export type PrintRecordPatch = PrintRecordIn

export interface MostPrintedItem {
  item_id: number
  item_key: string | null
  title: string | null
  count: number
}

export interface PrintStats {
  total_prints: number
  success_count: number
  fail_count: number
  success_rate: number | null
  total_filament_length_mm: number
  total_filament_weight_g: number
  total_print_time_s: number
  avg_print_time_s: number | null
  most_printed_items: MostPrintedItem[]
}

export const listPrintRecords = (key: string): Promise<PrintRecord[]> =>
  apiFetch<PrintRecord[]>(`/api/items/${key}/print-records`)

export const createPrintRecord = (
  key: string,
  body: PrintRecordIn,
): Promise<PrintRecord> =>
  apiFetch<PrintRecord>(`/api/items/${key}/print-records`, {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const updatePrintRecord = (
  key: string,
  recordId: number,
  body: PrintRecordPatch,
): Promise<PrintRecord> =>
  apiFetch<PrintRecord>(`/api/items/${key}/print-records/${recordId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })

export const deletePrintRecord = (key: string, recordId: number): Promise<void> =>
  apiFetch<void>(`/api/items/${key}/print-records/${recordId}`, {
    method: 'DELETE',
  })

export const uploadGcode = (
  key: string,
  recordId: number,
  file: File,
): Promise<PrintRecord> => {
  const form = new FormData()
  form.append('file', file)
  return apiFetchForm<PrintRecord>(
    `/api/items/${key}/print-records/${recordId}/gcode`,
    form,
  )
}

export const uploadPrintPhoto = (
  key: string,
  recordId: number,
  file: File,
): Promise<PrintRecord> => {
  const form = new FormData()
  form.append('file', file)
  return apiFetchForm<PrintRecord>(
    `/api/items/${key}/print-records/${recordId}/photo`,
    form,
  )
}

export const getPrintStats = (): Promise<PrintStats> =>
  apiFetch<PrintStats>('/api/print-stats')

// ---------------------------------------------------------------------------
// Phase 7 — Share Links
// ---------------------------------------------------------------------------

export interface ShareLink {
  id: number
  token: string
  scope: string  // 'item_design' | 'full_site'
  item_id: number | null
  item_key: string | null
  created_by_id: number | null
  expires_at: string | null
  revoked: boolean
  revoked_at: string | null
  label: string | null
  created_at: string
  is_active: boolean
}

export interface ShareAuditEvent {
  id: number
  share_link_id: number
  event_type: string
  ip_address: string | null
  user_agent: string | null
  created_at: string
}

export interface MintShareRequest {
  label?: string | null
  expires_days?: number | null
}

export const mintItemShare = (
  key: string,
  body: MintShareRequest,
): Promise<ShareLink> =>
  apiFetch<ShareLink>(`/api/items/${key}/shares`, {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const listItemShares = (key: string): Promise<ShareLink[]> =>
  apiFetch<ShareLink[]>(`/api/items/${key}/shares`)

export const mintSiteShare = (body: MintShareRequest): Promise<ShareLink> =>
  apiFetch<ShareLink>('/api/admin/shares/site', {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const listSiteShares = (): Promise<ShareLink[]> =>
  apiFetch<ShareLink[]>('/api/admin/shares/site')

export const revokeShare = (shareId: number): Promise<ShareLink> =>
  apiFetch<ShareLink>(`/api/shares/${shareId}/revoke`, { method: 'POST' })

export const getShareAudit = (shareId: number): Promise<ShareAuditEvent[]> =>
  apiFetch<ShareAuditEvent[]>(`/api/shares/${shareId}/audit`)

// ---------------------------------------------------------------------------
// Phase 7 — Public share endpoints (no auth)
// ---------------------------------------------------------------------------

export interface PublicPrintRecord {
  id: number
  note: string | null
  date: string | null
  printer: string | null
  material: string | null
  filament_color: string | null
  nozzle_diameter: number | null
  layer_height: number | null
  supports: boolean | null
  success: boolean | null
  rating: number | null
  filament_length_mm: number | null
  filament_weight_g: number | null
  estimated_print_time_s: number | null
}

export interface PublicShareItem {
  key: string
  title: string
  description: string | null
  license: string | null
  source_url: string | null
  source_site: string | null
  tags: string[]
  public_print_records: PublicPrintRecord[]
}

export interface PublicCatalogItem {
  key: string
  title: string
  description: string | null
}

export interface PublicCatalog {
  total: number
  page: number
  per_page: number
  items: PublicCatalogItem[]
}

export const getPublicShare = (token: string): Promise<PublicShareItem> =>
  apiFetch<PublicShareItem>(`/api/public/share/${token}`)

export const getPublicCatalog = (
  token: string,
  params: { page?: number; per_page?: number } = {},
): Promise<PublicCatalog> => {
  const sp = new URLSearchParams()
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  const qs = sp.toString()
  return apiFetch<PublicCatalog>(
    `/api/public/share/${token}/catalog${qs ? `?${qs}` : ''}`,
  )
}

/** Queue a public ZIP for a share token. */
export const queuePublicZip = (token: string): Promise<BundleOut> =>
  apiFetch<BundleOut>(`/api/public/share/${token}/zip`, { method: 'POST' })

/** Poll a public ZIP bundle. */
export const pollPublicZip = (token: string, bundleId: string): Promise<BundleOut> =>
  apiFetch<BundleOut>(`/api/public/share/${token}/zip/${bundleId}`)

/** Direct URL for a public share file download. */
export const publicFileDownloadUrl = (token: string, filePath: string): string =>
  `/api/public/share/${token}/files/${filePath}`

/** Direct URL for downloading a ready public ZIP bundle. */
export const publicZipDownloadUrl = (token: string, bundleId: string): string =>
  `/api/public/share/${token}/zip/${bundleId}?download=true`

// ---------------------------------------------------------------------------
// Phase 7 — Import from share link
// ---------------------------------------------------------------------------

export interface ShareLinkImportRequest {
  share_url: string
  library_id?: number | null
  include_public_notes?: boolean
  include_gcode?: boolean
  include_photos?: boolean
  include_settings?: boolean
}

export const importFromShareLink = (
  body: ShareLinkImportRequest,
): Promise<ImportSession> =>
  apiFetch<ImportSession>('/api/import-sessions/from-share-link', {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const approvePendingTag = (id: number): Promise<TagApproveOut> =>
  apiFetch<TagApproveOut>(`/api/tags/${id}/approve`, {
    method: 'POST',
  })

export const listAllTags = (params: {
  q?: string
  active_only?: boolean
  page?: number
  per_page?: number
} = {}): Promise<PaginatedTags> => {
  const sp = new URLSearchParams()
  if (params.q) sp.set('q', params.q)
  if (params.active_only === false) sp.set('active_only', 'false')
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  const qs = sp.toString()
  return apiFetch<PaginatedTags>(`/api/tags${qs ? `?${qs}` : ''}`)
}

// ---------------------------------------------------------------------------
// Phase 4 — Jobs
// ---------------------------------------------------------------------------

export interface JobOut {
  id: string
  type: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | string
  progress: number
  payload: Record<string, unknown>
  log: string | null
  error: string | null
  item_id: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface PaginatedJobs {
  total: number
  page: number
  per_page: number
  jobs: JobOut[]
}

export const listJobs = (params: {
  status?: string
  type?: string
  page?: number
  per_page?: number
} = {}): Promise<PaginatedJobs> => {
  const sp = new URLSearchParams()
  if (params.status) sp.set('status', params.status)
  if (params.type) sp.set('type', params.type)
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  const qs = sp.toString()
  return apiFetch<PaginatedJobs>(`/api/jobs${qs ? `?${qs}` : ''}`)
}

export const getJob = (jobId: string): Promise<JobOut> =>
  apiFetch<JobOut>(`/api/jobs/${jobId}`)

// ---------------------------------------------------------------------------
// Phase 4 — Scheduled Jobs
// ---------------------------------------------------------------------------

export interface ScheduledJobOut {
  name: string
  description: string
  schedule: string
  last_run_at: string | null
  last_run_status: 'succeeded' | 'failed' | null
  last_run_error: string | null
  next_run_at: string | null
  is_running: boolean
}

export const listScheduledJobs = (): Promise<ScheduledJobOut[]> =>
  apiFetch<ScheduledJobOut[]>('/api/scheduled-jobs')

export const runScheduledJobNow = (name: string): Promise<{ enqueued: boolean; message: string }> =>
  apiFetch<{ enqueued: boolean; message: string }>(`/api/scheduled-jobs/${name}/run`, {
    method: 'POST',
  })

// ---------------------------------------------------------------------------
// Phase 6 — Issues
// ---------------------------------------------------------------------------

export interface IssueOut {
  id: number
  issue_type: string
  severity: string
  status: string
  item_id: number | null
  detail: string
  suggested_action: string | null
  created_at: string
  updated_at: string
  resolved_at: string | null
}

export interface PaginatedIssues {
  total: number
  page: number
  per_page: number
  items: IssueOut[]
}

export const listIssues = (params: {
  status?: string
  issue_type?: string
  item_id?: number
  page?: number
  per_page?: number
} = {}): Promise<PaginatedIssues> => {
  const sp = new URLSearchParams()
  if (params.status) sp.set('status', params.status)
  if (params.issue_type) sp.set('issue_type', params.issue_type)
  if (params.item_id != null) sp.set('item_id', String(params.item_id))
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  const qs = sp.toString()
  return apiFetch<PaginatedIssues>(`/api/issues${qs ? `?${qs}` : ''}`)
}

export const getIssue = (id: number): Promise<IssueOut> =>
  apiFetch<IssueOut>(`/api/issues/${id}`)

export const resolveIssue = (id: number): Promise<IssueOut> =>
  apiFetch<IssueOut>(`/api/issues/${id}/resolve`, { method: 'POST' })

export const ignoreIssue = (id: number): Promise<IssueOut> =>
  apiFetch<IssueOut>(`/api/issues/${id}/ignore`, { method: 'POST' })

// ---------------------------------------------------------------------------
// Phase 6 — Change Log
// ---------------------------------------------------------------------------

export interface ChangeLogOut {
  id: number
  behavior: string
  change_type: string
  item_id: number | null
  summary: string
  before_state: unknown | null
  after_state: unknown | null
  source: string
  actor: string
  created_at: string
}

export interface PaginatedChanges {
  total: number
  page: number
  per_page: number
  items: ChangeLogOut[]
}

export const listChanges = (params: {
  behavior?: string
  item_id?: number
  page?: number
  per_page?: number
} = {}): Promise<PaginatedChanges> => {
  const sp = new URLSearchParams()
  if (params.behavior) sp.set('behavior', params.behavior)
  if (params.item_id != null) sp.set('item_id', String(params.item_id))
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  const qs = sp.toString()
  return apiFetch<PaginatedChanges>(`/api/changes${qs ? `?${qs}` : ''}`)
}

// ---------------------------------------------------------------------------
// Phase 6 — Review Queue
// ---------------------------------------------------------------------------

export interface ReviewItemOut {
  id: number
  behavior: string
  change_type: string
  item_id: number | null
  summary: string
  proposed_action: Record<string, unknown>
  status: string
  created_at: string
  updated_at: string
  resolved_at: string | null
  resolved_by_id: number | null
}

export interface PaginatedReviews {
  total: number
  page: number
  per_page: number
  items: ReviewItemOut[]
}

export const listReviews = (params: {
  status?: string
  page?: number
  per_page?: number
} = {}): Promise<PaginatedReviews> => {
  const sp = new URLSearchParams()
  if (params.status) sp.set('status', params.status)
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  const qs = sp.toString()
  return apiFetch<PaginatedReviews>(`/api/reviews${qs ? `?${qs}` : ''}`)
}

export const approveReview = (id: number): Promise<ReviewItemOut> =>
  apiFetch<ReviewItemOut>(`/api/reviews/${id}/approve`, { method: 'POST' })

export const rejectReview = (id: number): Promise<ReviewItemOut> =>
  apiFetch<ReviewItemOut>(`/api/reviews/${id}/reject`, { method: 'POST' })

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

// ---------------------------------------------------------------------------
// Phase 9 — Backups (admin)
// ---------------------------------------------------------------------------

export interface BackupRecordOut {
  id: number
  filename: string
  size_bytes: number | null
  /** 'pending' | 'running' | 'ready' | 'failed' */
  status: string
  error: string | null
  created_at: string
}

export interface BackupSettingsOut {
  retention_count: number
}

export const listBackups = (): Promise<BackupRecordOut[]> =>
  apiFetch<BackupRecordOut[]>('/api/admin/backups')

export const runBackupNow = (): Promise<{ enqueued: boolean; message: string }> =>
  apiFetch<{ enqueued: boolean; message: string }>('/api/admin/backups/run', {
    method: 'POST',
  })

export const getBackupSettings = (): Promise<BackupSettingsOut> =>
  apiFetch<BackupSettingsOut>('/api/admin/backups/settings')

export const updateBackupSettings = (retentionCount: number): Promise<BackupSettingsOut> =>
  apiFetch<BackupSettingsOut>('/api/admin/backups/settings', {
    method: 'PUT',
    body: JSON.stringify({ retention_count: retentionCount }),
  })

export const deleteBackup = (id: number): Promise<void> =>
  apiFetch<void>(`/api/admin/backups/${id}`, { method: 'DELETE' })

/** Direct URL for downloading a backup archive. Use as href with download attr. */
export const backupDownloadUrl = (id: number): string =>
  `/api/admin/backups/${id}/download`

// ---------------------------------------------------------------------------
// Phase 9 — Export (admin)
// ---------------------------------------------------------------------------

/** Direct URL for downloading the catalog JSON. Use as href. */
export const exportCatalogUrl = (): string => '/api/admin/export/catalog'

// ---------------------------------------------------------------------------
// Phase 9 — Tag admin (admin-only endpoints in /api/admin/tags/*)
// ---------------------------------------------------------------------------

export interface TagAdminOut {
  id: number
  name: string
  category: string | null
  popularity_count: number
  /** 'active' | 'pending' */
  status: string
}

export interface TagAliasOut {
  id: number
  alias: string
  tag_id: number
}

export interface MergeTagResponse {
  merged: boolean
  target_id: number
  source_name: string
  items_repointed: number
  aliases_repointed: number
}

export const listAdminPendingTags = (): Promise<TagAdminOut[]> =>
  apiFetch<TagAdminOut[]>('/api/admin/tags/pending')

export const adminApproveTag = (id: number): Promise<TagAdminOut> =>
  apiFetch<TagAdminOut>(`/api/admin/tags/${id}/approve`, { method: 'POST' })

export const adminRejectTag = (id: number): Promise<void> =>
  apiFetch<void>(`/api/admin/tags/${id}/reject`, { method: 'POST' })

export const adminSetTagCategory = (
  id: number,
  category: string | null,
): Promise<TagAdminOut> =>
  apiFetch<TagAdminOut>(`/api/admin/tags/${id}/category`, {
    method: 'PATCH',
    body: JSON.stringify({ category }),
  })

export const listTagAliases = (id: number): Promise<TagAliasOut[]> =>
  apiFetch<TagAliasOut[]>(`/api/admin/tags/${id}/aliases`)

export const addTagAlias = (id: number, alias: string): Promise<TagAliasOut> =>
  apiFetch<TagAliasOut>(`/api/admin/tags/${id}/aliases`, {
    method: 'POST',
    body: JSON.stringify({ alias }),
  })

export const deleteTagAlias = (aliasId: number): Promise<void> =>
  apiFetch<void>(`/api/admin/tags/aliases/${aliasId}`, { method: 'DELETE' })

export const mergeTag = (
  sourceId: number,
  targetId: number,
): Promise<MergeTagResponse> =>
  apiFetch<MergeTagResponse>(
    `/api/admin/tags/${sourceId}/merge-into/${targetId}`,
    { method: 'POST' },
  )

// ---------------------------------------------------------------------------
// Phase 9 — Admin site capabilities (admin-only; distinct from Phase 5 non-admin)
// ---------------------------------------------------------------------------

/** Full admin view of a site capability (includes created_at, updated_at). */
export interface AdminSiteCapabilityOut {
  domain: string
  can_scrape_metadata: boolean
  can_scrape_images: boolean
  requires_token: boolean
  is_manual_only: boolean
  last_probed_at: string | null
  notes: string | null
  created_at: string
  updated_at: string
  /** True when an encrypted token row exists (plaintext never returned). */
  has_token: boolean
}

export interface AdminSiteCapabilityUpdate {
  can_scrape_metadata?: boolean | null
  can_scrape_images?: boolean | null
  requires_token?: boolean | null
  is_manual_only?: boolean | null
  notes?: string | null
}

export interface ReprobeResponse {
  domain: string
  last_probed_at: string | null
}

export const listAdminSiteCapabilities = (): Promise<AdminSiteCapabilityOut[]> =>
  apiFetch<AdminSiteCapabilityOut[]>('/api/admin/site-capabilities')

export const updateAdminSiteCapability = (
  domain: string,
  body: AdminSiteCapabilityUpdate,
): Promise<AdminSiteCapabilityOut> =>
  apiFetch<AdminSiteCapabilityOut>(
    `/api/admin/site-capabilities/${encodeURIComponent(domain)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(body),
    },
  )

export const deleteAdminSiteCapability = (domain: string): Promise<void> =>
  apiFetch<void>(
    `/api/admin/site-capabilities/${encodeURIComponent(domain)}`,
    { method: 'DELETE' },
  )

export const setAdminSiteToken = (
  domain: string,
  token: string,
): Promise<AdminSiteCapabilityOut> =>
  apiFetch<AdminSiteCapabilityOut>(
    `/api/admin/site-capabilities/${encodeURIComponent(domain)}/token`,
    {
      method: 'POST',
      body: JSON.stringify({ token }),
    },
  )

export const clearAdminSiteToken = (domain: string): Promise<void> =>
  apiFetch<void>(
    `/api/admin/site-capabilities/${encodeURIComponent(domain)}/token`,
    { method: 'DELETE' },
  )

export const reprobeAdminSite = (domain: string): Promise<ReprobeResponse> =>
  apiFetch<ReprobeResponse>(
    `/api/admin/site-capabilities/${encodeURIComponent(domain)}/reprobe`,
    { method: 'POST' },
  )
