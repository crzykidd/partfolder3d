import { apiFetch } from './core'
import type { BundleOut } from './items'

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
  // Phase 15: local-modification tracking (baseline hashes NOT exposed)
  is_modified: boolean
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
