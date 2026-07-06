import { apiFetch, apiFetchForm } from './core'

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
  /** True when the item has at least one model or gcode file. */
  has_asset: boolean
}

export interface TagOut {
  id: number
  name: string
  category: string | null
}

// ---------------------------------------------------------------------------
// Phase 16 — Object analysis types
// ---------------------------------------------------------------------------

export interface ObjectAnalysis {
  /** Object name (geometry name or filename stem for STL). */
  name: string
  /** Number of distinct colors for this object. */
  color_count: number
  /** Raw hex color strings (e.g. '#FF0000'). Empty for STL (no color data). */
  colors: string[]
  /** Mesh volume in cm³. Null if could not be computed. */
  volume_cm3: number | null
  /**
   * Estimated filament weight in grams.
   * Formula: volume_cm3 × density × (infill_pct / 100).
   * ROUGH ESTIMATE — can be 2–5× off without real slicing.
   */
  est_grams: number | null
  /** Method used for the estimate. 'volume' = volume-based; 'sliced' reserved for future. */
  est_method: 'volume' | 'sliced' | string
  /** True if the mesh is watertight (volume is exact). */
  watertight: boolean
  /**
   * True if the estimate is low-confidence (non-watertight mesh; convex-hull
   * fallback used for volume).
   */
  low_confidence: boolean
  /** Bounding-box extents [x, y, z] in mm. Null on error. */
  dims_mm: [number, number, number] | null
}

// ---------------------------------------------------------------------------
// render-rework-A — 3MF sliced metadata types
// ---------------------------------------------------------------------------

/** One filament slot from 3MF slicer metadata (slice_info.config). */
export interface FilamentEntry {
  /** 1-indexed filament slot number. */
  slot: number
  /** Filament type, e.g. "PLA", "PETG". */
  type: string | null
  /** Hex color string, e.g. "#FF0000". */
  color_hex: string | null
  /** Filament used in grams. */
  used_g: number | null
  /** Filament used in meters. */
  used_m: number | null
}

/** One plate entry from 3MF slicer metadata (slice_info.config). */
export interface PlateEntry {
  /** 1-indexed plate number. */
  index: number
  /** Estimated print time in seconds. */
  print_time_s: number | null
  /** Total filament weight for this plate in grams. */
  weight_g: number | null
}

export interface FileObjectAnalysis {
  /** ISO datetime when this file was last analyzed. */
  analyzed_at: string
  /** sha256 of the file at analysis time (cache key). */
  source_hash: string
  /** Per-object breakdown. */
  objects: ObjectAnalysis[]
  /** Total object count in this file. */
  total_objects: number
  /**
   * Total distinct colors across all objects.
   * For STL this equals the number of objects (1 color each).
   */
  total_colors: number
  /** Sum of est_grams across all objects. */
  total_est_grams: number

  // render-rework-A: sliced-3MF extra fields (absent for STL/OBJ and unsliced 3MF)
  /** 'sliced' when numbers come from slicer; 'volume' for trimesh estimate. */
  est_method?: 'volume' | 'sliced' | string
  /** True when the 3MF file was sliced (Bambu/Orca) and slicer data was read. */
  sliced?: boolean
  /** Slicer name/version string, e.g. "BambuStudio 01.09.00.57". */
  slicer?: string | null
  /** Printer model string from project_settings.config. */
  printer_model?: string | null
  /** Total print time in seconds (sum across all plates). */
  print_time_s?: number | null
  /** Total plate count. */
  plate_count?: number
  /** Per-filament slot details. */
  filament?: FilamentEntry[]
  /** Per-plate breakdown. */
  plates?: PlateEntry[]
  /**
   * Item-relative path of this file's own embedded thumbnail
   * (e.g. "thumbs/embedded/<sha256>.png").
   * Populated by the analysis worker for 3MF files that carry an embedded
   * thumbnail.  Null/absent when no thumbnail was found or the extraction
   * failed.  Generic: STL/OBJ renders may populate this in the future.
   */
  thumbnail_path?: string | null
}

export interface FileOut {
  id: number
  path: string
  role: string
  size: number
  sha256: string | null
  /** Phase 16: per-object analysis; null until worker has run. */
  object_analysis: FileObjectAnalysis | null
  /** render-rework-A: true when the file can be previewed in the browser 3D viewer. */
  preview_3d: boolean
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
  // Phase 15: local-modification tracking
  is_modified: boolean
  locally_modified_at: string | null
  modified_override: string | null  // 'modified' | 'original' | null
  // Phase 16: object-analysis aggregate (null until at least one file is analyzed)
  analysis_total_objects: number | null
  analysis_total_colors: number | null
  analysis_total_est_grams: number | null
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
  /** Filter by one or more library ids (repeatable ?library_ids=1&library_ids=2). */
  library_ids?: number[]
  /**
   * If true, only items with model/gcode files.
   * If false, only items without model/gcode files.
   * Absent = all items.
   */
  has_asset?: boolean
}

export interface TagSummary {
  id: number
  name: string
  category: string | null
  popularity_count: number
  /** Real item count from COUNT(item_tags.item_id) join — accurate even if popularity_count drifted. */
  item_count: number
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
// Per-library × per-OS path prefixes (Phase 17)
// ---------------------------------------------------------------------------

/** Per-OS entry for one library. */
export interface PathPrefixEntry {
  windows: string | null
  posix: string | null
}

/**
 * Per-library prefix map.
 * Keys are library IDs as strings; values hold per-OS local path prefixes.
 */
export type PathPrefixMap = Record<string, PathPrefixEntry>

export interface PathPrefixesResponse {
  path_prefixes: PathPrefixMap
}

// ---------------------------------------------------------------------------
// Tag approve type (used by approvePendingTag / listAllTags below)
// ---------------------------------------------------------------------------

export interface TagApproveOut {
  id: number
  name: string
  status: string
  category: string | null
  popularity_count: number
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
  if (params.library_ids) params.library_ids.forEach((id) => sp.append('library_ids', String(id)))
  if (params.has_asset !== undefined) sp.set('has_asset', String(params.has_asset))
  const qs = sp.toString()
  return apiFetch<PaginatedItems>(`/api/items${qs ? `?${qs}` : ''}`)
}

export const getItem = (key: string): Promise<ItemDetail> =>
  apiFetch<ItemDetail>(`/api/items/${key}`)

/** Re-inventory the item's folder on disk + resync the sidecar (per-item rescan). */
export const rescanItem = (key: string): Promise<ItemDetail> =>
  apiFetch<ItemDetail>(`/api/items/${key}/rescan`, { method: 'POST' })

/**
 * Move an item to another library (issue #25). Relocates the on-disk directory
 * (copy → verify-hash → remove), updates library_id + dir_path, re-inventories.
 */
export const moveItem = (key: string, targetLibraryId: number): Promise<ItemDetail> =>
  apiFetch<ItemDetail>(`/api/items/${key}/move`, {
    method: 'POST',
    body: JSON.stringify({ target_library_id: targetLibraryId }),
  })

export interface BulkMoveResult {
  total: number
  moved: number
  skipped: { key: string; reason: string }[]
  errors: { key: string; reason: string }[]
}

/** Bulk-move items to another library (per-item isolation; partial success). */
export const bulkMoveItems = (
  keys: string[],
  targetLibraryId: number,
): Promise<BulkMoveResult> =>
  apiFetch<BulkMoveResult>('/api/items/move', {
    method: 'POST',
    body: JSON.stringify({ keys, target_library_id: targetLibraryId }),
  })

export const favoriteItem = (key: string): Promise<FavoriteOut> =>
  apiFetch<FavoriteOut>(`/api/items/${key}/favorite`, { method: 'POST' })

export const unfavoriteItem = (key: string): Promise<void> =>
  apiFetch<void>(`/api/items/${key}/favorite`, { method: 'DELETE' })

export const setDefaultImage = (key: string, imageId: number): Promise<ItemDetail> =>
  apiFetch<ItemDetail>(`/api/items/${key}/default-image`, {
    method: 'PATCH',
    body: JSON.stringify({ image_id: imageId }),
  })

export const uploadItemImage = (
  key: string,
  file: File,
  source: 'uploaded' | 'captured' = 'uploaded',
): Promise<ImageOut> => {
  const form = new FormData()
  form.append('file', file)
  const qs = source !== 'uploaded' ? `?source=${source}` : ''
  return apiFetchForm<ImageOut>(`/api/items/${key}/images${qs}`, form)
}

// Delete an item from the catalog. The server moves its directory to
// /data/trash/ (recoverable, never hard-deleted) and removes the DB row.
export const deleteItem = (key: string): Promise<void> =>
  apiFetch<void>(`/api/items/${key}`, { method: 'DELETE' })

export const deleteItemImage = (key: string, imageId: number): Promise<void> =>
  apiFetch<void>(`/api/items/${key}/images/${imageId}`, { method: 'DELETE' })

export const listTags = (params: {
  q?: string
  /** Typeahead prefix search — filters Tag.name ILIKE '<search>%', active only. */
  search?: string
  category?: string
  page?: number
  per_page?: number
  in_use_only?: boolean
} = {}): Promise<PaginatedTags> => {
  const sp = new URLSearchParams()
  if (params.q) sp.set('q', params.q)
  if (params.search) sp.set('search', params.search)
  if (params.category) sp.set('category', params.category)
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  if (params.in_use_only) sp.set('in_use_only', 'true')
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

/** Get the per-library × per-OS path prefix map for the current user. */
export const getPathPrefixes = (): Promise<PathPrefixesResponse> =>
  apiFetch<PathPrefixesResponse>('/api/me/path-prefixes')

/** Persist the per-library × per-OS path prefix map. */
export const setPathPrefixes = (
  path_prefixes: PathPrefixMap,
): Promise<PathPrefixesResponse> =>
  apiFetch<PathPrefixesResponse>('/api/me/path-prefixes', {
    method: 'PUT',
    body: JSON.stringify({ path_prefixes }),
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

export const uploadItemFile = (key: string, file: File): Promise<FileOut> => {
  const form = new FormData()
  form.append('file', file)
  return apiFetchForm<FileOut>(`/api/items/${key}/files`, form)
}

export const deleteItemFile = (key: string, fileId: number): Promise<void> =>
  apiFetch<void>(`/api/items/${key}/files/${fileId}`, { method: 'DELETE' })

export const renameItemFile = (
  key: string,
  fileId: number,
  name: string,
): Promise<FileOut> =>
  apiFetch<FileOut>(`/api/items/${key}/files/${fileId}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  })

/** Slim job record from GET /api/items/{key}/jobs — active or recent failed. */
export interface ItemJobSummary {
  id: string
  type: string
  status: string
  progress: number
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

/** Return active (queued/running) + recent non-archived failed jobs for an item. */
export const listItemJobs = (key: string): Promise<ItemJobSummary[]> =>
  apiFetch<ItemJobSummary[]>(`/api/items/${key}/jobs`)

/** URL for streaming the ready ZIP bundle (use as href or window.open). */
export const zipDownloadUrl = (key: string, bundleId: string): string =>
  `/api/items/${key}/zip/${bundleId}?download=true`

// ---------------------------------------------------------------------------
// Phase 15: local-modification tracking
// ---------------------------------------------------------------------------

/** Set or clear the manual modified-override for an item.
 *  override: 'modified' | 'original' | null  (null = revert to auto)
 */
export const patchModifiedOverride = (
  key: string,
  override: 'modified' | 'original' | null,
): Promise<ItemDetail> =>
  apiFetch<ItemDetail>(`/api/items/${key}/modified-override`, {
    method: 'PATCH',
    body: JSON.stringify({ override }),
  })

// ---------------------------------------------------------------------------
// Tag approve / list-all (orphaned between import and jobs sections)
// ---------------------------------------------------------------------------

export const approvePendingTag = (id: number): Promise<TagApproveOut> =>
  apiFetch<TagApproveOut>(`/api/tags/${id}/approve`, {
    method: 'POST',
  })

// ---------------------------------------------------------------------------
// Item jobs (for ObjectBreakdown analysis status)
// ---------------------------------------------------------------------------

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
