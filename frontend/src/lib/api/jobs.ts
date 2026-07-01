import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Phase 4 — Jobs
// ---------------------------------------------------------------------------

export interface JobOut {
  id: string
  type: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'superseded' | string
  progress: number
  payload: Record<string, unknown>
  log: string | null
  error: string | null
  item_id: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  retry_of_job_id: string | null
  archived_at: string | null
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
  archived?: boolean
  include_superseded?: boolean
} = {}): Promise<PaginatedJobs> => {
  const sp = new URLSearchParams()
  if (params.status) sp.set('status', params.status)
  if (params.type) sp.set('type', params.type)
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  if (params.archived != null) sp.set('archived', String(params.archived))
  if (params.include_superseded != null) sp.set('include_superseded', String(params.include_superseded))
  const qs = sp.toString()
  return apiFetch<PaginatedJobs>(`/api/jobs${qs ? `?${qs}` : ''}`)
}

export const getJob = (jobId: string): Promise<JobOut> =>
  apiFetch<JobOut>(`/api/jobs/${jobId}`)

export const retryJob = (jobId: string): Promise<{ queued: boolean }> =>
  apiFetch<{ queued: boolean }>(`/api/jobs/${jobId}/retry`, { method: 'POST' })

export const cancelJob = (jobId: string): Promise<JobOut> =>
  apiFetch<JobOut>(`/api/jobs/${jobId}/cancel`, { method: 'POST' })

export const restartJob = (jobId: string): Promise<{ queued: boolean }> =>
  apiFetch<{ queued: boolean }>(`/api/jobs/${jobId}/restart`, { method: 'POST' })

export const clearSucceededJobs = (): Promise<{ archived: number }> =>
  apiFetch<{ archived: number }>('/api/jobs/clear-succeeded', { method: 'POST' })

export const archiveJob = (jobId: string): Promise<JobOut> =>
  apiFetch<JobOut>(`/api/jobs/${jobId}/archive`, { method: 'POST' })

export const deleteJob = (jobId: string): Promise<void> =>
  apiFetch<void>(`/api/jobs/${jobId}`, { method: 'DELETE' })
