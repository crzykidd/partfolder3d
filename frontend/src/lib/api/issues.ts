import { apiFetch } from './core'

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
