import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Phase 9 — Tag admin (admin-only endpoints in /api/admin/tags/*)
// ---------------------------------------------------------------------------

export interface TagAdminOut {
  id: number
  name: string
  category: string | null
  popularity_count: number
  /** Real item count from COUNT(item_tags.item_id) join — always accurate. */
  item_count: number
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

export interface ApproveAllResponse {
  approved: number
}

/** Promote every pending tag to active in one call (admin, idempotent) — #31. */
export const adminApproveAllTags = (): Promise<ApproveAllResponse> =>
  apiFetch<ApproveAllResponse>('/api/admin/tags/approve-all', { method: 'POST' })

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

export interface LoadDefaultTagsResponse {
  added: number
  skipped: number
}

export interface DeleteTagResponse {
  deleted: boolean
  items_untagged: number
}

/** Seed the catalog with the curated starter tag vocabulary (admin, idempotent). */
export const loadDefaultTags = (): Promise<LoadDefaultTagsResponse> =>
  apiFetch<LoadDefaultTagsResponse>('/api/tags/load-defaults', { method: 'POST' })

/**
 * Delete a tag regardless of status.  Removes all ItemTag links (untags items —
 * never deletes items) and all aliases, then deletes the tag.
 */
export const deleteTag = (id: number): Promise<DeleteTagResponse> =>
  apiFetch<DeleteTagResponse>(`/api/admin/tags/${id}`, { method: 'DELETE' })

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
