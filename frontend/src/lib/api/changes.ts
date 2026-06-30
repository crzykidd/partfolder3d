import { apiFetch } from './core'

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
