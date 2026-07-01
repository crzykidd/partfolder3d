import { apiFetch } from './core'

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
