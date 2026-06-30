import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Phase 9 — Backups (admin)
// ---------------------------------------------------------------------------

export interface BackupRecordOut {
  id: number
  filename: string
  size_bytes: number | null
  /** 'pending' | 'running' | 'ready' | 'failed' */
  status: string
  error: string | null
  created_at: string
}

export interface BackupSettingsOut {
  retention_count: number
}

export const listBackups = (): Promise<BackupRecordOut[]> =>
  apiFetch<BackupRecordOut[]>('/api/admin/backups')

export const runBackupNow = (): Promise<{ enqueued: boolean; message: string }> =>
  apiFetch<{ enqueued: boolean; message: string }>('/api/admin/backups/run', {
    method: 'POST',
  })

export const getBackupSettings = (): Promise<BackupSettingsOut> =>
  apiFetch<BackupSettingsOut>('/api/admin/backups/settings')

export const updateBackupSettings = (retentionCount: number): Promise<BackupSettingsOut> =>
  apiFetch<BackupSettingsOut>('/api/admin/backups/settings', {
    method: 'PUT',
    body: JSON.stringify({ retention_count: retentionCount }),
  })

export const deleteBackup = (id: number): Promise<void> =>
  apiFetch<void>(`/api/admin/backups/${id}`, { method: 'DELETE' })

/** Direct URL for downloading a backup archive. Use as href with download attr. */
export const backupDownloadUrl = (id: number): string =>
  `/api/admin/backups/${id}/download`
