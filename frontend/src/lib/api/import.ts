import { apiFetch, apiFetchForm } from './core'

// ---------------------------------------------------------------------------
// Phase 5 — Import Sessions (types)
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
  /** Set by the worker: "Fetched via AgentQL" on agentql success, or a
   *  blocked/budget message. null for standard static scrapes. */
  scrape_note: string | null
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

export const deleteImportSession = (id: string): Promise<void> =>
  apiFetch<void>(`/api/import-sessions/${id}`, { method: 'DELETE' })

export const deleteImportSessionImage = (
  sessionId: string,
  imageId: number,
): Promise<ImportSession> =>
  apiFetch<ImportSession>(`/api/import-sessions/${sessionId}/images/${imageId}`, {
    method: 'DELETE',
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

export const importFromShareLink = (
  body: ShareLinkImportRequest,
): Promise<ImportSession> =>
  apiFetch<ImportSession>('/api/import-sessions/from-share-link', {
    method: 'POST',
    body: JSON.stringify(body),
  })
