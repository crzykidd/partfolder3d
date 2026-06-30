import { apiFetch } from './core'

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

export const retryJob = (jobId: string): Promise<{ queued: boolean }> =>
  apiFetch<{ queued: boolean }>(`/api/jobs/${jobId}/retry`, { method: 'POST' })
