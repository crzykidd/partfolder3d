import { apiFetch } from './core'

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
