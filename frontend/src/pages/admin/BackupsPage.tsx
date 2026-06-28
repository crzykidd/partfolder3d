/**
 * BackupsPage — admin backup management (Phase 9 — PRD §13).
 *
 * Route: /admin/backups
 *
 * IMPORTANT: These backups contain only the database and config (encryption
 * key). Library binary files (STL, images, etc.) are NOT backed up. A loud
 * warning callout makes this unavoidably clear.
 *
 * Features:
 *  - Prominent warning banner about what is/isn't backed up.
 *  - Table of backup records: filename, size, status, created_at,
 *    download link (status=ready only), delete with inline confirm.
 *  - "Run Backup Now" button → POST /api/admin/backups/run.
 *  - Retention count setting: inline form → PUT /api/admin/backups/settings.
 *
 * UI: Tailwind + CSS-variable theme + TanStack Query + apiFetch CSRF wrapper.
 * No Mantine, no toast library, no new deps.
 */

import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(bytes: number | null): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatTs(ts: string): string {
  return new Date(ts).toLocaleString()
}

function statusBadge(status: string) {
  const cls: Record<string, string> = {
    ready: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    running: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    pending: 'bg-muted text-muted-foreground',
  }
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls[status] ?? 'bg-muted text-muted-foreground'}`}
    >
      {status}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Retention settings form (inline, no modal)
// ---------------------------------------------------------------------------

function RetentionForm({ current }: { current: number }) {
  const queryClient = useQueryClient()
  const [value, setValue] = useState(String(current))
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const mutation = useMutation({
    mutationFn: (n: number) => api.updateBackupSettings(n),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['backup-settings'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to update.'),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const n = parseInt(value, 10)
    if (isNaN(n) || n < 1) {
      setError('Must be a whole number ≥ 1.')
      return
    }
    mutation.mutate(n)
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <label className="text-sm text-muted-foreground">Keep last</label>
      <input
        type="number"
        min={1}
        value={value}
        onChange={(e) => {
          setValue(e.target.value)
          setError(null)
          setSaved(false)
        }}
        className="input-base w-20 text-sm"
      />
      <label className="text-sm text-muted-foreground">backups</label>
      <button
        type="submit"
        disabled={mutation.isPending}
        className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50 transition-colors"
      >
        {mutation.isPending ? 'Saving…' : 'Save'}
      </button>
      {saved && <span className="text-xs text-green-600 dark:text-green-400">Saved</span>}
      {error && <span className="text-xs text-red-600 dark:text-red-400">{error}</span>}
    </form>
  )
}

// ---------------------------------------------------------------------------
// Backup row
// ---------------------------------------------------------------------------

function BackupRow({ record }: { record: api.BackupRecordOut }) {
  const queryClient = useQueryClient()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteBackup(record.id),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['backups'] }),
    onError: (err) =>
      setDeleteError(err instanceof Error ? err.message : 'Delete failed.'),
  })

  return (
    <tr className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
        {record.filename}
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {formatBytes(record.size_bytes)}
      </td>
      <td className="px-4 py-3">{statusBadge(record.status)}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {formatTs(record.created_at)}
      </td>
      <td className="px-4 py-3">
        {record.status === 'ready' ? (
          <a
            href={api.backupDownloadUrl(record.id)}
            download={record.filename}
            className="text-xs text-primary underline hover:opacity-80"
          >
            Download
          </a>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-4 py-3">
        {record.error && (
          <p className="mb-1 text-xs text-red-600 dark:text-red-400 max-w-xs truncate" title={record.error}>
            {record.error}
          </p>
        )}
        {confirmDelete ? (
          <span className="flex items-center gap-1.5 text-xs">
            <span className="text-muted-foreground">Sure?</span>
            <button
              type="button"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
              className="text-red-600 hover:text-red-700 font-medium disabled:opacity-50"
            >
              {deleteMutation.isPending ? 'Deleting…' : 'Confirm'}
            </button>
            <button
              type="button"
              onClick={() => setConfirmDelete(false)}
              className="text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
          </span>
        ) : (
          <button
            type="button"
            onClick={() => {
              setDeleteError(null)
              setConfirmDelete(true)
            }}
            className="text-xs text-red-500 hover:text-red-700 underline"
          >
            Delete
          </button>
        )}
        {deleteError && (
          <p className="mt-1 text-xs text-red-600 dark:text-red-400">{deleteError}</p>
        )}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function BackupsPage() {
  const queryClient = useQueryClient()
  const [runMessage, setRunMessage] = useState<string | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  const {
    data: backups = [],
    isLoading: backupsLoading,
    isError: backupsError,
    error: backupsErr,
  } = useQuery({
    queryKey: ['backups'],
    queryFn: api.listBackups,
    refetchInterval: 15_000,
  })

  const {
    data: settings,
    isLoading: settingsLoading,
  } = useQuery({
    queryKey: ['backup-settings'],
    queryFn: api.getBackupSettings,
  })

  const runMutation = useMutation({
    mutationFn: api.runBackupNow,
    onSuccess: (data) => {
      setRunMessage(data.message)
      setRunError(null)
      setTimeout(() => setRunMessage(null), 5000)
      void queryClient.invalidateQueries({ queryKey: ['backups'] })
    },
    onError: (err) => {
      setRunError(err instanceof Error ? err.message : 'Failed to enqueue backup.')
      setRunMessage(null)
    },
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Backups</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Database and configuration backups. Use the download link to
            retrieve an archive; use the scheduled job to run backups on a
            schedule.
          </p>
        </div>
        <button
          type="button"
          disabled={runMutation.isPending}
          onClick={() => {
            setRunError(null)
            runMutation.mutate()
          }}
          className="shrink-0 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50 transition-colors"
        >
          {runMutation.isPending ? 'Enqueueing…' : 'Run Backup Now'}
        </button>
      </div>

      {/* Run feedback */}
      {runMessage && (
        <p className="text-sm text-green-700 dark:text-green-400">{runMessage}</p>
      )}
      {runError && (
        <p className="text-sm text-red-600 dark:text-red-400">{runError}</p>
      )}

      {/* LOUD warning callout */}
      <div className="rounded-lg border border-amber-400 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-500 p-4">
        <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">
          Library files are NOT backed up.
        </p>
        <p className="mt-1 text-sm text-amber-700 dark:text-amber-400">
          These backups contain only the <strong>database</strong> and{' '}
          <strong>config (encryption key)</strong>. Your 3D model files,
          images, and other library files are <strong>not included</strong>.
          You are responsible for backing up your library files separately
          (e.g. via filesystem snapshots, cloud sync, or your own backup
          solution).
        </p>
      </div>

      {/* Retention settings */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-semibold">Retention</h2>
        {settingsLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : settings ? (
          <RetentionForm current={settings.retention_count} />
        ) : null}
      </div>

      {/* Backup list */}
      {backupsLoading && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}
      {backupsError && (
        <p className="text-sm text-red-600 dark:text-red-400">
          {backupsErr instanceof Error ? backupsErr.message : 'Failed to load backups.'}
        </p>
      )}

      {!backupsLoading && !backupsError && backups.length === 0 && (
        <div className="rounded-lg border border-dashed border-border py-16 text-center">
          <p className="text-muted-foreground">No backups yet.</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Click "Run Backup Now" or wait for the scheduled backup job to run.
          </p>
        </div>
      )}

      {backups.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-border">
          <div className="flex items-center justify-between px-4 py-2 bg-muted/50 border-b border-border">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {backups.length} backup{backups.length !== 1 ? 's' : ''}
            </span>
            <button
              type="button"
              onClick={() =>
                void queryClient.invalidateQueries({ queryKey: ['backups'] })
              }
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              Refresh
            </button>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-muted/30">
              <tr>
                {['Filename', 'Size', 'Status', 'Created', 'Download', 'Actions'].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {backups.map((b) => (
                <BackupRow key={b.id} record={b} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
